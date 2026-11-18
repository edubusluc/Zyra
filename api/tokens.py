"""
Ciclo de vida de los tokens de dispositivo: crear, resolver, renovar y revocar.

Lógica sin HTTP (las vistas solo la llaman). El token tiene 256 bits de entropía, por eso basta un
SHA-256 (no hace falta un hash lento). El reloj es un parámetro (``now``) para poder probarla.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import web_session
from .hashing import hash_token
from .models import DeviceToken

TOKEN_PREFIX = "zyra_"


def issue_token(user, device_name="", now=None):
    """Crea un token para ``user`` y devuelve ``(DeviceToken, token en claro)``. El claro no se vuelve a ver."""
    now = now or timezone.now()
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    device = DeviceToken.objects.create(
        user=user, token_hash=hash_token(raw), device_name=device_name.strip()[:100],
        last_used_at=now, expires_at=now + timedelta(days=settings.API_TOKEN_TTL_DAYS),
    )
    return device, raw


def resolve_token(raw, now=None):
    """
    Dispositivo activo del token en claro (con su usuario cargado) o None si no existe, está revocado o
    caducado, o su cuenta está desactivada. Una consulta indexada; solo escribe al renovar (``touch``).
    """
    if not raw.startswith(TOKEN_PREFIX):
        return None
    now = now or timezone.now()
    device = DeviceToken.objects.active(now).select_related("user").filter(token_hash=hash_token(raw)).first()
    if device is None or not device.user.is_active:
        return None
    touch(device, now)
    return device


def touch(device, now):
    """
    Anota el uso y renueva la caducidad, como mucho una vez cada ``API_TOKEN_TOUCH_SECONDS`` para no
    escribir en la base de datos en cada petición (dentro de la ventana no hace ninguna consulta). El
    ``UPDATE`` es condicional: con varias peticiones a la vez solo una escribe.
    """
    stale = now - timedelta(seconds=settings.API_TOKEN_TOUCH_SECONDS)
    if device.last_used_at >= stale:
        return
    expires_at = now + timedelta(days=settings.API_TOKEN_TTL_DAYS)
    if DeviceToken.objects.filter(pk=device.pk, last_used_at__lt=stale).update(
            last_used_at=now, expires_at=expires_at):
        device.last_used_at, device.expires_at = now, expires_at


def revoke_token(device, now=None):
    """
    Revoca el token (idempotente: no cambia la fecha si ya estaba revocado) y cierra las sesiones web que la
    app abrió con él (``api.web_session``): revocar un dispositivo corta todo lo que tenía.
    """
    web_session.end_sessions(device)
    DeviceToken.objects.filter(pk=device.pk, revoked_at__isnull=True).update(revoked_at=now or timezone.now())
