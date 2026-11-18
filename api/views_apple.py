"""Vista de ``/api/v1/auth/apple``: iniciar sesión con Apple. Existe siempre, pero responde 404 si no está configurado."""
from django.http import Http404
from django.utils.translation import gettext as _

from . import apple, apple_accounts
from .errors import ApiError
from .fields import text_field
from .views_auth import token_response
from .views_base import ApiView

MAX_TOKEN_LENGTH = 8192


class AppleView(ApiView):
    """``POST /api/v1/auth/apple``: ``identity_token`` de Apple → token de dispositivo."""
    public = True

    def post(self, request):
        """
        Cuerpo ``{"identity_token", "nonce", "first_name"?, "last_name"?, "device_name"?}``. ``nonce`` es el valor en
        claro cuyo SHA-256 la app pasó a Apple. Con éxito, 201 como el login normal. 401 ``invalid_apple_token`` si
        el token no es válido o ya se usó; 503 ``apple_unavailable`` si no hay claves de Apple.
        """
        if not apple.enabled():
            raise Http404
        body = self.json_body(request)
        token = text_field(body, "identity_token", max_length=MAX_TOKEN_LENGTH)
        nonce = text_field(body, "nonce", max_length=256)
        first_name = text_field(body, "first_name", required=False, max_length=150).strip()
        last_name = text_field(body, "last_name", required=False, max_length=150).strip()
        device_name = text_field(body, "device_name", required=False, max_length=100)
        try:
            claims = apple.verify_identity_token(token, nonce)
        except apple.AppleTokenError:
            raise ApiError("invalid_apple_token", _("No se pudo iniciar sesión con Apple."), 401)
        except apple.AppleUnavailable:
            raise ApiError("apple_unavailable", _("Apple no responde. Inténtalo de nuevo en un momento."), 503)
        user = apple_accounts.resolve_user(claims, first_name, last_name)
        return token_response(user, device_name)
