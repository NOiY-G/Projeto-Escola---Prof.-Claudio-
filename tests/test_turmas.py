import datetime

import pytest
from django.urls import reverse

from apps.catalogo.models import Curso, Instrutor
from apps.catalogo.services import criar_instrutor
from apps.matriculas.models import Matricula
from apps.turmas import services
from apps.turmas.models import Turma

pytestmark = pytest.mark.django_db


@pytest.fixture
def outra_turma(curso):
    outro = criar_instrutor(username="pedro", email="p@exemplo.com", senha="x", nome="Pedro")
    return Turma.objects.create(
        curso=Curso.objects.create(nome="Excel", carga_horaria=20),
        instrutor=outro,
        codigo="EXC-2026-01",
        data_inicio=datetime.date(2026, 10, 6),
        data_fim=datetime.date(2026, 11, 26),
        dias_semana="ter,qui",
        hora_inicio=datetime.time(14, 0),
        hora_fim=datetime.time(16, 0),
        vagas=15,
    )


def _dados_turma(curso, instrutor, **extra):
    dados = {
        "codigo": "INF-2026-02",
        "curso": curso.pk,
        "instrutor": instrutor.pk,
        "status": "planejada",
        "data_inicio": "2026-10-05",
        "data_fim": "2026-11-30",
        "dias_semana": ["qua", "seg"],
        "hora_inicio": "18:00",
        "hora_fim": "20:00",
        "sala": "Lab 1",
        "vagas": 20,
    }
    dados.update(extra)
    return dados


# Serviços


def test_turmas_visiveis_para_cada_perfil(
    turma, outra_turma, usuario_admin, usuario_instrutor, usuario_aluno
):
    assert set(services.turmas_visiveis_para(usuario_admin)) == {turma, outra_turma}
    assert list(services.turmas_visiveis_para(usuario_instrutor)) == [turma]
    assert list(services.turmas_visiveis_para(usuario_aluno)) == []


def test_filtrar_turmas(turma, outra_turma):
    todas = Turma.objects.all()
    assert list(services.filtrar_turmas(todas, status="inscricoes_abertas")) == [turma]
    assert list(services.filtrar_turmas(todas, curso_id=outra_turma.curso_id)) == [outra_turma]
    assert list(services.filtrar_turmas(todas, busca="exc")) == [outra_turma]


def test_vagas_livres_conta_so_matriculas_ativas(turma, aluno):
    turma.vagas = 2
    Matricula.objects.create(aluno=aluno, turma=turma, status=Matricula.Status.ATIVA)
    assert services.vagas_ocupadas(turma) == 1
    assert services.vagas_livres(turma) == 1


def test_horario_display(turma):
    assert turma.horario_display == "Seg/Qua, 08:00–10:00"


# Telas


def test_lista_de_turmas_com_filtros(client, usuario_admin, turma, outra_turma):
    client.force_login(usuario_admin)
    url = reverse("turmas:turma_lista")
    assert len(client.get(url).context["object_list"]) == 2
    resposta = client.get(url, {"status": "inscricoes_abertas"})
    assert list(resposta.context["object_list"]) == [turma]
    resposta = client.get(url, {"curso": outra_turma.curso_id})
    assert list(resposta.context["object_list"]) == [outra_turma]


def test_instrutor_ve_so_as_proprias_turmas(client, usuario_instrutor, turma, outra_turma):
    client.force_login(usuario_instrutor)
    assert list(client.get(reverse("turmas:turma_lista")).context["object_list"]) == [turma]
    assert client.get(reverse("turmas:turma_detalhe", args=[turma.pk])).status_code == 200
    assert client.get(reverse("turmas:turma_detalhe", args=[outra_turma.pk])).status_code == 404
    assert client.get(reverse("turmas:turma_nova")).status_code == 403
    assert client.get(reverse("turmas:turma_editar", args=[turma.pk])).status_code == 403


def test_aluno_nao_acessa_turmas(client, usuario_aluno, turma):
    client.force_login(usuario_aluno)
    assert client.get(reverse("turmas:turma_lista")).status_code == 403


def test_detalhe_mostra_alunos(client, usuario_admin, turma, aluno):
    Matricula.objects.create(aluno=aluno, turma=turma)
    client.force_login(usuario_admin)
    resposta = client.get(reverse("turmas:turma_detalhe", args=[turma.pk]))
    conteudo = resposta.content.decode()
    assert aluno.nome in conteudo
    assert "05/10/2026 a 27/11/2026" in conteudo
    assert resposta.context["vagas_livres"] == 19


def test_criar_turma(client, usuario_admin, curso, instrutor):
    client.force_login(usuario_admin)
    resposta = client.post(reverse("turmas:turma_nova"), _dados_turma(curso, instrutor))
    turma = Turma.objects.get(codigo="INF-2026-02")
    assert resposta.url == reverse("turmas:turma_detalhe", args=[turma.pk])
    assert turma.dias_semana == "seg,qua"
    assert turma.hora_inicio == datetime.time(18, 0)


def test_criar_turma_invalida(client, usuario_admin, curso, instrutor, turma):
    client.force_login(usuario_admin)
    dados = _dados_turma(
        curso, instrutor, codigo=turma.codigo, data_fim="2026-10-01", hora_fim="17:00", vagas=0,
        dias_semana=[],
    )
    resposta = client.post(reverse("turmas:turma_nova"), dados)
    assert resposta.status_code == 200
    erros = resposta.context["form"].errors
    assert {"codigo", "data_fim", "hora_fim", "vagas", "dias_semana"} <= set(erros)


def test_curso_inativo_nao_aparece_para_turma_nova(client, usuario_admin, curso, instrutor):
    inativo = Curso.objects.create(nome="Antigo", carga_horaria=10, ativo=False)
    client.force_login(usuario_admin)
    form = client.get(reverse("turmas:turma_nova")).context["form"]
    assert inativo not in form.fields["curso"].queryset
    resposta = client.post(reverse("turmas:turma_nova"), _dados_turma(inativo, instrutor))
    assert "curso" in resposta.context["form"].errors


def test_editar_turma_mantem_curso_atual_mesmo_inativo(client, usuario_admin, turma, instrutor):
    turma.curso.ativo = False
    turma.curso.save()
    client.force_login(usuario_admin)
    form = client.get(reverse("turmas:turma_editar", args=[turma.pk])).context["form"]
    assert turma.curso in form.fields["curso"].queryset
    assert form.initial["dias_semana"] == ["seg", "qua"]
    dados = _dados_turma(turma.curso, instrutor, codigo=turma.codigo, vagas=30, dias_semana=["sex"])
    assert client.post(reverse("turmas:turma_editar", args=[turma.pk]), dados).status_code == 302
    turma.refresh_from_db()
    assert (turma.vagas, turma.dias_semana) == (30, "sex")
