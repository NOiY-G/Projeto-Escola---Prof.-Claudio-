import datetime
from dataclasses import dataclass, field

from django.db import transaction

from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR, perfil_do_usuario

from .models import DIA_PARA_WEEKDAY, Aula, Turma


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
    """Todas as datas entre o início e o fim da turma que caem nos dias da semana dela."""
    weekdays = {DIA_PARA_WEEKDAY[d] for d in turma.dias_semana_lista}
    dia = turma.data_inicio
    datas = []
    while dia <= turma.data_fim:
        if dia.weekday() in weekdays:
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
