"""Vista de ``/api/v1/auth/google``: continuar con Google. Existe siempre, pero responde 404 si no está configurado."""
from django.http import Http404
from django.utils.translation import gettext as _

from . import google, google_accounts
from .errors import ApiError
from .fields import text_field
from .views_auth import token_response
from .views_base import ApiView

MAX_TOKEN_LENGTH = 8192


class GoogleView(ApiView):
    """``POST /api/v1/auth/google``: ``id_token`` de Google → token de dispositivo."""
    public = True

    def post(self, request):
        """
        Cuerpo ``{"id_token", "nonce", "device_name"?}``. ``nonce`` es el valor en claro que la app envió a Google al
        pedir el token. Con éxito, 201 como el login normal. 401 ``invalid_google_token`` si el token no es válido o
        ya se usó; 503 ``google_unavailable`` si no hay claves de Google. El nombre sale del propio token.
        """
        if not google.enabled():
            raise Http404
        body = self.json_body(request)
        token = text_field(body, "id_token", max_length=MAX_TOKEN_LENGTH)
        nonce = text_field(body, "nonce", max_length=256)
        device_name = text_field(body, "device_name", required=False, max_length=100)
        try:
            claims = google.verify_id_token(token, nonce)
        except google.GoogleTokenError:
            raise ApiError("invalid_google_token", _("No se pudo iniciar sesión con Google."), 401)
        except google.GoogleUnavailable:
            raise ApiError("google_unavailable", _("Google no responde. Inténtalo de nuevo en un momento."), 503)
        user = google_accounts.resolve_user(claims)
        return token_response(user, device_name)
