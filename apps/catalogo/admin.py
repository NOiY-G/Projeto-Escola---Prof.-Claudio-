from django.contrib import admin

from .models import Curso, Instrutor


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ["nome", "carga_horaria", "duracao_meses", "dias_por_semana", "horas_por_aula", "valor_mensalidade", "ativo"]
    readonly_fields = ["carga_horaria"]
    filter_horizontal = ["pre_requisitos"]
    list_filter = ["ativo"]
    search_fields = ["nome"]


@admin.register(Instrutor)
class InstrutorAdmin(admin.ModelAdmin):
    list_display = ["nome", "telefone", "usuario"]
    search_fields = ["nome", "usuario__username"]
    autocomplete_fields = ["usuario"]
