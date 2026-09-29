import datetime

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.alunos.models import Aluno
from apps.catalogo.services import criar_instrutor
from apps.contas.services import GRUPO_ALUNO, atribuir_perfil
from apps.matriculas import services as matriculas
from apps.matriculas.models import Frequencia
from apps.turmas import services as turmas
from apps.turmas.models import Turma

pytestmark = pytest.mark.django_db

HOJE = timezone.localdate()
CPFS = ["11144477735", "39053344705", "82286187041"]


@pytest.fixture
def alunos(db):
    return [
        Aluno.objects.create(nome=f"Aluno {i}", cpf=cpf, data_nascimento=datetime.date(2000, 1, 1))
        for i, cpf in enumerate(CPFS, start=1)
    ]


@pytest.fixture
def turma_diaria(curso, instrutor):
    """Turma com aula todo dia, de 3 dias atrás até daqui a 3 dias (7 aulas)."""
    turma = Turma.objects.create(
        curso=curso,
        instrutor=instrutor,
        codigo="DIA-01",
        data_inicio=HOJE - datetime.timedelta(days=3),
        data_fim=HOJE + datetime.timedelta(days=3),
        dias_semana="seg,ter,qua,qui,sex,sab,dom",
        hora_inicio=datetime.time(8),
        hora_fim=datetime.time(10),
        vagas=10,
        status=Turma.Status.INSCRICOES_ABERTAS,
    )
    turmas.gerar_aulas(turma)
    return turma


@pytest.fixture
def matriculas_ativas(turma_diaria, alunos):
    return [matriculas.matricular(a, turma_diaria) for a in alunos]


def _aula(turma, dias_a_partir_de_hoje):
    return turma.aulas.get(data=HOJE + datetime.timedelta(days=dias_a_partir_de_hoje))


# Geração de aulas


def test_datas_das_aulas_seguem_os_dias_da_semana(turma):
    # 05/10 (seg) a 27/11/2026 (sex), seg/qua: 8 segundas + 8 quartas.
    datas = turmas.datas_das_aulas(turma)
    assert len(datas) == 16
    assert datas[0] == datetime.date(2026, 10, 5)
    assert datas[1] == datetime.date(2026, 10, 7)
    assert datas[-1] == datetime.date(2026, 11, 25)
    assert {d.weekday() for d in datas} == {0, 2}


def test_gerar_aulas_cria_e_nao_duplica(turma):
    resultado = turmas.gerar_aulas(turma)
    assert len(resultado.criadas) == 16
    assert turma.aulas.count() == 16
    de_novo = turmas.gerar_aulas(turma)
    assert not de_novo.mudou
    assert turma.aulas.count() == 16


def test_mudar_calendario_remove_aulas_sem_chamada_e_mantem_as_com_chamada(turma, aluno):
    turmas.gerar_aulas(turma)
    matricula = matriculas.matricular(aluno, turma)
    quarta = turma.aulas.get(data=datetime.date(2026, 10, 7))
    Frequencia.objects.create(matricula=matricula, aula=quarta, presente=True)

    turma.dias_semana = "seg,sex"
    turma.save()
    resultado = turmas.gerar_aulas(turma)

    assert len(resultado.criadas) == 8  # sextas
    assert len(resultado.removidas) == 7  # quartas sem chamada
    assert resultado.mantidas == [quarta]
    assert turma.aulas.filter(data=quarta.data).exists()
    assert turma.aulas.count() == 8 + 8 + 1


def test_calendario_mudou():
    assert turmas.calendario_mudou(["vagas", "dias_semana"])
    assert not turmas.calendario_mudou(["vagas", "sala"])


def test_criar_turma_pela_tela_gera_aulas(client, usuario_admin, curso, instrutor):
    client.force_login(usuario_admin)
    dados = {
        "codigo": "INF-2026-09", "curso": curso.pk, "instrutor": instrutor.pk,
        "status": "planejada", "data_inicio": "2026-10-05", "data_fim": "2026-10-16",
        "dias_semana": ["ter", "qui"], "hora_inicio": "18:00", "hora_fim": "20:00", "vagas": 10,
    }
    resposta = client.post(reverse("turmas:turma_nova"), dados, follow=True)
    assert "4 aulas geradas" in resposta.content.decode()
    turma = Turma.objects.get(codigo="INF-2026-09")
    assert [a.data.day for a in turma.aulas.all()] == [6, 8, 13, 15]


def _dados_edicao(turma, **extra):
    dados = {
        "codigo": turma.codigo, "curso": turma.curso_id, "instrutor": turma.instrutor_id,
        "status": turma.status, "data_inicio": turma.data_inicio.isoformat(),
        "data_fim": turma.data_fim.isoformat(), "dias_semana": turma.dias_semana_lista,
        "hora_inicio": "08:00", "hora_fim": "10:00", "sala": "", "vagas": turma.vagas,
    }
    dados.update(extra)
    return dados


def test_editar_sem_mudar_calendario_nao_recria_aula_apagada(client, usuario_admin, turma):
    turmas.gerar_aulas(turma)
    feriado = turma.aulas.get(data=datetime.date(2026, 11, 2))
    feriado.delete()
    client.force_login(usuario_admin)
    client.post(reverse("turmas:turma_editar", args=[turma.pk]), _dados_edicao(turma, vagas=25))
    assert not turma.aulas.filter(data=datetime.date(2026, 11, 2)).exists()


def test_editar_calendario_regenera_aulas(client, usuario_admin, turma):
    turmas.gerar_aulas(turma)
    client.force_login(usuario_admin)
    resposta = client.post(
        reverse("turmas:turma_editar", args=[turma.pk]),
        _dados_edicao(turma, data_fim="2026-10-09"),
        follow=True,
    )
    assert "removidas" in resposta.content.decode()
    # Seg/qua de 05/10 a 09/10: só 05/10 e 07/10.
    assert [a.data.day for a in turma.aulas.all()] == [5, 7]

def test_admin_gera_aulas_ao_criar_turma(client, curso, instrutor):
    su = User.objects.create_superuser("root", "r@exemplo.com", "x")
    client.force_login(su)
    dados = {
        "curso": curso.pk, "instrutor": instrutor.pk, "codigo": "ADM-1",
        "data_inicio": "05/10/2026", "data_fim": "09/10/2026", "dias_semana": "seg,qua,sex",
        "hora_inicio": "08:00", "hora_fim": "10:00", "sala": "", "vagas": 5,
        "status": "planejada",
        "aulas-TOTAL_FORMS": 0, "aulas-INITIAL_FORMS": 0,
        "aulas-MIN_NUM_FORMS": 0, "aulas-MAX_NUM_FORMS": 1000,
    }
    resposta = client.post("/admin/turmas/turma/add/", dados)
    assert resposta.status_code == 302, resposta.context["adminform"].errors
    assert Turma.objects.get(codigo="ADM-1").aulas.count() == 3


# Chamada (serviços)


def test_registrar_chamada_grava_presencas_faltas_e_observacoes(turma_diaria, matriculas_ativas):
    m1, m2, m3 = matriculas_ativas
    aula = _aula(turma_diaria, 0)
    matriculas.registrar_chamada(
        aula, presentes=[m1.pk, m3.pk], observacoes={m2.pk: " Avisou que estava doente "},
        conteudo="Introdução ao teclado",
    )
    registros = {f.matricula_id: f for f in aula.frequencias.all()}
    assert [registros[m.pk].presente for m in matriculas_ativas] == [True, False, True]
    assert registros[m2.pk].observacao == "Avisou que estava doente"
    aula.refresh_from_db()
    assert aula.conteudo == "Introdução ao teclado"


def test_refazer_chamada_atualiza_sem_duplicar(turma_diaria, matriculas_ativas):
    m1, *_ = matriculas_ativas
    aula = _aula(turma_diaria, -1)
    matriculas.registrar_chamada(aula, presentes=[m1.pk])
    matriculas.registrar_chamada(aula, presentes=[])
    assert aula.frequencias.count() == 3
    assert not aula.frequencias.filter(presente=True).exists()


def test_chamada_de_aula_futura_nao_e_permitida(turma_diaria, matriculas_ativas):
    with pytest.raises(matriculas.MatriculaErro, match="ainda não aconteceu"):
        matriculas.registrar_chamada(_aula(turma_diaria, 1), presentes=[])
    assert not Frequencia.objects.exists()


@pytest.mark.parametrize("status", [Turma.Status.CONCLUIDA, Turma.Status.CANCELADA])
def test_chamada_bloqueada_em_turma_encerrada(turma_diaria, matriculas_ativas, status):
    turma_diaria.status = status
    turma_diaria.save()
    with pytest.raises(matriculas.MatriculaErro):
        matriculas.registrar_chamada(_aula(turma_diaria, 0), presentes=[])


def test_chamada_so_aceita_matriculas_ativas(turma_diaria, matriculas_ativas):
    m1, *_ = matriculas_ativas
    matriculas.cancelar(m1)
    with pytest.raises(matriculas.MatriculaErro, match="não estão ativos"):
        matriculas.registrar_chamada(_aula(turma_diaria, 0), presentes=[m1.pk])
    # E quem saiu não entra mais na lista da chamada.
    assert m1 not in matriculas.matriculas_da_chamada(turma_diaria)


# Regra 4: percentual de frequência


def test_percentual_frequencia(turma_diaria, matriculas_ativas):
    m1, m2, m3 = matriculas_ativas
    # 4 aulas realizadas (de -3 até hoje). m1 vai a 3, m2 a 1, m3 a nenhuma.
    for dias, presentes in [(-3, [m1, m2]), (-2, [m1]), (-1, [m1]), (0, [])]:
        matriculas.registrar_chamada(_aula(turma_diaria, dias), presentes=[m.pk for m in presentes])
    assert matriculas.percentual_frequencia(m1) == 75.0
    assert matriculas.percentual_frequencia(m2) == 25.0
    assert matriculas.percentual_frequencia(m3) == 0.0
    assert matriculas.resumo_frequencia(turma_diaria) == {m1.pk: 75.0, m2.pk: 25.0, m3.pk: 0.0}


def test_aula_sem_chamada_conta_como_falta_e_aula_futura_nao_conta(turma_diaria, matriculas_ativas):
    m1, *_ = matriculas_ativas
    # Presente só em -3; as aulas -2, -1 e hoje ficaram sem chamada.
    matriculas.registrar_chamada(_aula(turma_diaria, -3), presentes=[m1.pk])
    assert matriculas.percentual_frequencia(m1) == 25.0
    # Olhando a partir de 3 dias atrás, só havia 1 aula realizada.
    assert matriculas.percentual_frequencia(m1, hoje=HOJE - datetime.timedelta(days=3)) == 100.0


def test_percentual_arredonda_uma_casa(turma_diaria, matriculas_ativas):
    m1, *_ = matriculas_ativas
    for dias in (-3, -2, -1):
        matriculas.registrar_chamada(_aula(turma_diaria, dias), presentes=[m1.pk] if dias != -1 else [])
    assert matriculas.percentual_frequencia(m1, hoje=HOJE - datetime.timedelta(days=1)) == 66.7


def test_sem_aulas_realizadas_percentual_e_none(turma, aluno):
    turmas.gerar_aulas(turma)  # turma começa em 05/10/2026
    matricula = matriculas.matricular(aluno, turma)
    antes = datetime.date(2026, 10, 1)
    assert matriculas.percentual_frequencia(matricula, hoje=antes) is None
    assert matriculas.resumo_frequencia(turma, hoje=antes) == {}


def test_aula_padrao(turma_diaria, turma):
    assert matriculas.aula_padrao(turma_diaria) == _aula(turma_diaria, 0)
    turmas.gerar_aulas(turma)
    # Antes de começar, abre a primeira aula; depois de terminar, a última.
    assert matriculas.aula_padrao(turma, hoje=datetime.date(2026, 9, 1)).data == datetime.date(2026, 10, 5)
    assert matriculas.aula_padrao(turma, hoje=datetime.date(2027, 1, 1)).data == datetime.date(2026, 11, 25)


# Tela de chamada


def _url(turma, aula):
    return reverse("matriculas:chamada", args=[turma.pk, aula.pk])


def test_chamada_inicio_abre_a_aula_de_hoje(client, usuario_instrutor, turma_diaria):
    client.force_login(usuario_instrutor)
    resposta = client.get(reverse("matriculas:chamada_inicio", args=[turma_diaria.pk]))
    assert resposta.url == _url(turma_diaria, _aula(turma_diaria, 0))


def test_turma_sem_aulas_volta_com_aviso(client, usuario_admin, turma):
    client.force_login(usuario_admin)
    resposta = client.get(reverse("matriculas:chamada_inicio", args=[turma.pk]), follow=True)
    assert "ainda não tem aulas" in resposta.content.decode()


def test_acesso_a_chamada(client, turma_diaria, usuario_admin, usuario_aluno):
    url = _url(turma_diaria, _aula(turma_diaria, 0))
    client.force_login(usuario_admin)
    assert client.get(url).status_code == 200
    client.force_login(usuario_aluno)
    assert client.get(url).status_code == 403
    outro = criar_instrutor(username="pedro", email="p@exemplo.com", senha="x", nome="Pedro")
    client.force_login(outro.usuario)
    assert client.get(url).status_code == 404


def test_aula_de_outra_turma_da_404(client, usuario_admin, turma_diaria, turma):
    turmas.gerar_aulas(turma)
    client.force_login(usuario_admin)
    assert client.get(_url(turma_diaria, turma.aulas.first())).status_code == 404


def test_fazer_chamada_com_htmx(client, usuario_instrutor, turma_diaria, matriculas_ativas):
    m1, m2, m3 = matriculas_ativas
    aula = _aula(turma_diaria, 0)
    client.force_login(usuario_instrutor)

    tela = client.get(_url(turma_diaria, aula)).content.decode()
    assert "Chamada pendente" in tela and "Aluno 1" in tela and "Marcar todos presentes" in tela

    resposta = client.post(
        _url(turma_diaria, aula),
        {"presente": [m1.pk, m2.pk], f"obs_{m3.pk}": "Chegou atrasado", "conteudo": "Mouse"},
        HTTP_HX_REQUEST="true",
    )
    conteudo = resposta.content.decode()
    assert "<html" not in conteudo
    assert "Chamada salva" in conteudo and "Chamada feita" in conteudo
    assert set(aula.frequencias.filter(presente=True).values_list("matricula_id", flat=True)) == {m1.pk, m2.pk}
    assert aula.frequencias.get(matricula=m3).observacao == "Chegou atrasado"
    # Frequência de hoje (1 aula realizada das 4 com chamada só hoje): m1 25%.
    assert "25%" in conteudo


def test_fazer_chamada_sem_htmx_redireciona(client, usuario_admin, turma_diaria, matriculas_ativas):
    aula = _aula(turma_diaria, -1)
    client.force_login(usuario_admin)
    resposta = client.post(_url(turma_diaria, aula), {"presente": [matriculas_ativas[0].pk]}, follow=True)
    assert resposta.redirect_chain[-1][0] == _url(turma_diaria, aula)
    assert "salva" in resposta.content.decode()


def test_chamada_de_aula_futura_mostra_aviso_e_recusa(client, usuario_admin, turma_diaria, matriculas_ativas):
    aula = _aula(turma_diaria, 2)
    client.force_login(usuario_admin)
    tela = client.get(_url(turma_diaria, aula)).content.decode()
    assert "Aula futura" in tela and "Salvar chamada" not in tela
    resposta = client.post(_url(turma_diaria, aula), {"presente": [matriculas_ativas[0].pk]}, HTTP_HX_REQUEST="true")
    assert "ainda não aconteceu" in resposta.content.decode()
    assert not Frequencia.objects.exists()


def test_detalhe_da_turma_mostra_frequencia(client, usuario_admin, turma_diaria, matriculas_ativas):
    m1, *_ = matriculas_ativas
    matriculas.registrar_chamada(_aula(turma_diaria, 0), presentes=[m1.pk])
    client.force_login(usuario_admin)
    conteudo = client.get(reverse("turmas:turma_detalhe", args=[turma_diaria.pk])).content.decode()
    assert "4 de 7 realizadas" in conteudo
    assert "frequência 25%" in conteudo and "frequência 0%" in conteudo
    assert "Fazer chamada" in conteudo


def test_aluno_ve_a_propria_frequencia(client, turma_diaria, matriculas_ativas):
    m1, *_ = matriculas_ativas
    usuario = User.objects.create_user("aluno1", password="x")
    atribuir_perfil(usuario, GRUPO_ALUNO)
    m1.aluno.usuario = usuario
    m1.aluno.save()
    for dias in (-3, -2, -1):
        matriculas.registrar_chamada(_aula(turma_diaria, dias), presentes=[m1.pk])
    client.force_login(usuario)
    assert "Frequência: 75% (mínimo 75%)" in client.get(reverse("matriculas:minhas_matriculas")).content.decode()


def test_painel_do_instrutor_mostra_aulas_de_hoje(client, usuario_instrutor, turma_diaria, turma):
    client.force_login(usuario_instrutor)
    resposta = client.get(reverse("contas:painel"))
    assert [a.turma for a in resposta.context["aulas_hoje"]] == [turma_diaria]
    assert _url(turma_diaria, _aula(turma_diaria, 0)) in resposta.content.decode()
