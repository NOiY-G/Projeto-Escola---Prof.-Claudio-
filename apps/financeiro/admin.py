from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Comprovante, Pagamento, Parcela


class PagamentoInline(admin.TabularInline):
    model = Pagamento
    extra = 0
    fields = ["data", "forma", "valor", "codigo_transacao", "recebido_por", "estornado_em", "motivo_estorno"]
    readonly_fields = fields
    can_delete = False


@admin.register(Parcela)
class ParcelaAdmin(admin.ModelAdmin):
    list_display = ["matricula", "numero", "valor", "vencimento", "status"]
    list_filter = ["status", "matricula__turma__curso"]
    search_fields = ["matricula__aluno__nome", "matricula__aluno__cpf", "matricula__turma__codigo"]
    date_hierarchy = "vencimento"
    autocomplete_fields = ["matricula"]
    inlines = [PagamentoInline]


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ["parcela", "data", "forma", "valor", "recebido_por", "estornado_em"]
    list_filter = ["forma", "data"]
    search_fields = ["parcela__matricula__aluno__nome", "codigo_transacao"]
    # Pagamentos se corrigem por estorno (na tela do aluno), não editando o registro.
    readonly_fields = [f.name for f in Pagamento._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Comprovante)
class ComprovanteAdmin(admin.ModelAdmin):
    list_display = ["parcela", "enviado_em", "status", "analisado_por"]
    list_filter = ["status"]
    search_fields = ["parcela__matricula__aluno__nome"]
    fields = ["parcela", "ver_arquivo", "tipo_conteudo", "enviado_em", "enviado_por", "status",
              "motivo_recusa", "analisado_em", "analisado_por"]
    readonly_fields = fields

    @admin.display(description="Arquivo")
    def ver_arquivo(self, obj):
        # Pela view protegida: o arquivo não tem endereço público.
        url = reverse("financeiro:arquivo_comprovante", args=[obj.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">Abrir comprovante</a>', url)

    def has_add_permission(self, request):
        return False
