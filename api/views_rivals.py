"""
Equipos rivales en la API: ``GET /teams/<id>/rivals``, la misma lista que ``team.views.list_team`` (búsqueda por nombre o
localidad y casilla «solo mi grupo»). Las altas, ediciones y bajas llegan en endpoints propios.
"""
from django.db.models import Q
from django.utils.translation import gettext as _  # noqa: F401  (convención del módulo: textos traducibles)

from team.models import Team

from .responses import json_ok
from .teams import membership_for_team
from .views_base import ApiView


def _rival(team):
    """Un rival: identificador público, nombre, localidad, división, si es de mi grupo y su foto."""
    return {
        "id": str(team.public_id), "name": team.name, "location": team.location,
        "division": team.division, "division_label": str(team.get_division_display()) if team.division else "",
        "in_group": team.in_group, "photo": team.photo.url if team.photo else None,
    }


class RivalsView(ApiView):
    """``GET /api/v1/teams/<id>/rivals``: rivales del equipo."""

    def get(self, request, team_id):
        """
        Parámetros ``search`` (nombre o localidad) y ``group`` (``0`` para ver también los de fuera del grupo; solo lo respetan
        capitán y gestores, como en la web). Devuelve ``can_manage``, ``only_group``, ``count`` y ``rivals`` por nombre; con
        ``group=0`` primero los del grupo.
        """
        membership = membership_for_team(request.user, team_id)
        club = membership.club
        only_group = request.GET.get("group", "1") != "0" or not membership.can_manage
        teams = Team.objects.filter(club=club, is_own=False)
        teams = teams.filter(in_group=True).order_by("name") if only_group else teams.order_by("-in_group", "name")
        search = request.GET.get("search", "").strip()
        if search:
            teams = teams.filter(Q(name__icontains=search) | Q(location__icontains=search))
        rivals = [_rival(t) for t in teams]
        return json_ok({"can_manage": membership.can_manage, "only_group": only_group, "count": len(rivals), "rivals": rivals})
