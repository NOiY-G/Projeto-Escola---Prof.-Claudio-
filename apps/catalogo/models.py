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
    duracao_meses = models.PositiveSmallIntegerField(
        "duração (meses)",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(36)],
        help_text="Tempo total do curso. Também é o número de mensalidades.",
    )
    horas_por_aula = models.DecimalField(
        "duração da aula (h)",
        max_digits=4,
        decimal_places=2,
        default=Decimal("2"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("12"))],
        help_text="Ex.: 2 ou 1,5",
    )
    pre_requisitos = models.TextField("pré-requisitos", blank=True)
    valor_mensalidade = models.DecimalField(
        "mensalidade (R$)",
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
            models.CheckConstraint(
                condition=models.Q(valor_mensalidade__gte=0), name="curso_mensalidade_nao_negativa"
            ),
            models.CheckConstraint(condition=models.Q(duracao_meses__gt=0), name="curso_duracao_positiva"),
            models.CheckConstraint(condition=models.Q(horas_por_aula__gt=0), name="curso_aula_positiva"),
            models.CheckConstraint(
                condition=models.Q(frequencia_minima__lte=100), name="curso_frequencia_minima_ate_100"
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def gratuito(self):
        return self.valor_mensalidade == 0

    @property
    def planejamento(self):
        from .services import planejamento_do_curso

        return planejamento_do_curso(self)

    @property
    def dias_minimos(self):
        """Mínimo de dias de aula por semana para cumprir a carga horária."""
        return self.planejamento.dias_minimos

    @property
    def valor_total(self):
        """Todas as mensalidades, sem desconto."""
        return self.valor_mensalidade * self.duracao_meses


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
