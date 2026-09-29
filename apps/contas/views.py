from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def painel(request):
    return render(request, "contas/painel.html")
