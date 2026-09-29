from decimal import Decimal

from django import forms

from apps.alunos.models import Aluno
from apps.contas.forms import EstiloTailwindMixin
from apps.contas.templatetags.formatos import reais
from apps.turmas.models import Turma


class TurmaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, turma):
        preco = "gratuito" if turma.curso.gratuito else f"{reais(turma.curso.valor)} em até {turma.curso.parcelas_max}x"
        return f"{turma.codigo} – {turma.curso.nome} ({turma.horario_display}) – {preco}"


class MatriculaForm(EstiloTailwindMixin, forms.Form):
    aluno = forms.ModelChoiceField(label="Aluno", queryset=Aluno.objects.order_by("nome"))
    turma = TurmaChoiceField(
        label="Turma",
        queryset=Turma.objects.filter(status=Turma.Status.INSCRICOES_ABERTAS)
        .select_related("curso")
        .order_by("codigo"),
        help_text="Só aparecem turmas com inscrições abertas.",
    )
    n_parcelas = forms.IntegerField(
        label="Parcelas", min_value=1, max_value=12, initial=1, required=False,
        help_text="Até o máximo permitido pelo curso. Cursos gratuitos ignoram este campo.",
    )
    desconto = forms.DecimalField(
        label="Desconto (%)", min_value=0, max_value=100, decimal_places=2, initial=0, required=False,
        help_text="Bolsa: 100 deixa a matrícula isenta.",
    )

    def clean_n_parcelas(self):
        return self.cleaned_data["n_parcelas"] or 1

    def clean_desconto(self):
        valor = self.cleaned_data["desconto"]
        return Decimal("0") if valor is None else valor
