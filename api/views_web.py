"""Vista web (no JSON) que canjea el ticket de ``/api/v1/auth/web-session``: crea la sesión web de la app."""
from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from core import sessions
from core.context_processors import is_app_request

from . import web_session

BACKEND = "django.contrib.auth.backends.ModelBackend"


def _rejected(request):
    """Ticket no válido: aviso y a la pantalla de acceso (sin decir si no existía, caducó o ya se había usado)."""
    messages.error(request, _("El enlace de acceso ha caducado. Vuelve a abrir la sección desde la app."))
    return redirect("login")


@require_safe
@never_cache
def start_web_session(request, ticket):
    """
    ``GET /app/session/<ticket>/``: con un ticket válido inicia la sesión web de la cuenta y redirige a la ruta
    que se pidió, sin el ticket en la URL final ni en ``Referer``. Solo lo canjea la app (User-Agent ``ZyraApp/``):
    así un navegador o una vista previa de enlaces no gasta el ticket. Sesión igual que «Mantener la sesión iniciada».
    """
    if not is_app_request(request):
        return _rejected(request)
    used = web_session.consume_ticket(ticket)
    if used is None:
        return _rejected(request)
    user = used.device_token.user
    # Las pestañas de la app comparten cookies y canjean un ticket cada una. Si la sesión ya es de esta cuenta no se vuelve a
    # iniciar: login() rota el token CSRF y rompería los formularios de las páginas ya abiertas en otras pestañas.
    if not (request.user.is_authenticated and request.user.pk == user.pk):
        login(request, user, backend=BACKEND)
        sessions.apply_login_expiry(request, user, remember=True)
    if request.session.session_key is None:  # login() de otra cuenta vacía la sesión y la clave se crea al guardar
        request.session.save()
    web_session.remember_session(used, request.session.session_key)
    response = HttpResponseRedirect(used.next_path)
    response["Referrer-Policy"] = "no-referrer"
    return response
