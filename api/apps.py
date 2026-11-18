"""Configuración de la app ``api``."""
from django.apps import AppConfig


class ApiConfig(AppConfig):
    """App de la API para clientes móviles."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
