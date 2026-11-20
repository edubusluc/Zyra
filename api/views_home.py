"""``GET /api/v1/home``: lo que necesita el Inicio nativo de la app."""
from django.db.models import Q

from core.competitions import COMPETITIONS
from core.models import Membership
from players.models import Player, current_season

from .responses import json_ok
from .views_base import ApiView


def _display_name(user):
    """Nombre con el que se saluda: el de pila, y si no hay, el usuario."""
    return (user.first_name or "").strip() or user.get_username()


def _memberships(user):
    """Membresías de la cuenta: (activas, clubes suspendidos), con las activas en el orden de las competiciones.

    Mismo criterio que el middleware de la web: no cuentan los clubes suspendidos ni los archivados.
    """
    memberships = list(Membership.objects.filter(user=user).select_related("club").order_by("club__name"))
    suspended = [m.club for m in memberships if m.club.is_suspended]
    active = [m for m in memberships if not m.club.is_suspended and not m.club.is_archived]
    order = list(COMPETITIONS)
    active.sort(key=lambda m: order.index(m.club.competition) if m.club.competition in order else len(order))
    return active, suspended


def _team(membership):
    """Un equipo de la cuenta: nombre, escudo, competición, rol y categoría o división."""
    club = membership.club
    team = club.own_team
    rules = club.rules
    return {
        "id": str(club.public_id),
        "name": club.name,
        "crest": team.photo.url if team is not None and team.photo else None,
        "competition": club.competition,
        "competition_name": rules.name,
        "has_snp": bool(rules.has_snp),
        "role": membership.role,
        "role_label": str(membership.team_role_label),
        "can_manage": membership.can_manage,
        "division": team.division if team is not None else "",
        "division_label": str(team.get_division_display()) if team is not None and team.division else None,
    }


class HomeView(ApiView):
    """
    ``GET /api/v1/home``: base del Inicio nativo. Dice en qué situación está la cuenta (``state``: ``ok``,
    ``no_team`` o ``suspended``), sus equipos con el rol en cada uno y los datos para el saludo. Las tarjetas
    del Inicio (próximo enfrentamiento, pendientes, «Mi forma», avisos…) se irán añadiendo a esta respuesta.
    """

    def get(self, request):
        """Resumen de la cuenta para pintar la cabecera del Inicio y decidir qué pantalla mostrar."""
        user = request.user
        active, suspended = _memberships(user)
        players = Player.objects.filter(Q(user=user) | Q(past_user=user))
        if active:
            state = "ok"
        elif suspended:
            state = "suspended"
        else:
            state = "no_team"
        return json_ok({
            "state": state,
            "user": {"username": user.get_username(), "display_name": _display_name(user)},
            "season": current_season(),
            "teams": [_team(m) for m in active],
            "suspended_clubs": [{"name": club.name} for club in suspended],
            "has_player": players.filter(user=user, club__in=[m.club_id for m in active]).exists(),
            "has_history": players.exists(),
        })
