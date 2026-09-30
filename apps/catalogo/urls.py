from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("cursos/", views.CursoListView.as_view(), name="curso_lista"),
    path("cursos/novo/", views.CursoCreateView.as_view(), name="curso_novo"),
    path("cursos/planejamento/", views.curso_planejamento, name="curso_planejamento"),
    path("cursos/<int:pk>/editar/", views.CursoUpdateView.as_view(), name="curso_editar"),
    path("cursos/<int:pk>/ativo/", views.curso_alternar_ativo, name="curso_alternar_ativo"),
    path("instrutores/", views.InstrutorListView.as_view(), name="instrutor_lista"),
    path("instrutores/novo/", views.InstrutorCreateView.as_view(), name="instrutor_novo"),
    path("instrutores/<int:pk>/editar/", views.InstrutorUpdateView.as_view(), name="instrutor_editar"),
]
