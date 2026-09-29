from .services import perfil_do_usuario


def perfil(request):
    return {"perfil": perfil_do_usuario(getattr(request, "user", None))}
