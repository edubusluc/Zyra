"""Autenticación de la API: token de dispositivo en ``Authorization: Bearer <token>``."""
from django.utils.translation import gettext as _

from .errors import ApiError
from .tokens import resolve_token


def bearer_token(request):
    """Token en claro de la cabecera ``Authorization``, o None si falta o no es de tipo Bearer."""
    scheme, _sep, value = request.META.get("HTTP_AUTHORIZATION", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


def authenticate(request):
    """
    Dispositivo activo de la petición. Lanza ``ApiError`` 401 (``unauthorized``) si no hay token o no es
    válido; el mismo error para «no existe», «caducado» y «revocado», para no dar pistas.
    """
    raw = bearer_token(request)
    device = resolve_token(raw) if raw else None
    if device is None:
        raise ApiError("unauthorized", _("Sesión no válida. Inicia sesión de nuevo."), 401,
                       {"WWW-Authenticate": "Bearer"})
    return device
