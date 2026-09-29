from django import forms

from apps.alunos.models import Aluno
from apps.contas.forms import EstiloTailwindMixin
from apps.turmas.models import Turma


class TurmaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, turma):
        return f"{turma.codigo} – {turma.curso.nome} ({turma.horario_display})"


class MatriculaForm(EstiloTailwindMixin, forms.Form):
    aluno = forms.ModelChoiceField(label="Aluno", queryset=Aluno.objects.order_by("nome"))
    turma = TurmaChoiceField(
        label="Turma",
        queryset=Turma.objects.filter(status=Turma.Status.INSCRICOES_ABERTAS)
        .select_related("curso")
        .order_by("codigo"),
        help_text="Só aparecem turmas com inscrições abertas.",
    )
