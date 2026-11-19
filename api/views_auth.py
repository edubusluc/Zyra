"""
Vistas de acceso de la API: iniciar sesión (token de dispositivo) y cerrarla (revocarlo).

El login usa el mismo freno que el de la web (``core.login_throttle``): los fallos de uno cuentan en el
otro. No crea sesión web: no llama a ``login()``, solo emite un token.
"""
from django.conf import settings
from django.contrib.auth import authenticate
from django.urls import reverse
from django.utils.translation import gettext as _

from django.db import IntegrityError, transaction

from core import email_verification, login_throttle, ratelimit
from core.forms import SignUpForm, ZyraResetPasswordForm
from core.views import REGISTER_LIMIT, REGISTER_WINDOW

from . import throttle, web_session
from .errors import ApiError
from .fields import text_field
from .responses import json_ok
from .tokens import issue_token, revoke_token
from .views_base import ApiView

MAX_PASSWORD_LENGTH = 1024


def team_summary(user):
    """Equipo propio del primer club de ``user`` para la pantalla de acceso: ``{"name", "crest"}`` (``crest`` es la
    ruta o URL del escudo, o None). None si la cuenta no tiene club."""
    from core.services import club_of

    club = club_of(user)
    team = club.own_team if club else None
    if team is None:
        return None
    return {"name": team.name, "crest": team.photo.url if team.photo else None}


def token_response(user, device_name):
    """Respuesta 201 de los accesos (contraseña, Apple, Google o alta): token en claro (única vez), dispositivo, datos básicos y equipo."""
    device, token = issue_token(user, device_name)
    return json_ok({
        "token": token, "device": device.public_id, "expires_at": device.expires_at.isoformat(),
        "user": {"username": user.get_username(), "email": user.email},
        "team": team_summary(user),
    }, status=201)


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
        return token_response(user, device_name)


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


class RegisterAccountView(ApiView):
    """``POST /api/v1/auth/register``: crea una cuenta sin club (jugador que espera la invitación de su capitán)."""
    public = True

    def post(self, request):
        """
        Cuerpo ``{"username", "email", "password", "device_name"?}`` con las reglas de ``SignUpForm`` (las de la web).
        400 ``validation_error`` con ``fields`` (``account.<campo>``); 429 si se pasa del límite de altas (el mismo que
        ``register_account``). 201 como el login, con ``team`` a None y verificación de email iniciada.
        """
        if ratelimit.too_many(request, "register-account", REGISTER_LIMIT, REGISTER_WINDOW):
            raise ApiError("rate_limited", _("Demasiados intentos. Inténtalo más tarde."), 429)
        body = self.json_body(request)
        device_name = text_field(body, "device_name", required=False, max_length=100)
        password = body.get("password", "")
        form = SignUpForm({"username": body.get("username", ""), "email": body.get("email", ""),
                           "password1": password, "password2": password})
        user = None
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
            except IntegrityError:
                if not form.report_taken():
                    raise
        if user is None:
            names = {"password1": "password", "password2": "password"}
            fields = {}
            for field, messages in form.errors.items():
                key = "account" if field == "__all__" else f"account.{names.get(field, field)}"
                fields.setdefault(key, []).extend(str(m) for m in messages)
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400, extra={"fields": fields})
        email_verification.start_verification(request, user)
        return token_response(user, device_name)


class PasswordResetView(ApiView):
    """``POST /api/v1/auth/password-reset``: «¿Has olvidado tu contraseña?», igual que la web."""
    public = True

    def post(self, request):
        """
        Cuerpo ``{"email"}``. Reutiliza ``ZyraResetPasswordForm`` (mismos frenos por IP y por email que la web): manda el
        enlace de recuperación (una página de la web) si el email es el principal de una cuenta, y responde siempre
        200 ``{"sent": true}``, exista o no, para no delatar qué emails tienen cuenta. 400 ``validation_error`` solo si lo
        escrito no es un email.
        """
        body = self.json_body(request)
        form = ZyraResetPasswordForm({"email": str(body.get("email", "")).strip()})
        if not form.is_valid():
            fields = {f"account.{field}" if field != "__all__" else "account": [str(m) for m in messages]
                      for field, messages in form.errors.items()}
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400, extra={"fields": fields})
        form.save(request)
        return json_ok({"sent": True})
