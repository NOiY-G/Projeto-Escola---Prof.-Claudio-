from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.contas.decorators import PerfilRequeridoMixin, perfil_requerido
from apps.contas.services import PERFIL_ADMINISTRADOR

from . import services
from .forms import CursoForm, InstrutorForm, NovoInstrutorForm
from .models import Curso, Instrutor


class AdminMixin(PerfilRequeridoMixin):
    perfis = (PERFIL_ADMINISTRADOR,)


class FormPaginaMixin:
    template_name = "partials/form_pagina.html"
    titulo = ""
    voltar_url = None
    mensagem = "Salvo com sucesso."

    def get_context_data(self, **kwargs):
        return super().get_context_data(titulo=self.titulo, voltar_url=self.voltar_url, **kwargs)

    def form_valid(self, form):
        resposta = super().form_valid(form)
        messages.success(self.request, self.mensagem)
        return resposta


# Cursos


class CursoListView(AdminMixin, ListView):
    model = Curso
    template_name = "catalogo/curso_lista.html"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Curso.objects.annotate(total_turmas=Count("turmas"))
            .prefetch_related("pre_requisitos")
            .order_by("nome")
        )
        situacao = self.request.GET.get("situacao")
        if situacao == "ativos":
            qs = qs.filter(ativo=True)
        elif situacao == "inativos":
            qs = qs.filter(ativo=False)
        busca = self.request.GET.get("q", "").strip()
        if busca:
            qs = qs.filter(nome__icontains=busca)
        return qs


class CursoCreateView(AdminMixin, FormPaginaMixin, CreateView):
    model = Curso
    form_class = CursoForm
    template_name = "catalogo/curso_form.html"
    titulo = "Novo curso"
    voltar_url = reverse_lazy("catalogo:curso_lista")
    success_url = reverse_lazy("catalogo:curso_lista")
    mensagem = "Curso cadastrado."


class CursoUpdateView(AdminMixin, FormPaginaMixin, UpdateView):
    model = Curso
    form_class = CursoForm
    template_name = "catalogo/curso_form.html"
    voltar_url = reverse_lazy("catalogo:curso_lista")
    success_url = reverse_lazy("catalogo:curso_lista")
    mensagem = "Curso atualizado."

    @property
    def titulo(self):
        return f"Editar curso: {self.object.nome}"


def _numero(valor, tipo):
    try:
        numero = tipo(str(valor).replace(",", "."))
    except (ArithmeticError, ValueError):
        return None
    return numero if numero > 0 else None


@perfil_requerido(PERFIL_ADMINISTRADOR)
def curso_calculo(request):
    """Prévia (HTMX) da carga horária enquanto o curso é preenchido."""
    meses = _numero(request.GET.get("duracao_meses"), int)
    dias = _numero(request.GET.get("dias_por_semana"), int)
    horas = _numero(request.GET.get("horas_por_aula"), Decimal)
    calculo = None
    if meses and dias and horas and meses <= 36 and dias <= 6 and horas <= 12:
        calculo = services.calcular(meses, dias, horas)
    return render(request, "catalogo/_calculo.html", {"calculo": calculo})


@require_POST
@perfil_requerido(PERFIL_ADMINISTRADOR)
def curso_alternar_ativo(request, pk):
    curso = services.alternar_ativo(get_object_or_404(Curso, pk=pk))
    if request.headers.get("HX-Request"):
        return render(request, "catalogo/_curso_situacao.html", {"curso": curso})
    messages.success(request, f"Curso {'ativado' if curso.ativo else 'desativado'}.")
    return redirect("catalogo:curso_lista")


# Instrutores


class InstrutorListView(AdminMixin, ListView):
    model = Instrutor
    template_name = "catalogo/instrutor_lista.html"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Instrutor.objects.select_related("usuario")
            .annotate(total_turmas=Count("turmas"))
            .order_by("nome")
        )
        busca = self.request.GET.get("q", "").strip()
        if busca:
            qs = qs.filter(Q(nome__icontains=busca) | Q(especialidades__icontains=busca))
        return qs


class InstrutorCreateView(AdminMixin, FormPaginaMixin, CreateView):
    model = Instrutor
    form_class = NovoInstrutorForm
    titulo = "Novo instrutor"
    voltar_url = reverse_lazy("catalogo:instrutor_lista")

    def form_valid(self, form):
        dados = form.cleaned_data
        services.criar_instrutor(
            username=dados["username"],
            email=dados["email"],
            senha=dados["senha"],
            nome=dados["nome"],
            telefone=dados["telefone"],
            especialidades=dados["especialidades"],
        )
        messages.success(self.request, "Instrutor cadastrado.")
        return redirect("catalogo:instrutor_lista")


class InstrutorUpdateView(AdminMixin, FormPaginaMixin, UpdateView):
    model = Instrutor
    form_class = InstrutorForm
    voltar_url = reverse_lazy("catalogo:instrutor_lista")

    @property
    def titulo(self):
        return f"Editar instrutor: {self.object.nome}"

    def form_valid(self, form):
        services.atualizar_instrutor(form.instance, email=form.cleaned_data["email"])
        messages.success(self.request, "Instrutor atualizado.")
        return redirect(reverse("catalogo:instrutor_lista"))
