from django import forms

from apps.catalogo.models import Curso
from apps.contas.forms import DataInput, EstiloTailwindMixin, HoraInput

from .models import DIAS_SEMANA, Feriado, Turma
from .services import data_fim_sugerida


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
        self.fields["data_fim"].required = False
        self.fields["data_fim"].help_text = "Em branco: calculada pela duração do curso."

    def clean(self):
        dados = super().clean()
        if not dados.get("data_fim") and dados.get("curso") and dados.get("data_inicio"):
            dados["data_fim"] = data_fim_sugerida(dados["curso"], dados["data_inicio"])
        elif not dados.get("data_fim") and not self.has_error("data_fim"):
            self.add_error("data_fim", "Informe a data de término.")
        return dados

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
