from django.urls import path

from . import views

app_name = "relatorios"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("<slug:slug>/", views.relatorio, name="relatorio"),
    path("<slug:slug>/csv/", views.relatorio_csv, name="csv"),
]
