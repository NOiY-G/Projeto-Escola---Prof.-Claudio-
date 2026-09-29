from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Curso(models.Model):
    nome = models.CharField("nome", max_length=120, unique=True)
    descricao = models.TextField("descrição", blank=True)
    carga_horaria = models.PositiveIntegerField(
        "carga horária (h)", validators=[MinValueValidator(1)]
    )
    pre_requisitos = models.TextField("pré-requisitos", blank=True)
    valor = models.DecimalField(
        "valor (R$)",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="0 = gratuito",
    )
    frequencia_minima = models.PositiveSmallIntegerField(
        "frequência mínima (%)",
        default=75,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    parcelas_max = models.PositiveSmallIntegerField(
        "máximo de parcelas",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="1 = só à vista",
    )
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["nome"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(carga_horaria__gt=0), name="curso_carga_horaria_positiva"
            ),
            models.CheckConstraint(condition=models.Q(valor__gte=0), name="curso_valor_nao_negativo"),
            models.CheckConstraint(
                condition=models.Q(frequencia_minima__lte=100), name="curso_frequencia_minima_ate_100"
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def gratuito(self):
        return self.valor == 0


class Instrutor(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="instrutor",
        verbose_name="usuário",
    )
    nome = models.CharField("nome", max_length=150)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    especialidades = models.TextField("especialidades", blank=True)

    class Meta:
        verbose_name = "instrutor"
        verbose_name_plural = "instrutores"
        ordering = ["nome"]

    def __str__(self):
        return self.nome
