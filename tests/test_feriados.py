import datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.urls import reverse

from apps.matriculas import services as matriculas
from apps.matriculas.models import Frequencia
from apps.turmas import services
from apps.turmas.models import Aula, Feriado, Turma

pytestmark = pytest.mark.django_db

# A turma da fixture: seg/qua de 05/10 a 27/11/2026 (16 aulas).
FINADOS = datetime.date(2026, 11, 2)  # segunda
QUINTA = datetime.date(2026, 10, 8)  # dia sem aula (turma é seg/qua)


def _datas(turma):
    return list(turma.aulas.values_list("data", flat=True))


@pytest.fixture
def cliente_admin(client, usuario_admin):
    client.force_login(usuario_admin)
    return client


# Geração de aulas


def test_gerar_aulas_pula_feriados(turma):
    Feriado.objects.create(data=FINADOS, descricao="Finados")
    services.gerar_aulas(turma)
    assert turma.aulas.count() == 15
    assert FINADOS not in _datas(turma)


def test_data_do_feriado_e_unica():
    Feriado.objects.create(data=FINADOS, descricao="Finados")
    with pytest.raises(IntegrityError):
        Feriado.objects.create(data=FINADOS, descricao="Outro")


# Cadastrar e remover


def test_cadastrar_feriado_tira_a_aula_do_dia(turma):
    services.gerar_aulas(turma)
    feriado, resultado = services.cadastrar_feriado(FINADOS, "  Finados ")
    assert feriado.descricao == "Finados"
    assert [a.data for a in resultado.removidas] == [FINADOS]
    assert FINADOS not in _datas(turma)
    assert turma.aulas.count() == 15


def test_cadastrar_feriado_mantem_aula_com_chamada(turma, aluno):
    services.gerar_aulas(turma)
    matricula = matriculas.matricular(aluno, turma)
    aula = turma.aulas.get(data=FINADOS)
    Frequencia.objects.create(matricula=matricula, aula=aula, presente=True)
    _, resultado = services.cadastrar_feriado(FINADOS, "Finados")
    assert resultado.mantidas == [aula] and resultado.removidas == []
    assert FINADOS in _datas(turma)


@pytest.mark.parametrize("status", [Turma.Status.CONCLUIDA, Turma.Status.CANCELADA])
def test_feriado_nao_mexe_em_turma_encerrada(turma, status):
    services.gerar_aulas(turma)
    Turma.objects.filter(pk=turma.pk).update(status=status)
    _, resultado = services.cadastrar_feriado(FINADOS, "Finados")
    assert resultado.removidas == []
    assert FINADOS in _datas(turma)


def test_feriado_em_dia_sem_aula_nao_muda_nada(turma):
    services.gerar_aulas(turma)
    feriado, resultado = services.cadastrar_feriado(QUINTA, "Recesso")
    assert (resultado.removidas, resultado.mantidas) == ([], [])
    assert services.remover_feriado(feriado).criadas == []
    assert turma.aulas.count() == 16


def test_remover_feriado_devolve_so_a_aula_daquele_dia(turma):
    services.gerar_aulas(turma)
    feriado, _ = services.cadastrar_feriado(FINADOS, "Finados")
    # Uma aula apagada à mão em outro dia não deve voltar.
    turma.aulas.filter(data=datetime.date(2026, 10, 5)).delete()
    resultado = services.remover_feriado(feriado)
    assert [a.data for a in resultado.criadas] == [FINADOS]
    assert not Feriado.objects.exists()
    assert FINADOS in _datas(turma)
    assert datetime.date(2026, 10, 5) not in _datas(turma)


def test_remover_feriado_fora_do_periodo_da_turma(turma):
    services.gerar_aulas(turma)
    feriado, _ = services.cadastrar_feriado(datetime.date(2026, 12, 7), "Recesso")
    assert services.remover_feriado(feriado).criadas == []


# Feriados nacionais


@pytest.mark.parametrize(
    "ano,sexta_santa", [(2024, datetime.date(2024, 3, 29)), (2026, datetime.date(2026, 4, 3))]
)
def test_feriados_nacionais(ano, sexta_santa):
    feriados = dict(services.feriados_nacionais(ano))
    assert len(feriados) == 10
    assert feriados[sexta_santa] == "Sexta-feira Santa"
    assert feriados[datetime.date(ano, 11, 20)] == "Dia Nacional de Zumbi e da Consciência Negra"


def test_cadastrar_feriados_nacionais_nao_duplica(turma):
    services.gerar_aulas(turma)
    Feriado.objects.create(data=datetime.date(2026, 12, 25), descricao="Natal (já existia)")
    cadastrados, resultado = services.cadastrar_feriados_nacionais(2026)
    assert len(cadastrados) == 9
    # Na turma seg/qua de out–nov/2026 caem 12/10 (seg) e 02/11 (seg).
    assert sorted(a.data for a in resultado.removidas) == [
        datetime.date(2026, 10, 12), FINADOS,
    ]
    assert services.cadastrar_feriados_nacionais(2026) == ([], services.ResultadoFeriado())
    assert Feriado.objects.filter(data__year=2026).count() == 10


# Tela


def test_tela_de_feriados_so_para_administrador(client, usuario_instrutor):
    client.force_login(usuario_instrutor)
    assert client.get(reverse("turmas:feriados")).status_code == 403
    assert client.post(reverse("turmas:feriados_nacionais"), {"ano": 2026}).status_code == 403


def test_cadastrar_pela_tela_avisa_as_turmas_afetadas(cliente_admin, turma):
    services.gerar_aulas(turma)
    resposta = cliente_admin.post(
        reverse("turmas:feriados"), {"data": "2026-11-02", "descricao": "Finados"}, follow=True
    )
    conteudo = resposta.content.decode()
    assert resposta.redirect_chain[-1][0].endswith("?ano=2026")
    assert "Feriado de 02/11/2026 cadastrado" in conteudo
    assert "1 aula(s) retirada(s) do calendário: INF-2026-01" in conteudo
    assert "Finados" in conteudo


def test_cadastro_repetido_mostra_erro(cliente_admin):
    Feriado.objects.create(data=FINADOS, descricao="Finados")
    resposta = cliente_admin.post(reverse("turmas:feriados"), {"data": "2026-11-02", "descricao": "X"})
    assert resposta.status_code == 200
    assert "data" in resposta.context["form"].errors


def test_remover_pela_tela(cliente_admin, turma):
    services.gerar_aulas(turma)
    feriado, _ = services.cadastrar_feriado(FINADOS, "Finados")
    url = reverse("turmas:feriado_remover", args=[feriado.pk])
    assert cliente_admin.get(url).status_code == 405
    conteudo = cliente_admin.post(url, follow=True).content.decode()
    assert "devolvida(s) ao calendário: INF-2026-01" in conteudo
    assert FINADOS in _datas(turma)


def test_botao_de_feriados_nacionais(cliente_admin):
    tela = cliente_admin.get(reverse("turmas:feriados"), {"ano": 2026}).content.decode()
    assert "Cadastrar feriados nacionais de 2026" in tela
    conteudo = cliente_admin.post(
        reverse("turmas:feriados_nacionais"), {"ano": "2026"}, follow=True
    ).content.decode()
    assert "10 feriado(s) nacional(is) de 2026 cadastrado(s)" in conteudo
    assert "Tiradentes" in conteudo
    assert "Cadastrar feriados nacionais de 2026" not in conteudo


def test_popular_demo_cadastra_feriados(settings):
    settings.DEBUG = True
    call_command("popular_demo", stdout=StringIO())
    assert Feriado.objects.count() == 30  # nacionais do ano anterior, atual e seguinte
    datas_feriado = set(Feriado.objects.values_list("data", flat=True))
    assert not Aula.objects.filter(data__in=datas_feriado).exists()
