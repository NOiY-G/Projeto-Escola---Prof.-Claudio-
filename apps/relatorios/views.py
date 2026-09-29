from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.catalogo.models import Curso
from apps.contas.decorators import perfil_requerido
from apps.contas.services import PERFIL_ADMINISTRADOR

from . import services


def _alunos_por_curso(turmas):
    return services.alunos_por_curso(turmas), None


# slug -> título, explicação, colunas (chave, título, tipo) e função que gera as linhas.
# Tipos: "texto", "numero", "pct" (percentual) e "medidor" (percentual com barra).
RELATORIOS = {
    "alunos-por-curso": {
        "titulo": "Alunos por curso",
        "explicacao": "Alunos distintos com matrícula não cancelada nas turmas de cada curso, "
        "e as matrículas por situação.",
        "colunas": [
            ("curso", "Curso", "texto"),
            ("turmas", "Turmas", "numero"),
            ("alunos", "Alunos", "numero"),
            ("ativas", "Ativas", "numero"),
            ("espera", "Na fila", "numero"),
            ("concluidas", "Concluídas", "numero"),
            ("desistentes", "Desistentes", "numero"),
            ("canceladas", "Canceladas", "numero"),
        ],
        "gerar": _alunos_por_curso,
    },
    "conclusao-evasao": {
        "titulo": "Conclusão e evasão",
        "explicacao": "Taxa de conclusão = concluídas ÷ (concluídas + desistentes), só em turmas "
        "concluídas. Evasão = desistentes ÷ (ativas + concluídas + desistentes). "
        "Turmas canceladas não entram.",
        "colunas": [
            ("turma", "Turma", "texto"),
            ("curso", "Curso", "texto"),
            ("status", "Situação", "texto"),
            ("ativas", "Ativas", "numero"),
            ("concluidas", "Concluídas", "numero"),
            ("desistentes", "Desistentes", "numero"),
            ("taxa_conclusao", "Conclusão", "pct"),
            ("taxa_evasao", "Evasão", "pct"),
        ],
        "gerar": services.conclusao_e_evasao,
    },
    "ocupacao": {
        "titulo": "Ocupação das turmas",
        "explicacao": "Matrículas ativas ÷ vagas, nas turmas planejadas, com inscrições abertas "
        "ou em andamento.",
        "colunas": [
            ("turma", "Turma", "texto"),
            ("curso", "Curso", "texto"),
            ("status", "Situação", "texto"),
            ("vagas", "Vagas", "numero"),
            ("ocupadas", "Ocupadas", "numero"),
            ("livres", "Livres", "numero"),
            ("espera", "Na fila", "numero"),
            ("ocupacao", "Ocupação", "medidor"),
        ],
        "gerar": lambda turmas: (services.ocupacao(turmas), None),
    },
}


def _filtros(request):
    ano = request.GET.get("ano", "")
    curso = request.GET.get("curso", "")
    return (int(ano) if ano.isdigit() else None), (int(curso) if curso.isdigit() else None)


def _dados(slug, request):
    relatorio = RELATORIOS.get(slug)
    if relatorio is None:
        raise Http404
    ano, curso_id = _filtros(request)
    linhas, total = relatorio["gerar"](services.turmas_filtradas(ano=ano, curso_id=curso_id))
    return relatorio, linhas, total, ano, curso_id


@perfil_requerido(PERFIL_ADMINISTRADOR)
def inicio(request):
    return redirect("relatorios:relatorio", slug="alunos-por-curso")


@perfil_requerido(PERFIL_ADMINISTRADOR)
def relatorio(request, slug):
    relatorio, linhas, total, ano, curso_id = _dados(slug, request)
    return render(
        request,
        "relatorios/relatorio.html",
        {
            "slug": slug,
            "relatorio": relatorio,
            "relatorios": RELATORIOS,
            "linhas": linhas,
            "total": total,
            "anos": services.anos_disponiveis(),
            "cursos": Curso.objects.order_by("nome"),
            "ano": ano,
            "curso_id": curso_id,
        },
    )


@perfil_requerido(PERFIL_ADMINISTRADOR)
def relatorio_csv(request, slug):
    relatorio, linhas, total, ano, curso_id = _dados(slug, request)
    colunas = [(chave, titulo) for chave, titulo, _ in relatorio["colunas"]]
    conteudo = services.gerar_csv(colunas, linhas + ([total] if total else []))
    resposta = HttpResponse(conteudo, content_type="text/csv; charset=utf-8")
    partes = [slug] + ([str(ano)] if ano else []) + [timezone.localdate().strftime("%Y-%m-%d")]
    resposta["Content-Disposition"] = f'attachment; filename="{"_".join(partes)}.csv"'
    return resposta
