from django.contrib.auth.models import User
from django.db import transaction

from apps.contas.services import GRUPO_INSTRUTOR, atribuir_perfil

from .models import Curso, Instrutor


def alternar_ativo(curso: Curso) -> Curso:
    """Ativa um curso inativo ou desativa um ativo."""
    curso.ativo = not curso.ativo
    curso.save(update_fields=["ativo"])
    return curso


def cursos_ativos():
    return Curso.objects.filter(ativo=True)


@transaction.atomic
def criar_instrutor(*, username, email, senha, nome, telefone="", especialidades="") -> Instrutor:
    """Cria o usuário de acesso, coloca no grupo Instrutor e cria o cadastro."""
    usuario = User.objects.create_user(username=username, email=email, password=senha)
    partes = nome.split(maxsplit=1)
    usuario.first_name = partes[0][:150]
    usuario.last_name = (partes[1] if len(partes) > 1 else "")[:150]
    usuario.save(update_fields=["first_name", "last_name"])
    atribuir_perfil(usuario, GRUPO_INSTRUTOR)
    return Instrutor.objects.create(
        usuario=usuario, nome=nome, telefone=telefone, especialidades=especialidades
    )


@transaction.atomic
def atualizar_instrutor(instrutor: Instrutor, *, email) -> Instrutor:
    """Salva o cadastro e mantém o e-mail do usuário de acesso em dia."""
    instrutor.save()
    if instrutor.usuario.email != email:
        instrutor.usuario.email = email
        instrutor.usuario.save(update_fields=["email"])
    return instrutor
