from django.conf import settings
from django.db import models

from .validators import formatar_cpf, somente_digitos, validar_cpf


class Aluno(models.Model):
    class Escolaridade(models.TextChoices):
        FUNDAMENTAL_INCOMPLETO = "fund_inc", "Fundamental incompleto"
        FUNDAMENTAL_COMPLETO = "fund_comp", "Fundamental completo"
        MEDIO_INCOMPLETO = "medio_inc", "Médio incompleto"
        MEDIO_COMPLETO = "medio_comp", "Médio completo"
        SUPERIOR_INCOMPLETO = "sup_inc", "Superior incompleto"
        SUPERIOR_COMPLETO = "sup_comp", "Superior completo"

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aluno",
        verbose_name="usuário",
    )
    nome = models.CharField("nome", max_length=150)
    cpf = models.CharField(
        "CPF", max_length=11, unique=True, validators=[validar_cpf], help_text="Somente números"
    )
    data_nascimento = models.DateField("data de nascimento")
    telefone = models.CharField("telefone", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    endereco = models.CharField("endereço", max_length=255, blank=True)
    escolaridade = models.CharField(
        "escolaridade", max_length=12, choices=Escolaridade.choices, blank=True
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "aluno"
        verbose_name_plural = "alunos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        # CPF sempre guardado só com dígitos, para a unicidade funcionar.
        self.cpf = somente_digitos(self.cpf)
        super().save(*args, **kwargs)

    @property
    def cpf_formatado(self):
        return formatar_cpf(self.cpf)
