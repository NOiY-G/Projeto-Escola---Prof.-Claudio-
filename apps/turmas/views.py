from django.contrib import messages
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.catalogo.models import Curso
from apps.catalogo.views import AdminMixin, FormPaginaMixin
from apps.contas.decorators import PerfilRequeridoMixin
from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR

from . import services
from .forms import TurmaForm
from .models import Turma


class AdminOuInstrutorMixin(PerfilRequeridoMixin):
    perfis = (PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR)


class TurmaListView(AdminOuInstrutorMixin, ListView):
    template_name = "turmas/turma_lista.html"
    paginate_by = 20

    def get_queryset(self):
        return services.filtrar_turmas(
            services.turmas_visiveis_para(self.request.user),
            status=self.request.GET.get("status"),
            curso_id=self.request.GET.get("curso") or None,
            busca=self.request.GET.get("q", "").strip(),
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            status_opcoes=Turma.Status.choices, cursos=Curso.objects.all(), **kwargs
        )


class TurmaDetailView(AdminOuInstrutorMixin, DetailView):
    template_name = "turmas/turma_detalhe.html"

    def get_queryset(self):
        return services.turmas_visiveis_para(self.request.user)

    def get_context_data(self, **kwargs):
        turma = self.object
        return super().get_context_data(
            matriculas=turma.matriculas.select_related("aluno").order_by("status", "aluno__nome"),
            vagas_ocupadas=services.vagas_ocupadas(turma),
            vagas_livres=services.vagas_livres(turma),
            **kwargs,
        )


class TurmaCreateView(AdminMixin, FormPaginaMixin, CreateView):
    model = Turma
    form_class = TurmaForm
    titulo = "Nova turma"
    mensagem = "Turma cadastrada."

    @property
    def voltar_url(self):
        return reverse("turmas:turma_lista")

    def get_success_url(self):
        return reverse("turmas:turma_detalhe", args=[self.object.pk])


class TurmaUpdateView(AdminMixin, FormPaginaMixin, UpdateView):
    model = Turma
    form_class = TurmaForm
    mensagem = "Turma atualizada."

    @property
    def titulo(self):
        return f"Editar turma {self.object.codigo}"

    @property
    def voltar_url(self):
        return reverse("turmas:turma_detalhe", args=[self.object.pk])

    def get_success_url(self):
        return reverse("turmas:turma_detalhe", args=[self.object.pk])
