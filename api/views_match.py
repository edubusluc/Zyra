"""``GET /api/v1/matches/<id>``: la ficha nativa de un enfrentamiento (solo lectura)."""
import datetime

from django.urls import reverse
from django.utils.translation import gettext as _

from call import availability as availability_logic
from call.models import Availability, Call
from core.competitions import competition_for
from core.templatetags.zyra_format import date_short
from match import outcomes
from match.models import Game, Match
from match.phase import (CLOSE_CALL, CLOSE_MATCH, CREATE_CALL, CREATE_GAMES, ENTER_RESULTS, NOTHING, STEPS, phase_for,
                         player_status)
from match.views import OUTCOME_LABELS, call_roster, club_score, lineup_rows, match_outcome, stage_countdown
from players.models import Player

from .errors import ApiError
from .responses import json_ok
from .views_base import ApiView
from .views_home import _kind_label, _me, _memberships, _side


def _steps(phase):
    """Las cuatro fases con su estado (``done``, ``cur`` o ``todo``), como el indicador de la web."""
    return [{"label": str(label), "state": {"done": "done", "cur": "cur"}.get(step["state"], "todo")}
            for label, step in zip(STEPS, phase.track)]


def _primary(match, phase, can_manage):
    """
    Acción principal de quien gestiona: ``{"key", "label", "web_path", "enabled", "reason"}``. En esta fase la app
    abre el paso en la web; ``enabled`` es falso (con ``reason``) si todavía no se puede dar el paso.
    """
    ficha = reverse("call_for_match", args=[match.public_id])
    if not can_manage:
        return None
    if phase.action == CREATE_CALL:
        return {"key": "create_call", "label": _("Crear convocatoria"), "web_path": reverse("create_call", args=[match.public_id]),
                "enabled": True, "reason": None}
    if phase.action == CLOSE_CALL:
        blocked = phase.blocked_by_min
        reason = (_("Faltan %(n)s apuntados") % {"n": phase.missing_players}) if blocked else None
        return {"key": "close_call", "label": _("Cerrar convocatoria"), "web_path": ficha, "enabled": not blocked,
                "reason": reason}
    if phase.action == CREATE_GAMES:
        return {"key": "create_games", "label": _("Alinear parejas"), "web_path": reverse("create_game", args=[match.public_id]),
                "enabled": True, "reason": None}
    if phase.action == ENTER_RESULTS:
        return {"key": "enter_results", "label": _("Poner resultados"),
                "web_path": reverse("enter_results", args=[match.public_id]), "enabled": True, "reason": None}
    if phase.action == CLOSE_MATCH:
        return {"key": "close_match", "label": _("Cerrar acta"), "web_path": ficha, "enabled": True, "reason": None}
    if phase.action == NOTHING:
        return {"key": "share_result", "label": _("Compartir resultado"), "web_path": ficha, "enabled": True,
                "reason": None}
    return None


def _sets(result, own_is_local):
    """Sets del partido desde el punto de vista del equipo propio: «6-3 4-6 7-5»."""
    pairs = [(result.set1_local, result.set1_visiting), (result.set2_local, result.set2_visiting),
             (result.set3_local, result.set3_visiting)]
    return " ".join(f"{a}-{b}" if own_is_local else f"{b}-{a}" for a, b in pairs if a is not None and b is not None)


def _games(match, games, me_id):
    """Parejas propias de cada partido. Con el acta cerrada también con el resultado de cada uno."""
    own_is_local = match.own_is_local
    own_win = outcomes.WINNER_LOCAL if own_is_local else outcomes.WINNER_VISITING
    rows = []
    for game in games:
        label = game.local_pair_label if own_is_local else game.visiting_pair_label
        if not label or game.no_show:
            continue
        own_ids = ((game.player_1_local_id, game.player_2_local_id) if own_is_local
                   else (game.player_1_visiting_id, game.player_2_visiting_id))
        state = "" if not game.winner else ("win" if game.winner == own_win else "loss")
        result = getattr(game, "result", None)
        rows.append({"n": game.n_game, "pair": label, "state": state, "me": bool(me_id) and me_id in own_ids,
                     "score": _sets(result, own_is_local) if result is not None and state else None})
    return rows


class MatchView(ApiView):
    """``GET /api/v1/matches/<id>``: ficha de un enfrentamiento de un equipo activo de la cuenta."""

    def get(self, request, match_id):
        """
        Devuelve ``{"match", "outcome", "steps", "me", "can_manage", "primary", "call", "games", "availability"}``.
        ``outcome`` solo con el acta cerrada; ``call`` solo si hay convocatoria; ``availability`` es el resumen para
        quien gestiona. 404 si el enfrentamiento no es de un equipo activo de la cuenta.
        """
        active, _suspended = _memberships(request.user)
        members = {m.club_id: m for m in active}
        match = Match.objects.select_related("club", "local", "visiting").filter(
            public_id=match_id, club_id__in=list(members)).first()
        if match is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        can_manage = members[match.club_id].can_manage
        call = Call.objects.filter(match=match).first()
        games = list(Game.objects.filter(match=match).order_by("n_game").select_related(
            "player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting").prefetch_related("results"))
        for game in games:
            game.result = next(iter(game.results.all()), None)
        phase = phase_for(match)
        today = datetime.date.today()
        player = Player.objects.filter(club=match.club, user=request.user).first()
        status = player_status(player, call, games) if player else None
        convocados = call_roster(call, games) if call else []
        availability = Availability.objects.filter(match=match, player=player).first() if player else None
        open_for_answers = bool(match.draft_mode and availability_logic.is_open(match))
        code = match_outcome(match)
        own, rival = club_score(match)
        data = {
            "match": {
                "id": str(match.public_id), "team_id": str(match.club.public_id),
                "competition": match.club.competition, "competition_name": match.club.rules.name,
                "kind_label": _kind_label(match), "date": match.start_date.isoformat(),
                "date_label": date_short(match.start_date),
                "time": match.start_time.strftime("%H:%M") if match.start_time else None,
                "location": match.location or None, "maps_url": match.maps_url or None,
                "neutral_venue": bool(match.neutral_venue), "local": _side(match.local, match.local_name),
                "visiting": _side(match.visiting, match.visiting_name),
                "open": bool(match.draft_mode), "no_show": bool(match.no_show),
                "status_label": str(phase.label), "countdown": stage_countdown(match, today),
                "web_path": reverse("call_for_match", args=[match.public_id]),
            },
            "outcome": None if code is None else {
                "code": code, "label": str(OUTCOME_LABELS[code]), "own": own, "rival": rival,
                "league_points": match.league_points},
            "steps": _steps(phase),
            "me": _me(status, player is not None, can_manage),
            "can_manage": can_manage,
            "primary": _primary(match, phase, can_manage),
            "call": None if call is None else {
                "count": len(convocados), "min": competition_for(match).min_call_players, "closed": not call.draft_mode,
                "players": [{"name": p.short_name, "sub": p.is_sub, "me": bool(player) and p.id == player.id}
                            for p in convocados]},
            "games": _games(match, games, player.id if player else None),
            "answer": None if player is None else {
                "can_answer": open_for_answers, "value": availability.answer if availability else None,
                "comment": availability.comment if availability else ""},
        }
        if can_manage and call is not None:
            board = availability_logic.board(match)
            data["availability"] = {"open": open_for_answers,
                                    "counts": {key: board["counts"].get(key, 0) for key in ("yes", "no", "maybe")}}
        return json_ok(data)
