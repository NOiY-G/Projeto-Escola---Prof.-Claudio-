"""Relatórios e números do painel.

Definições usadas (mostradas também nas telas):
- Alunos por curso: alunos distintos com matrícula não cancelada nas turmas do curso.
- Taxa de conclusão: concluídas ÷ (concluídas + desistentes), só em turmas concluídas.
- Evasão: desistentes ÷ (ativas + concluídas + desistentes), em qualquer turma.
- Ocupação: matrículas ativas ÷ vagas, nas turmas ainda não encerradas.
"""

import csv
import datetime
import io
from dataclasses import dataclass

from django.db.models import Count, Q
from django.utils import timezone

from apps.catalogo.models import Curso
from apps.matriculas.models import Matricula
from apps.turmas.models import Aula, Turma

S = Matricula.Status
TURMAS_ABERTAS = (Turma.Status.PLANEJADA, Turma.Status.INSCRICOES_ABERTAS, Turma.Status.EM_ANDAMENTO)


def _taxa(parte, total):
    return round(parte * 100 / total, 1) if total else None


def _contagens():
    """Anotações de Turma com a contagem de matrículas por status."""
    def contar(status):
        return Count("matriculas", filter=Q(matriculas__status=status), distinct=True)

    return {
        "ativas": contar(S.ATIVA),
        "espera": contar(S.LISTA_ESPERA),
        "concluidas": contar(S.CONCLUIDA),
        "desistentes": contar(S.DESISTENTE),
        "canceladas": contar(S.CANCELADA),
    }


# Filtros


def turmas_filtradas(ano=None, curso_id=None):
    """Turmas que entram nos relatórios: por ano de início e/ou curso."""
    qs = Turma.objects.all()
    if ano:
        qs = qs.filter(data_inicio__year=ano)
    if curso_id:
        qs = qs.filter(curso_id=curso_id)
    return qs


def anos_disponiveis():
    return sorted({d.year for d in Turma.objects.dates("data_inicio", "year")}, reverse=True)


# Relatórios


def alunos_por_curso(turmas):
    def contar(status):
        return Count(
            "turmas__matriculas",
            filter=Q(turmas__in=turmas, turmas__matriculas__status=status),
            distinct=True,
        )

    cursos = (
        Curso.objects.filter(turmas__in=turmas)
        .annotate(
            total_turmas=Count("turmas", filter=Q(turmas__in=turmas), distinct=True),
            alunos=Count(
                "turmas__matriculas__aluno",
                filter=Q(turmas__in=turmas) & ~Q(turmas__matriculas__status=S.CANCELADA),
                distinct=True,
            ),
            ativas=contar(S.ATIVA),
            espera=contar(S.LISTA_ESPERA),
            concluidas=contar(S.CONCLUIDA),
            desistentes=contar(S.DESISTENTE),
            canceladas=contar(S.CANCELADA),
        )
        .order_by("nome")
    )
    return [
        {
            "curso": c.nome,
            "turmas": c.total_turmas,
            "alunos": c.alunos,
            "ativas": c.ativas,
            "espera": c.espera,
            "concluidas": c.concluidas,
            "desistentes": c.desistentes,
            "canceladas": c.canceladas,
        }
        for c in cursos
    ]


def conclusao_e_evasao(turmas):
    """Uma linha por turma, mais o total geral no fim."""
    linhas = []
    qs = (
        turmas.exclude(status=Turma.Status.CANCELADA)
        .select_related("curso")
        .annotate(**_contagens())
        .order_by("-data_inicio", "codigo")
    )
    totais = {"concluidas": 0, "desistentes": 0, "ativas": 0, "concluidas_fechadas": 0, "desistentes_fechadas": 0}
    for t in qs:
        concluida = t.status == Turma.Status.CONCLUIDA
        linhas.append(
            {
                "turma": t.codigo,
                "curso": t.curso.nome,
                "status": t.get_status_display(),
                "ativas": t.ativas,
                "concluidas": t.concluidas,
                "desistentes": t.desistentes,
                "taxa_conclusao": _taxa(t.concluidas, t.concluidas + t.desistentes) if concluida else None,
                "taxa_evasao": _taxa(t.desistentes, t.ativas + t.concluidas + t.desistentes),
            }
        )
        totais["concluidas"] += t.concluidas
        totais["desistentes"] += t.desistentes
        totais["ativas"] += t.ativas
        if concluida:
            totais["concluidas_fechadas"] += t.concluidas
            totais["desistentes_fechadas"] += t.desistentes
    total = {
        "turma": "Total",
        "curso": "",
        "status": "",
        "ativas": totais["ativas"],
        "concluidas": totais["concluidas"],
        "desistentes": totais["desistentes"],
        "taxa_conclusao": _taxa(
            totais["concluidas_fechadas"], totais["concluidas_fechadas"] + totais["desistentes_fechadas"]
        ),
        "taxa_evasao": _taxa(
            totais["desistentes"], totais["ativas"] + totais["concluidas"] + totais["desistentes"]
        ),
    }
    return linhas, total


def ocupacao(turmas):
    qs = (
        turmas.filter(status__in=TURMAS_ABERTAS)
        .select_related("curso")
        .annotate(**_contagens())
        .order_by("data_inicio", "codigo")
    )
    return [
        {
            "turma": t.codigo,
            "curso": t.curso.nome,
            "status": t.get_status_display(),
            "vagas": t.vagas,
            "ocupadas": t.ativas,
            "livres": max(t.vagas - t.ativas, 0),
            "espera": t.espera,
            "ocupacao": _taxa(t.ativas, t.vagas),
            # Largura da barra na tela (a ocupação passa de 100% se as vagas forem reduzidas).
            "barra": min(_taxa(t.ativas, t.vagas) or 0, 100),
        }
        for t in qs
    ]


# Painel


@dataclass
class NumerosPainel:
    turmas_em_andamento: int
    vagas_livres: int
    matriculas_7_dias: int
    na_fila: int
    aulas_hoje: int
    recentes: list


def numeros_do_painel(hoje=None):
    hoje = hoje or timezone.localdate()
    abertas = Turma.objects.filter(status=Turma.Status.INSCRICOES_ABERTAS).annotate(**_contagens())
    inicio_semana = timezone.make_aware(
        datetime.datetime.combine(hoje - datetime.timedelta(days=6), datetime.time.min)
    )
    return NumerosPainel(
        turmas_em_andamento=Turma.objects.filter(status=Turma.Status.EM_ANDAMENTO).count(),
        vagas_livres=sum(max(t.vagas - t.ativas, 0) for t in abertas),
        matriculas_7_dias=Matricula.objects.filter(data__gte=inicio_semana).count(),
        na_fila=Matricula.objects.filter(status=S.LISTA_ESPERA).count(),
        aulas_hoje=Aula.objects.filter(data=hoje).exclude(turma__status=Turma.Status.CANCELADA).count(),
        recentes=list(
            Matricula.objects.select_related("aluno", "turma__curso").order_by("-data", "-pk")[:5]
        ),
    )


# CSV


def _celula(valor):
    """Formato brasileiro: decimal com vírgula; vazio para 'não se aplica'."""
    if valor is None:
        return ""
    if isinstance(valor, float):
        return f"{valor:.1f}".replace(".", ",")
    return valor


def gerar_csv(colunas, linhas):
    """CSV separado por ';' com BOM, para abrir direto no Excel em português.

    `colunas` é uma lista de (chave, título).
    """
    saida = io.StringIO()
    saida.write("﻿")
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow([titulo for _, titulo in colunas])
    for linha in linhas:
        escritor.writerow([_celula(linha[chave]) for chave, _ in colunas])
    return saida.getvalue()
