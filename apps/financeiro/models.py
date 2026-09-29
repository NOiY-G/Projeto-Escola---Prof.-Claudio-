import uuid

from django.conf import settings
from django.db import models


class Parcela(models.Model):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        EM_ANALISE = "em_analise", "Comprovante em análise"
        PAGA = "paga", "Paga"
        CANCELADA = "cancelada", "Cancelada"

    matricula = models.ForeignKey(
        "matriculas.Matricula", on_delete=models.PROTECT, related_name="parcelas", verbose_name="matrícula"
    )
    numero = models.PositiveSmallIntegerField("número")
    valor = models.DecimalField("valor (R$)", max_digits=10, decimal_places=2)
    vencimento = models.DateField("vencimento")
    status = models.CharField("situação", max_length=12, choices=Status.choices, default=Status.ABERTA)

    class Meta:
        verbose_name = "parcela"
        verbose_name_plural = "parcelas"
        ordering = ["vencimento", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["matricula", "numero"], name="parcela_unica_por_numero"),
            models.CheckConstraint(condition=models.Q(valor__gt=0), name="parcela_valor_positivo"),
        ]

    def __str__(self):
        return f"Parcela {self.numero} – {self.matricula}"

    @property
    def identificador(self):
        """Código que vai no Pix e aparece no extrato, ex.: PARC000123."""
        return f"PARC{self.pk:06d}"


def _caminho_comprovante(instance, filename):
    # Nome aleatório: o nome original do arquivo não é usado nem exposto.
    return f"comprovantes/{uuid.uuid4().hex}"


class Comprovante(models.Model):
    class Status(models.TextChoices):
        EM_ANALISE = "em_analise", "Em análise"
        APROVADO = "aprovado", "Aprovado"
        RECUSADO = "recusado", "Recusado"

    parcela = models.ForeignKey(
        Parcela, on_delete=models.PROTECT, related_name="comprovantes", verbose_name="parcela"
    )
    arquivo = models.FileField("arquivo", upload_to=_caminho_comprovante)
    tipo_conteudo = models.CharField("tipo", max_length=40)
    enviado_em = models.DateTimeField("enviado em", auto_now_add=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    status = models.CharField("situação", max_length=12, choices=Status.choices, default=Status.EM_ANALISE)
    motivo_recusa = models.CharField("motivo da recusa", max_length=255, blank=True)
    analisado_em = models.DateTimeField("analisado em", null=True, blank=True)
    analisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "comprovante"
        verbose_name_plural = "comprovantes"
        ordering = ["-enviado_em"]

    def __str__(self):
        return f"Comprovante de {self.parcela}"


class Pagamento(models.Model):
    class Forma(models.TextChoices):
        PIX = "pix", "Pix"
        DINHEIRO = "dinheiro", "Dinheiro"

    parcela = models.ForeignKey(
        Parcela, on_delete=models.PROTECT, related_name="pagamentos", verbose_name="parcela"
    )
    valor = models.DecimalField("valor (R$)", max_digits=10, decimal_places=2)
    data = models.DateField("data do pagamento")
    forma = models.CharField("forma", max_length=10, choices=Forma.choices)
    codigo_transacao = models.CharField(
        "código da transação Pix", max_length=64, blank=True,
        help_text="O ID que aparece no comprovante do banco (opcional).",
    )
    observacao = models.CharField("observação", max_length=255, blank=True)
    comprovante = models.OneToOneField(
        Comprovante, on_delete=models.PROTECT, null=True, blank=True, related_name="pagamento"
    )
    recebido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
        verbose_name="recebido por",
    )
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)
    estornado_em = models.DateTimeField("estornado em", null=True, blank=True)
    motivo_estorno = models.CharField("motivo do estorno", max_length=255, blank=True)

    class Meta:
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"
        ordering = ["-data", "-pk"]
        constraints = [
            # O mesmo Pix não pode quitar duas parcelas (estornados não contam).
            models.UniqueConstraint(
                fields=["codigo_transacao"],
                condition=~models.Q(codigo_transacao="") & models.Q(estornado_em__isnull=True),
                name="pagamento_codigo_pix_unico",
            ),
            models.CheckConstraint(condition=models.Q(valor__gt=0), name="pagamento_valor_positivo"),
        ]

    def __str__(self):
        return f"{self.get_forma_display()} de {self.valor} – {self.parcela}"

    @property
    def estornado(self):
        return self.estornado_em is not None
