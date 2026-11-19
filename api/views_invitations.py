"""
Invitaciones al club desde la app: consultar a qué club invita un enlace y aceptarla con el token de la cuenta. Usa las
mismas reglas que la web (``core.services.accept_invitation``: caducidad, un solo uso, un equipo por competición, emails
bloqueados, ficha copiada). También sirve el fichero de asociación de los enlaces universales de iOS.
"""
from django.conf import settings
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.utils.translation import gettext as _

from core.emails import send_welcome_email
from core.models import Invitation, Membership
from core.services import InvitationError, accept_invitation, club_of, one_space_message

from .errors import ApiError
from .responses import json_ok
from .views_auth import team_summary
from .views_base import ApiView


def _invitation(token):
    """Invitación del ``token`` (404 si no existe)."""
    invitation = Invitation.objects.select_related("club").filter(token=token).first()
    if invitation is None:
        raise ApiError("not_found", _("No encontrado."), 404)
    return invitation


def _crest(club):
    """Ruta o URL del escudo del equipo propio del club, o None."""
    team = club.own_team
    return team.photo.url if team is not None and team.photo else None


class InvitationView(ApiView):
    """``GET /api/v1/invitations/<token>``: a qué club invita el enlace, para confirmar antes de unirse."""

    def get(self, request, token):
        """
        ``{"club": {name, competition, crest, captains}, "can_join", "message"}``. 404 si el token no existe; 410
        ``invitation_invalid`` si ya se usó, caducó o el club está suspendido. Con la cuenta ya en un equipo de esa competición
        responde 200 con ``can_join`` falso y el motivo en ``message``.
        """
        invitation = _invitation(token)
        club = invitation.club
        if not invitation.is_valid or club.is_suspended:
            raise ApiError("invitation_invalid", _("Esta invitación ya se ha usado o ha caducado."), 410)
        message = ""
        if Membership.objects.filter(user=request.user, club=club).exists():
            message = _("Ya eres miembro de %(club)s.") % {"club": club.name}
        else:
            current = club_of(request.user, club.competition)
            if current is not None:
                message = str(one_space_message(current))
        captains = [m.user.get_full_name().strip() or m.user.get_username()
                    for m in club.memberships.filter(role=Membership.ADMIN).select_related("user")]
        return json_ok({
            "club": {"name": club.name, "competition": club.competition, "crest": _crest(club), "captains": captains},
            "can_join": not message, "message": message,
        })


class AcceptInvitationView(ApiView):
    """``POST /api/v1/invitations/<token>/accept``: la cuenta entra en el club como miembro."""

    def post(self, request, token):
        """
        201 con ``club``, ``team`` y ``next_path`` (la página web donde elige quién es en la plantilla). 404 si el token no
        existe; 409 ``invitation_error`` con el motivo de la web (usada, caducada, ya es miembro, ya tiene equipo en esa
        competición, email bloqueado, ficha de otra cuenta).
        """
        invitation = _invitation(token)
        try:
            membership = accept_invitation(invitation, request.user)
        except InvitationError as exc:
            raise ApiError("invitation_error", str(exc), 409)
        club = membership.club
        send_welcome_email(request.user, club, site_url=request.build_absolute_uri("/"))
        return json_ok({
            "club": {"name": club.name, "competition": club.competition},
            "team": team_summary(request.user), "next_path": reverse("member_welcome"),
        }, status=201)


@require_GET
def apple_app_site_association(request):
    """
    ``/.well-known/apple-app-site-association``: asocia los enlaces de invitación (``/invite/…``) con la app de iOS para que
    se abran en ella (enlaces universales). Se activa con ``APPLE_APP_LINK_IDS`` (``<ID de equipo>.<bundle id>``, separados
    por comas); vacío = 404. La app necesita además la capacidad Associated Domains (cuenta de pago de Apple).
    """
    app_ids = [item.strip() for item in settings.APPLE_APP_LINK_IDS.split(",") if item.strip()]
    if not app_ids:
        raise Http404
    return JsonResponse({"applinks": {"details": [{"appIDs": app_ids, "components": [{"/": "/invite/*"}]}]}})
