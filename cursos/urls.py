from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Cursos Livres"
admin.site.site_title = "Cursos Livres"
admin.site.index_title = "Administração"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.contas.urls")),
    path("catalogo/", include("apps.catalogo.urls")),
    path("turmas/", include("apps.turmas.urls")),
    path("alunos/", include("apps.alunos.urls")),
    path("matriculas/", include("apps.matriculas.urls")),
    path("certificados/", include("apps.certificados.urls")),
]
