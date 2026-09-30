import math
from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from apps.contas.services import GRUPO_INSTRUTOR, atribuir_perfil

from .models import Curso, Instrutor


# Carga horária

# Cada mês conta como 4 semanas cheias: sobra folga para feriados e meses de 30 dias.
SEMANAS_POR_MES = 4
# As aulas podem ser de segunda a sábado.
DIAS_DE_AULA_POR_SEMANA = 6


@dataclass(frozen=True)
class Calculo:
    """Carga horária do curso a partir de meses, dias por semana e horas por aula."""

    duracao_meses: int
    dias_por_semana: int
    horas_por_aula: Decimal
    semanas: int
    aulas: int
    carga_horaria: int


def calcular(duracao_meses, dias_por_semana, horas_por_aula) -> Calculo:
    """carga horária = meses × 4 semanas × dias por semana × horas por aula."""
    horas_por_aula = Decimal(horas_por_aula)
    if duracao_meses <= 0 or horas_por_aula <= 0 or not 1 <= dias_por_semana <= DIAS_DE_AULA_POR_SEMANA:
        raise ValueError("Meses e horas por aula precisam ser maiores que zero; dias por semana, de 1 a 6.")
    semanas = duracao_meses * SEMANAS_POR_MES
    aulas = semanas * dias_por_semana
    return Calculo(
        duracao_meses=duracao_meses,
        dias_por_semana=dias_por_semana,
        horas_por_aula=horas_por_aula,
        semanas=semanas,
        aulas=aulas,
        # Com aulas de 15 em 15 minutos a conta é exata; se não for, arredonda para cima.
        carga_horaria=math.ceil(aulas * horas_por_aula),
    )


def calcular_carga_horaria(duracao_meses, dias_por_semana, horas_por_aula) -> int:
    return calcular(duracao_meses, dias_por_semana, horas_por_aula).carga_horaria


def calculo_do_curso(curso: Curso) -> Calculo:
    return calcular(curso.duracao_meses, curso.dias_por_semana, curso.horas_por_aula)


# Pré-requisitos


def cursos_que_dependem_de(curso: Curso):
    """Cursos que pedem `curso` como pré-requisito, direta ou indiretamente."""
    encontrados, fila = set(), [curso.pk]
    while fila:
        ids = set(
            Curso.pre_requisitos.through.objects.filter(to_curso_id__in=fila).values_list("from_curso_id", flat=True)
        ) - encontrados
        encontrados |= ids
        fila = list(ids)
    return Curso.objects.filter(pk__in=encontrados)


def validar_pre_requisitos(curso: Curso, escolhidos):
    """Mensagem de erro se a escolha cria um ciclo (A pede B e B pede A); senão None."""
    if curso.pk is None:
        return None
    if any(c.pk == curso.pk for c in escolhidos):
        return "Um curso não pode ser pré-requisito dele mesmo."
    ciclo = [c.nome for c in escolhidos if c in set(cursos_que_dependem_de(curso))]
    if ciclo:
        return f"{', '.join(ciclo)} já depende(m) deste curso; não pode(m) ser pré-requisito dele."
    return None


def formatar_horas(horas):
    """Ex.: 2 → "2 h"; 1.5 → "1,5 h"."""
    texto = f"{Decimal(horas).quantize(Decimal('0.01')).normalize():f}".replace(".", ",")
    return f"{texto} h"


# Cursos


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
