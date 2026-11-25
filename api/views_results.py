"""``/api/v1/matches/<id>/results``, ``…/games/<id>/result`` y ``…/close``: resultados y cierre del acta para la app nativa."""
import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from match import outcomes
from match.models import Game, Result
from match.views import _mark_pair_no_show, close_match_now, valid_close_match

from .errors import ApiError
from .fields import invalid
from .responses import json_ok
from .views_base import ApiView
from .views_match import _managed_match

_SET_FIELDS = [f"set{n}_{side}" for n in (1, 2, 3) for side in ("local", "visiting")]


def _own_keys(match):
    """Nombres de campo del equipo propio y del rival (``local``/``visiting``) en este enfrentamiento."""
    return ("local", "visiting") if match.own_is_local else ("visiting", "local")


def _result_data(match, result):
    """Resultado con los sets desde el punto de vista del equipo propio (``[propios, rivales]``) o ``None``."""
    if result is None:
        return None
    own, rival = _own_keys(match)
    sets = []
    for n in (1, 2, 3):
        a, b = getattr(result, f"set{n}_{own}"), getattr(result, f"set{n}_{rival}")
        if a is not None and b is not None:
            sets.append([a, b])
    injured = result.injured_side
    mine = "own" if injured == own else "rival" if injured else ""
    return {"sets": sets, "retired": bool(result.retired), "injured": mine if result.retired else ""}


def _game_data(match, game):
    """Un partido: ``id``, ``n``, ``points``, ``no_show``, jugadores propios, ``state`` y ``result``."""
    own = "local" if match.own_is_local else "visiting"
    players = [getattr(game, f"player_{i}_{own}") for i in (1, 2)]
    result = game.results.all()[0] if game.results.all() else None
    win = outcomes.WINNER_LOCAL if match.own_is_local else outcomes.WINNER_VISITING
    return {"id": str(game.public_id), "n": game.n_game, "points": game.score, "no_show": game.no_show,
            "players": [p.short_name for p in players if p is not None],
            "state": "" if not game.winner else ("win" if game.winner == win else "loss"),
            "result": _result_data(match, result)}


def _games(match):
    """Partidos del enfrentamiento con sus resultados, en orden de juego."""
    return list(match.games.order_by("n_game").select_related(
        "player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting").prefetch_related("results"))


def _open_game(user, match_id, game_id):
    """Enfrentamiento gestionado y partido suyo, con el acta abierta (409 ``locked`` si no); 404 si no existen."""
    match, _membership = _managed_match(user, match_id)
    game = Game.objects.filter(match=match, public_id=game_id).first()
    if game is None:
        raise ApiError("not_found", _("No encontrado."), 404)
    if not match.draft_mode:
        raise ApiError("locked", _("El acta está cerrada: reábrela para cambiar los resultados."), 409)
    return match, game


class MatchResultsView(ApiView):
    """``GET /api/v1/matches/<id>/results``: partidos con su resultado y si se puede cerrar el acta."""

    def get(self, request, match_id):
        """
        Solo capitán y gestores (404 si no). Devuelve ``{"open", "games", "can_close", "missing", "future",
        "pair_no_show", "injury_completes"}``: ``games[]`` con ``id``, ``n``, ``points``, ``no_show`` (``own``/``rival``/vacío),
        ``players``, ``state`` (``win``/``loss``/vacío) y ``result`` (``sets`` como ``[propios, rivales]``, ``retired``,
        ``injured`` ``own``/``rival``) o ``null``; ``can_close`` si ya se puede cerrar, ``missing`` los partidos sin resultado
        y ``future`` si la fecha aún no ha llegado (el cierre pedirá confirmar).
        """
        match, _membership = _managed_match(request.user, match_id)
        games = _games(match)
        valid, _message = valid_close_match(games, match)
        missing = [g.n_game for g in games if not g.no_show and not g.results.all()]
        rules = match.club.rules
        return json_ok({
            "open": bool(match.draft_mode), "games": [_game_data(match, g) for g in games],
            "can_close": bool(valid and match.draft_mode), "missing": missing,
            "future": match.start_date > datetime.date.today(),
            "pair_no_show": bool(rules.pair_no_show), "injury_completes": bool(rules.injury_completes)})


class GameResultView(ApiView):
    """``PUT`` y ``DELETE /api/v1/matches/<id>/games/<game_id>/result``: poner, cambiar o borrar el resultado de un partido."""

    def put(self, request, match_id, game_id):
        """
        Cuerpo ``{"sets": [[propios, rivales], …] (1 a 3), "retired"?, "injured"?: "own" | "rival"}``. Crea o cambia el
        resultado con las reglas de la web (``Result.clean``: sets válidos, lesión, ganador). Solo con el acta abierta (409
        ``locked``) y si la pareja se presentó (409 ``no_show``); 400 ``validation_error`` con ``fields.sets`` y el motivo.
        Devuelve el partido (como ``games[]`` de ``GET …/results``).
        """
        body = self.json_body(request)
        sets, retired, injured = body.get("sets"), body.get("retired", False), body.get("injured", "")
        if (not isinstance(sets, list) or not 1 <= len(sets) <= 3 or not isinstance(retired, bool)
                or injured not in ("", "own", "rival")
                or not all(isinstance(s, list) and len(s) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in s)
                           for s in sets)):
            raise invalid("sets")
        match, game = _open_game(request.user, match_id, game_id)
        if game.no_show:
            raise ApiError("no_show", _("Esta pareja no se presentó: alinea las parejas antes de poner el resultado."), 409)
        own, rival = _own_keys(match)
        result = game.results.first() or Result(game=game)
        for n in (1, 2, 3):
            pair = sets[n - 1] if n <= len(sets) else (None, None)
            setattr(result, f"set{n}_{own}", pair[0])
            setattr(result, f"set{n}_{rival}", pair[1])
        result.retired = retired
        result.injured_side = (own if injured == "own" else rival if injured == "rival" else "") if retired else ""
        try:
            result.full_clean(exclude=["game", "result", "retired", "injured_side"] + _SET_FIELDS, validate_unique=False)
            result.result = result.determine_winner()
        except ValidationError as error:
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400,
                           extra={"fields": {"sets": [str(m) for m in error.messages]}})
        with transaction.atomic():
            result.save()
            game.winner = outcomes.winner_of(result.result)
            game.save(update_fields=["winner"])
        game = Game.objects.prefetch_related("results").select_related(
            "player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting").get(pk=game.pk)
        return json_ok(_game_data(match, game))

    def delete(self, request, match_id, game_id):
        """Borra el resultado del partido (como la web: el ganador vuelve a estar sin decidir). 409 ``locked`` con el acta cerrada."""
        match, game = _open_game(request.user, match_id, game_id)
        with transaction.atomic():
            game.results.all().delete()
            game.winner = None
            game.save(update_fields=["winner"])
        game = Game.objects.prefetch_related("results").select_related(
            "player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting").get(pk=game.pk)
        return json_ok(_game_data(match, game))


class GameNoShowView(ApiView):
    """``POST /api/v1/matches/<id>/games/<game_id>/no-show``: marca la pareja que no se presentó (competiciones que lo admiten)."""

    def post(self, request, match_id, game_id):
        """
        Cuerpo ``{"side": "own" | "rival"}``. Borra el resultado y los jugadores del partido (los puntos se reparten al cerrar el
        acta). 400 si el cuerpo no cuadra o la competición no admite pareja no presentada; 409 ``locked`` con el acta cerrada.
        Devuelve el partido.
        """
        body = self.json_body(request)
        side = body.get("side")
        if side not in (Game.NO_SHOW_OWN, Game.NO_SHOW_RIVAL):
            raise invalid("side")
        match, game = _open_game(request.user, match_id, game_id)
        if not match.club.rules.pair_no_show:
            raise invalid("side")
        _mark_pair_no_show(game, side)
        game = Game.objects.prefetch_related("results").select_related(
            "player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting").get(pk=game.pk)
        return json_ok(_game_data(match, game))


class CloseMatchView(ApiView):
    """``POST /api/v1/matches/<id>/close``: cierra el acta (mismas reglas que la web: ``match.views.close_match_now``)."""

    def post(self, request, match_id):
        """
        Cuerpo opcional ``{"confirm_future"?, "resend_email"?}`` (booleanos). Solo quien gestiona (404 si no). 409
        ``cannot_close`` con el motivo (faltan partidos o resultados, ya cerrada) y 409 ``future_date`` si la fecha aún no ha
        llegado (repetir con ``confirm_future``). Devuelve ``{"closed": true, "summary"}`` con el texto del resultado.
        """
        body = self.json_body(request)
        flags = {}
        for name in ("confirm_future", "resend_email"):
            value = body.get(name, False)
            if not isinstance(value, bool):
                raise invalid(name)
            flags[name] = value
        match, _membership = _managed_match(request.user, match_id)
        code, message = close_match_now(match, confirm_future=flags["confirm_future"], resend_email=flags["resend_email"])
        if code != "closed":
            raise ApiError("future_date" if code == "future" else "cannot_close", str(message), 409)
        return json_ok({"closed": True, "summary": str(message)})
