"""
Acciones de los avisos del Inicio nativo: reenviar el email de confirmación, aceptar o rechazar la invitación de una
ficha, cerrar avisos y responder la disponibilidad de un enfrentamiento. Mismas reglas que las vistas de la web
(``core.views``, ``call.views``); aquí solo cambian la entrada (JSON con token) y la salida.
"""
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from call import availability as availability_logic
from core import email_verification, ratelimit
from core.emails import send_welcome_email
from core.models import Membership, UserPreference
from core.services import InvitationError, accept_invitation
from match.models import Match
from players import copy as player_copy
from players.models import Player

from .errors import ApiError
from .fields import choice_field, invalid, text_field
from .responses import json_ok
from .views_base import ApiView

RESEND_LIMIT, RESEND_WINDOW = 5, 60 * 60


class ResendVerificationView(ApiView):
    """``POST /api/v1/account/resend-verification``: vuelve a enviar el enlace para confirmar el email de la cuenta."""

    def post(self, request):
        """
        ``{"sent": bool}``: ``false`` si no hay nada que confirmar (sin email o ya verificado). 429 con el mismo
        límite por IP que la web y 502 ``email_failed`` si no se pudo enviar el correo.
        """
        user = request.user
        if ratelimit.too_many(request, "resend-verification", RESEND_LIMIT, RESEND_WINDOW):
            raise ApiError("rate_limited", _("Demasiadas peticiones. Espera un momento."), 429)
        if not user.email or email_verification.is_verified(user):
            return json_ok({"sent": False})
        if not email_verification.start_verification(request, user):
            raise ApiError("email_failed", _("No se pudo enviar el correo. Inténtalo de nuevo más tarde."), 502)
        return json_ok({"sent": True})


class CopyInvitationView(ApiView):
    """``POST /api/v1/copy-invitations/<token>``: aceptar o rechazar la invitación de una ficha (la de ``notices``)."""

    def post(self, request, token):
        """
        Cuerpo ``{"action": "accept" | "decline"}``. Aceptar entra en el equipo como jugador y enlaza la ficha
        (``{"accepted": true, "club": {...}}``); rechazar la borra (``{"accepted": false}``). 404 si ya no está
        pendiente para esta cuenta; 409 ``invitation_error`` con el motivo de la web si no se puede aceptar.
        """
        body = self.json_body(request)
        action = choice_field(body, "action", ("accept", "decline"), "")
        invitation = next((i for i in player_copy.pending_for(request.user) if i.token == token), None)
        if invitation is None:
            raise ApiError("not_found", _("Esa invitación ya no está pendiente."), 404)
        if action == "decline":
            player_copy.decline(invitation)
            return json_ok({"accepted": False})
        try:
            membership = accept_invitation(invitation, request.user)
        except InvitationError as exc:
            raise ApiError("invitation_error", str(exc), 409)
        send_welcome_email(request.user, membership.club, site_url=request.build_absolute_uri("/"))
        return json_ok({"accepted": True, "club": {"name": membership.club.name,
                                                   "competition": membership.club.competition}})


class DismissNoticeView(ApiView):
    """``POST /api/v1/home/dismiss``: cierra la bienvenida de gestor o el aviso «Añade un gestor»."""

    def post(self, request):
        """
        Cuerpo ``{"notice": "manager_welcome" | "manager_tip", "team_id"?}`` (``team_id`` es obligatorio para la
        bienvenida, que es de un equipo). Idempotente: devuelve ``{"dismissed": true}``.
        """
        body = self.json_body(request)
        notice = choice_field(body, "notice", ("manager_welcome", "manager_tip"), "")
        if notice == "manager_tip":
            UserPreference.objects.update_or_create(
                user=request.user, defaults={"manager_tip_dismissed_at": timezone.now()})
        else:
            team_id = text_field(body, "team_id", max_length=64)
            Membership.objects.filter(user=request.user, club__public_id=team_id).update(manager_welcome_pending=False)
        return json_ok({"dismissed": True})


class AvailabilityView(ApiView):
    """``POST /api/v1/matches/<id>/availability``: el jugador responde si puede jugar el enfrentamiento."""

    def post(self, request, match_id):
        """
        Cuerpo ``{"answer": "yes" | "no" | "maybe", "comment"?}`` (el comentario solo se guarda con ``maybe``). 404 si el
        enfrentamiento no es de un equipo de la cuenta o la cuenta no tiene ficha allí; 409 ``closed`` si el acta o la
        convocatoria ya se cerraron. Devuelve ``{"answer"}``.
        """
        body = self.json_body(request)
        answer = body.get("answer")
        if not isinstance(answer, str) or not availability_logic.valid_answer(answer):
            raise invalid("answer")
        comment = body.get("comment", "")
        if not isinstance(comment, str):
            raise invalid("comment")
        match = Match.objects.select_related("club").filter(
            public_id=match_id, club__memberships__user=request.user).first()
        player = Player.objects.filter(club=match.club, user=request.user).first() if match else None
        if match is None or player is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        with transaction.atomic():
            row = availability_logic.set_answer(match, player, answer, comment)
        if row is None:
            raise ApiError("closed", _("La convocatoria está cerrada: ya no se puede cambiar la respuesta."), 409)
        return json_ok({"answer": row.answer})
