"""``GET /api/v1/home``: lo que necesita el Inicio nativo de la app."""
import datetime

from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext as _

from call.models import Call
from core.competitions import COMPETITIONS
from core.models import Membership
from match.models import Game, Match
from match.phase import player_status
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


def _week_end(day):
    """Domingo de la semana natural que contiene ``day`` (el carrusel solo llega hasta ahí)."""
    return day + datetime.timedelta(days=6 - day.weekday())


def _kind_label(match):
    """«Jornada 6» en la liga regular; en el resto, el tipo («Play Off», «Amistoso»…)."""
    if match.round_number and match.is_league:
        return _("Jornada %(n)s") % {"n": match.round_number}
    return str(match.type_label)


def _side(team, name):
    """Un lado del enfrentamiento: nombre y si es el equipo propio (``team`` puede faltar si el rival se escribió a mano)."""
    return {"name": name, "is_own": bool(team and team.is_own)}


def _me(status, linked, can_manage):
    """
    Estado del jugador en un enfrentamiento: ``{"state", "game"?, "points"?, "partner"?}`` o None si no aplica.
    ``unlinked`` (cuenta sin ficha enlazada y sin gestionar), ``no_call``, ``applied_open``, ``called``,
    ``called_no_pair``, ``not_called`` o ``not_called_open``. Mismas reglas que la tarjeta de la web.
    """
    if not linked:
        return None if can_manage else {"state": "unlinked"}
    if not status["has_call"]:
        return {"state": "no_call"}
    if status["called"] and not status["closed"]:
        return {"state": "applied_open"}
    if status["called"]:
        game = status["game"]
        if game is None:
            return {"state": "called_no_pair"}
        partner = status["partner"]
        return {"state": "called", "game": game.n_game, "points": game.score,
                "partner": partner.full_name if partner else None}
    return {"state": "not_called" if status["closed"] else "not_called_open"}


def _upcoming(user, memberships, today):
    """
    Carrusel «Próximo enfrentamiento»: enfrentamientos abiertos de todos los equipos activos que caen en la semana
    natural del más cercano (como en la web), el más cercano primero.
    """
    clubs = [m.club for m in memberships]
    members = {m.club_id: m for m in memberships}
    matches = list(Match.objects.filter(club__in=clubs, draft_mode=True, start_date__gte=today)
                   .select_related("local", "visiting", "club").order_by("start_date", "id")[:200])
    if not matches:
        return []
    last = _week_end(matches[0].start_date)
    matches = [m for m in matches if m.start_date <= last]
    players = {p.club_id: p for p in Player.objects.filter(user=user, club__in=clubs)}
    calls = {c.match_id: c for c in Call.objects.filter(match__in=matches)}
    games = {}
    for game in Game.objects.filter(match__in=matches).select_related(
            "player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting"):
        games.setdefault(game.match_id, []).append(game)
    out = []
    for m in matches:
        player = players.get(m.club_id)
        status = player_status(player, calls.get(m.id), games.get(m.id, [])) if player else None
        can_manage = members[m.club_id].can_manage
        out.append({
            "id": str(m.public_id),
            "team_id": str(m.club.public_id),
            "competition": m.club.competition,
            "competition_name": m.club.rules.name,
            "kind_label": _kind_label(m),
            "date": m.start_date.isoformat(),
            "days_left": (m.start_date - today).days,
            "time": m.start_time.strftime("%H:%M") if m.start_time else None,
            "location": m.location or None,
            "maps_url": m.maps_url or None,
            "neutral_venue": bool(m.neutral_venue),
            "local": _side(m.local, m.local_name),
            "visiting": _side(m.visiting, m.visiting_name),
            "me": _me(status, player is not None, can_manage),
            "web_path": reverse("call_for_match", args=[m.public_id]),
        })
    return out


class HomeView(ApiView):
    """
    ``GET /api/v1/home``: base del Inicio nativo. Dice en qué situación está la cuenta (``state``: ``ok``,
    ``no_team`` o ``suspended``), sus equipos con el rol en cada uno, los datos para el saludo y ``upcoming``, el
    carrusel «Próximo enfrentamiento». Las demás tarjetas del Inicio (pendientes, «Mi forma», avisos…) se irán
    añadiendo a esta respuesta.
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
            "upcoming": _upcoming(user, active, datetime.date.today()),
            "has_player": players.filter(user=user, club__in=[m.club_id for m in active]).exists(),
            "has_history": players.exists(),
        })
