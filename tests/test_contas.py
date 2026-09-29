import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core import mail
from django.urls import reverse

from apps.contas.services import (
    GRUPO_ADMINISTRADOR,
    GRUPOS,
    PERFIL_ADMINISTRADOR,
    PERFIL_ALUNO,
    PERFIL_INSTRUTOR,
    perfil_do_usuario,
)

pytestmark = pytest.mark.django_db


def test_grupos_de_perfil_sao_criados_apos_migracao():
    assert set(Group.objects.values_list("name", flat=True)) >= set(GRUPOS)


def test_administrador_tem_todas_as_permissoes():
    grupo = Group.objects.get(name=GRUPO_ADMINISTRADOR)
    assert grupo.permissions.count() == Permission.objects.count()


def test_perfil_do_usuario(usuario_admin, usuario_instrutor, usuario_aluno):
    assert perfil_do_usuario(usuario_admin) == PERFIL_ADMINISTRADOR
    assert perfil_do_usuario(usuario_instrutor) == PERFIL_INSTRUTOR
    assert perfil_do_usuario(usuario_aluno) == PERFIL_ALUNO
    assert perfil_do_usuario(User.objects.create_user("sem_perfil")) is None


def test_superusuario_e_administrador():
    su = User.objects.create_superuser("root", "root@exemplo.com", "x")
    assert perfil_do_usuario(su) == PERFIL_ADMINISTRADOR


def test_painel_exige_login(client):
    resposta = client.get(reverse("contas:painel"))
    assert resposta.status_code == 302
    assert reverse("contas:login") in resposta.url


def test_login_redireciona_para_painel(client, usuario_aluno):
    resposta = client.post(
        reverse("contas:login"), {"username": "aluno", "password": "senha-forte-123"}
    )
    assert resposta.status_code == 302
    assert resposta.url == reverse("contas:painel")
    assert client.get(reverse("contas:painel")).status_code == 200


def test_login_invalido(client, usuario_aluno):
    resposta = client.post(reverse("contas:login"), {"username": "aluno", "password": "errada"})
    assert resposta.status_code == 200
    assert "inválidos" in resposta.content.decode()


def test_recuperacao_de_senha_envia_email(client, usuario_aluno):
    resposta = client.post(reverse("contas:password_reset"), {"email": "aluno@exemplo.com"})
    assert resposta.status_code == 302
    assert len(mail.outbox) == 1
    assert "/senha/redefinir/" in mail.outbox[0].body
