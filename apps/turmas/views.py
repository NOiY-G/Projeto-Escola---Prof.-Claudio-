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
            matriculas=turma.matriculas.select_related("aluno", "certificado")
            .exclude(status=Matricula.Status.LISTA_ESPERA)
            .order_by("status", "aluno__nome"),
            fila=matriculas_services.lista_espera(turma),
            frequencias=matriculas_services.resumo_frequencia(turma),
            total_aulas=turma.aulas.count(),
            aulas_realizadas=matriculas_services.aulas_realizadas(turma).count(),
            vagas_ocupadas=services.vagas_ocupadas(turma),
            vagas_livres=services.vagas_livres(turma),
            **kwargs,
        )


def _avisar_geracao(request, resultado):
    if resultado.criadas:
        n = len(resultado.criadas)
        messages.info(request, f"{n} aula{'s' if n > 1 else ''} gerada{'s' if n > 1 else ''} no calendário.")
    if resultado.removidas:
        n = len(resultado.removidas)
        messages.info(request, f"{n} aula{'s' if n > 1 else ''} fora do novo calendário removida{'s' if n > 1 else ''}.")
    if resultado.mantidas:
        datas = ", ".join(f"{a.data:%d/%m/%Y}" for a in resultado.mantidas)
        messages.warning(
            request,
            f"Aulas fora do novo calendário foram mantidas porque já têm chamada: {datas}.",
        )


class TurmaCreateView(AdminMixin, FormPaginaMixin, CreateView):
    model = Turma
    form_class = TurmaForm
    titulo = "Nova turma"
    mensagem = "Turma cadastrada."

    @property
    def voltar_url(self):
        return reverse("turmas:turma_lista")

    def form_valid(self, form):
        resposta = super().form_valid(form)
        _avisar_geracao(self.request, services.gerar_aulas(self.object))
        return resposta

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
        if services.calendario_mudou(form.changed_data):
            _avisar_geracao(self.request, services.gerar_aulas(self.object))
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
