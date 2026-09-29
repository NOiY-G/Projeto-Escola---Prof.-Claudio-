import datetime
from dataclasses import dataclass, field

from django.db import transaction

from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR, perfil_do_usuario

from .models import DIA_PARA_WEEKDAY, Aula, Feriado, Turma


def turmas_visiveis_para(usuario):
    """Administrador vê todas as turmas; instrutor, só as próprias."""
    qs = Turma.objects.select_related("curso", "instrutor")
    perfil = perfil_do_usuario(usuario)
    if perfil == PERFIL_ADMINISTRADOR:
        return qs
    if perfil == PERFIL_INSTRUTOR:
        return qs.filter(instrutor__usuario=usuario)
    return qs.none()


def filtrar_turmas(qs, *, status=None, curso_id=None, busca=None):
    if status:
        qs = qs.filter(status=status)
    if curso_id:
        qs = qs.filter(curso_id=curso_id)
    if busca:
        qs = qs.filter(codigo__icontains=busca)
    return qs


def vagas_ocupadas(turma):
    from apps.matriculas.models import Matricula

    return turma.matriculas.filter(status=Matricula.Status.ATIVA).count()


def vagas_livres(turma):
    return max(turma.vagas - vagas_ocupadas(turma), 0)


# Aulas


def datas_das_aulas(turma):
    """Datas entre o início e o fim da turma nos dias da semana dela, menos os feriados."""
    weekdays = {DIA_PARA_WEEKDAY[d] for d in turma.dias_semana_lista}
    feriados = set(
        Feriado.objects.filter(data__range=(turma.data_inicio, turma.data_fim)).values_list("data", flat=True)
    )
    dia = turma.data_inicio
    datas = []
    while dia <= turma.data_fim:
        if dia.weekday() in weekdays and dia not in feriados:
            datas.append(dia)
        dia += datetime.timedelta(days=1)
    return datas


CAMPOS_DO_CALENDARIO = {"data_inicio", "data_fim", "dias_semana"}


def calendario_mudou(campos_alterados):
    """Se a edição mexeu no período ou nos dias, as aulas precisam ser refeitas."""
    return bool(CAMPOS_DO_CALENDARIO & set(campos_alterados))


@dataclass
class ResultadoGeracao:
    criadas: list = field(default_factory=list)
    removidas: list = field(default_factory=list)
    # Aulas fora do novo calendário que já têm chamada: ficam para não perder a frequência.
    mantidas: list = field(default_factory=list)

    @property
    def mudou(self):
        return bool(self.criadas or self.removidas)


@transaction.atomic
def gerar_aulas(turma) -> ResultadoGeracao:
    """Deixa as aulas da turma de acordo com o período e os dias da semana.

    Cria as que faltam e apaga as que saíram do calendário, a não ser que já
    tenham chamada registrada. Pode ser chamada de novo sem duplicar nada.
    """
    resultado = ResultadoGeracao()
    esperadas = set(datas_das_aulas(turma))
    existentes = {aula.data: aula for aula in turma.aulas.all()}

    for data in sorted(esperadas - existentes.keys()):
        resultado.criadas.append(Aula(turma=turma, data=data))
    Aula.objects.bulk_create(resultado.criadas)

    for data in sorted(existentes.keys() - esperadas):
        aula = existentes[data]
        if aula.frequencias.exists():
            resultado.mantidas.append(aula)
        else:
            resultado.removidas.append(aula)
    if resultado.removidas:
        Aula.objects.filter(pk__in=[a.pk for a in resultado.removidas]).delete()
    return resultado


def aulas_do_dia(usuario, dia):
    """Aulas do dia nas turmas que o usuário pode ver (canceladas não entram)."""
    return (
        Aula.objects.filter(turma__in=turmas_visiveis_para(usuario), data=dia)
        .exclude(turma__status=Turma.Status.CANCELADA)
        .select_related("turma__curso")
        .order_by("turma__hora_inicio")
    )


# Feriados


TURMAS_ENCERRADAS = (Turma.Status.CONCLUIDA, Turma.Status.CANCELADA)


def turmas_no_dia(data):
    """Turmas não encerradas cujo período inclui a data."""
    return (
        Turma.objects.exclude(status__in=TURMAS_ENCERRADAS)
        .filter(data_inicio__lte=data, data_fim__gte=data)
        .order_by("codigo")
    )


@dataclass
class ResultadoFeriado:
    removidas: list = field(default_factory=list)
    # Aulas no feriado que já têm chamada: ficam, para não perder a frequência.
    mantidas: list = field(default_factory=list)
    criadas: list = field(default_factory=list)


@transaction.atomic
def cadastrar_feriado(data, descricao):
    """Cadastra o feriado e tira do calendário as aulas desse dia (sem chamada)."""
    feriado = Feriado.objects.create(data=data, descricao=descricao.strip())
    resultado = ResultadoFeriado()
    aulas = Aula.objects.filter(turma__in=turmas_no_dia(data), data=data).select_related("turma")
    for aula in aulas:
        if aula.frequencias.exists():
            resultado.mantidas.append(aula)
        else:
            resultado.removidas.append(aula)
    Aula.objects.filter(pk__in=[a.pk for a in resultado.removidas]).delete()
    return feriado, resultado


@transaction.atomic
def remover_feriado(feriado):
    """Apaga o feriado e devolve a aula desse dia às turmas que têm aula naquele dia da semana."""
    data = feriado.data
    feriado.delete()
    resultado = ResultadoFeriado()
    for turma in turmas_no_dia(data):
        tem_aula_no_dia = data.weekday() in {DIA_PARA_WEEKDAY[d] for d in turma.dias_semana_lista}
        if tem_aula_no_dia and not turma.aulas.filter(data=data).exists():
            resultado.criadas.append(Aula.objects.create(turma=turma, data=data))
    return resultado


def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return datetime.date(ano, mes, dia)


def feriados_nacionais(ano):
    """Feriados nacionais oficiais (Lei 662/1949 e alterações; Lei 14.759/2023)."""
    return [
        (datetime.date(ano, 1, 1), "Confraternização Universal"),
        (pascoa(ano) - datetime.timedelta(days=2), "Sexta-feira Santa"),
        (datetime.date(ano, 4, 21), "Tiradentes"),
        (datetime.date(ano, 5, 1), "Dia do Trabalho"),
        (datetime.date(ano, 9, 7), "Independência do Brasil"),
        (datetime.date(ano, 10, 12), "Nossa Senhora Aparecida"),
        (datetime.date(ano, 11, 2), "Finados"),
        (datetime.date(ano, 11, 15), "Proclamação da República"),
        (datetime.date(ano, 11, 20), "Dia Nacional de Zumbi e da Consciência Negra"),
        (datetime.date(ano, 12, 25), "Natal"),
    ]


@transaction.atomic
def cadastrar_feriados_nacionais(ano):
    """Cadastra os feriados nacionais do ano que ainda não existem."""
    existentes = set(Feriado.objects.filter(data__year=ano).values_list("data", flat=True))
    cadastrados = []
    resultado = ResultadoFeriado()
    for data, descricao in feriados_nacionais(ano):
        if data in existentes:
            continue
        feriado, parcial = cadastrar_feriado(data, descricao)
        cadastrados.append(feriado)
        resultado.removidas += parcial.removidas
        resultado.mantidas += parcial.mantidas
    return cadastrados, resultado
