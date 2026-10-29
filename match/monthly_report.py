"""
Datos del informe mensual de un jugador: sus partidos por parejas del último mes natural.

``previous_month`` da el mes a informar y ``build_monthly_report`` reúne los partidos
cerrados que jugó el jugador (en el drive o en el revés, como local o visitante), con
sus parejas, sets y rachas. Lo consumen ``monthly_pdf`` (el PDF) y ``monthly_email``.
"""
from . import outcomes
import datetime
from collections import defaultdict

from django.db.models import Q

from core.models import REPORT_SCOPE_COMPETITIVE
from data_analyse.pairs import COMPETITIVE, _current_run, match_type_lookup
from data_analyse.sets import own_sets, set_stats
from call.models import Call
from match.models import Game
from players.models import SnpScoreHistory, joined_by

CALL_PLAYED, CALL_BENCHED, CALL_ABSENT = "played", "benched", "absent"

MAX_GAME_ROWS = 14  # filas del detalle de partidos en el PDF; el resto se cuenta
MAX_CALL_ROWS = 10  # filas del listado de convocatorias en el PDF; el resto se cuenta


def previous_month(today=None):
    """Primer día del mes natural anterior a ``today`` (hoy si no se indica)."""
    today = today or datetime.date.today()
    return (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)


def month_range(month):
    """(primer día, último día) del mes que empieza en ``month``."""
    nxt = (month + datetime.timedelta(days=32)).replace(day=1)
    return month, nxt - datetime.timedelta(days=1)


def _partner_and_side(game, player):
    """(nombre de la pareja, partner, es_local) del jugador en el partido; es_local es None si no jugó.

    Si la pareja se eliminó, ``partner`` es None y el nombre sale de ``Game.removed_player_names``.
    """
    for first, second, local in (("player_1_local", "player_2_local", True),
                                 ("player_1_visiting", "player_2_visiting", False)):
        for mine, other in ((first, second), (second, first)):
            if getattr(game, mine + "_id") == player.pk:
                partner = getattr(game, other)
                name = partner.short_name if partner else game.removed_player_names.get(other, "").upper()
                return name, partner, local
    return "", None, None


def monthly_calls(player, start, end, scope=None):
    """
    Convocatorias cerradas del club con partido entre ``start`` y ``end``, en orden cronológico.

    Cada una lleva ``status``: ``CALL_PLAYED`` (se apuntó y lo alinearon en algún partido),
    ``CALL_BENCHED`` (se apuntó pero no jugó: no convocado) o ``CALL_ABSENT`` (no se apuntó).
    """
    calls = (
        Call.objects.filter(match__club=player.club, match__start_date__range=(start, end), match__draft_mode=False, draft_mode=False)
        .filter(**match_type_lookup(COMPETITIVE if scope == REPORT_SCOPE_COMPETITIVE else None, "match__"))
        .select_related("match__local", "match__visiting", "match__club")
        .order_by("match__start_date", "match_id")
    )
    signed = set(Call.objects.filter(pk__in=[c.pk for c in calls], players=player).values_list("pk", flat=True))
    played = set(
        Game.objects.filter(
            Q(player_1_local=player) | Q(player_2_local=player) | Q(player_1_visiting=player) | Q(player_2_visiting=player),
            match_id__in=[c.match_id for c in calls],
        ).values_list("match_id", flat=True)
    )
    rows = []
    for call in calls:
        if not joined_by(player.joined_season, call.match.season):
            continue  # convocatoria de una temporada anterior a su incorporación
        if call.pk not in signed:
            status = CALL_ABSENT
        else:
            status = CALL_PLAYED if call.match_id in played else CALL_BENCHED
        rows.append({"date": call.match.start_date, "rival": call.match.rival_label,
                     "match_type": call.match.type_label, "status": status})
    return rows


def monthly_snp(player, start, end):
    """Puntos SNP del jugador en el mes: [(fecha, puntos)] de ``SnpScoreHistory``, por fecha."""
    return list(SnpScoreHistory.objects.filter(player=player, date__range=(start, end))
                .order_by("date").values_list("date", "score"))


def build_monthly_report(player, month, scope=None):
    """
    Estadísticas de ``player`` en el mes que empieza en ``month``.

    ``scope`` es ``REPORT_SCOPE_COMPETITIVE`` para dejar fuera los amistosos. Devuelve un
    diccionario con ``games`` (partidos en orden cronológico: fecha, rival, tipo, pareja,
    número, sets, ganado y puntos), ``played``/``wins``/``losses``/``pct``, ``points``,
    ``sets`` (ver data_analyse.sets.set_stats), ``partners`` (por pareja: jugados y
    victorias, la mejor primero), ``form`` (resultados, el último al final), ``streak`` y
    ``matches`` (enfrentamientos distintos en los que jugó), ``calls`` (convocatorias del mes
    con su estado, ver ``monthly_calls``), ``call_counts`` (cuántas por estado) y ``snp``
    (puntos SNP del mes, ver ``monthly_snp``). Con ``played == 0`` no hay informe.
    """
    start, end = month_range(month)
    games = (
        Game.objects
        .filter(Q(player_1_local=player) | Q(player_2_local=player)
                | Q(player_1_visiting=player) | Q(player_2_visiting=player),
                match__club=player.club, match__start_date__range=(start, end),
                match__draft_mode=False, draft_mode=False, winner__in=outcomes.WINNERS)
        .filter(**match_type_lookup(COMPETITIVE if scope == REPORT_SCOPE_COMPETITIVE else None, "match__"))
        .select_related("match__local", "match__visiting", "match__club", "player_1_local", "player_2_local",
                        "player_1_visiting", "player_2_visiting")
        .prefetch_related("results")
        .order_by("match__start_date", "match_id", "n_game")
    )
    rows, log = [], []
    partners = defaultdict(lambda: {"name": "", "played": 0, "wins": 0})
    for g in games:
        name, partner, is_local = _partner_and_side(g, player)
        if is_local is None:
            continue
        won = (g.winner == outcomes.WINNER_LOCAL) == is_local
        sets = own_sets(next(iter(g.results.all()), None), is_local)
        points = (g.score or 0) if won else 0
        rows.append({
            "date": g.match.start_date, "rival": g.match.rival_label, "match_type": g.match.type_label,
            "partner": name, "n_game": g.n_game, "sets": sets, "won": won, "points": points,
            "match_id": g.match_id,
        })
        log.append({"sets": sets, "won": won})
        key = partner.pk if partner else name
        entry = partners[key]
        entry["name"] = name
        entry["played"] += 1
        entry["wins"] += won
    wins = sum(r["won"] for r in rows)
    played = len(rows)
    calls = monthly_calls(player, start, end, scope)
    form = [r["won"] for r in rows]
    return {
        "player": player, "club": player.club, "month": month, "scope": scope,
        "games": rows, "played": played, "wins": wins, "losses": played - wins,
        "pct": round(wins / played * 100) if played else 0,
        "points": sum(r["points"] for r in rows),
        "sets": set_stats(log),
        "partners": sorted((p for p in partners.values() if p["name"]),
                           key=lambda p: (-p["wins"] / p["played"], -p["played"], p["name"])),
        "form": form, "streak": _current_run(form),
        "matches": len({r["match_id"] for r in rows}),
        "calls": calls,
        "call_counts": {s: sum(c["status"] == s for c in calls) for s in (CALL_PLAYED, CALL_BENCHED, CALL_ABSENT)},
        "snp": monthly_snp(player, start, end),
    }
