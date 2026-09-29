from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _criar_grupos(sender, **kwargs):
    from .services import garantir_grupos

    garantir_grupos()


class ContasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contas"
    verbose_name = "Contas"

    def ready(self):
        post_migrate.connect(_criar_grupos, dispatch_uid="contas_criar_grupos")
