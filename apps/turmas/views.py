from django.contrib import messages
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.catalogo.models import Curso
from apps.catalogo.views import AdminMixin, FormPaginaMixin
from apps.contas.decorators import PerfilRequeridoMixin
from apps.contas.services import PERFIL_ADMINISTRADOR, PERFIL_INSTRUTOR

from apps.matriculas import services as matriculas_services
from apps.matriculas.models import Matricula

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
            matriculas=turma.matriculas.select_related("aluno")
            .exclude(status=Matricula.Status.LISTA_ESPERA)
            .order_by("status", "aluno__nome"),
            fila=matriculas_services.lista_espera(turma),
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

    def form_valid(self, form):
        resposta = super().form_valid(form)
        # Mais vagas (ou reabertura da turma) chamam os primeiros da fila.
        for matricula in matriculas_services.preencher_vagas(self.object):
            messages.info(
                self.request,
                f"{matricula.aluno.nome} saiu da lista de espera e agora está com matrícula ativa.",
            )
        return resposta

    @property
    def voltar_url(self):
        return reverse("turmas:turma_detalhe", args=[self.object.pk])

    def get_success_url(self):
        return reverse("turmas:turma_detalhe", args=[self.object.pk])
