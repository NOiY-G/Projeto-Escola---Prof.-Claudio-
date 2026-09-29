from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Cursos Livres"
admin.site.site_title = "Cursos Livres"
admin.site.index_title = "Administração"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.contas.urls")),
]
