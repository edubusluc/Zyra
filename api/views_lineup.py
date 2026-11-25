"""``/api/v1/matches/<id>/lineup``: parejas y orden de los partidos (alinear y editar) para la app nativa."""
import json

from django.utils.translation import gettext as _

from call.models import Call
from core.competitions import competition_for
from match import lineup as lineup_logic
from match.models import Game
from match.report import suggested_lineups
from match.views import validate_game_for_match

from .errors import ApiError
from .fields import invalid
from .responses import json_ok
from .views_base import ApiView
from .views_match import _managed_match


def _own_ids(match, game):
    """Ids internos de los dos jugadores del club en un partido (``None`` si la pareja no se presenta)."""
    side = "local" if match.own_is_local else "visiting"
    first, second = getattr(game, f"player_1_{side}_id"), getattr(game, f"player_2_{side}_id")
    return (first, second) if first and second else None


def _locked_reason(match, call):
    """Motivo por el que no se pueden alinear parejas (acta cerrada o falta convocatoria cerrada), o ``None``."""
    if not match.draft_mode:
        return _("El acta está cerrada: reábrela para cambiar las parejas.")
    valid, message = validate_game_for_match(call)
    return None if valid else str(message)


class MatchLineupView(ApiView):
    """``GET`` y ``PUT /api/v1/matches/<id>/lineup``: convocados, parejas actuales y sugerencias; alta y cambio de parejas."""

    def get(self, request, match_id):
        """
        Solo capitán y gestores (404 si no, o sin convocatoria). Devuelve ``{"exists", "locked", "pairs", "ordered",
        "points", "players", "games", "suggestions"}``: ``locked`` es el motivo si no se puede alinear (o ``null``),
        ``pairs`` las parejas que hay que completar, ``ordered`` si el orden cuenta (SNP: se ordenan por la suma de
        puntos SNP), ``points`` lo que vale cada partido, ``players[]`` los convocados (``id``, ``name``, ``snp``),
        ``games[]`` las parejas actuales en orden (``id``, ``n``, ``points``, ``players`` con dos ids o ``null`` si no
        se presenta, ``has_result``) y ``suggestions[]`` las alineaciones recomendadas A y B (``key``, ``title``, ``win``,
        ``expected``, ``explanation``, ``pairs``) solo si se puede alinear.
        """
        match, _membership = _managed_match(request.user, match_id)
        call = Call.objects.filter(match=match).first()
        if call is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        comp = competition_for(match)
        locked = _locked_reason(match, call)
        players = sorted(call.players.all(), key=lambda p: (p.name, p.last_name))
        public = {p.id: str(p.public_id) for p in players}
        games = list(Game.objects.filter(match=match).order_by("n_game"))
        data = {
            "exists": bool(games), "locked": locked, "pairs": lineup_logic.required_pairs(call),
            "ordered": comp.ordered_pairs, "points": [comp.points_for(n) for n in range(1, comp.games + 1)],
            "players": [{"id": public[p.id], "name": p.short_name, "snp": p.snp_score} for p in players],
            "games": [{
                "id": str(g.public_id), "n": g.n_game, "points": g.score, "has_result": g.results.exists(),
                "players": None if _own_ids(match, g) is None else [public.get(i) for i in _own_ids(match, g)],
            } for g in games],
            "suggestions": [] if locked else [{
                **{k: s[k] for k in ("key", "title", "win", "expected", "explanation")},
                "pairs": [[public[i] for i in pair] for pair in s["pairs"]],
            } for s in suggested_lineups(call)],
        }
        return json_ok(data)

    def put(self, request, match_id):
        """
        Cuerpo ``{"pairs": [[id, id], …]}`` con las parejas en orden de juego (ids de ``players``). Crea los partidos
        (si no había) o reasigna las parejas del partido 1, 2… con las reglas de la web (``match.lineup``). 400
        ``invalid_field`` si el cuerpo no cuadra; 409 ``locked`` (acta cerrada o convocatoria sin cerrar) y 409
        ``invalid_lineup`` con el motivo (faltan parejas, jugador repetido, partido con resultado…). Devuelve
        ``{"created", "count"}``.
        """
        body = self.json_body(request)
        pairs = body.get("pairs")
        if not isinstance(pairs, list) or not all(
                isinstance(p, list) and len(p) == 2 and all(isinstance(i, str) for i in p) for p in pairs):
            raise invalid("pairs")
        match, _membership = _managed_match(request.user, match_id)
        call = Call.objects.filter(match=match).first()
        if call is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        reason = _locked_reason(match, call)
        if reason:
            raise ApiError("locked", reason, 409)
        internal = {str(p.public_id): p.id for p in call.players.all()}
        games = list(Game.objects.filter(match=match).order_by("n_game"))
        try:
            ids = [[internal[i] for i in pair] for pair in pairs]
        except KeyError:
            raise ApiError("invalid_lineup", _("Los dos jugadores de cada pareja deben estar en la convocatoria."), 409)
        raw = json.dumps([{"gameId": games[n].id if n < len(games) else None, "player1Id": a, "player2Id": b}
                          for n, (a, b) in enumerate(ids)])
        try:
            parsed = lineup_logic.parse_lineup(raw, call, match_games=games or None)
            if games:
                lineup_logic.update_games(match, parsed)
            else:
                lineup_logic.create_games(match, parsed)
        except lineup_logic.LineupError as error:
            raise ApiError("invalid_lineup", str(error), 409)
        return json_ok({"created": not games, "count": len(pairs)})
