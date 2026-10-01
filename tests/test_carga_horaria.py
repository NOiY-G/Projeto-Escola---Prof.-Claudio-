"""Duração do curso em meses, dias mínimos por semana e carga prevista das turmas."""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.catalogo.models import Curso
from apps.turmas import services as turmas
from apps.turmas.models import Turma

pytestmark = pytest.mark.django_db


@pytest.fixture
def curso(db):
    # 2 meses × 4 semanas × 3 dias × 2 h = 48 h
    return Curso.objects.create(nome="Informática Básica", duracao_meses=2, dias_por_semana=3)


@pytest.fixture
def cliente_admin(client, usuario_admin):
    client.force_login(usuario_admin)
    return client


def _turma(curso, instrutor, dias="seg,qua,sex", hora_fim=datetime.time(10), **extra):
    dados = dict(
        curso=curso, instrutor=instrutor, codigo="INF-01",
        data_inicio=datetime.date(2026, 10, 5), data_fim=datetime.date(2026, 12, 4),
        dias_semana=dias, hora_inicio=datetime.time(8), hora_fim=hora_fim, vagas=10,
        status=Turma.Status.INSCRICOES_ABERTAS,
    )
    dados.update(extra)
    return Turma.objects.create(**dados)


def test_data_fim_sugerida_pela_duracao_do_curso(curso):
    curso.duracao_meses = 2
    assert turmas.data_fim_sugerida(curso, datetime.date(2026, 10, 5)) == datetime.date(2026, 12, 4)
    curso.duracao_meses = 1
    assert turmas.data_fim_sugerida(curso, datetime.date(2026, 1, 31)) == datetime.date(2026, 2, 27)


def test_carga_da_turma_conta_aulas_sem_feriados(curso, instrutor):
    # 05/10 a 04/12/2026, seg/qua/sex, 2 h: 27 dias de aula, menos 12/10 (seg), 2/11 (seg)
    # e 20/11 (sex) = 24 aulas = 48 h.
    for data in (datetime.date(2026, 10, 12), datetime.date(2026, 11, 2), datetime.date(2026, 11, 20)):
        turmas.cadastrar_feriado(data, "Feriado")
    carga = turmas.carga_da_turma(_turma(curso, instrutor))
    assert (carga.aulas, carga.horas_por_aula, carga.carga_prevista) == (24, Decimal(2), Decimal(48))
    assert carga.carga_do_curso == 48 and carga.suficiente and carga.ok


def test_aviso_quando_o_calendario_nao_cumpre_a_carga(curso, instrutor):
    turma = _turma(curso, instrutor, dias="sab")  # 8 sábados × 2 h = 16 h de 48 h
    carga = turmas.carga_da_turma(turma)
    assert not carga.suficiente and carga.faltam == Decimal(32) and carga.poucos_dias
    aviso = turmas.aviso_de_carga(turma)
    assert "tem 1 dia(s) de aula por semana e o curso pede no mínimo 3" in aviso
    assert "prevê 16 h" in aviso and "menos que as 48 h do curso" in aviso
    assert turmas.aviso_de_carga(_turma(curso, instrutor, codigo="INF-02")) is None


def test_aula_mais_longa_cumpre_a_carga_mas_avisa_dos_dias(curso, instrutor):
    # Duas aulas de 3 h por semana: 17 aulas × 3 h = 51 h ≥ 48 h, mas o curso pede 3 dias.
    turma = _turma(curso, instrutor, dias="ter,qui", hora_fim=datetime.time(11))
    carga = turmas.carga_da_turma(turma)
    assert carga.suficiente and carga.poucos_dias and not carga.ok


def test_aula_mais_curta_que_o_minimo_avisa(curso, instrutor):
    turma = _turma(curso, instrutor, hora_fim=datetime.time(9))  # aulas de 1 h; o curso pede 2 h
    carga = turmas.carga_da_turma(turma)
    assert carga.aula_curta and not carga.suficiente
    assert "tem aulas de 1 h e o curso pede no mínimo 2 h" in turmas.aviso_de_carga(turma)


def test_criar_turma_sem_data_fim_usa_duracao_do_curso(client, usuario_admin, curso, instrutor):
    client.force_login(usuario_admin)
    dados = {
        "codigo": "INF-2026-09", "curso": curso.pk, "instrutor": instrutor.pk, "status": "planejada",
        "data_inicio": "2026-10-05", "data_fim": "", "dias_semana": ["seg", "qua", "sex"],
        "hora_inicio": "08:00", "hora_fim": "10:00", "vagas": 10,
    }
    resposta = client.post(reverse("turmas:turma_nova"), dados, follow=True)
    turma = Turma.objects.get(codigo="INF-2026-09")
    assert turma.data_fim == datetime.date(2026, 12, 4)  # curso de 2 meses
    assert "A turma INF-2026-09" not in resposta.content.decode()  # nenhum aviso


def test_criar_turma_com_poucos_dias_avisa(client, usuario_admin, curso, instrutor):
    client.force_login(usuario_admin)
    dados = {
        "codigo": "INF-2026-10", "curso": curso.pk, "instrutor": instrutor.pk, "status": "planejada",
        "data_inicio": "2026-10-05", "data_fim": "", "dias_semana": ["sab"],
        "hora_inicio": "08:00", "hora_fim": "10:00", "vagas": 10,
    }
    conteudo = client.post(reverse("turmas:turma_nova"), dados, follow=True).content.decode()
    assert Turma.objects.filter(codigo="INF-2026-10").exists()  # só avisa, não bloqueia
    assert "menos que as 48 h do curso" in conteudo
    turma = Turma.objects.get(codigo="INF-2026-10")
    detalhe = client.get(reverse("turmas:turma_detalhe", args=[turma.pk])).content.decode()
    assert "16 h previstas de 48 h" in detalhe and "no mínimo 3 dias por semana" in detalhe


def test_matricula_informa_dias_minimos_e_mensalidades(cliente_admin, curso, instrutor):
    curso.valor_mensalidade = Decimal("80")
    curso.save()
    turma = _turma(curso, instrutor, dias="sab")
    url = reverse("matriculas:matricula_resumo_turma")
    conteudo = cliente_admin.get(url, {"turma": turma.pk}).content.decode()
    assert "48 h — mínimo de 3 dias por semana, aulas de no mínimo 2 h" in conteudo
    assert "1 dia por semana" in conteudo and "não chega às 48 h" in conteudo
    assert "2 mensalidades de R$ 80,00" in conteudo
    assert cliente_admin.get(url, {"turma": "abc"}).content.decode().strip() == ""
    pagina = cliente_admin.get(reverse("matriculas:matricula_nova")).content.decode()
    assert url in pagina


def test_resumo_da_turma_so_para_administrador(client, usuario_instrutor, turma):
    client.force_login(usuario_instrutor)
    resposta = client.get(reverse("matriculas:matricula_resumo_turma"), {"turma": turma.pk})
    assert resposta.status_code == 403


def test_matricula_em_curso_gratuito(cliente_admin, turma):
    turma.status = Turma.Status.INSCRICOES_ABERTAS
    turma.save()
    conteudo = cliente_admin.get(reverse("matriculas:matricula_resumo_turma"), {"turma": turma.pk}).content.decode()
    assert "Curso gratuito" in conteudo
