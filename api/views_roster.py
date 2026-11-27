"""Plantilla en la API: ``GET /teams/<id>/roster`` y las altas, bajas, ediciones y borrados de jugadores."""
from django.db import transaction
from django.utils.translation import gettext as _

from core import similarity
from core.models import Membership
from core.services import AltaError, RemovalError, dar_de_alta, dar_de_baja, open_matches_with
from match.models import Game
from players.forms import PlayerEditForm, PlayerForm
from players.models import Player

from .errors import ApiError
from .fields import invalid
from .responses import json_ok
from .teams import membership_for_team
from .views_base import ApiView
from .views_profile import decode_photo


def _roles(club):
    """Rol de cada cuenta con ficha en el club: ``{user_id: "captain" | "manager"}`` (los miembros sin rol no salen)."""
    names = {Membership.ADMIN: "captain", Membership.MANAGER: "manager"}
    return {m.user_id: names[m.role] for m in Membership.objects.filter(club=club, role__in=names)}


def _player(player, roles, pending=frozenset()):
    """Un jugador de la plantilla: nombre, foto, posición, mano, estado y a qué rol y cuenta está enlazado."""
    return {
        "id": str(player.public_id), "name": player.name, "last_name": player.last_name, "full_name": player.full_name,
        "photo": player.photo.url if player.photo else None,
        "position": player.position, "hand": player.skillfull_hand, "joined_season": player.joined_season,
        "in_team": player.in_team, "left_on": player.left_on.isoformat() if player.left_on else None,
        "snp_score": player.snp_score, "linked": player.user_id is not None, "role": roles.get(player.user_id),
        "had_account": player.past_user_id is not None,
        "copied_from": player.copied_from.club.name if player.copied_from_id else None,
        "pending_copy": player.pk in pending,
    }


def _team_player(user, player_id, *, manage=True):
    """Jugador ``player_id`` y la membresía de ``user`` en su club (gestor por defecto); 404 si no existe o no es de sus equipos."""
    player = Player.objects.select_related("club", "copied_from__club").filter(public_id=player_id).first()
    if player is None:
        raise ApiError("not_found", _("No encontrado."), 404)
    membership = membership_for_team(user, player.club.public_id, manage=manage)
    return player, membership


def _form_fields(errors):
    """Errores de un formulario de Django como ``{campo: [texto]}``, con ``hand`` en lugar de ``skillfull_hand``."""
    return {("hand" if f == "skillfull_hand" else f): [str(e) for e in errs] for f, errs in errors.items()}


def _validation_error(form):
    """400 ``validation_error`` con los errores por campo del formulario."""
    return ApiError("validation_error", _("Revisa los datos del formulario."), 400, extra={"fields": _form_fields(form.errors)})


def games_played(player):
    """Partidos (de cualquier enfrentamiento) en los que ha jugado ``player``."""
    from django.db.models import Q
    return Game.objects.filter(Q(player_1_local=player) | Q(player_2_local=player) |
                               Q(player_1_visiting=player) | Q(player_2_visiting=player)).count()


class RosterView(ApiView):
    """``GET /api/v1/teams/<id>/roster``: la plantilla del equipo."""

    def get(self, request, team_id):
        """
        ``team`` (``id``, ``name``, ``competition``, ``max_roster``), ``can_manage``, ``in_team`` (cuántos hay en la
        plantilla) y ``players`` ordenados por nombre. Quien gestiona ve también las bajas (``in_team`` falso); el resto
        solo la plantilla. ``role`` es ``captain`` o ``manager`` en las fichas con esa cuenta.
        """
        membership = membership_for_team(request.user, team_id)
        club = membership.club
        players = Player.objects.filter(club=club).select_related("copied_from__club").order_by("name", "last_name")
        if not membership.can_manage:
            players = players.filter(in_team=True)
        players = list(players)
        roles = _roles(club)
        return json_ok({
            "team": {"id": str(club.public_id), "name": club.name, "competition": club.competition,
                     "competition_name": club.rules.name, "max_roster": club.rules.max_roster},
            "can_manage": membership.can_manage,
            "in_team": sum(p.in_team for p in players),
            "players": [_player(p, roles) for p in players],
        })


class CreatePlayerView(ApiView):
    """``POST /api/v1/teams/<id>/players``: alta de un jugador en el equipo (gestores)."""

    def post(self, request, team_id):
        """
        Cuerpo ``name``, ``last_name`` y, opcionales, ``position``, ``hand``, ``joined_season`` y ``photo`` (base64). Con
        ``check: true`` solo valida y devuelve ``{"valid": true, "similar": [...]}`` sin crear nada. Si ya hay jugadores con un
        nombre igual o parecido responde 409 ``similar_players`` con ``similar``; se repite con ``confirm_similar: true`` si
        es otra persona. Devuelve el jugador creado (201).
        """
        membership = membership_for_team(request.user, team_id, manage=True)
        club = membership.club
        body = self.json_body(request)
        photo = decode_photo(body.get("photo"))
        data = {"name": body.get("name", ""), "last_name": body.get("last_name", ""),
                "position": body.get("position", "NONE"), "skillfull_hand": body.get("hand", "NONE"),
                "joined_season": body.get("joined_season", "")}
        form = PlayerForm(data, {"photo": photo} if photo else {}, club=club)
        form.uploader = request.user
        check = body.get("check") is True
        form.check_only = check
        if not form.is_valid():
            raise _validation_error(form)
        similar = similarity.similar_players(club, form.cleaned_data["name"], form.cleaned_data["last_name"])
        similar_out = [{"id": str(p.public_id), "name": p.full_name} for p in similar]
        if check:
            return json_ok({"valid": True, "similar": similar_out})
        if similar and body.get("confirm_similar") is not True:
            raise ApiError("similar_players", _("Ya existe un jugador parecido."), 409, extra={"similar": similar_out})
        player = form.save(commit=False)
        player.club = club
        player.team = club.own_team
        player.save()
        return json_ok({"player": _player(player, _roles(club))}, status=201)


class PlayerView(ApiView):
    """``PATCH /api/v1/players/<id>``: edita un jugador de la plantilla (gestores)."""

    def patch(self, request, player_id):
        """
        Cuerpo con cualquiera de ``name``, ``last_name``, ``position``, ``hand``, ``joined_season``, ``photo`` (base64) y
        ``remove_photo``. La baja y el alta se hacen con ``/players/<id>/leave`` y ``/join``. Devuelve el jugador.
        """
        player, membership = _team_player(request.user, player_id)
        body = self.json_body(request)
        remove = body.get("remove_photo", False)
        if not isinstance(remove, bool):
            raise invalid("remove_photo")
        photo = decode_photo(body.get("photo"))
        data = {"name": body.get("name", player.name), "last_name": body.get("last_name", player.last_name),
                "position": body.get("position", player.position), "skillfull_hand": body.get("hand", player.skillfull_hand),
                "joined_season": body.get("joined_season", player.joined_season), "in_team": player.in_team}
        form = PlayerEditForm(data, {"photo": photo} if photo else {}, instance=player)
        form.uploader = request.user
        if not form.is_valid():
            raise _validation_error(form)
        form.save()
        if remove and photo is None:
            player.photo = None
            player.save(update_fields=["photo"])
        return json_ok({"player": _player(player, _roles(membership.club))})


class LeaveView(ApiView):
    """``POST /api/v1/players/<id>/leave``: da de baja a un jugador de la plantilla."""

    def post(self, request, player_id):
        """
        Como la baja de la web: quien tiene cuenta enlazada sale del equipo (solo el capitán puede) y el capitán no se da de
        baja. 409 ``cannot_leave`` con el motivo. Devuelve el jugador, ``open_matches`` (enfrentamientos abiertos que se
        quedan con huecos) y ``roster_empty``.
        """
        player, membership = _team_player(request.user, player_id)
        if not player.in_team:
            raise ApiError("cannot_leave", _("Este jugador ya está de baja."), 409)
        affected = open_matches_with([player.pk])
        try:
            with transaction.atomic():
                dar_de_baja(player, request.user, request.build_absolute_uri("/"))
        except RemovalError as exc:
            raise ApiError("cannot_leave", str(exc), 409)
        player.refresh_from_db()
        club = membership.club
        return json_ok({"player": _player(player, _roles(club)), "open_matches": len(affected),
                        "roster_empty": not Player.objects.filter(club=club, in_team=True).exists()})


class JoinView(ApiView):
    """``POST /api/v1/players/<id>/join``: da de alta a un jugador que estaba de baja."""

    def post(self, request, player_id):
        """
        Si la ficha dejó una cuenta, se le invita por email a volver (``invited`` verdadero). 409 ``cannot_join`` con el motivo.
        Devuelve el jugador.
        """
        player, membership = _team_player(request.user, player_id)
        if player.in_team:
            raise ApiError("cannot_join", _("Este jugador ya está en la plantilla."), 409)
        try:
            with transaction.atomic():
                invitation = dar_de_alta(player, request.user, request.build_absolute_uri("/"))
        except AltaError as exc:
            raise ApiError("cannot_join", str(exc), 409)
        player.refresh_from_db()
        return json_ok({"player": _player(player, _roles(membership.club)), "invited": invitation is not None})


class DeletePlayerView(ApiView):
    """``POST /api/v1/players/<id>/delete``: elimina un jugador que nunca ha jugado."""

    def post(self, request, player_id):
        """
        409 ``cannot_delete`` si la ficha es de una cuenta (actual o anterior) o ha jugado partidos: se da de baja en su lugar.
        Se borran también sus convocatorias y advertencias. Devuelve ``{"deleted": true}``.
        """
        player, _membership = _team_player(request.user, player_id)
        if player.user_id or player.past_user_id:
            raise ApiError("cannot_delete", _("Esta ficha es de una cuenta y no se puede eliminar para no borrar sus "
                                              "estadísticas. Dala de baja para sacarla de la plantilla."), 409)
        if games_played(player):
            raise ApiError("cannot_delete", _("Este jugador ha jugado partidos y no se puede eliminar para no borrarlos "
                                              "de las estadísticas del equipo y de sus compañeros. Dalo de baja."), 409)
        player.delete()
        return json_ok({"deleted": True})
