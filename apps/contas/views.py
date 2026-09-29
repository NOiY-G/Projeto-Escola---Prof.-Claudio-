from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.turmas.services import aulas_do_dia

from .services import PERFIL_INSTRUTOR, perfil_do_usuario


@login_required
def painel(request):
    contexto = {}
    if perfil_do_usuario(request.user) == PERFIL_INSTRUTOR:
        contexto["aulas_hoje"] = aulas_do_dia(request.user, timezone.localdate())
    return render(request, "contas/painel.html", contexto)
