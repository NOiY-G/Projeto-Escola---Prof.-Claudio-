import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from apps.alunos.models import Aluno
from apps.catalogo.models import Curso, Instrutor
from apps.contas.services import GRUPO_ADMINISTRADOR, GRUPO_ALUNO, GRUPO_INSTRUTOR, atribuir_perfil
from apps.turmas.models import Turma


def _usuario(username, grupo=None):
    usuario = User.objects.create_user(username, f"{username}@exemplo.com", "senha-forte-123")
    if grupo:
        atribuir_perfil(usuario, grupo)
    return usuario


@pytest.fixture
def usuario_admin(db):
    return _usuario("admin", GRUPO_ADMINISTRADOR)


@pytest.fixture
def usuario_instrutor(db):
    return _usuario("instrutor", GRUPO_INSTRUTOR)


@pytest.fixture
def usuario_aluno(db):
    return _usuario("aluno", GRUPO_ALUNO)


@pytest.fixture
def curso(db):
    return Curso.objects.create(nome="Informática Básica", carga_horaria=40, valor=Decimal("0"))


@pytest.fixture
def instrutor(usuario_instrutor):
    return Instrutor.objects.create(usuario=usuario_instrutor, nome="Maria Souza")


@pytest.fixture
def turma(curso, instrutor):
    return Turma.objects.create(
        curso=curso,
        instrutor=instrutor,
        codigo="INF-2026-01",
        data_inicio=datetime.date(2026, 10, 5),
        data_fim=datetime.date(2026, 11, 27),
        dias_semana="seg,qua",
        hora_inicio=datetime.time(8, 0),
        hora_fim=datetime.time(10, 0),
        vagas=20,
        status=Turma.Status.INSCRICOES_ABERTAS,
    )


@pytest.fixture
def aluno(db):
    return Aluno.objects.create(
        nome="João da Silva", cpf="529.982.247-25", data_nascimento=datetime.date(2000, 1, 15)
    )
