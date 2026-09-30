from decimal import Decimal

from django import forms

from apps.alunos.models import Aluno
from apps.contas.forms import EstiloTailwindMixin
from apps.contas.templatetags.formatos import reais
from apps.turmas.models import Turma


class TurmaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, turma):
        curso = turma.curso
        preco = "gratuito" if curso.gratuito else f"{reais(curso.valor_mensalidade)}/mês × {curso.duracao_meses}"
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
    desconto = forms.DecimalField(
        label="Desconto (%)", min_value=0, max_value=100, decimal_places=2, initial=0, required=False,
        help_text="Vale para todas as mensalidades. Bolsa: 100 deixa a matrícula isenta.",
    )

    def clean_desconto(self):
        valor = self.cleaned_data["desconto"]
        return Decimal("0") if valor is None else valor
