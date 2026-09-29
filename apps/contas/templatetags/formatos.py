from decimal import Decimal, InvalidOperation

from django import template

from apps.alunos.validators import formatar_cpf, mascarar_cpf

register = template.Library()


@register.filter
def reais(valor):
    """Formata um número como moeda brasileira: 1234.5 -> R$ 1.234,50"""
    try:
        valor = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return valor
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@register.filter
def cpf(valor):
    return formatar_cpf(valor)


@register.filter
def cpf_mascarado(valor):
    return mascarar_cpf(valor)
