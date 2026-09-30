from django.conf import settings
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.alunos.models import Aluno
from apps.contas.decorators import perfil_requerido
from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_ALUNO, PERFIL_INSTRUTOR
from apps.financeiro import services as financeiro
from apps.financeiro.forms import ComprovanteForm
from apps.turmas import services as turmas_services
from apps.turmas.models import Turma

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
                matricula = services.matricular(
                    form.cleaned_data["aluno"],
                    turma,
                    desconto=form.cleaned_data["desconto"],
                    pre_requisito_outra_escola=form.cleaned_data["pre_requisito_outra_escola"],
                )
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
        "matriculas/matricula_form.html",
        {"form": form, "titulo": "Nova matrícula", "voltar_url": voltar},
    )


@perfil_requerido(PERFIL_ADMINISTRADOR)
def matricula_resumo_turma(request):
    """Prévia (HTMX): carga horária, mínimo de dias por semana e mensalidades da turma escolhida."""
    turma_id = request.GET.get("turma", "")
    turma = (
        Turma.objects.select_related("curso", "instrutor").filter(pk=turma_id).first()
        if turma_id.isdigit()
        else None
    )
    aluno_id = request.GET.get("aluno", "")
    aluno = Aluno.objects.filter(pk=aluno_id).first() if aluno_id.isdigit() else None
    contexto = {"turma": turma, "aluno": aluno}
    if turma:
        contexto.update(
            pre_requisitos=list(turma.curso.pre_requisitos.order_by("nome")),
            pendentes=services.pre_requisitos_pendentes(aluno, turma.curso) if aluno else None,
            carga=turmas_services.carga_da_turma(turma),
            vencimentos=financeiro.vencimentos_das_mensalidades(turma),
        )
    return render(request, "matriculas/_resumo_turma.html", contexto)


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
        matricula.percentual = services.percentual_frequencia(matricula)
        matricula.lista_parcelas = financeiro.parcelas_do_aluno(matricula)
        matricula.situacao = financeiro.situacao_das_parcelas(matricula.lista_parcelas)
    return render(
        request,
        "matriculas/minhas_matriculas.html",
        {
            "matriculas": matriculas,
            "tem_cadastro": hasattr(request.user, "aluno"),
            "hoje": timezone.localdate(),
            "pix_nome": settings.PIX_NOME_RECEBEDOR,
            "form_comprovante": ComprovanteForm(),
        },
    )


# Chamada


def _turma_da_chamada(request, turma_pk):
    """Administrador abre qualquer turma; instrutor, só as próprias (senão 404)."""
    return get_object_or_404(turmas_services.turmas_visiveis_para(request.user), pk=turma_pk)


@perfil_requerido(PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR)
def chamada_inicio(request, turma_pk):
    turma = _turma_da_chamada(request, turma_pk)
    aula = services.aula_padrao(turma)
    if aula is None:
        messages.warning(request, "Esta turma ainda não tem aulas no calendário.")
        return redirect("turmas:turma_detalhe", pk=turma.pk)
    return redirect("matriculas:chamada", turma_pk=turma.pk, aula_pk=aula.pk)


@perfil_requerido(PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR)
def chamada(request, turma_pk, aula_pk):
    turma = _turma_da_chamada(request, turma_pk)
    aula = get_object_or_404(turma.aulas, pk=aula_pk)
    erro = None
    salva = False

    if request.method == "POST":
        observacoes = {
            chave.removeprefix("obs_"): valor
            for chave, valor in request.POST.items()
            if chave.startswith("obs_") and chave.removeprefix("obs_").isdigit()
        }
        try:
            services.registrar_chamada(
                aula,
                presentes=[pk for pk in request.POST.getlist("presente") if pk.isdigit()],
                observacoes=observacoes,
                conteudo=request.POST.get("conteudo", ""),
            )
        except services.MatriculaErro as e:
            erro = e.message
        else:
            salva = True
            if not request.headers.get("HX-Request"):
                messages.success(request, f"Chamada de {aula.data:%d/%m/%Y} salva.")
                return redirect("matriculas:chamada", turma_pk=turma.pk, aula_pk=aula.pk)
        aula.refresh_from_db()

    contexto = {
        "turma": turma,
        "aula": aula,
        "aulas": turma.aulas.annotate(registros=Count("frequencias")),
        "linhas": services.chamada_da_aula(aula),
        "situacoes": financeiro.situacoes(turma.matriculas.all()),
        "frequencias": services.resumo_frequencia(turma),
        "hoje": timezone.localdate(),
        "chamada_feita": aula.frequencias.exists(),
        "encerrada": turma.status in (Turma.Status.CONCLUIDA, Turma.Status.CANCELADA),
        "erro": erro,
        "salva": salva,
    }
    if request.headers.get("HX-Request"):
        return render(request, "matriculas/_chamada_form.html", contexto)
    return render(request, "matriculas/chamada.html", contexto)
