"""Vistas de ``/api/v1/devices``: registro del dispositivo para notificaciones push (sin envío todavía)."""
from . import push
from .fields import choice_field, text_field
from .models import PushDevice
from .responses import json_ok
from .views_base import ApiView

# Token de APNs: hexadecimal (hoy 64 caracteres; Apple permite crecer, de ahí el margen).
APNS_TOKEN_PATTERN = r"[0-9a-fA-F]{32,200}"
APP_VERSION_PATTERN = r"[0-9A-Za-z.+_-]{1,32}"


class DevicesView(ApiView):
    """``POST`` registra o actualiza el token de APNs del dispositivo del token y ``DELETE`` lo retira."""

    def post(self, request):
        """
        Cuerpo ``{"apns_token", "environment"?, "app_version"?}`` (``environment``: ``production`` por defecto o
        ``sandbox``). Idempotente: 201 la primera vez y 200 al repetirlo o cambiar el token. Si ese token de APNs
        estaba en otro dispositivo (otra cuenta en el mismo teléfono), pasa a este. No devuelve el token.
        """
        body = self.json_body(request)
        apns_token = text_field(body, "apns_token", max_length=200, pattern=APNS_TOKEN_PATTERN).lower()
        environment = choice_field(body, "environment", PushDevice.ENVIRONMENTS, PushDevice.PRODUCTION)
        app_version = text_field(body, "app_version", required=False, max_length=32, pattern=APP_VERSION_PATTERN)
        registered, created = push.register(request.device_token, apns_token, environment, app_version)
        return json_ok({"registered": True, "environment": registered.environment}, status=201 if created else 200)

    def delete(self, request):
        """Retira el registro push de este dispositivo (idempotente, p. ej. si el usuario apaga las notificaciones)."""
        push.unregister(request.device_token)
        return json_ok({"registered": False})
