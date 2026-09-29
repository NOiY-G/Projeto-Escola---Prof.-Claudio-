from django.urls import path

from . import views

app_name = "certificados"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("emitir/<int:matricula_pk>/", views.emitir, name="emitir"),
    path("<str:codigo>/pdf/", views.baixar_pdf, name="pdf"),
    path("validar/", views.validar_redireciona, name="validar_busca"),
    path("validar/<str:codigo>/", views.validar, name="validar"),
    path("concluir-turma/<int:turma_pk>/", views.concluir_turma, name="concluir_turma"),
]
