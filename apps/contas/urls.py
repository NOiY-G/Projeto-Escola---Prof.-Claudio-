from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "contas"

urlpatterns = [
    path("", views.painel, name="painel"),
    path(
        "entrar/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "senha/recuperar/",
        auth_views.PasswordResetView.as_view(
            success_url=reverse_lazy("contas:password_reset_done"),
            email_template_name="registration/password_reset_email.txt",
            subject_template_name="registration/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "senha/recuperar/enviado/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            success_url=reverse_lazy("contas:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "senha/redefinir/concluido/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
