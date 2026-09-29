from django.urls import path

from . import views

app_name = "matriculas"

urlpatterns = [
    path("nova/", views.matricula_nova, name="matricula_nova"),
    path("espera/", views.lista_espera, name="lista_espera"),
    path("minhas/", views.minhas_matriculas, name="minhas_matriculas"),
    path("<int:pk>/cancelar/", views.matricula_cancelar, name="matricula_cancelar"),
    path("chamada/<int:turma_pk>/", views.chamada_inicio, name="chamada_inicio"),
    path("chamada/<int:turma_pk>/aula/<int:aula_pk>/", views.chamada, name="chamada"),
    path("<int:pk>/desistencia/", views.matricula_desistencia, name="matricula_desistencia"),
]
