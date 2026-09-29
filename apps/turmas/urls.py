from django.urls import path

from . import views

app_name = "turmas"

urlpatterns = [
    path("", views.TurmaListView.as_view(), name="turma_lista"),
    path("nova/", views.TurmaCreateView.as_view(), name="turma_nova"),
    path("feriados/", views.feriados, name="feriados"),
    path("feriados/nacionais/", views.feriados_nacionais, name="feriados_nacionais"),
    path("feriados/<int:pk>/remover/", views.feriado_remover, name="feriado_remover"),
    path("<int:pk>/", views.TurmaDetailView.as_view(), name="turma_detalhe"),
    path("<int:pk>/editar/", views.TurmaUpdateView.as_view(), name="turma_editar"),
]
