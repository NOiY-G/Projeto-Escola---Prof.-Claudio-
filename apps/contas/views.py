from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.financeiro.services import numeros_do_painel as numeros_financeiros
from apps.relatorios.services import numeros_do_painel
from apps.turmas.services import aulas_do_dia

from .services import PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR, perfil_do_usuario


@login_required
def painel(request):
    contexto = {}
    perfil = perfil_do_usuario(request.user)
    if perfil == PERFIL_INSTRUTOR:
        contexto["aulas_hoje"] = aulas_do_dia(request.user, timezone.localdate())
    elif perfil == PERFIL_ADMINISTRADOR:
        contexto["numeros"] = numeros_do_painel()
        contexto["financeiro"] = numeros_financeiros()
        contexto["tolerancia"] = str(settings.TOLERANCIA_PAGAMENTO_DIAS)
    return render(request, "contas/painel.html", contexto)
