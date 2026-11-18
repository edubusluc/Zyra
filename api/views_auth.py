"""
Vistas de acceso de la API: iniciar sesión (token de dispositivo) y cerrarla (revocarlo).

El login usa el mismo freno que el de la web (``core.login_throttle``): los fallos de uno cuentan en el
otro. No crea sesión web: no llama a ``login()``, solo emite un token.
"""
from django.conf import settings
from django.contrib.auth import authenticate
from django.urls import reverse
from django.utils.translation import gettext as _

from core import login_throttle

from . import throttle, web_session
from .errors import ApiError
from .fields import text_field
from .responses import json_ok
from .tokens import issue_token, revoke_token
from .views_base import ApiView

MAX_PASSWORD_LENGTH = 1024


class LoginView(ApiView):
    """``POST /api/v1/auth/login``: usuario o email y contraseña → token de dispositivo."""
    public = True

    def post(self, request):
        """
        Cuerpo ``{"login", "password", "device_name"?}``. 429 si el freno de login se ha agotado (se comprueba antes
        de mirar la contraseña); 401 ``invalid_credentials`` con el mismo mensaje para cuenta inexistente, contraseña
        mala o cuenta desactivada. Con éxito devuelve el token en claro (única vez) y los datos básicos de la cuenta.
        """
        body = self.json_body(request)
        login = text_field(body, "login").strip()
        password = text_field(body, "password", max_length=MAX_PASSWORD_LENGTH)
        device_name = text_field(body, "device_name", required=False, max_length=100)
        if login_throttle.is_locked(request, login):
            raise ApiError("login_locked", _("Demasiados intentos fallidos. Espera 15 minutos y vuelve a intentarlo."),
                           429, {"Retry-After": str(login_throttle.LOGIN_LOCKOUT_SECONDS)})
        user = authenticate(request, username=login, password=password)
        if user is None:
            login_throttle.record_failure(request, login)
            raise ApiError("invalid_credentials", _("Usuario o contraseña incorrectos."), 401)
        login_throttle.record_success(request, login, user)
        device, token = issue_token(user, device_name)
        return json_ok({
            "token": token, "device": device.public_id, "expires_at": device.expires_at.isoformat(),
            "user": {"username": user.get_username(), "email": user.email},
        }, status=201)


class LogoutView(ApiView):
    """``POST /api/v1/auth/logout``: revoca el token con el que se hace la petición (solo ese dispositivo)."""

    def post(self, request):
        """Revoca el token y responde ``{"revoked": true}``; el siguiente uso devuelve 401."""
        revoke_token(request.device_token)
        return json_ok({"revoked": True})


class WebSessionView(ApiView):
    """``POST /api/v1/auth/web-session``: URL de un solo uso (60 s) con la que la app abre la web ya con la sesión iniciada."""

    def post(self, request):
        """
        Cuerpo opcional ``{"next": "/ruta/"}`` (ruta relativa de la web; por defecto ``/``). Devuelve ``{"url",
        "expires_at"}``; la app debe abrir esa URL de inmediato con su User-Agent ``ZyraApp/``. Límite por token.
        """
        next_path = web_session.clean_next(self.json_body(request).get("next"))
        if next_path is None:
            raise ApiError("invalid_next", _("La ruta de destino no es válida."), 400)
        if throttle.hit("web-session", request.device_token.pk) > settings.API_WEB_SESSION_LIMIT_PER_MINUTE:
            raise ApiError("rate_limited", _("Demasiadas peticiones. Espera un momento."), 429,
                           {"Retry-After": str(throttle.WINDOW_SECONDS)})
        ticket, raw = web_session.issue_ticket(request.device_token, next_path)
        return json_ok({"url": request.build_absolute_uri(reverse("app_web_session", args=[raw])),
                        "expires_at": ticket.expires_at.isoformat()}, status=201)
