from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from apps.contas.forms import EstiloTailwindMixin

from .models import Curso, Instrutor
from .services import validar_pre_requisitos


class CursoForm(EstiloTailwindMixin, forms.ModelForm):
    class Meta:
        model = Curso
        fields = [
            "nome",
            "valor_mensalidade",
            "frequencia_minima",
            "pre_requisitos",
            "aceita_outra_escola",
            "ativo",
            # Por último, logo acima do cálculo da carga horária.
            "duracao_meses",
            "dias_por_semana",
            "horas_por_aula",
        ]
        widgets = {
            "pre_requisitos": forms.CheckboxSelectMultiple,
            "dias_por_semana": forms.Select(
                choices=[(n, f"{n} dia{'s' if n > 1 else ''} por semana") for n in range(1, 7)]
            ),
            "horas_por_aula": forms.NumberInput(attrs={"step": "0.25"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cursos = Curso.objects.order_by("nome")
        if self.instance.pk:
            cursos = cursos.exclude(pk=self.instance.pk)
        self.fields["pre_requisitos"].queryset = cursos
        self.fields["pre_requisitos"].help_text = (
            "Cursos já cadastrados que o aluno precisa ter concluído. Deixe em branco se não houver."
        )

    def clean_pre_requisitos(self):
        escolhidos = self.cleaned_data["pre_requisitos"]
        erro = validar_pre_requisitos(self.instance, escolhidos)
        if erro:
            raise forms.ValidationError(erro)
        return escolhidos


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
