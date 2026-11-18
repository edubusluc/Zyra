"""
Registro de dispositivos para notificaciones push (token de APNs). Lógica sin HTTP.

Solo guarda y retira registros: el envío no está implementado todavía.
"""
from django.db import IntegrityError, transaction

from .models import PushDevice


def register(device, apns_token, environment=PushDevice.PRODUCTION, app_version=""):
    """
    Registra (o actualiza) el token de APNs del dispositivo y devuelve ``(PushDevice, creado)``. Si ese token de
    APNs estaba registrado en otro dispositivo (el mismo teléfono con otra cuenta) pasa a este. Dos altas a la
    vez del mismo token pueden chocar con la restricción única: se reintenta una vez.
    """
    for attempt in (1, 2):
        try:
            with transaction.atomic():
                PushDevice.objects.filter(apns_token=apns_token).exclude(device_token=device).delete()
                return PushDevice.objects.update_or_create(
                    device_token=device,
                    defaults={"apns_token": apns_token, "environment": environment, "app_version": app_version},
                )
        except IntegrityError:
            if attempt == 2:
                raise


def unregister(device):
    """Retira el registro push del dispositivo (idempotente). Devuelve True si había alguno."""
    return bool(PushDevice.objects.filter(device_token=device).delete()[0])
