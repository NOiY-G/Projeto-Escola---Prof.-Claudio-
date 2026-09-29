from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR, perfil_do_usuario

from .models import Turma


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
