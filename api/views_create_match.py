"""``GET /api/v1/matches/new`` y ``POST /api/v1/matches``: crear un enfrentamiento desde la app nativa.

Reutiliza ``match.forms.MatchForm`` (las mismas reglas y mensajes que la web): la app no valida nada por su cuenta.
"""
import datetime

from django.utils.translation import gettext as _

from core.models import REPORT_SCOPES
from match.forms import MatchForm
from team.models import Team

from .errors import ApiError
from .responses import json_ok
from .teams import active_memberships, membership_for_team
from .views_base import ApiView
from .views_home import _team
from .views_matches_list import list_matches


def _rules(club):
    """Reglas de la competición que cambian el formulario: tipos, jornada y tipos de sede neutral."""
    rules = club.rules
    return {
        "match_types": [{"value": value, "label": str(label)} for value, label, _plural in rules.match_types],
        "default_type": rules.default_type,
        "has_rounds": bool(rules.league_type),
        "league_type": rules.league_type or None,
        "neutral_types": list(rules.neutral_types),
        "league_points": list(rules.league_points) if getattr(rules, "league_points", None) else None,
        "final_types": list(getattr(rules, "final_types", ()) or ()),
        "finals_min_regular": getattr(rules, "finals_min_regular", 0) or 0,
    }


def _form_options(request, club):
    """Equipos rivales, valores por defecto y opciones del informe para el equipo ``club``."""
    form = MatchForm(club=club, user=request.user)
    own = club.own_team
    time = form.initial.get("start_time")
    rivals = [{"id": str(t.public_id), "name": t.name, "location": t.location or ""}
              for t in Team.objects.filter(club=club, is_own=False, in_group=True).order_by("name")]
    return {
        "rules": _rules(club),
        "rivals": rivals,
        "rival_suggestions": form.rival_suggestions,
        "defaults": {
            "location": form.initial.get("location") or "",
            "time": time.strftime("%H:%M") if isinstance(time, datetime.time) else (time or None),
            "round_number": form.initial.get("round_number"),
            "report_scope": form.initial.get("report_scope") or form.default_report_scope,
            "own_team": own.name if own else "",
        },
        "report_scopes": [{"value": value, "label": str(label)} for value, label in REPORT_SCOPES],
        "other_competitions_available": bool(form.other_competitions_available),
    }


class NewMatchView(ApiView):
    """``GET /api/v1/matches/new``: equipos donde se puede crear y, con ``?team=<id>``, las opciones del formulario."""

    def get(self, request):
        """
        Sin ``team``: ``{"teams": […]}`` con los equipos que la cuenta gestiona (como en el Inicio), para elegir en
        qué liga y equipo se crea. Con ``team``: además ``rules``, ``rivals``, ``defaults``… de ese equipo (404 si no
        existe, 403 si no se gestiona).
        """
        team_id = request.GET.get("team")
        if team_id:
            membership = membership_for_team(request.user, team_id, manage=True)
            return json_ok({"team": _team(membership), **_form_options(request, membership.club)})
        active, _suspended = active_memberships(request.user)
        return json_ok({"teams": [_team(m) for m in active if m.can_manage]})


class MatchesView(ApiView):
    """``GET /api/v1/matches`` (lista, ver ``views_matches_list``) y ``POST /api/v1/matches`` (crea un enfrentamiento)."""

    def get(self, request):
        """Lista de Partidos con filtros y paginación."""
        return list_matches(request)

    def post(self, request):
        """
        Cuerpo: ``team`` (id del equipo), ``mode`` (``competitivo``/``amistoso``), ``match_type``, ``own_side``
        (``local``/``visiting``), ``rival`` (id de un equipo del grupo) o ``rival_name`` (amistoso y sede neutral),
        ``rival_link`` (id del equipo parecido o ``new``), ``start_date`` (AAAA-MM-DD), ``start_time`` (HH:MM),
        ``location``, ``round_number``, ``report_scope`` y ``report_other_competitions``. Valida con ``MatchForm``:
        400 ``invalid_match`` con ``fields`` (errores por campo; ``__all__`` los generales) y, si el rival escrito se
        parece a uno existente, ``rival_matches`` (``id``, ``name``) y ``rival_exact``. Devuelve 201 ``{"id"}``.
        """
        body = self.json_body(request)
        team_id = body.get("team")
        if not isinstance(team_id, str):
            raise ApiError("invalid_field", _("Campo no válido: %(name)s.") % {"name": "team"}, 400)
        club = membership_for_team(request.user, team_id, manage=True).club
        teams = {str(t.public_id): t for t in Team.objects.filter(club=club)}
        data = {}
        for name in ("mode", "match_type", "own_side", "rival_name", "start_date", "start_time", "location",
                     "round_number", "report_scope"):
            value = body.get(name)
            if value is not None:
                data[name] = str(value)
        if body.get("report_other_competitions"):
            data["report_other_competitions"] = "on"
        rival = body.get("rival")
        if rival:
            data["rival"] = str(teams[rival].pk) if rival in teams else "0"
        link = body.get("rival_link")
        if link:
            data["rival_link"] = "new" if link == "new" else str(teams[link].pk) if link in teams else "0"
        form = MatchForm(data, club=club, user=request.user)
        if not form.is_valid():
            fields = {name: [str(m) for m in messages] for name, messages in form.errors.items()}
            extra = {"fields": fields}
            if form.rival_matches:
                extra["rival_matches"] = [{"id": str(t.public_id), "name": t.name} for t in form.rival_matches]
                extra["rival_exact"] = bool(form.rival_exact)
            first = next(iter(form.errors.values()), [_("Revisa los datos del enfrentamiento.")])[0]
            raise ApiError("invalid_match", str(first), 400, extra=extra)
        match = form.save()
        return json_ok({"id": str(match.public_id)}, status=201)
