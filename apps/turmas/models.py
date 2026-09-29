from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

DIAS_SEMANA = [
    ("seg", "Segunda"),
    ("ter", "Terça"),
    ("qua", "Quarta"),
    ("qui", "Quinta"),
    ("sex", "Sexta"),
    ("sab", "Sábado"),
    ("dom", "Domingo"),
]
# Índices compatíveis com date.weekday() (segunda = 0).
DIA_PARA_WEEKDAY = {codigo: i for i, (codigo, _) in enumerate(DIAS_SEMANA)}


def validar_dias_semana(valor):
    dias = [d.strip() for d in valor.split(",") if d.strip()]
    if not dias:
        raise ValidationError("Informe ao menos um dia da semana.")
    invalidos = [d for d in dias if d not in DIA_PARA_WEEKDAY]
    if invalidos:
        raise ValidationError(
            "Dias inválidos: %(dias)s. Use seg, ter, qua, qui, sex, sab ou dom.",
            params={"dias": ", ".join(invalidos)},
        )


class Turma(models.Model):
    class Status(models.TextChoices):
        PLANEJADA = "planejada", "Planejada"
        INSCRICOES_ABERTAS = "inscricoes_abertas", "Inscrições abertas"
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        CONCLUIDA = "concluida", "Concluída"
        CANCELADA = "cancelada", "Cancelada"

    curso = models.ForeignKey(
        "catalogo.Curso", on_delete=models.PROTECT, related_name="turmas", verbose_name="curso"
    )
    instrutor = models.ForeignKey(
        "catalogo.Instrutor",
        on_delete=models.PROTECT,
        related_name="turmas",
        verbose_name="instrutor",
    )
    codigo = models.CharField("código", max_length=30, unique=True, help_text="Ex.: INF-2026-01")
    data_inicio = models.DateField("data de início")
    data_fim = models.DateField("data de término")
    dias_semana = models.CharField(
        "dias da semana",
        max_length=40,
        validators=[validar_dias_semana],
        help_text="Separados por vírgula. Ex.: seg,qua",
    )
    hora_inicio = models.TimeField("hora de início")
    hora_fim = models.TimeField("hora de término")
    sala = models.CharField("sala", max_length=50, blank=True)
    vagas = models.PositiveIntegerField("vagas", validators=[MinValueValidator(1)])
    status = models.CharField(
        "status", max_length=20, choices=Status.choices, default=Status.PLANEJADA
    )

    class Meta:
        verbose_name = "turma"
        verbose_name_plural = "turmas"
        ordering = ["-data_inicio", "codigo"]
        constraints = [
            models.CheckConstraint(condition=models.Q(vagas__gt=0), name="turma_vagas_positivas"),
            models.CheckConstraint(
                condition=models.Q(data_fim__gte=models.F("data_inicio")),
                name="turma_periodo_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(hora_fim__gt=models.F("hora_inicio")),
                name="turma_horario_valido",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} – {self.curso}"

    def clean(self):
        erros = {}
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            erros["data_fim"] = "A data de término deve ser igual ou posterior ao início."
        if self.hora_inicio and self.hora_fim and self.hora_fim <= self.hora_inicio:
            erros["hora_fim"] = "A hora de término deve ser posterior à de início."
        if erros:
            raise ValidationError(erros)

    @property
    def dias_semana_lista(self):
        return [d.strip() for d in self.dias_semana.split(",") if d.strip()]

    @property
    def dias_semana_display(self):
        """Ex.: "Seg/Qua" """
        return "/".join(d.capitalize() for d in self.dias_semana_lista)

    @property
    def horario_display(self):
        """Ex.: "Seg/Qua, 08:00–10:00" """
        return f"{self.dias_semana_display}, {self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M}"


class Aula(models.Model):
    turma = models.ForeignKey(
        Turma, on_delete=models.CASCADE, related_name="aulas", verbose_name="turma"
    )
    data = models.DateField("data")
    conteudo = models.TextField("conteúdo", blank=True)

    class Meta:
        verbose_name = "aula"
        verbose_name_plural = "aulas"
        ordering = ["data"]
        constraints = [
            models.UniqueConstraint(fields=["turma", "data"], name="aula_unica_por_turma_data"),
        ]

    def __str__(self):
        return f"{self.turma.codigo} – {self.data:%d/%m/%Y}"


class Feriado(models.Model):
    """Dia sem aula para todas as turmas (feriado, recesso, ponto facultativo)."""

    data = models.DateField("data", unique=True)
    descricao = models.CharField("descrição", max_length=120)

    class Meta:
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        ordering = ["data"]

    def __str__(self):
        return f"{self.data:%d/%m/%Y} – {self.descricao}"
