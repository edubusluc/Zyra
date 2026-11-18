"""Configuración de la app ``api``."""
from django.apps import AppConfig


class ApiConfig(AppConfig):
    """App de la API para clientes móviles."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        """Conecta la revocación de tokens a los cambios de contraseña."""
        from allauth.account.signals import password_changed, password_reset, password_set

        from .signals import revoke_tokens_on_password_change
        for signal in (password_changed, password_set, password_reset):
            signal.connect(revoke_tokens_on_password_change, dispatch_uid=f"api-revoke-{id(signal)}")
