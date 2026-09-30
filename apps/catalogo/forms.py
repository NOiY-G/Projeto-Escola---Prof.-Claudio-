from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from apps.contas.forms import EstiloTailwindMixin

from .models import Curso, Instrutor
from .services import validar_planejamento


class CursoForm(EstiloTailwindMixin, forms.ModelForm):
    class Meta:
        model = Curso
        fields = [
            "nome",
            "descricao",
            "pre_requisitos",
            "valor_mensalidade",
            "frequencia_minima",
            "ativo",
            # Por último, logo acima da prévia dos dias mínimos por semana.
            "carga_horaria",
            "duracao_meses",
            "horas_por_aula",
        ]
        widgets = {
            "descricao": forms.Textarea,
            "pre_requisitos": forms.Textarea,
            "horas_por_aula": forms.NumberInput(attrs={"step": "0.5"}),
        }
        help_texts = {"carga_horaria": "Total de horas que o aluno precisa cumprir."}

    def clean(self):
        dados = super().clean()
        carga, meses, horas = (dados.get(c) for c in ("carga_horaria", "duracao_meses", "horas_por_aula"))
        if carga and meses and horas and not self.has_error("carga_horaria"):
            erro = validar_planejamento(carga, meses, horas)
            if erro:
                self.add_error("carga_horaria", erro)
        return dados


class InstrutorForm(EstiloTailwindMixin, forms.ModelForm):
    email = forms.EmailField(label="E-mail")

    class Meta:
        model = Instrutor
        fields = ["nome", "email", "telefone", "especialidades"]
        widgets = {"especialidades": forms.Textarea}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["email"].initial = self.instance.usuario.email


class NovoInstrutorForm(InstrutorForm):
    username = forms.CharField(label="Usuário de acesso", max_length=150)
    senha = forms.CharField(label="Senha inicial", widget=forms.PasswordInput)

    class Meta(InstrutorForm.Meta):
        fields = ["nome", "email", "username", "senha", "telefone", "especialidades"]

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Já existe um usuário com esse nome.")
        return username

    def clean_senha(self):
        senha = self.cleaned_data["senha"]
        validate_password(senha)
        return senha

    def _post_clean(self):
        # O usuário ainda não existe; a validação do modelo fica para o service.
        pass
