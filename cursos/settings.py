"""Configurações do projeto de Cadastro de Cursos Livres."""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-apenas-para-desenvolvimento",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.contas",
    "apps.catalogo",
    "apps.turmas",
    "apps.alunos",
    "apps.matriculas",
    "apps.certificados",
    "apps.relatorios",
    "apps.financeiro",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "cursos.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.contas.context_processors.perfil",
            ],
        },
    },
]

WSGI_APPLICATION = "cursos.wsgi.application"

# SQLite em desenvolvimento; PostgreSQL em produção via DATABASE_URL.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Belem"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "contas:login"
LOGIN_REDIRECT_URL = "contas:painel"
LOGOUT_REDIRECT_URL = "contas:login"

# Em desenvolvimento, e-mails de recuperação de senha saem no console.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "nao-responda@cursos.local")

# Tailwind e HTMX pela internet (padrão) ou pelas cópias em static/vendor/ (sem internet).
USAR_CDN = os.environ.get("USAR_CDN", "1") == "1"

# Nome que aparece no cabeçalho dos certificados.
NOME_INSTITUICAO = os.environ.get("NOME_INSTITUICAO", "Cursos Livres")

# Arquivos enviados (comprovantes). NÃO são servidos publicamente: só por views
# que conferem a permissão de quem pede.
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "arquivos_privados"))

# Financeiro
TOLERANCIA_PAGAMENTO_DIAS = int(os.environ.get("TOLERANCIA_PAGAMENTO_DIAS", "7"))
COMPROVANTE_TAMANHO_MAX_MB = 5
# Dados do Pix da escola (aparecem para o aluno no QR Code).
PIX_CHAVE = os.environ.get("PIX_CHAVE", "pix@exemplo.com")
PIX_NOME_RECEBEDOR = os.environ.get("PIX_NOME_RECEBEDOR", "CURSOS LIVRES")
PIX_CIDADE = os.environ.get("PIX_CIDADE", "BELEM")
