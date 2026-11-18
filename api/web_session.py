"""
Puente de la app a la web: un ticket de un solo uso y 60 s que, al abrirlo la app en su navegador interno, crea la
sesión web normal de la cuenta (sin pedir la contraseña otra vez).

Lógica sin HTTP. El ticket tiene 256 bits y solo se guarda su hash; se gasta con un ``UPDATE`` condicional
atómico (con dos canjes a la vez solo uno gana). Sirve solo mientras el token del dispositivo y la cuenta sigan
activos. El ``next`` se valida al crearlo: solo rutas relativas de la propia web.
"""
import secrets
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .hashing import hash_token
from .models import WebLoginTicket

TICKET_TTL_SECONDS = 60
MAX_NEXT_LENGTH = 500
# Los tickets canjeados se conservan mientras pueda vivir la sesión que crearon (un año, ``core/sessions.py``).
KEEP_USED_DAYS = 400


def clean_next(value):
    """
    Ruta a la que se llega tras entrar: ``/`` por defecto; None si ``value`` no es una ruta relativa segura
    (otro dominio, ``//``, barras invertidas, caracteres de control, la propia API o demasiado larga).
    """
    if value is None:
        return "/"
    if (not isinstance(value, str) or len(value) > MAX_NEXT_LENGTH or not value.startswith("/")
            or value.startswith(("//", "/api/")) or "\\" in value or any(ord(c) < 32 for c in value)):
        return None
    return value if url_has_allowed_host_and_scheme(value, allowed_hosts=None) else None


def issue_ticket(device, next_path="/", now=None):
    """Crea un ticket para ``device`` y devuelve ``(WebLoginTicket, ticket en claro)``. ``next_path`` ya validado."""
    now = now or timezone.now()
    _purge(now)
    raw = secrets.token_urlsafe(32)
    ticket = WebLoginTicket.objects.create(
        device_token=device, ticket_hash=hash_token(raw), next_path=next_path,
        expires_at=now + timedelta(seconds=TICKET_TTL_SECONDS),
    )
    return ticket, raw


def consume_ticket(raw, now=None):
    """
    Gasta el ticket y lo devuelve (con el dispositivo y la cuenta cargados), o None si no existe, caducó, ya se
    usó, su token está revocado o caducado, o la cuenta está desactivada. Un ticket que llega a gastarse no se
    puede volver a usar aunque la comprobación posterior falle.
    """
    now = now or timezone.now()
    ticket = (WebLoginTicket.objects.select_related("device_token__user")
              .filter(ticket_hash=hash_token(raw)).first())
    if ticket is None:
        return None
    claimed = WebLoginTicket.objects.filter(pk=ticket.pk, used_at__isnull=True, expires_at__gt=now).update(used_at=now)
    if not claimed:
        return None
    device = ticket.device_token
    if not device.is_active(now) or not device.user.is_active:
        return None
    return ticket


def remember_session(ticket, session_key):
    """Anota la sesión web que creó el ticket, para poder cerrarla al revocar el dispositivo."""
    WebLoginTicket.objects.filter(pk=ticket.pk).update(session_key=session_key)


def end_sessions(device):
    """Cierra las sesiones web que se abrieron desde la app con este dispositivo (al revocar su token)."""
    keys = WebLoginTicket.objects.filter(device_token=device).exclude(session_key="").values_list(
        "session_key", flat=True)
    Session.objects.filter(session_key__in=list(keys)).delete()


def _purge(now):
    """Borra los tickets sin canjear caducados hace más de un día y los canjeados hace más de ``KEEP_USED_DAYS``."""
    WebLoginTicket.objects.filter(used_at__isnull=True, expires_at__lt=now - timedelta(days=1)).delete()
    WebLoginTicket.objects.filter(used_at__lt=now - timedelta(days=KEEP_USED_DAYS)).delete()
