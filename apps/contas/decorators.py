from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .services import perfil_do_usuario


def perfil_requerido(*perfis):
    """Restringe a view aos perfis informados (ex.: "administrador")."""

    def decorator(view):
        @wraps(view)
        @login_required
        def _view(request, *args, **kwargs):
            if perfil_do_usuario(request.user) not in perfis:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return _view

    return decorator


class PerfilRequeridoMixin(LoginRequiredMixin):
    perfis = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if perfil_do_usuario(request.user) not in self.perfis:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
