"""
Edición del equipo propio en la API: ``GET/PUT /teams/<id>/own-team``. Usa el mismo formulario que la web (``team.forms.Teamform``,
vista ``edit_team``): nombre, categoría, país, división, sede y hora habitual. La foto no se edita aquí.
"""
from django.utils.translation import gettext as _

from match.locations import propagate_team_location
from team.forms import Teamform
from team.models import Team, divisions_for

from .errors import ApiError
from .responses import json_ok
from .teams import membership_for_team
from .views_base import ApiView


def _team_json(club, team):
    """El equipo propio y las opciones de cada campo desplegable."""
    return {
        "id": str(team.public_id), "name": team.name, "gender": team.gender, "country": team.country, "division": team.division,
        "location": team.location, "default_time": f"{team.default_time:%H:%M}" if team.default_time else None,
        "genders": [{"key": k, "label": str(v)} for k, v in Team.GENDERS],
        "countries": [{"key": k, "label": str(v)} for k, v in Team.COUNTRIES],
        "divisions": [{"key": k, "label": str(v)} for k, v in divisions_for(club.rules)],
    }


class OwnTeamView(ApiView):
    """``/api/v1/teams/<id>/own-team``: ver y editar el equipo propio (capitán y gestores, como la web)."""

    def get(self, request, team_id):
        """``{"id", "name", "gender", "country", "division", "location", "default_time", "genders", "countries", "divisions"}``."""
        club = membership_for_team(request.user, team_id, manage=True).club
        return json_ok(_team_json(club, club.own_team))

    def put(self, request, team_id):
        """
        Cuerpo con ``name``, ``gender``, ``country``, ``division``, ``location`` y ``default_time`` (HH:MM, opcional). Los que no
        vengan conservan su valor. 400 ``validation_error`` con ``fields``. Si cambia la sede se actualiza también en los
        enfrentamientos abiertos (``moved``).
        """
        club = membership_for_team(request.user, team_id, manage=True).club
        team = club.own_team
        body = self.json_body(request)
        data = {"name": team.name, "gender": team.gender, "country": team.country, "division": team.division,
                "location": team.location, "default_time": f"{team.default_time:%H:%M}" if team.default_time else ""}
        for key in data:
            if key in body:
                data[key] = "" if body[key] is None else str(body[key]).strip()
        form = Teamform(data, instance=team, club=club)
        if not form.is_valid():
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400, extra={"fields": {
                name: [str(e) for e in errors] for name, errors in form.errors.items()}})
        old_location = team.location
        form.uploader = request.user
        team = form.save()
        moved = propagate_team_location(team, old_location)
        return json_ok({**_team_json(club, team), "moved": moved})
