import re

from django.core.exceptions import ValidationError


def somente_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def cpf_valido(valor):
    cpf = somente_digitos(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def validar_cpf(valor):
    if not cpf_valido(valor):
        raise ValidationError("CPF inválido.")


def formatar_cpf(valor):
    cpf = somente_digitos(valor)
    if len(cpf) != 11:
        return valor
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def mascarar_cpf(valor):
    """Ex.: 123.456.789-09 -> ***.456.789-**"""
    cpf = somente_digitos(valor)
    if len(cpf) != 11:
        return valor
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"
