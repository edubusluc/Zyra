"""
Equipos rivales en la API: ``GET /teams/<id>/rivals`` (la misma lista que ``team.views.list_team``: búsqueda por nombre o
localidad y casilla «solo mi grupo»), ``POST /teams/<id>/rivals`` (alta) y ``PUT /teams/<id>/rivals/<rival>`` (edición). Usan
el mismo formulario que la web (``team.forms.Teamform``). Las bajas llegan en endpoints propios.
"""
from django.db.models import Q
from django.utils.translation import gettext as _

from core import similarity
from team.forms import Teamform
from team.models import Team, divisions_for
from match.locations import propagate_team_location

from .errors import ApiError
from .responses import json_ok
from .teams import membership_for_team
from .views_base import ApiView
from .views_profile import decode_photo


def _rival(team):
    """Un rival: identificador público, nombre, localidad, división, si es de mi grupo y su foto."""
    return {
        "id": str(team.public_id), "name": team.name, "location": team.location,
        "gender": team.gender, "country": team.country,
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
        return json_ok({"can_manage": membership.can_manage, "only_group": only_group, "count": len(rivals), "rivals": rivals,
                        "options": _options(club) if membership.can_manage else None})

    def post(self, request, team_id):
        """
        Alta de un rival (capitán y gestores). Cuerpo ``name``, ``location``, ``gender``, ``country``, ``division``, ``in_group``
        (por defecto verdadero: copia categoría, país y división del equipo propio) y ``photo`` (base64, opcional). Con
        ``check: true`` solo valida y devuelve ``{"valid": true, "similar": [...], "exists": bool}``. Si ya hay equipos con un
        nombre parecido responde 409 ``similar_teams`` (se repite con ``confirm_similar: true``); si coincide con uno dado de
        baja del grupo, 409 ``team_exists`` con su ``id``. Devuelve el rival creado (201).
        """
        club = membership_for_team(request.user, team_id, manage=True).club
        body = self.json_body(request)
        photo = decode_photo(body.get("photo"))
        form = Teamform(_form_data(body, None), {"photo": photo} if photo else {}, club=club)
        form.uploader = request.user
        check = body.get("check") is True
        form.check_only = check
        if not form.is_valid():
            raise _validation_error(form)
        similar = similarity.similar_teams(club, form.cleaned_data["name"])
        similar_out = [{"id": str(t.public_id), "name": t.name, "in_group": t.in_group} for t in similar]
        exists = bool(form.exact_matches)
        if check:
            return json_ok({"valid": True, "exists": exists, "similar": similar_out})
        if exists:
            raise ApiError("team_exists", _("Ya existe ese equipo, dado de baja de tu grupo."), 409,
                           extra={"id": str(form.exact_matches[0].public_id)})
        if similar and body.get("confirm_similar") is not True:
            raise ApiError("similar_teams", _("Ya existe un equipo parecido."), 409, extra={"similar": similar_out})
        team = form.save(commit=False)
        team.club = club
        team.save()
        return json_ok(_rival(team), status=201)


class RivalView(ApiView):
    """``PUT /api/v1/teams/<id>/rivals/<rival>``: edita un rival (capitán y gestores)."""

    def put(self, request, team_id, rival_id):
        """
        Cuerpo con los mismos campos que el alta; los que no vengan conservan su valor. 400 ``validation_error`` con ``fields``;
        404 si el rival no es de este equipo. Si cambia la localidad se actualiza en los enfrentamientos abiertos (``moved``).
        """
        club = membership_for_team(request.user, team_id, manage=True).club
        team = Team.objects.filter(club=club, is_own=False, public_id=rival_id).first()
        if team is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        body = self.json_body(request)
        photo = decode_photo(body.get("photo"))
        form = Teamform(_form_data(body, team), {"photo": photo} if photo else {}, instance=team, club=club)
        form.uploader = request.user
        old_location = team.location
        if not form.is_valid():
            raise _validation_error(form)
        team = form.save()
        moved = propagate_team_location(team, old_location)
        return json_ok({**_rival(team), "moved": moved})


def _options(club):
    """Opciones de los campos desplegables y valores propuestos para un rival nuevo (los del equipo propio)."""
    own = club.own_team
    return {
        "genders": [{"key": k, "label": str(v)} for k, v in Team.GENDERS],
        "countries": [{"key": k, "label": str(v)} for k, v in Team.COUNTRIES],
        "divisions": [{"key": k, "label": str(v)} for k, v in divisions_for(club.rules)],
        "defaults": {"gender": own.gender, "country": own.country, "division": own.division} if own else {},
    }


def _form_data(body, team):
    """Datos del formulario a partir del cuerpo; en una edición, lo que no viene conserva el valor del equipo."""
    data = {}
    for key in ("name", "location", "gender", "country", "division"):
        if key in body:
            data[key] = "" if body[key] is None else str(body[key]).strip()
        elif team is not None:
            data[key] = getattr(team, key)
    in_group = body["in_group"] if "in_group" in body else (team.in_group if team is not None else True)
    if in_group is True:
        data["in_group"] = "on"
    return data


def _validation_error(form):
    """400 ``validation_error`` con los errores por campo del formulario."""
    return ApiError("validation_error", _("Revisa los datos del formulario."), 400, extra={"fields": {
        name: [str(e) for e in errors] for name, errors in form.errors.items()}})
