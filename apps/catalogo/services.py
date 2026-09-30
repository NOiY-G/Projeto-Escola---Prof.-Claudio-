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
class Planejamento:
    """Quantas aulas por semana o curso precisa para cumprir a carga horária."""

    carga_horaria: int
    duracao_meses: int
    horas_por_aula: Decimal
    semanas: int
    aulas_necessarias: int
    dias_minimos: int  # por semana; pode passar de 6 quando não cabe
    carga_maxima: Decimal  # aula de segunda a sábado durante todo o curso

    @property
    def cabe(self):
        return self.dias_minimos <= DIAS_DE_AULA_POR_SEMANA

    @property
    def carga_planejada(self):
        """Horas dadas com o mínimo de dias por semana durante todo o curso."""
        return self.dias_minimos * self.semanas * self.horas_por_aula


def planejar(carga_horaria, duracao_meses, horas_por_aula) -> Planejamento:
    """Calcula o mínimo de dias de aula por semana (de segunda a sábado).

    aulas necessárias = carga horária ÷ duração da aula (arredondado para cima)
    dias por semana   = aulas necessárias ÷ (meses × 4 semanas) (arredondado para cima)
    """
    horas_por_aula = Decimal(horas_por_aula)
    if carga_horaria <= 0 or duracao_meses <= 0 or horas_por_aula <= 0:
        raise ValueError("Carga horária, duração e horas por aula precisam ser maiores que zero.")
    semanas = duracao_meses * SEMANAS_POR_MES
    aulas = math.ceil(Decimal(carga_horaria) / horas_por_aula)
    return Planejamento(
        carga_horaria=carga_horaria,
        duracao_meses=duracao_meses,
        horas_por_aula=horas_por_aula,
        semanas=semanas,
        aulas_necessarias=aulas,
        dias_minimos=max(1, math.ceil(aulas / semanas)),
        carga_maxima=DIAS_DE_AULA_POR_SEMANA * semanas * horas_por_aula,
    )


def planejamento_do_curso(curso: Curso) -> Planejamento:
    return planejar(curso.carga_horaria, curso.duracao_meses, curso.horas_por_aula)


def validar_planejamento(carga_horaria, duracao_meses, horas_por_aula):
    """Mensagem de erro se nem com aula de segunda a sábado a carga horária cabe; senão None."""
    plano = planejar(carga_horaria, duracao_meses, horas_por_aula)
    if plano.cabe:
        return None
    return (
        f"Não cabe: com aulas de {formatar_horas(plano.horas_por_aula)} de segunda a sábado, "
        f"{plano.duracao_meses} {'mês' if plano.duracao_meses == 1 else 'meses'} dão no máximo "
        f"{formatar_horas(plano.carga_maxima)}. Aumente a duração ou o tempo de aula, "
        "ou diminua a carga horária."
    )


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
