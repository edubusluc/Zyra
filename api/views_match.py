"""``GET /api/v1/matches/<id>``: la ficha nativa de un enfrentamiento (solo lectura)."""
import datetime
import logging

from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext as _

from call import availability as availability_logic
from call.models import Availability, Call, ReportDelivery
from core.competitions import competition_for
from core.templatetags.zyra_format import date_short
from match import league, lineup, outcomes
from match.models import Game, Match
from match.notifications import is_past_match, send_call_report
from match.phase import (CLOSE_CALL, CLOSE_MATCH, CREATE_CALL, CREATE_GAMES, ENTER_RESULTS, NOTHING, STEPS, phase_for,
                         player_status)
from match.views import OUTCOME_LABELS, validate_call, call_roster, club_score, lineup_rows, match_outcome, stage_countdown
from players.models import Player

from .errors import ApiError
from .fields import invalid
from .responses import json_ok
from .views_base import ApiView
from .views_home import _kind_label, _me, _memberships, _side

logger = logging.getLogger(__name__)


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


def _action(key, label, group, web_path, *, locked=False, reason=None, danger=False):
    """Una acción de la hoja «Acciones»: abre ``web_path`` (o muestra ``reason`` si está bloqueada)."""
    return {"key": key, "label": str(label), "group": group, "web_path": web_path, "locked": locked,
            "reason": str(reason) if reason else None, "danger": danger}


def _actions(match, call, games, membership):
    """
    Acciones de la hoja de quien gestiona, agrupadas (``call``, ``pairs``, ``report``, ``match``). Las que no se pueden
    hacer salen con ``locked`` y el motivo en ``reason``. Por ahora todas abren una página de la web: las que en la web
    son un envío (reabrir, reenviar, no presentado) abren la ficha, donde está el botón.
    """
    ficha = reverse("call_for_match", args=[match.public_id])
    has_results = any(g.result is not None for g in games)
    all_results = bool(games) and all(g.result is not None for g in games)
    out = []
    if call is not None:
        locked = has_results
        out.append(_action("edit_call", _("Editar convocatoria"), "call", reverse("edit_call", args=[call.public_id]),
                           locked=locked, reason=_("Hay resultados guardados: no se puede cambiar la convocatoria. "
                                                   "Borra el resultado del partido para poder hacerlo.") if locked else None))
        if not call.draft_mode:
            blocked = bool(games)
            out.append(_action("reopen_call", _("Reabrir convocatoria"), "call", ficha, locked=blocked,
                               reason=_("Hay parejas alineadas: no se puede reabrir la convocatoria.") if blocked else None))
        out.append(_action("call_log", _("Advertencias"), "call", reverse("view_call_log", args=[call.public_id])))
    if games:
        out.append(_action("edit_games", _("Editar parejas"), "pairs", reverse("edit_games_match", args=[match.public_id]),
                           locked=all_results,
                           reason=_("Todos los partidos tienen resultado: no se pueden cambiar las parejas. "
                                    "Borra el resultado del partido para poder hacerlo.") if all_results else None))
        out.append(_action("enter_results", _("Poner resultados"), "pairs", reverse("enter_results", args=[match.public_id])))
    if call is not None:
        out.append(_action("report_pdf", _("Informe PDF"), "report", reverse("call_report", args=[match.public_id])))
        if not call.draft_mode:
            out.append(_action("resend_report", _("Reenviar informe"), "report", ficha))
    if match.draft_mode:
        out.append(_action("edit_date", _("Cambiar fecha y hora"), "match", reverse("edit_match_date", args=[match.public_id])))
        if match.club.rules.no_show and not match.is_friendly:
            out.append(_action("no_show_rival", _("No se presentó el rival"), "match", ficha))
            out.append(_action("no_show_own", _("No nos presentamos"), "match", ficha, danger=True))
        if not match.was_closed or membership.is_admin:
            out.append(_action("delete", _("Eliminar enfrentamiento"), "match",
                               reverse("delete_match", args=[match.public_id]) + "?desde=ficha", danger=True))
    return out


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
        membership = members[match.club_id]
        can_manage = membership.can_manage
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
        # La lista de apuntados o convocados solo la ve quien gestiona; los jugadores, con la convocatoria cerrada y el
        # ajuste del equipo ``call_list_public`` encendido (como la web: ``Club.call_list_public``).
        show_call = call is not None and (
            can_manage or (not call.draft_mode and getattr(match.club, "call_list_public", False)))
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
            "me": _me(status, player is not None, can_manage, bool(games)),
            "can_manage": can_manage,
            "primary": _primary(match, phase, can_manage),
            "call": None if not show_call else {
                "count": len(convocados), "min": competition_for(match).min_call_players, "closed": not call.draft_mode,
                "players": [{"name": p.short_name, "sub": p.is_sub, "me": bool(player) and p.id == player.id}
                            for p in convocados]},
            "games": _games(match, games, player.id if player else None),
            "actions": _actions(match, call, games, membership) if can_manage else [],
            "answer": None if player is None else {
                "can_answer": open_for_answers, "value": availability.answer if availability else None,
                "comment": availability.comment if availability else ""},
        }
        if can_manage and call is not None:
            board = availability_logic.board(match)
            data["availability"] = {"open": open_for_answers,
                                    "counts": {key: board["counts"].get(key, 0) for key in ("yes", "no", "maybe")}}
        return json_ok(data)


def _report_state(call, match, user, resend):
    """
    Envía el informe del cierre como la web (``match.views.close_call``) y devuelve cómo quedó: ``skipped`` (partido
    pasado o ya enviado y sin pedir reenvío), ``sent``, ``pending`` (se reintenta solo), ``no_email`` o ``failed``.
    """
    already_sent = call.report_deliveries.filter(status=ReportDelivery.SENT).exists()
    if (is_past_match(match) or already_sent) and not resend:
        return "skipped"
    try:
        deliveries = send_call_report(call, sender=user)
    except Exception:
        logger.exception("No se pudo enviar el informe de la convocatoria %s", call.pk)
        return "failed"
    if not deliveries:
        return "no_email"
    return "sent" if all(d.status == ReportDelivery.SENT for d in deliveries) else "pending"


class CloseCallView(ApiView):
    """``POST /api/v1/matches/<id>/close-call``: cierra la convocatoria (mismas reglas que ``match.views.close_call``)."""

    def post(self, request, match_id):
        """
        Cuerpo opcional ``{"allow_short"?, "force_finals"?, "resend_report"?}`` (booleanos). Solo quien gestiona el
        equipo (404 si no). 409 ``cannot_close`` con el motivo de la web si no se puede cerrar (sin apuntados, por
        debajo del mínimo, ya cerrada); 409 ``short_call`` si falta gente pero la competición deja cerrar con
        ``allow_short``; 409 ``finals_rule`` si la regla de fases finales pide ``force_finals``. Devuelve
        ``{"closed": true, "report": "sent" | "pending" | "no_email" | "failed" | "skipped"}``.
        """
        body = self.json_body(request)
        flags = {}
        for name in ("allow_short", "force_finals", "resend_report"):
            value = body.get(name, False)
            if not isinstance(value, bool):
                raise invalid(name)
            flags[name] = value
        active, _suspended = _memberships(request.user)
        members = {m.club_id: m for m in active if m.can_manage}
        call = Call.objects.select_related("match__club").filter(
            match__public_id=match_id, match__club_id__in=list(members)).first()
        if call is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        match = call.match
        is_valid, message = validate_call(call, allow_short=flags["allow_short"])
        if not is_valid:
            # Falta gente pero la competición deja cerrar si se confirma: la app pregunta y vuelve a enviar.
            count = call.players.count()
            can_confirm = (call.draft_mode and 0 < count < competition_for(match).min_call_players
                           and lineup.short_call_allowed(match.club.rules, count) and not flags["allow_short"])
            code = "short_call" if can_confirm else "cannot_close"
            raise ApiError(code, str(message), 409)
        short = league.finals_shortfall(match, call.players.all())
        if short and not flags["force_finals"]:
            names = ", ".join(p.full_name for p, _n in short)
            raise ApiError("finals_rule", _("Según el reglamento, en esta fase solo pueden jugar quienes han jugado al "
                                            "menos %(n)s enfrentamientos de liga esta temporada. No lo cumplen: "
                                            "%(names)s.") % {"n": match.club.rules.finals_min_regular, "names": names}, 409)
        with transaction.atomic():
            # Cierre atómico: si otra petición la cerró en el mismo instante, esta no repite el informe.
            if not Call.objects.filter(pk=call.pk, draft_mode=True).update(draft_mode=False):
                raise ApiError("cannot_close", _("La convocatoria ya estaba cerrada."), 409)
        call.draft_mode = False
        return json_ok({"closed": True, "report": _report_state(call, match, request.user, flags["resend_report"])})
