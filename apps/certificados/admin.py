from django.contrib import admin

from .models import Certificado


@admin.register(Certificado)
class CertificadoAdmin(admin.ModelAdmin):
    list_display = ["codigo_validacao", "matricula", "emitido_em"]
    search_fields = ["codigo_validacao", "matricula__aluno__nome"]
    readonly_fields = ["codigo_validacao", "emitido_em"]
    autocomplete_fields = ["matricula"]
