from decimal import Decimal

import pytest
from django.urls import reverse

from apps.financeiro.models import Parcela
from apps.matriculas.models import Matricula

pytestmark = pytest.mark.django_db


def _menu(client, usuario, url=None):
    client.force_login(usuario)
    return client.get(url or reverse("contas:painel")).context["menu"]


def _rotulos(menu):
    return [e.rotulo for e in menu]


def test_menu_do_administrador_agrupado(client, usuario_admin):
    menu = _menu(client, usuario_admin)
    assert _rotulos(menu) == ["Painel", "Cadastros", "Turmas", "Financeiro", "Certificados", "Relatórios"]
    grupos = {e.rotulo: [i.rotulo for i in e.itens] for e in menu if hasattr(e, "itens")}
    assert grupos == {
        "Cadastros": ["Cursos", "Instrutores", "Alunos"],
        "Turmas": ["Turmas", "Lista de espera", "Feriados"],
        "Financeiro": ["Pagamentos", "Comprovantes para conferir", "Relatório financeiro"],
    }


@pytest.mark.parametrize(
    "fixture,esperado",
    [("usuario_instrutor", ["Painel", "Minhas turmas"]), ("usuario_aluno", ["Painel", "Minhas matrículas"])],
)
def test_menu_dos_outros_perfis(client, request, fixture, esperado):
    assert _rotulos(_menu(client, request.getfixturevalue(fixture))) == esperado


def test_destaca_o_grupo_da_pagina_atual(client, usuario_admin, curso):
    menu = _menu(client, usuario_admin, reverse("catalogo:curso_editar", args=[curso.pk]))
    ativos = [e.rotulo for e in menu if e.ativo]
    assert ativos == ["Cadastros"]
    cadastros = next(e for e in menu if e.rotulo == "Cadastros")
    assert [i.rotulo for i in cadastros.itens if i.ativo] == ["Cursos"]


def test_contador_de_comprovantes(client, usuario_admin, turma, aluno):
    matricula = Matricula.objects.create(aluno=aluno, turma=turma)
    for numero in (1, 2):
        Parcela.objects.create(
            matricula=matricula, numero=numero, valor=Decimal("50"), vencimento=turma.data_inicio,
            status=Parcela.Status.EM_ANALISE,
        )
    menu = _menu(client, usuario_admin)
    financeiro = next(e for e in menu if e.rotulo == "Financeiro")
    assert financeiro.contador == 2
    assert [i.contador for i in financeiro.itens] == [0, 2, 0]


def test_html_do_menu(client, usuario_admin, usuario_aluno):
    client.force_login(usuario_admin)
    conteudo = client.get(reverse("contas:painel")).content.decode()
    assert "Cadastros" in conteudo and "Django Admin" in conteudo and 'aria-current="page"' in conteudo
    client.force_login(usuario_aluno)
    conteudo = client.get(reverse("contas:painel")).content.decode()
    assert "Cadastros" not in conteudo and "Django Admin" not in conteudo
    assert reverse("matriculas:minhas_matriculas") in conteudo


def test_sem_menu_para_visitante(client):
    resposta = client.get(reverse("contas:login"))
    assert "menu" not in resposta.context or resposta.context.get("menu") is None
