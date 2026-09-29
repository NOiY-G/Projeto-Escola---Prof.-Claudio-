import datetime

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.alunos.models import Aluno
from apps.contas.services import GRUPO_ALUNO, atribuir_perfil
from apps.matriculas import services
from apps.matriculas.models import Matricula
from apps.turmas.models import Turma

pytestmark = pytest.mark.django_db

CPFS = ["11144477735", "39053344705", "82286187041", "71428793860", "45317828791"]
Status = Matricula.Status


@pytest.fixture
def alunos(db):
    return [
        Aluno.objects.create(nome=f"Aluno {i}", cpf=cpf, data_nascimento=datetime.date(2000, 1, 1))
        for i, cpf in enumerate(CPFS, start=1)
    ]


@pytest.fixture
def turma_pequena(turma):
    turma.vagas = 2
    turma.save()
    return turma


def _nova_turma(turma, codigo, **campos):
    """Cópia da turma base com alguns campos trocados."""
    dados = {
        "curso": turma.curso,
        "instrutor": turma.instrutor,
        "codigo": codigo,
        "data_inicio": turma.data_inicio,
        "data_fim": turma.data_fim,
        "dias_semana": turma.dias_semana,
        "hora_inicio": turma.hora_inicio,
        "hora_fim": turma.hora_fim,
        "vagas": 10,
        "status": Turma.Status.INSCRICOES_ABERTAS,
    }
    dados.update(campos)
    return Turma.objects.create(**dados)


def _status(matricula):
    matricula.refresh_from_db()
    return matricula.status


# Regra 1: só turma com inscrições abertas


@pytest.mark.parametrize(
    "status",
    [Turma.Status.PLANEJADA, Turma.Status.EM_ANDAMENTO, Turma.Status.CONCLUIDA, Turma.Status.CANCELADA],
)
def test_so_matricula_em_turma_com_inscricoes_abertas(turma, aluno, status):
    turma.status = status
    turma.save()
    with pytest.raises(services.MatriculaErro, match="inscrições abertas"):
        services.matricular(aluno, turma)
    assert not Matricula.objects.exists()


def test_matricula_ativa_quando_ha_vaga(turma, aluno):
    assert services.matricular(aluno, turma).status == Status.ATIVA


def test_nao_matricula_duas_vezes_na_mesma_turma(turma, aluno):
    services.matricular(aluno, turma)
    with pytest.raises(services.MatriculaErro, match="já tem matrícula"):
        services.matricular(aluno, turma)


def test_rematricula_depois_de_cancelar_reaproveita_registro(turma, aluno):
    matricula = services.matricular(aluno, turma)
    services.cancelar(matricula)
    nova = services.matricular(aluno, turma)
    assert nova.pk == matricula.pk
    assert nova.status == Status.ATIVA


# Regra 2: lista de espera e promoção automática


def test_turma_cheia_vai_para_lista_de_espera(turma_pequena, alunos):
    a1, a2, a3, a4 = (services.matricular(a, turma_pequena) for a in alunos[:4])
    assert [a1.status, a2.status] == [Status.ATIVA, Status.ATIVA]
    assert [a3.status, a4.status] == [Status.LISTA_ESPERA, Status.LISTA_ESPERA]
    assert list(services.lista_espera(turma_pequena)) == [a3, a4]
    assert services.posicao_na_fila(a3) == 1
    assert services.posicao_na_fila(a4) == 2
    assert services.posicao_na_fila(a1) is None


@pytest.mark.parametrize("operacao", [services.cancelar, services.registrar_desistencia])
def test_vaga_aberta_promove_o_primeiro_da_fila(turma_pequena, alunos, operacao):
    a1, _, a3, a4 = (services.matricular(a, turma_pequena) for a in alunos[:4])
    matricula, promovidas = operacao(a1)
    assert matricula.status in (Status.CANCELADA, Status.DESISTENTE)
    assert promovidas == [a3]
    assert _status(a3) == Status.ATIVA
    assert _status(a4) == Status.LISTA_ESPERA
    assert services.posicao_na_fila(a4) == 1


def test_sair_da_fila_nao_promove_ninguem(turma_pequena, alunos):
    _, _, a3, a4 = (services.matricular(a, turma_pequena) for a in alunos[:4])
    _, promovidas = services.cancelar(a3)
    assert promovidas == []
    assert _status(a4) == Status.LISTA_ESPERA


def test_nao_altera_matricula_ja_encerrada(turma, aluno):
    matricula = services.matricular(aluno, turma)
    services.cancelar(matricula)
    with pytest.raises(services.MatriculaErro):
        services.registrar_desistencia(matricula)


def test_aumentar_vagas_chama_a_fila(turma_pequena, alunos):
    _, _, a3, a4 = (services.matricular(a, turma_pequena) for a in alunos[:4])
    turma_pequena.vagas = 3
    turma_pequena.save()
    assert services.preencher_vagas(turma_pequena) == [a3]
    assert _status(a4) == Status.LISTA_ESPERA


def test_turma_concluida_nao_promove_fila(turma_pequena, alunos):
    a1, _, a3 = (services.matricular(a, turma_pequena) for a in alunos[:3])
    turma_pequena.status = Turma.Status.CONCLUIDA
    turma_pequena.save()
    _, promovidas = services.cancelar(a1)
    assert promovidas == []
    assert _status(a3) == Status.LISTA_ESPERA


def test_promocao_pula_quem_tem_conflito_de_horario(turma_pequena, alunos):
    a1, _, a3, a4 = (services.matricular(a, turma_pequena) for a in alunos[:4])
    # Enquanto espera, o aluno 3 entra numa turma no mesmo horário.
    services.matricular(alunos[2], _nova_turma(turma_pequena, "INF-2026-99"))
    _, promovidas = services.cancelar(a1)
    assert promovidas == [a4]
    assert _status(a3) == Status.LISTA_ESPERA


# Regra 3: conflito de horário


def test_nao_permite_duas_ativas_com_horario_conflitante(turma, aluno):
    services.matricular(aluno, turma)
    outra = _nova_turma(turma, "EXC-2026-01", hora_inicio=datetime.time(9), hora_fim=datetime.time(11))
    with pytest.raises(services.MatriculaErro, match="INF-2026-01"):
        services.matricular(aluno, outra)


def test_conflito_so_conta_matriculas_ativas(turma, aluno):
    matricula = services.matricular(aluno, turma)
    services.cancelar(matricula)
    assert services.matricular(aluno, _nova_turma(turma, "EXC-2026-01")).status == Status.ATIVA


@pytest.mark.parametrize(
    "campos,conflita",
    [
        ({}, True),
        ({"hora_inicio": datetime.time(9, 59), "hora_fim": datetime.time(12)}, True),
        # Uma termina às 10h e a outra começa às 10h: não conflita.
        ({"hora_inicio": datetime.time(10), "hora_fim": datetime.time(12)}, False),
        ({"dias_semana": "ter,qui"}, False),
        ({"dias_semana": "qua,sex"}, True),
        ({"data_inicio": datetime.date(2026, 12, 2), "data_fim": datetime.date(2026, 12, 20)}, False),
        # Os períodos só se encostam na terça 01/12, dia sem aula nas duas (seg/qua).
        ({"data_inicio": datetime.date(2026, 12, 1), "data_fim": datetime.date(2026, 12, 20)}, False),
        # Encostam na segunda 30/11: aí há aula nas duas.
        ({"data_inicio": datetime.date(2026, 11, 30), "data_fim": datetime.date(2026, 12, 20)}, True),
    ],
)
def test_horarios_conflitam(turma, campos, conflita):
    # Base: seg/qua, 08h–10h, de segunda 05/10 a terça 01/12/2026.
    base = _nova_turma(turma, "BASE", data_fim=datetime.date(2026, 12, 1))
    outra = _nova_turma(turma, "OUTRA", **campos)
    assert services.horarios_conflitam(base, outra) is conflita
    assert services.horarios_conflitam(outra, base) is conflita


def test_filas_de_espera(turma_pequena, alunos):
    matriculas = [services.matricular(a, turma_pequena) for a in alunos[:4]]
    assert services.filas_de_espera() == {turma_pequena: matriculas[2:]}


# Telas


@pytest.fixture
def cliente_admin(client, usuario_admin):
    client.force_login(usuario_admin)
    return client


def test_matricular_pela_tela(cliente_admin, turma, aluno):
    url = reverse("matriculas:matricula_nova")
    form = cliente_admin.get(url, {"turma": turma.pk}).context["form"]
    assert form.initial["turma"] == str(turma.pk)
    resposta = cliente_admin.post(url, {"aluno": aluno.pk, "turma": turma.pk}, follow=True)
    assert resposta.redirect_chain[-1][0] == reverse("turmas:turma_detalhe", args=[turma.pk])
    assert "matriculado(a) em INF-2026-01" in resposta.content.decode()
    assert Matricula.objects.get().status == Status.ATIVA


def test_tela_avisa_lista_de_espera(cliente_admin, turma_pequena, alunos):
    for a in alunos[:2]:
        services.matricular(a, turma_pequena)
    resposta = cliente_admin.post(
        reverse("matriculas:matricula_nova"),
        {"aluno": alunos[2].pk, "turma": turma_pequena.pk},
        follow=True,
    )
    assert "lista de espera (posição 1)" in resposta.content.decode()


def test_tela_mostra_erro_de_conflito(cliente_admin, turma, aluno):
    services.matricular(aluno, turma)
    outra = _nova_turma(turma, "EXC-2026-01")
    resposta = cliente_admin.post(
        reverse("matriculas:matricula_nova"), {"aluno": aluno.pk, "turma": outra.pk}
    )
    assert resposta.status_code == 200
    assert "horário conflitante" in resposta.content.decode()


def test_tela_so_lista_turmas_com_inscricoes_abertas(cliente_admin, turma):
    fechada = _nova_turma(turma, "X-1", status=Turma.Status.PLANEJADA)
    form = cliente_admin.get(reverse("matriculas:matricula_nova")).context["form"]
    assert list(form.fields["turma"].queryset) == [turma]
    assert fechada not in form.fields["turma"].queryset


def test_cancelar_pela_tela_promove_e_avisa(cliente_admin, turma_pequena, alunos):
    a1, _, a3 = (services.matricular(a, turma_pequena) for a in alunos[:3])
    url = reverse("matriculas:matricula_cancelar", args=[a1.pk])
    assert cliente_admin.get(url).status_code == 405
    resposta = cliente_admin.post(url, follow=True)
    conteudo = resposta.content.decode()
    assert "Matrícula de Aluno 1 cancelada" in conteudo
    assert "Aluno 3 saiu da lista de espera" in conteudo
    assert _status(a3) == Status.ATIVA


def test_desistencia_pela_tela_respeita_next(cliente_admin, turma, aluno):
    matricula = services.matricular(aluno, turma)
    destino = reverse("alunos:aluno_detalhe", args=[aluno.pk])
    resposta = cliente_admin.post(
        reverse("matriculas:matricula_desistencia", args=[matricula.pk]), {"next": destino}
    )
    assert resposta.url == destino
    assert _status(matricula) == Status.DESISTENTE
    externo = cliente_admin.post(
        reverse("matriculas:matricula_cancelar", args=[matricula.pk]),
        {"next": "https://exemplo.com/"},
    )
    assert externo.url == reverse("turmas:turma_detalhe", args=[turma.pk])


def test_editar_turma_com_mais_vagas_promove_fila(cliente_admin, turma_pequena, alunos):
    *_, a3 = (services.matricular(a, turma_pequena) for a in alunos[:3])
    t = turma_pequena
    dados = {
        "codigo": t.codigo, "curso": t.curso_id, "instrutor": t.instrutor_id, "status": t.status,
        "data_inicio": t.data_inicio.isoformat(), "data_fim": t.data_fim.isoformat(),
        "dias_semana": t.dias_semana_lista, "hora_inicio": "08:00", "hora_fim": "10:00",
        "sala": "", "vagas": 3,
    }
    resposta = cliente_admin.post(reverse("turmas:turma_editar", args=[t.pk]), dados, follow=True)
    assert "Aluno 3 saiu da lista de espera" in resposta.content.decode()
    assert _status(a3) == Status.ATIVA


def test_detalhe_da_turma_separa_fila(cliente_admin, turma_pequena, alunos):
    for a in alunos[:3]:
        services.matricular(a, turma_pequena)
    contexto = cliente_admin.get(reverse("turmas:turma_detalhe", args=[turma_pequena.pk])).context
    assert [m.aluno.nome for m in contexto["matriculas"]] == ["Aluno 1", "Aluno 2"]
    assert [m.aluno.nome for m in contexto["fila"]] == ["Aluno 3"]


def test_pagina_de_lista_de_espera(cliente_admin, turma_pequena, alunos):
    for a in alunos[:3]:
        services.matricular(a, turma_pequena)
    conteudo = cliente_admin.get(reverse("matriculas:lista_espera")).content.decode()
    assert "INF-2026-01" in conteudo and "Aluno 3" in conteudo and "Aluno 1" not in conteudo


def test_matriculas_so_para_administrador(client, usuario_instrutor, turma, aluno):
    matricula = services.matricular(aluno, turma)
    client.force_login(usuario_instrutor)
    assert client.get(reverse("matriculas:matricula_nova")).status_code == 403
    assert client.get(reverse("matriculas:lista_espera")).status_code == 403
    assert client.post(reverse("matriculas:matricula_cancelar", args=[matricula.pk])).status_code == 403
    assert _status(matricula) == Status.ATIVA


def test_aluno_ve_as_proprias_matriculas(client, turma_pequena, alunos):
    usuario = User.objects.create_user("aluno1", password="x")
    atribuir_perfil(usuario, GRUPO_ALUNO)
    alunos[2].usuario = usuario
    alunos[2].save()
    for a in alunos[:3]:
        services.matricular(a, turma_pequena)
    client.force_login(usuario)
    resposta = client.get(reverse("matriculas:minhas_matriculas"))
    assert [m.aluno for m in resposta.context["matriculas"]] == [alunos[2]]
    assert "1º na fila" in resposta.content.decode()


def test_aluno_sem_cadastro_vinculado(client, usuario_aluno):
    client.force_login(usuario_aluno)
    resposta = client.get(reverse("matriculas:minhas_matriculas"))
    assert "não está ligado" in resposta.content.decode()
