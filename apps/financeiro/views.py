from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.contas.decorators import perfil_requerido
from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_ALUNO
from apps.contas.templatetags.formatos import reais

from . import services
from .forms import AprovarComprovanteForm, ComprovanteForm, MotivoForm, PagamentoForm
from .models import Comprovante, Pagamento, Parcela


def _voltar(request, padrao):
    destino = request.POST.get("next") or request.GET.get("next")
    if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return padrao


@perfil_requerido(PERFIL_ADMINISTRADOR)
def pagamentos(request):
    em_analise = Parcela.objects.filter(status=Parcela.Status.EM_ANALISE).count()
    filtro = request.GET.get("ver") or ("comprovantes" if em_analise else "vencidas")
    if filtro not in services.FILTROS:
        filtro = "abertas"
    parcelas = list(services.parcelas_filtradas(filtro, request.GET.get("q", ""))[:200])
    situacoes = services.situacoes({p.matricula for p in parcelas})
    for parcela in parcelas:
        parcela.situacao = situacoes[parcela.matricula_id]
    return render(
        request,
        "financeiro/pagamentos.html",
        {
            "filtro": filtro,
            "filtros": services.FILTROS,
            "parcelas": parcelas,
            "em_analise": em_analise,
            "hoje": timezone.localdate(),
        },
    )


@perfil_requerido(PERFIL_ADMINISTRADOR)
def registrar(request, parcela_pk):
    parcela = get_object_or_404(
        Parcela.objects.select_related("matricula__aluno", "matricula__turma__curso"), pk=parcela_pk
    )
    voltar = _voltar(request, reverse("financeiro:pagamentos"))
    form = PagamentoForm(request.POST or None, initial={"forma": Pagamento.Forma.PIX})
    if request.method == "POST" and form.is_valid():
        try:
            pagamento = services.registrar_pagamento(
                parcela, recebido_por=request.user, **form.cleaned_data
            )
        except services.FinanceiroErro as erro:
            form.add_error(None, erro.message)
        else:
            messages.success(
                request,
                f"Pagamento de {reais(parcela.valor)} ({pagamento.get_forma_display()}) registrado para "
                f"{parcela.matricula.aluno.nome}.",
            )
            return redirect(voltar)
    return render(
        request,
        "financeiro/registrar.html",
        {"form": form, "parcela": parcela, "voltar_url": voltar},
    )


@perfil_requerido(PERFIL_ADMINISTRADOR)
def conferir(request, comprovante_pk):
    comprovante = get_object_or_404(
        Comprovante.objects.select_related("parcela__matricula__aluno", "parcela__matricula__turma__curso"),
        pk=comprovante_pk,
    )
    aprovar = AprovarComprovanteForm(request.POST if request.POST.get("acao") == "aprovar" else None)
    recusar = MotivoForm(request.POST if request.POST.get("acao") == "recusar" else None)
    if request.method == "POST":
        try:
            if request.POST.get("acao") == "aprovar" and aprovar.is_valid():
                services.aprovar_comprovante(comprovante, usuario=request.user, **aprovar.cleaned_data)
                messages.success(request, f"Pagamento de {comprovante.parcela.matricula.aluno.nome} confirmado.")
                return redirect(f"{reverse('financeiro:pagamentos')}?ver=comprovantes")
            if request.POST.get("acao") == "recusar" and recusar.is_valid():
                services.recusar_comprovante(comprovante, usuario=request.user, **recusar.cleaned_data)
                messages.info(request, "Comprovante recusado; o aluno vai ver o motivo.")
                return redirect(f"{reverse('financeiro:pagamentos')}?ver=comprovantes")
        except services.FinanceiroErro as erro:
            messages.error(request, erro.message)
    return render(
        request,
        "financeiro/conferir.html",
        {"comprovante": comprovante, "parcela": comprovante.parcela, "aprovar": aprovar, "recusar": recusar},
    )


@login_required
def arquivo_comprovante(request, comprovante_pk):
    comprovante = get_object_or_404(Comprovante.objects.select_related("parcela__matricula__aluno"), pk=comprovante_pk)
    # Quem não pode ver recebe 404, para não revelar que o arquivo existe.
    if not services.pode_ver_matricula(request.user, comprovante.parcela.matricula):
        raise Http404
    resposta = FileResponse(comprovante.arquivo.open("rb"), content_type=comprovante.tipo_conteudo)
    extensao = {"image/png": "png", "image/jpeg": "jpg", "application/pdf": "pdf"}[comprovante.tipo_conteudo]
    resposta["Content-Disposition"] = f'inline; filename="comprovante-{comprovante.pk}.{extensao}"'
    resposta["Cache-Control"] = "private, no-store"
    return resposta


@require_POST
@perfil_requerido(PERFIL_ALUNO)
def enviar_comprovante(request, parcela_pk):
    parcela = get_object_or_404(Parcela.objects.select_related("matricula__aluno"), pk=parcela_pk)
    if not services.pode_ver_matricula(request.user, parcela.matricula):
        raise Http404
    form = ComprovanteForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Escolha o arquivo do comprovante.")
    else:
        try:
            services.enviar_comprovante(parcela, form.cleaned_data["arquivo"], request.user)
        except services.FinanceiroErro as erro:
            messages.error(request, erro.message)
        else:
            messages.success(request, "Comprovante enviado! A secretaria vai conferir o pagamento.")
    return redirect("matriculas:minhas_matriculas")


@require_POST
@perfil_requerido(PERFIL_ADMINISTRADOR)
def estornar(request, pagamento_pk):
    pagamento = get_object_or_404(Pagamento.objects.select_related("parcela__matricula__aluno"), pk=pagamento_pk)
    form = MotivoForm(request.POST)
    try:
        if not form.is_valid():
            raise services.FinanceiroErro("Informe o motivo do estorno.")
        services.estornar_pagamento(pagamento, motivo=form.cleaned_data["motivo"], usuario=request.user)
    except services.FinanceiroErro as erro:
        messages.error(request, erro.message)
    else:
        messages.success(request, "Pagamento estornado; a parcela voltou a ficar em aberto.")
    return redirect(_voltar(request, reverse("alunos:aluno_detalhe", args=[pagamento.parcela.matricula.aluno_id])))


@login_required
def recibo(request, pagamento_pk):
    pagamento = get_object_or_404(
        Pagamento.objects.select_related("parcela__matricula__aluno", "parcela__matricula__turma__curso"),
        pk=pagamento_pk,
        estornado_em__isnull=True,
    )
    if not services.pode_ver_matricula(request.user, pagamento.parcela.matricula):
        raise Http404
    resposta = HttpResponse(services.gerar_recibo_pdf(pagamento), content_type="application/pdf")
    resposta["Content-Disposition"] = f'attachment; filename="recibo-{pagamento.pk}.pdf"'
    return resposta
