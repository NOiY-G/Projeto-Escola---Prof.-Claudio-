from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Matricula(models.Model):
    class Status(models.TextChoices):
        ATIVA = "ativa", "Ativa"
        LISTA_ESPERA = "lista_espera", "Lista de espera"
        CONCLUIDA = "concluida", "Concluída"
        DESISTENTE = "desistente", "Desistente"
        CANCELADA = "cancelada", "Cancelada"

    aluno = models.ForeignKey(
        "alunos.Aluno", on_delete=models.PROTECT, related_name="matriculas", verbose_name="aluno"
    )
    turma = models.ForeignKey(
        "turmas.Turma", on_delete=models.PROTECT, related_name="matriculas", verbose_name="turma"
    )
    data = models.DateTimeField("data", default=timezone.now)
    status = models.CharField(
        "status", max_length=20, choices=Status.choices, default=Status.ATIVA
    )
    desconto = models.DecimalField(
        "desconto (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Vale para todas as mensalidades. 100 = bolsa integral",
    )

    class Meta:
        verbose_name = "matrícula"
        verbose_name_plural = "matrículas"
        ordering = ["data", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["aluno", "turma"], name="matricula_unica_aluno_turma"),
        ]

    def __str__(self):
        return f"{self.aluno} em {self.turma.codigo}"


class Frequencia(models.Model):
    matricula = models.ForeignKey(
        Matricula, on_delete=models.CASCADE, related_name="frequencias", verbose_name="matrícula"
    )
    aula = models.ForeignKey(
        "turmas.Aula", on_delete=models.CASCADE, related_name="frequencias", verbose_name="aula"
    )
    presente = models.BooleanField("presente", default=False)
    observacao = models.CharField("observação", max_length=255, blank=True)

    class Meta:
        verbose_name = "frequência"
        verbose_name_plural = "frequências"
        ordering = ["aula__data"]
        constraints = [
            models.UniqueConstraint(fields=["matricula", "aula"], name="frequencia_unica_matricula_aula"),
        ]

    def __str__(self):
        return f"{self.matricula.aluno} – {self.aula} – {'P' if self.presente else 'F'}"
