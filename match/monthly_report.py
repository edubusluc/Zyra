"""
Datos del informe mensual de un jugador: sus partidos por parejas del último mes natural.

``previous_month`` da el mes a informar y ``build_monthly_report`` reúne los partidos
cerrados que jugó el jugador (en el drive o en el revés, como local o visitante), con
sus parejas, sets y rachas. Lo consumen ``monthly_pdf`` (el PDF) y ``monthly_email``.
"""
import datetime
from collections import defaultdict

from django.db.models import Q

from core.models import REPORT_SCOPE_COMPETITIVE
from data_analyse.pairs import COMPETITIVE, _current_run, match_type_lookup
from data_analyse.sets import own_sets, set_stats
from match.models import Game

MAX_GAME_ROWS = 14  # filas del detalle de partidos en el PDF; el resto se cuenta


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


def build_monthly_report(player, month, scope=None):
    """
    Estadísticas de ``player`` en el mes que empieza en ``month``.

    ``scope`` es ``REPORT_SCOPE_COMPETITIVE`` para dejar fuera los amistosos. Devuelve un
    diccionario con ``games`` (partidos en orden cronológico: fecha, rival, tipo, pareja,
    número, sets, ganado y puntos), ``played``/``wins``/``losses``/``pct``, ``points``,
    ``sets`` (ver data_analyse.sets.set_stats), ``partners`` (por pareja: jugados y
    victorias, la mejor primero), ``form`` (resultados, el último al final), ``streak`` y
    ``matches`` (enfrentamientos distintos en los que jugó). Con ``played == 0`` no hay informe.
    """
    start, end = month_range(month)
    games = (
        Game.objects
        .filter(Q(player_1_local=player) | Q(player_2_local=player)
                | Q(player_1_visiting=player) | Q(player_2_visiting=player),
                match__club=player.club, match__start_date__range=(start, end),
                draft_mode=False, winner__in=("Local", "Visitante"))
        .filter(**match_type_lookup(COMPETITIVE if scope == REPORT_SCOPE_COMPETITIVE else None, "match__"))
        .select_related("match__local", "match__visiting", "player_1_local", "player_2_local",
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
        won = (g.winner == "Local") == is_local
        sets = own_sets(next(iter(g.results.all()), None), is_local)
        points = (g.score or 0) if won else 0
        rows.append({
            "date": g.match.start_date, "rival": g.match.rival_label, "match_type": g.match.get_match_type_display(),
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
    }
