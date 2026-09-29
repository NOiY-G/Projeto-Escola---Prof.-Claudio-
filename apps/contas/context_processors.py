from .menu import montar_menu
from .services import perfil_do_usuario


def perfil(request):
    usuario = getattr(request, "user", None)
    perfil_atual = perfil_do_usuario(usuario)
    contexto = {"perfil": perfil_atual}
    if usuario is not None and usuario.is_authenticated:
        contexto["menu"] = montar_menu(request, perfil_atual)
    return contexto
