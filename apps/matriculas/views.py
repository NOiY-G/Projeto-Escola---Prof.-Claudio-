from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.contas.decorators import perfil_requerido
from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_ALUNO

from . import services
from .forms import MatriculaForm
from .models import Matricula


def _avisar_promovidas(request, promovidas):
    for matricula in promovidas:
        messages.info(
            request,
            f"{matricula.aluno.nome} saiu da lista de espera e agora está com matrícula ativa.",
        )


@perfil_requerido(PERFIL_ADMINISTRADOR)
def matricula_nova(request):
    if request.method == "POST":
        form = MatriculaForm(request.POST)
        if form.is_valid():
            turma = form.cleaned_data["turma"]
            try:
                matricula = services.matricular(form.cleaned_data["aluno"], turma)
            except services.MatriculaErro as erro:
                form.add_error(None, erro.message)
            else:
                if matricula.status == Matricula.Status.ATIVA:
                    messages.success(request, f"{matricula.aluno.nome} matriculado(a) em {turma.codigo}.")
                else:
                    messages.warning(
                        request,
                        f"Turma {turma.codigo} cheia: {matricula.aluno.nome} entrou na lista de "
                        f"espera (posição {services.posicao_na_fila(matricula)}).",
                    )
                return redirect("turmas:turma_detalhe", pk=turma.pk)
    else:
        form = MatriculaForm(initial={"turma": request.GET.get("turma"), "aluno": request.GET.get("aluno")})
    voltar = request.GET.get("voltar")
    if not url_has_allowed_host_and_scheme(voltar, allowed_hosts={request.get_host()}):
        voltar = reverse("matriculas:lista_espera")
    return render(
        request,
        "partials/form_pagina.html",
        {"form": form, "titulo": "Nova matrícula", "voltar_url": voltar},
    )


def _alterar(request, pk, operacao, mensagem):
    matricula = get_object_or_404(Matricula.objects.select_related("aluno", "turma"), pk=pk)
    try:
        _, promovidas = operacao(matricula)
    except services.MatriculaErro as erro:
        messages.error(request, erro.message)
    else:
        messages.success(request, mensagem.format(nome=matricula.aluno.nome))
        _avisar_promovidas(request, promovidas)
    destino = request.POST.get("next")
    if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect("turmas:turma_detalhe", pk=matricula.turma_id)


@require_POST
@perfil_requerido(PERFIL_ADMINISTRADOR)
def matricula_cancelar(request, pk):
    return _alterar(request, pk, services.cancelar, "Matrícula de {nome} cancelada.")


@require_POST
@perfil_requerido(PERFIL_ADMINISTRADOR)
def matricula_desistencia(request, pk):
    return _alterar(request, pk, services.registrar_desistencia, "Desistência de {nome} registrada.")


@perfil_requerido(PERFIL_ADMINISTRADOR)
def lista_espera(request):
    return render(request, "matriculas/lista_espera.html", {"filas": services.filas_de_espera()})


@perfil_requerido(PERFIL_ALUNO)
def minhas_matriculas(request):
    matriculas = list(services.matriculas_do_usuario(request.user))
    for matricula in matriculas:
        matricula.posicao = services.posicao_na_fila(matricula)
    return render(
        request,
        "matriculas/minhas_matriculas.html",
        {"matriculas": matriculas, "tem_cadastro": hasattr(request.user, "aluno")},
    )
