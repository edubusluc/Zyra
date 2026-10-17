"""
«Entrar como» un usuario, con edición y auditado: el personal usa Zyra tal y como la usa el capitán.

La sesión sigue siendo la de la persona del personal; el middleware cambia ``request.user`` por el
usuario visto mientras dure el modo (``request.impersonator`` guarda a quien entró). Se puede crear
y corregir datos como ese usuario para resolver incidencias; cada escritura (POST, PUT, PATCH,
DELETE) queda en la auditoría con el personal real como autor. Las acciones sensibles (cuenta,
email o contraseña, abandonar o borrar el club, ver la contraseña de SNP) siguen bloqueadas. No se
cuenta como actividad del usuario visto y el modo caduca solo a los 30 minutos. Empezar y terminar
quedan en la auditoría (con el motivo).
"""
import datetime

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .audit import audit

SESSION_KEY = "backoffice_impersonation"
MAX_DURATION = datetime.timedelta(minutes=30)
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
# Rutas bloqueadas con cualquier método: acciones sobre la cuenta o el club que no se hacen como otro
# usuario (cuenta y contraseña, abandonar/borrar el club, aceptar invitaciones, ver la clave de SNP...).
BLOCKED_PREFIXES = (
    "/accounts/", "/core/profile/", "/core/members/leave/", "/core/invite/", "/core/monthly-report/",
    "/core/switch_club/", "/core/logout/", "/players/snp/password/",
)
# El perfil (``/core/profile/``) se puede mirar con GET, pero no cambiar.


def start(request, target, reason):
    """Empieza a ver Zyra como ``target`` (la vista ya comprobó que se puede) y lo anota en la auditoría."""
    request.session[SESSION_KEY] = {
        "user_id": target.pk, "username": target.get_username(), "started": timezone.now().isoformat(), "reason": reason,
    }
    audit(request, "impersonate.start", target, label=target.get_username(), reason=reason)


def stop(request, expired=False):
    """Termina el modo y lo anota (duración incluida). Devuelve el nombre del usuario visto, o None si no había modo."""
    data = request.session.pop(SESSION_KEY, None)
    if not data:
        return None
    started = datetime.datetime.fromisoformat(data["started"])
    minutes = round((timezone.now() - started).total_seconds() / 60, 1)
    audit(request, "impersonate.stop", label=data["username"], minutes=minutes, expired=expired or None)
    return data["username"]


class ImpersonationMiddleware:
    """Cambia ``request.user`` por el usuario visto mientras el modo «Entrar como» está activo."""

    def __init__(self, get_response):
        """Guarda la siguiente capa de la cadena de middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Aplica el modo (con edición auditada y caducidad) o lo deshace si ya no es válido."""
        request.impersonator = None
        data = request.session.get(SESSION_KEY)
        user = request.user
        if not data:
            return self.get_response(request)
        # Detener el modo siempre va con la persona del personal real.
        if request.path == reverse("backoffice:impersonate_stop"):
            return self.get_response(request)
        if not (user.is_authenticated and user.is_staff and user.is_active):
            request.session.pop(SESSION_KEY, None)
            return self.get_response(request)
        started = datetime.datetime.fromisoformat(data["started"])
        if timezone.now() - started > MAX_DURATION:
            stop(request, expired=True)
            return self.get_response(request)
        target = get_user_model().objects.filter(pk=data["user_id"], is_active=True, is_staff=False).first()
        if target is None:
            stop(request)
            return self.get_response(request)
        if self.is_blocked(request):
            request.impersonator = user
            request.user = target
            return render(request, "backoffice/impersonation_blocked.html", status=403)
        request.impersonator = user
        request.user = target
        response = self.get_response(request)
        if request.method not in SAFE_METHODS:
            # Sin cuerpo de la petición: podría llevar contraseñas. Con el personal real como autor.
            audit(request, "impersonate.write", label=target.get_username(),
                  method=request.method, path=request.path, status=response.status_code)
        return response

    @staticmethod
    def is_blocked(request):
        """Dice si la petición es una acción sensible que no se permite como otro usuario."""
        path = request.path
        if path.startswith(BLOCKED_PREFIXES) and not (path.rstrip("/") == "/core/profile" and request.method in SAFE_METHODS):
            return True
        return False
