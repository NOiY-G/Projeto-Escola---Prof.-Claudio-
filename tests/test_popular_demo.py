import random
from io import StringIO

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from apps.alunos.models import Aluno
from apps.alunos.validators import cpf_valido
from apps.catalogo.management.commands.popular_demo import gerar_cpf
from apps.catalogo.models import Curso
from apps.certificados.models import Certificado
from apps.contas.services import (
    PERFIL_ADMINISTRADOR,
    PERFIL_ALUNO,
    PERFIL_INSTRUTOR,
    perfil_do_usuario,
)
from apps.financeiro import services as financeiro
from apps.financeiro.models import Comprovante
from apps.matriculas.models import Frequencia, Matricula
from apps.turmas.models import Turma
from apps.turmas.services import aviso_de_carga

pytestmark = pytest.mark.django_db
S = Matricula.Status


@pytest.fixture
def modo_dev(settings):
    settings.DEBUG = True


def _popular(*args):
    saida = StringIO()
    call_command("popular_demo", *args, stdout=saida)
    return saida.getvalue()


def test_gerar_cpf_sempre_valido():
    rng = random.Random(1)
    assert all(cpf_valido(gerar_cpf(rng)) for _ in range(500))


def test_popular_demo_cria_os_quatro_cursos(modo_dev):
    saida = _popular()
    assert set(Curso.objects.values_list("nome", flat=True)) == {
        "Informática Básica", "Excel", "Digitação", "Internet Segura",
    }
    assert "Demonstração criada" in saida and "demo1234" in saida


def test_popular_demo_tem_turmas_em_todas_as_situacoes(modo_dev):
    _popular()
    assert set(Turma.objects.values_list("status", flat=True)) == set(Turma.Status.values)
    assert all(t.aulas.exists() for t in Turma.objects.all())


def test_popular_demo_respeita_as_regras(modo_dev):
    _popular()
    # Nenhuma turma com mais ativas que vagas; fila só onde a turma lotou.
    for turma in Turma.objects.all():
        ativas = turma.matriculas.filter(status=S.ATIVA).count()
        assert ativas <= turma.vagas
        if turma.matriculas.filter(status=S.LISTA_ESPERA).exists():
            assert ativas == turma.vagas
    # Turma concluída: cada concluída tem certificado; ninguém ficou ativo.
    concluida = Turma.objects.get(status=Turma.Status.CONCLUIDA)
    assert not concluida.matriculas.filter(status__in=[S.ATIVA, S.LISTA_ESPERA]).exists()
    assert concluida.matriculas.filter(status=S.DESISTENTE).exists()
    assert Certificado.objects.count() == Matricula.objects.filter(status=S.CONCLUIDA).count() > 0
    # Turma em andamento: tem chamadas e uma desistência que chamou alguém da fila.
    andamento = Turma.objects.get(status=Turma.Status.EM_ANDAMENTO, curso__nome="Informática Básica")
    assert Frequencia.objects.filter(aula__turma=andamento).exists()
    assert andamento.matriculas.filter(status=S.DESISTENTE).count() == 1
    assert andamento.matriculas.filter(status=S.ATIVA).count() == andamento.vagas
    # Planejada sem matrículas; cancelada só com canceladas.
    assert not Turma.objects.get(status=Turma.Status.PLANEJADA).matriculas.exists()
    cancelada = Turma.objects.get(status=Turma.Status.CANCELADA)
    assert set(cancelada.matriculas.values_list("status", flat=True)) == {S.CANCELADA}
    # Todo calendário cumpre a carga horária do curso.
    assert all(aviso_de_carga(t) is None for t in Turma.objects.all())
    # Todos os CPFs gerados são válidos.
    assert all(cpf_valido(cpf) for cpf in Aluno.objects.values_list("cpf", flat=True))


def test_popular_demo_cria_logins_de_cada_perfil(modo_dev):
    _popular("--senha", "outra-senha-123")
    esperados = {
        "admin": PERFIL_ADMINISTRADOR,
        "maria": PERFIL_INSTRUTOR,
        "carlos": PERFIL_INSTRUTOR,
        "aluno": PERFIL_ALUNO,
    }
    for username, perfil in esperados.items():
        usuario = authenticate(username=username, password="outra-senha-123")
        assert usuario is not None, username
        assert perfil_do_usuario(usuario) == perfil
    assert User.objects.get(username="admin").is_staff
    # O aluno de demonstração tem certificado e uma matrícula ativa.
    aluno = Aluno.objects.get(usuario__username="aluno")
    assert aluno.matriculas.filter(status=S.CONCLUIDA, certificado__isnull=False).exists()
    assert aluno.matriculas.filter(status=S.ATIVA).exists()


def test_nao_sobrescreve_dados_sem_limpar(modo_dev, curso):
    with pytest.raises(CommandError, match="--limpar"):
        _popular()
    assert list(Curso.objects.all()) == [curso]


def test_limpar_recria_do_zero(modo_dev):
    _popular()
    primeira = (Aluno.objects.count(), Matricula.objects.count(), Certificado.objects.count())
    saida = _popular("--limpar")
    assert "Dados anteriores apagados" in saida
    assert (Aluno.objects.count(), Matricula.objects.count(), Certificado.objects.count()) == primeira
    assert User.objects.filter(username="maria").count() == 1


def test_limpar_preserva_superusuario(modo_dev):
    User.objects.create_superuser("admin", "a@exemplo.com", "x")
    _popular("--limpar")
    admin = User.objects.get(username="admin")
    assert admin.is_superuser and admin.check_password("x")


def test_recusa_em_producao(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="produção"):
        _popular()
    assert not Curso.objects.exists()
    _popular("--permitir-producao")
    assert Curso.objects.count() == 4


def test_popular_demo_tem_cada_situacao_financeira(modo_dev):
    _popular()
    situacoes = {s.codigo for s in financeiro.situacoes(Matricula.objects.filter(status=S.ATIVA)).values()}
    assert {"em_dia", "pendente", "inadimplente", "isento"} <= situacoes
    assert Comprovante.objects.filter(status=Comprovante.Status.EM_ANALISE).count() == 1
    assert Comprovante.objects.filter(status=Comprovante.Status.RECUSADO).count() == 1
    # O aluno de login tem uma parcela em aberto para testar o Pix.
    aluno = Aluno.objects.get(usuario__username="aluno")
    assert aluno.matriculas.filter(parcelas__status="aberta").exists()
