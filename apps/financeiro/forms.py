from django import forms
from django.utils import timezone

from apps.contas.forms import DataInput, EstiloTailwindMixin

from .models import Pagamento


class PagamentoForm(EstiloTailwindMixin, forms.Form):
    forma = forms.ChoiceField(label="Forma", choices=Pagamento.Forma.choices, widget=forms.RadioSelect)
    data = forms.DateField(label="Data do pagamento", widget=DataInput)
    codigo_transacao = forms.CharField(
        label="Código da transação Pix", max_length=64, required=False,
        help_text="Opcional. O ID do comprovante do banco; evita lançar o mesmo Pix duas vezes.",
    )
    observacao = forms.CharField(label="Observação", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data"].initial = timezone.localdate()
        self.fields["forma"].widget.attrs["class"] = "h-4 w-4"


class AprovarComprovanteForm(EstiloTailwindMixin, forms.Form):
    data = forms.DateField(label="Data do Pix (no extrato)", widget=DataInput)
    codigo_transacao = forms.CharField(label="Código da transação Pix", max_length=64, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data"].initial = timezone.localdate()


class MotivoForm(EstiloTailwindMixin, forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=200)


class ComprovanteForm(forms.Form):
    arquivo = forms.FileField(
        label="Comprovante (foto ou PDF, até 5 MB)",
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf"}),
    )
