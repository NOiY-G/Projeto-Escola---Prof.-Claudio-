from django.urls import path

from . import views

app_name = "alunos"

urlpatterns = [
    path("", views.AlunoListView.as_view(), name="aluno_lista"),
    path("novo/", views.AlunoCreateView.as_view(), name="aluno_novo"),
    path("<int:pk>/", views.AlunoDetailView.as_view(), name="aluno_detalhe"),
    path("<int:pk>/editar/", views.AlunoUpdateView.as_view(), name="aluno_editar"),
]
