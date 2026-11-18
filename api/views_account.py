"""Vistas de ``/api/v1/account``: eliminar la cuenta desde la app (requisito de la App Store)."""
from django.db import transaction
from django.utils.translation import gettext as _

from core import ratelimit
from core.services import (
    DELETE_ACCOUNT_LIMIT, DELETE_ACCOUNT_WINDOW, CaptaincyError, account_delete_blocker, account_delete_confirmed,
    delete_account,
)

from .errors import ApiError
from .fields import text_field
from .models import DeviceToken
from .responses import json_ok
from .tokens import revoke_token
from .views_base import ApiView

MAX_CONFIRM_LENGTH = 1024


class DeleteAccountView(ApiView):
    """``POST /api/v1/account/delete``: elimina la cuenta con las mismas reglas que la web."""

    def post(self, request):
        """
        Cuerpo ``{"confirm", "delete_player"?}``: ``confirm`` es la contraseña (o el nombre de usuario en las cuentas
        sin contraseña) y ``delete_player`` (``false`` por defecto) elimina también la ficha de jugador. 409
        ``account_blocked`` con el motivo si es capitán (o personal de Zyra); 403 ``confirmation_failed`` si la
        confirmación no coincide; 429 tras 5 intentos por hora. Revoca todos los dispositivos del usuario y borra
        la cuenta con ``core.services.delete_account`` en una sola transacción.
        """
        body = self.json_body(request)
        confirm = text_field(body, "confirm", max_length=MAX_CONFIRM_LENGTH)
        delete_player = body.get("delete_player", False)
        if not isinstance(delete_player, bool):
            raise ApiError("invalid_field", _("«delete_player» debe ser verdadero o falso."), 400)
        user = request.user
        blocker = account_delete_blocker(user)
        if blocker:
            raise ApiError("account_blocked", blocker, 409)
        if ratelimit.too_many_user(request, "delete-account", DELETE_ACCOUNT_LIMIT, DELETE_ACCOUNT_WINDOW):
            raise ApiError("rate_limited", _("Demasiadas peticiones. Espera un momento."), 429,
                           {"Retry-After": str(DELETE_ACCOUNT_WINDOW)})
        if not account_delete_confirmed(user, confirm):
            raise ApiError("confirmation_failed", _("La confirmación no es correcta."), 403)
        try:
            with transaction.atomic():
                for device in DeviceToken.objects.filter(user=user):
                    revoke_token(device)
                delete_account(user, delete_player=delete_player)
        except CaptaincyError as exc:
            raise ApiError("account_blocked", str(exc), 409)
        return json_ok({"deleted": True})
