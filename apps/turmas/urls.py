from django.urls import path

from . import views

app_name = "turmas"

urlpatterns = [
    path("", views.TurmaListView.as_view(), name="turma_lista"),
    path("nova/", views.TurmaCreateView.as_view(), name="turma_nova"),
    path("<int:pk>/", views.TurmaDetailView.as_view(), name="turma_detalhe"),
    path("<int:pk>/editar/", views.TurmaUpdateView.as_view(), name="turma_editar"),
]
