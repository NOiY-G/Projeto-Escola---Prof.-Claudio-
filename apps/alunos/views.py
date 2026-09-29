from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.catalogo.views import AdminMixin, FormPaginaMixin
from apps.financeiro import services as financeiro

from . import services
from .forms import AlunoForm
from .models import Aluno


class AlunoListView(AdminMixin, ListView):
    template_name = "alunos/aluno_lista.html"
    paginate_by = 20

    def get_queryset(self):
        return services.buscar_alunos(self.request.GET.get("q"))

    def get_template_names(self):
        # Na busca com HTMX devolvemos só a lista de resultados.
        cabecalhos = self.request.headers
        if cabecalhos.get("HX-Request") and not cabecalhos.get("HX-History-Restore-Request"):
            return ["alunos/_aluno_resultados.html"]
        return [self.template_name]


class AlunoDetailView(AdminMixin, DetailView):
    model = Aluno
    template_name = "alunos/aluno_detalhe.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            historico=services.historico_do_aluno(self.object),
            financeiro=financeiro.resumo_do_aluno(self.object),
            hoje=timezone.localdate(),
            **kwargs,
        )


class AlunoCreateView(AdminMixin, FormPaginaMixin, CreateView):
    model = Aluno
    form_class = AlunoForm
    titulo = "Novo aluno"
    mensagem = "Aluno cadastrado."

    @property
    def voltar_url(self):
        return reverse("alunos:aluno_lista")

    def get_success_url(self):
        return reverse("alunos:aluno_detalhe", args=[self.object.pk])


class AlunoUpdateView(AdminMixin, FormPaginaMixin, UpdateView):
    model = Aluno
    form_class = AlunoForm
    mensagem = "Aluno atualizado."

    @property
    def titulo(self):
        return f"Editar aluno: {self.object.nome}"

    @property
    def voltar_url(self):
        return reverse("alunos:aluno_detalhe", args=[self.object.pk])

    def get_success_url(self):
        return reverse("alunos:aluno_detalhe", args=[self.object.pk])
