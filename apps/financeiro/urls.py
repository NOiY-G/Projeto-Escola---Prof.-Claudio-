from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    path("", views.pagamentos, name="pagamentos"),
    path("parcela/<int:parcela_pk>/pagar/", views.registrar, name="registrar"),
    path("parcela/<int:parcela_pk>/comprovante/", views.enviar_comprovante, name="enviar_comprovante"),
    path("comprovante/<int:comprovante_pk>/", views.conferir, name="conferir"),
    path("comprovante/<int:comprovante_pk>/arquivo/", views.arquivo_comprovante, name="arquivo_comprovante"),
    path("pagamento/<int:pagamento_pk>/estornar/", views.estornar, name="estornar"),
    path("pagamento/<int:pagamento_pk>/recibo/", views.recibo, name="recibo"),
]
