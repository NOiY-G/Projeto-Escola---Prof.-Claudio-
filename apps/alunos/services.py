from django.db.models import Q

from .models import Aluno
from .validators import somente_digitos


def buscar_alunos(termo=""):
    """Busca por parte do nome ou do CPF (com ou sem pontuação)."""
    qs = Aluno.objects.all()
    termo = (termo or "").strip()
    if not termo:
        return qs
    filtro = Q(nome__icontains=termo)
    digitos = somente_digitos(termo)
    if digitos:
        filtro |= Q(cpf__contains=digitos)
    return qs.filter(filtro)


def historico_do_aluno(aluno):
    """Todas as matrículas do aluno, da mais recente para a mais antiga."""
    return aluno.matriculas.select_related("turma__curso").order_by("-data")
