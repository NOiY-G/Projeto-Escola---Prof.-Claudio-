from django import forms

from apps.catalogo.models import Curso
from apps.contas.forms import DataInput, EstiloTailwindMixin, HoraInput

from .models import DIAS_SEMANA, Feriado, Turma


class TurmaForm(EstiloTailwindMixin, forms.ModelForm):
    dias_semana = forms.MultipleChoiceField(
        label="Dias da semana", choices=DIAS_SEMANA, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Turma
        fields = [
            "codigo",
            "curso",
            "instrutor",
            "status",
            "data_inicio",
            "data_fim",
            "dias_semana",
            "hora_inicio",
            "hora_fim",
            "sala",
            "vagas",
        ]
        widgets = {
            "data_inicio": DataInput,
            "data_fim": DataInput,
            "hora_inicio": HoraInput,
            "hora_fim": HoraInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Só cursos ativos podem receber turmas novas (mantém o atual na edição).
        cursos = Curso.objects.filter(ativo=True)
        if self.instance.pk:
            cursos = cursos | Curso.objects.filter(pk=self.instance.curso_id)
            self.initial["dias_semana"] = self.instance.dias_semana_lista
        self.fields["curso"].queryset = cursos.distinct()

    def clean_dias_semana(self):
        # Guarda na ordem da semana, ex.: "seg,qua".
        escolhidos = set(self.cleaned_data["dias_semana"])
        return ",".join(codigo for codigo, _ in DIAS_SEMANA if codigo in escolhidos)


class FeriadoForm(EstiloTailwindMixin, forms.ModelForm):
    class Meta:
        model = Feriado
        fields = ["data", "descricao"]
        widgets = {"data": DataInput}
        labels = {"descricao": "Descrição"}
