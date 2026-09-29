from django.contrib import admin

from .models import Aluno


@admin.register(Aluno)
class AlunoAdmin(admin.ModelAdmin):
    list_display = ["nome", "cpf_formatado", "telefone", "email", "escolaridade"]
    list_filter = ["escolaridade"]
    search_fields = ["nome", "cpf"]
    autocomplete_fields = ["usuario"]

    @admin.display(description="CPF", ordering="cpf")
    def cpf_formatado(self, obj):
        return obj.cpf_formatado
