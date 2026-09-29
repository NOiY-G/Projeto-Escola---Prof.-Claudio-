from django import forms

from apps.contas.forms import DataInput, EstiloTailwindMixin

from .models import Aluno
from .validators import somente_digitos, validar_cpf


class AlunoForm(EstiloTailwindMixin, forms.ModelForm):
    # Aceita o CPF com pontuação; é guardado só com os dígitos.
    cpf = forms.CharField(label="CPF", max_length=14, help_text="Ex.: 123.456.789-09")

    class Meta:
        model = Aluno
        fields = [
            "nome",
            "cpf",
            "data_nascimento",
            "telefone",
            "email",
            "escolaridade",
            "endereco",
        ]
        widgets = {"data_nascimento": DataInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["cpf"] = self.instance.cpf_formatado
        self.fields["cpf"].widget.attrs["inputmode"] = "numeric"

    def clean_cpf(self):
        cpf = self.cleaned_data["cpf"]
        validar_cpf(cpf)
        return somente_digitos(cpf)
