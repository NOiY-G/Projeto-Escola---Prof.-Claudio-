from django.contrib import admin

from . import services
from .models import Aula, Turma


class AulaInline(admin.TabularInline):
    model = Aula
    extra = 0


@admin.register(Turma)
class TurmaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "curso", "instrutor", "data_inicio", "data_fim", "vagas", "status"]
    list_filter = ["status", "curso"]
    search_fields = ["codigo", "curso__nome", "instrutor__nome"]
    autocomplete_fields = ["curso", "instrutor"]
    date_hierarchy = "data_inicio"
    inlines = [AulaInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not change or services.calendario_mudou(form.changed_data):
            services.gerar_aulas(form.instance)


@admin.register(Aula)
class AulaAdmin(admin.ModelAdmin):
    list_display = ["turma", "data"]
    list_filter = ["turma__curso"]
    search_fields = ["turma__codigo"]
    autocomplete_fields = ["turma"]
    date_hierarchy = "data"
