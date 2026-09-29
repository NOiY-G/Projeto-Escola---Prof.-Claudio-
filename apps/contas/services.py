from django.contrib.auth.models import Group, Permission

GRUPO_ADMINISTRADOR = "Administrador"
GRUPO_INSTRUTOR = "Instrutor"
GRUPO_ALUNO = "Aluno"

GRUPOS = (GRUPO_ADMINISTRADOR, GRUPO_INSTRUTOR, GRUPO_ALUNO)

PERFIL_ADMINISTRADOR = "administrador"
PERFIL_INSTRUTOR = "instrutor"
PERFIL_ALUNO = "aluno"

_PERFIL_POR_GRUPO = {
    GRUPO_ADMINISTRADOR: PERFIL_ADMINISTRADOR,
    GRUPO_INSTRUTOR: PERFIL_INSTRUTOR,
    GRUPO_ALUNO: PERFIL_ALUNO,
}


def garantir_grupos():
    """Cria os grupos de perfil e dá ao Administrador todas as permissões."""
    grupos = {nome: Group.objects.get_or_create(name=nome)[0] for nome in GRUPOS}
    grupos[GRUPO_ADMINISTRADOR].permissions.set(Permission.objects.all())
    return grupos


def perfil_do_usuario(usuario):
    """Retorna o perfil principal do usuário (o de maior acesso) ou None."""
    if not usuario or not usuario.is_authenticated:
        return None
    if usuario.is_superuser:
        return PERFIL_ADMINISTRADOR
    nomes = set(usuario.groups.values_list("name", flat=True))
    for grupo in GRUPOS:
        if grupo in nomes:
            return _PERFIL_POR_GRUPO[grupo]
    return None


def atribuir_perfil(usuario, grupo):
    """Coloca o usuário no grupo de perfil indicado."""
    if grupo not in GRUPOS:
        raise ValueError(f"Perfil desconhecido: {grupo}")
    usuario.groups.add(Group.objects.get_or_create(name=grupo)[0])
