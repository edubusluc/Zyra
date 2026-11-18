"""
Clase base de todas las vistas de la API. Es la única puerta: aquí (y solo aquí) se exime del CSRF, se
autentica por token, se aplican los límites, se elige el idioma y se da formato a los errores. Una vista
concreta solo escribe ``get``/``post``/… y devuelve ``json_ok``.
"""
import json

from django.conf import settings
from django.http import Http404
from django.utils import translation
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from core.ratelimit import client_ip

from . import throttle
from .auth import authenticate
from .errors import ApiError
from .responses import json_error


def _too_many():
    """Error 429 con ``Retry-After``."""
    return ApiError("rate_limited", _("Demasiadas peticiones. Espera un momento."), 429,
                    {"Retry-After": str(throttle.WINDOW_SECONDS)})


@method_decorator(csrf_exempt, name="dispatch")
class ApiView(View):
    """
    Vista de la API. Con ``public = False`` (lo normal) exige token válido y deja el dispositivo en
    ``request.device_token`` y su cuenta en ``request.user``; el límite es por token. Con ``public = True``
    (login, etc.) no exige token y el límite es por IP. Los intentos con token inválido también cuentan
    por IP, para frenar a quien los pruebe a ciegas sin gastar consultas.
    """
    public = False

    def dispatch(self, request, *args, **kwargs):
        """Idioma, autenticación y límite; después la vista. Todo ``ApiError`` sale como JSON y sin caché."""
        with translation.override(translation.get_language_from_request(request, check_path=False)):
            try:
                self.check_access(request)
                response = super().dispatch(request, *args, **kwargs)
            except ApiError as error:
                response = json_error(error)
            except Http404:
                response = json_error(ApiError("not_found", _("No encontrado."), 404))
        response["Cache-Control"] = "no-store"
        return response

    def check_access(self, request):
        """Aplica el límite y, si la vista no es pública, la autenticación (lanza ``ApiError``)."""
        ip = client_ip(request)
        if self.public:
            if throttle.hit("public", ip) > settings.API_PUBLIC_LIMIT_PER_MINUTE:
                raise _too_many()
            return
        if throttle.count("authfail", ip) >= settings.API_AUTH_FAILURES_PER_MINUTE:
            raise _too_many()
        try:
            device = authenticate(request)
        except ApiError:
            throttle.hit("authfail", ip)
            raise
        if throttle.hit("token", device.pk) > settings.API_RATE_LIMIT_PER_MINUTE:
            raise _too_many()
        request.device_token = device
        request.user = device.user

    def json_body(self, request):
        """Cuerpo de la petición como diccionario JSON. ``ApiError`` 400 (``invalid_json``) si no lo es."""
        try:
            body = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            body = None
        if not isinstance(body, dict):
            raise ApiError("invalid_json", _("El cuerpo debe ser un objeto JSON."), 400)
        return body

    def http_method_not_allowed(self, request, *args, **kwargs):
        """405 en JSON (la de Django es HTML), con la cabecera ``Allow``."""
        raise ApiError("method_not_allowed", _("Método no permitido."), 405,
                       {"Allow": ", ".join(self._allowed_methods())})
