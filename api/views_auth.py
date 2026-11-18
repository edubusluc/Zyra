"""
Vistas de acceso de la API: iniciar sesión (token de dispositivo) y cerrarla (revocarlo).

El login usa el mismo freno que el de la web (``core.login_throttle``): los fallos de uno cuentan en el
otro. No crea sesión web: no llama a ``login()``, solo emite un token.
"""
from django.contrib.auth import authenticate
from django.utils.translation import gettext as _

from core import login_throttle

from .errors import ApiError
from .responses import json_ok
from .tokens import issue_token, revoke_token
from .views_base import ApiView

MAX_LOGIN_LENGTH = 254
MAX_PASSWORD_LENGTH = 1024


def _text(body, name, required=True, max_length=MAX_LOGIN_LENGTH):
    """Campo de texto del cuerpo: ``ApiError`` 400 (``invalid_field``) si falta (cuando es obligatorio) o no es texto razonable."""
    value = body.get(name)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > max_length:
        raise ApiError("invalid_field", _("Campo no válido: %(name)s.") % {"name": name}, 400)
    return value


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
        login = _text(body, "login").strip()
        password = _text(body, "password", max_length=MAX_PASSWORD_LENGTH)
        device_name = _text(body, "device_name", required=False, max_length=100)
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
