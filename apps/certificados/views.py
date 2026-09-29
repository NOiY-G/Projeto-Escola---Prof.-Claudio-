from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.contas.decorators import perfil_requerido
from apps.contas.services import PERFIL_ADMINISTRADOR
from apps.matriculas.models import Matricula
from apps.turmas.models import Turma

from . import services
from .models import Certificado


@perfil_requerido(PERFIL_ADMINISTRADOR)
def concluir_turma(request, turma_pk):
    """GET mostra a prévia (quem conclui, quem fica como desistente); POST conclui."""
    turma = get_object_or_404(Turma.objects.select_related("curso"), pk=turma_pk)
    if request.method == "POST":
        try:
            resultado = services.concluir_turma(turma)
        except services.CertificadoErro as erro:
            messages.error(request, erro.message)
        else:
            messages.success(
                request,
                f"Turma {turma.codigo} concluída: {len(resultado.concluidas)} aluno(s) concluíram e "
                f"receberam certificado, {len(resultado.desistentes)} ficaram como desistentes.",
            )
            if resultado.espera_canceladas:
                messages.info(
                    request,
                    f"{len(resultado.espera_canceladas)} matrícula(s) da lista de espera foram canceladas.",
                )
        return redirect("turmas:turma_detalhe", pk=turma.pk)

    erro = None
    try:
        services.verificar_conclusao(turma)
    except services.CertificadoErro as e:
        erro = e.message
    return render(
        request,
        "certificados/concluir_turma.html",
        {
            "turma": turma,
            "linhas": services.previa_conclusao(turma) if not erro else [],
            "erro": erro,
            "na_fila": turma.matriculas.filter(status=Matricula.Status.LISTA_ESPERA).count(),
        },
    )


@perfil_requerido(PERFIL_ADMINISTRADOR)
def lista(request):
    return render(
        request,
        "certificados/lista.html",
        {
            "pendentes": services.concluidas_sem_certificado(),
            "certificados": Certificado.objects.select_related(
                "matricula__aluno", "matricula__turma__curso"
            )[:50],
        },
    )


@require_POST
@perfil_requerido(PERFIL_ADMINISTRADOR)
def emitir(request, matricula_pk):
    matricula = get_object_or_404(Matricula.objects.select_related("aluno"), pk=matricula_pk)
    try:
        services.emitir_certificado(matricula)
    except services.CertificadoErro as erro:
        messages.error(request, erro.message)
    else:
        messages.success(request, f"Certificado de {matricula.aluno.nome} emitido.")
    return redirect("certificados:lista")


@login_required
def baixar_pdf(request, codigo):
    certificado = services.buscar_por_codigo(codigo)
    # Quem não pode baixar recebe 404, para não revelar que o código existe.
    if certificado is None or not services.pode_baixar(request.user, certificado):
        raise Http404
    url_validacao = request.build_absolute_uri(
        reverse("certificados:validar", args=[certificado.codigo_validacao])
    )
    pdf = services.gerar_pdf(certificado, url_validacao)
    resposta = HttpResponse(pdf, content_type="application/pdf")
    nome = f"certificado-{certificado.matricula.turma.codigo}-{certificado.codigo_validacao.hex[:8]}.pdf"
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


def validar(request, codigo=None):
    """Página pública (regra 7): diz se o certificado é válido e mostra dados básicos."""
    codigo = codigo or request.GET.get("codigo", "").strip()
    if not codigo:
        return render(request, "certificados/validar.html", {"consultado": False})
    certificado = services.buscar_por_codigo(codigo)
    contexto = {
        "consultado": True,
        "codigo": codigo,
        "valido": certificado is not None,
        "dados": services.dados_do_certificado(certificado) if certificado else None,
    }
    return render(request, "certificados/validar.html", contexto, status=200 if certificado else 404)


def validar_redireciona(request):
    """Formulário da página de validação envia ?codigo=...; leva à URL canônica."""
    codigo = request.GET.get("codigo", "").strip()
    if codigo:
        return redirect("certificados:validar", codigo=codigo)
    return validar(request)
