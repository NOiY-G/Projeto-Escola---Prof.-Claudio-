from django.contrib import admin

from .models import Frequencia, Matricula


@admin.register(Matricula)
class MatriculaAdmin(admin.ModelAdmin):
    list_display = ["aluno", "turma", "data", "status"]
    list_filter = ["status", "turma__curso"]
    search_fields = ["aluno__nome", "aluno__cpf", "turma__codigo"]
    autocomplete_fields = ["aluno", "turma"]


@admin.register(Frequencia)
class FrequenciaAdmin(admin.ModelAdmin):
    list_display = ["matricula", "aula", "presente"]
    list_filter = ["presente", "aula__turma"]
    search_fields = ["matricula__aluno__nome", "aula__turma__codigo"]
    autocomplete_fields = ["matricula", "aula"]
