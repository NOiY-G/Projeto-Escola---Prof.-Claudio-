import datetime

import pytest
from django.urls import reverse

from apps.alunos import services
from apps.alunos.models import Aluno
from apps.matriculas.models import Matricula

pytestmark = pytest.mark.django_db


@pytest.fixture
def cliente_admin(client, usuario_admin):
    client.force_login(usuario_admin)
    return client


@pytest.fixture
def outro_aluno(db):
    return Aluno.objects.create(
        nome="Ana Beatriz", cpf="11144477735", data_nascimento=datetime.date(1995, 5, 5)
    )


def _dados_aluno(**extra):
    dados = {
        "nome": "Carla Mendes",
        "cpf": "390.533.447-05",
        "data_nascimento": "2001-03-10",
        "telefone": "(91) 98888-7777",
        "email": "carla@exemplo.com",
        "escolaridade": "medio_comp",
        "endereco": "Rua A, 10",
    }
    dados.update(extra)
    return dados


# Serviços


@pytest.mark.parametrize(
    "termo,esperado",
    [
        ("joão", {"João da Silva"}),
        ("BEATRIZ", {"Ana Beatriz"}),
        ("529.982", {"João da Silva"}),
        ("11144477735", {"Ana Beatriz"}),
        ("", {"João da Silva", "Ana Beatriz"}),
        ("zzz", set()),
    ],
)
def test_buscar_alunos_por_nome_ou_cpf(aluno, outro_aluno, termo, esperado):
    assert {a.nome for a in services.buscar_alunos(termo)} == esperado


def test_historico_do_aluno(aluno, turma):
    matricula = Matricula.objects.create(aluno=aluno, turma=turma)
    assert list(services.historico_do_aluno(aluno)) == [matricula]


# Telas


def test_alunos_so_para_administrador(client, usuario_instrutor):
    client.force_login(usuario_instrutor)
    assert client.get(reverse("alunos:aluno_lista")).status_code == 403


def test_busca_de_alunos_com_htmx_devolve_so_resultados(cliente_admin, aluno, outro_aluno):
    resposta = cliente_admin.get(reverse("alunos:aluno_lista"), {"q": "529"}, HTTP_HX_REQUEST="true")
    conteudo = resposta.content.decode()
    assert "<html" not in conteudo
    assert "João da Silva" in conteudo and "Ana Beatriz" not in conteudo
    assert "529.982.247-25" in conteudo

    completa = cliente_admin.get(reverse("alunos:aluno_lista"), {"q": "529"})
    assert "<html" in completa.content.decode()


def test_criar_aluno_com_cpf_formatado(cliente_admin):
    resposta = cliente_admin.post(reverse("alunos:aluno_novo"), _dados_aluno())
    aluno = Aluno.objects.get(nome="Carla Mendes")
    assert resposta.url == reverse("alunos:aluno_detalhe", args=[aluno.pk])
    assert aluno.cpf == "39053344705"
    assert aluno.data_nascimento == datetime.date(2001, 3, 10)


def test_criar_aluno_cpf_invalido_ou_repetido(cliente_admin, aluno):
    resposta = cliente_admin.post(reverse("alunos:aluno_novo"), _dados_aluno(cpf="123.456.789-00"))
    assert "cpf" in resposta.context["form"].errors
    resposta = cliente_admin.post(reverse("alunos:aluno_novo"), _dados_aluno(cpf="529.982.247-25"))
    assert "cpf" in resposta.context["form"].errors
    assert Aluno.objects.count() == 1


def test_editar_aluno(cliente_admin, aluno):
    url = reverse("alunos:aluno_editar", args=[aluno.pk])
    assert cliente_admin.get(url).context["form"].initial["cpf"] == "529.982.247-25"
    resposta = cliente_admin.post(url, _dados_aluno(nome="João S.", cpf="529.982.247-25"))
    assert resposta.status_code == 302
    aluno.refresh_from_db()
    assert aluno.nome == "João S."


def test_detalhe_mostra_historico(cliente_admin, aluno, turma):
    Matricula.objects.create(aluno=aluno, turma=turma, status=Matricula.Status.CONCLUIDA)
    conteudo = cliente_admin.get(reverse("alunos:aluno_detalhe", args=[aluno.pk])).content.decode()
    assert "Informática Básica" in conteudo
    assert "Concluída" in conteudo
    assert "15/01/2000" in conteudo
