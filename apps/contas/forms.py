from django import forms

_CLASSE_CAMPO = "mt-1 w-full rounded border border-slate-300 px-3 py-2"
_CLASSE_CHECKBOX = "h-4 w-4 rounded border-slate-300"


class DataInput(forms.DateInput):
    """Campo de data com seletor nativo (bom no celular)."""

    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


class HoraInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%H:%M")


class EstiloTailwindMixin:
    """Aplica as classes do Tailwind aos widgets do formulário."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                widget.attrs.setdefault("class", _CLASSE_CHECKBOX)
            else:
                widget.attrs.setdefault("class", _CLASSE_CAMPO)
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)
