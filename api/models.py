"""Modelos de la API."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.public_id import PublicIdModel


class DeviceTokenQuerySet(models.QuerySet):
    """QuerySet de DeviceToken con filtros propios."""

    def active(self, now=None):
        """Tokens que se pueden usar: sin revocar y sin caducar."""
        return self.filter(revoked_at__isnull=True, expires_at__gt=now or timezone.now())


class DeviceToken(PublicIdModel):
    """
    Credencial de un dispositivo de una cuenta para la API. Solo se guarda el hash SHA-256 del token
    (``api.tokens``): el token en claro se entrega una vez al crearlo y no se puede recuperar. Es
    revocable y caduca; el uso lo renueva (caducidad deslizante) y anota ``last_used_at``.
    """
    PUBLIC_ID_PREFIX = "DVT"
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_tokens")
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    device_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = DeviceTokenQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "revoked_at"])]

    def is_active(self, now=None):
        """True si no está revocado ni caducado."""
        return self.revoked_at is None and self.expires_at > (now or timezone.now())

    def __str__(self):
        """Nombre del dispositivo y su identificador público (nunca el token)."""
        return f"{self.device_name or 'Dispositivo'} ({self.public_id})"


class WebLoginTicket(models.Model):
    """
    Ticket de un solo uso para abrir la web dentro de la app sin pedir la contraseña (``api.web_session``): vale
    ``TICKET_TTL_SECONDS`` y se gasta al canjearlo. Solo se guarda el hash del ticket. Tras canjearlo apunta
    a la sesión web que creó (``session_key``), para cerrarla cuando se revoca el token del dispositivo.
    """
    device_token = models.ForeignKey(DeviceToken, on_delete=models.CASCADE, related_name="web_tickets")
    ticket_hash = models.CharField(max_length=64, unique=True, editable=False)
    next_path = models.CharField(max_length=500, default="/")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    session_key = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PushDevice(models.Model):
    """
    Registro para notificaciones push del dispositivo de la app (token de APNs). Uno por ``DeviceToken``; el token
    de APNs es único: si el mismo teléfono entra con otra cuenta, pasa a esta. Aún no se envía nada: solo se guarda
    para cuando haya envío. Desaparece al revocar el token del dispositivo o al eliminar la cuenta.
    """
    SANDBOX = "sandbox"
    PRODUCTION = "production"
    ENVIRONMENTS = (SANDBOX, PRODUCTION)

    device_token = models.OneToOneField(DeviceToken, on_delete=models.CASCADE, related_name="push_device")
    apns_token = models.CharField(max_length=200, unique=True)
    environment = models.CharField(max_length=10, default=PRODUCTION)
    app_version = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
