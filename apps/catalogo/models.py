from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def validar_quarto_de_hora(valor):
    """A duração da aula anda de 15 em 15 minutos (1; 1,25; 1,5...), para a carga dar horas inteiras."""
    if (Decimal(valor) * 4) % 1:
        raise ValidationError("Use múltiplos de 15 minutos (ex.: 1, 1,25, 1,5 ou 2).")


class Curso(models.Model):
    nome = models.CharField("nome", max_length=120, unique=True)
    duracao_meses = models.PositiveSmallIntegerField(
        "duração (meses)",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(36)],
        help_text="Tempo total do curso. Também é o número de mensalidades.",
    )
    dias_por_semana = models.PositiveSmallIntegerField(
        "mínimo de dias de aula por semana",
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="De 1 a 6 (segunda a sábado).",
    )
    horas_por_aula = models.DecimalField(
        "mínimo de horas por aula",
        max_digits=4,
        decimal_places=2,
        default=Decimal("2"),
        validators=[
            MinValueValidator(Decimal("0.5")),
            MaxValueValidator(Decimal("12")),
            validar_quarto_de_hora,
        ],
        help_text="Ex.: 2 ou 1,5",
    )
    carga_horaria = models.PositiveIntegerField(
        "carga horária (h)",
        editable=False,
        help_text="Calculada: meses × 4 semanas × dias por semana × horas por aula.",
    )
    pre_requisitos = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="libera",
        verbose_name="pré-requisitos",
        help_text="Cursos que o aluno precisa ter concluído antes.",
    )
    aceita_outra_escola = models.BooleanField(
        "aceita pré-requisito feito em outra escola",
        default=True,
        help_text="Na matrícula, permite informar que o aluno fez o pré-requisito em outra escola.",
    )
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
            models.CheckConstraint(
                condition=models.Q(dias_por_semana__gte=1, dias_por_semana__lte=6),
                name="curso_dias_por_semana_1_a_6",
            ),
            models.CheckConstraint(condition=models.Q(horas_por_aula__gt=0), name="curso_aula_positiva"),
            models.CheckConstraint(
                condition=models.Q(frequencia_minima__lte=100), name="curso_frequencia_minima_ate_100"
            ),
        ]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        # A carga horária nunca é digitada: sempre sai dos três números do curso.
        from .services import calcular_carga_horaria

        self.carga_horaria = calcular_carga_horaria(self.duracao_meses, self.dias_por_semana, self.horas_por_aula)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "carga_horaria"}
        super().save(*args, **kwargs)

    @property
    def gratuito(self):
        return self.valor_mensalidade == 0

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
