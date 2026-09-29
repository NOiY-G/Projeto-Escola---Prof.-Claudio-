import uuid

from django.db import models


class Certificado(models.Model):
    matricula = models.OneToOneField(
        "matriculas.Matricula",
        on_delete=models.PROTECT,
        related_name="certificado",
        verbose_name="matrícula",
    )
    codigo_validacao = models.UUIDField(
        "código de validação", default=uuid.uuid4, unique=True, editable=False
    )
    emitido_em = models.DateTimeField("emitido em", auto_now_add=True)

    class Meta:
        verbose_name = "certificado"
        verbose_name_plural = "certificados"
        ordering = ["-emitido_em"]

    def __str__(self):
        return f"Certificado {self.codigo_validacao} – {self.matricula}"
