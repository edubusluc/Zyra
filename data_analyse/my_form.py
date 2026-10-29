"""
«Mi forma»: resumen personal de un jugador para la tarjeta del Inicio.

Solo cuenta partidos competitivos (los amistosos no entran en nada). Todo es de la temporada actual: los
últimos partidos, la racha, el balance y las convocatorias, sumando las competiciones en las que la cuenta
tiene jugador (SNP y LAPI). Los puntos SNP salen del histórico que ya se guarda en ``SnpScoreHistory``.
"""
import datetime

from call.models import Call
from match.models import Match
from players.models import current_season

from . import pairs

LAST_GAMES = 5
SNP_WINDOW_DAYS = 30
CHART_WIDTH = 300
CHART_HEIGHT = 80
CHART_PAD = 8
# Perímetro del anillo del balance (SVG, radio 26).
RING_LENGTH = 163.4


def _snp(player, today):
    """
    Puntos SNP actuales y su gráfica de los últimos 30 días (o None sin puntos). La gráfica coloca cada
    actualización del histórico según su fecha: ``line`` y ``area`` (puntos SVG de un lienzo de
    ``CHART_WIDTH`` x ``CHART_HEIGHT``), ``dot`` (posición en % del último punto), ``high`` y ``low``,
    ``start`` y ``end`` (fechas del periodo), ``points`` (cada actualización con su posición en %, puntos y
    fecha, para el indicador al pasar el ratón) y ``delta`` (cambio entre la primera y la última); vacía si
    hay menos de dos actualizaciones.
    """
    if player.snp_score is None:
        return None
    start = today - datetime.timedelta(days=SNP_WINDOW_DAYS)
    history = list(player.snp_history.filter(date__gte=start, date__lte=today).order_by("date"))
    data = {"score": player.snp_score, "delta": None, "chart": None}
    if len(history) < 2:
        return data
    scores = [h.score for h in history]
    low, high = min(scores), max(scores)
    span = (high - low) or 1
    xs = [(h.date - start).days / SNP_WINDOW_DAYS * CHART_WIDTH for h in history]
    ys = [CHART_PAD + (high - score) / span * (CHART_HEIGHT - 2 * CHART_PAD) if high != low else CHART_HEIGHT / 2
          for score in scores]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    data["delta"] = scores[-1] - scores[0]
    data["chart"] = {
        "line": line,
        "area": f"{line} {xs[-1]:.1f},{CHART_HEIGHT} {xs[0]:.1f},{CHART_HEIGHT}",
        "dot": {"x": round(xs[-1] / CHART_WIDTH * 100, 1), "y": round(ys[-1] / CHART_HEIGHT * 100, 1)},
        "high": high, "low": low, "start": start, "end": today,
        "points": [{"x": round(x / CHART_WIDTH * 100, 1), "y": round(y / CHART_HEIGHT * 100, 1),
                    "score": h.score, "date": h.date} for x, y, h in zip(xs, ys, history)],
    }
    return data


def _season_entries(club, player, season):
    """Partidos competitivos de ``player`` en ``club`` esta temporada (orden cronológico) y los enfrentamientos a los que se apuntó."""
    log = [g for g in pairs.club_game_log(club, match_type=pairs.COMPETITIVE) if player.id in g["pair"]]
    season_log = [g for g in log if g["season"] == season]
    called = set(Call.objects.filter(
        match__club=club, match__season=season, match__draft_mode=False, players=player,
        match__match_type__in=[value for value, _label in Match.COMPETITIVE_TYPES],
    ).values_list("match_id", flat=True))
    return season_log, called


def my_form(club, player, today=None, others=()):
    """
    Datos de «Mi forma» de ``player``: ``last`` (últimos 5 partidos, True = victoria, del más antiguo al
    más reciente), ``run`` (``('V' | 'D', n)``, o ``(None, 0)``), ``season`` (ganados, perdidos, %), ``called``
    y ``played`` (a cuántos enfrentamientos cerrados de la temporada se apuntó y en cuántos de ellos jugó),
    ``win_arc`` (largo del arco de victorias del anillo del balance), ``played_pct``, ``snp`` y ``empty``.

    ``others``: jugadores de la misma cuenta en otras competiciones (cada uno en su club). Sus partidos y
    convocatorias se suman (son partidos ganados y perdidos, no puntos); entonces ``last_games`` dice la
    competición de cada uno de los últimos partidos y ``by_competition`` trae el desglose (``code``,
    ``name``, ``wins``, ``losses``, ``called``, ``played``, ``called_pct``: tramo de la barra). Los puntos
    SNP son del jugador de la SNP.
    """
    today = today or datetime.date.today()
    season = current_season()
    entries, by_competition, called_total, played_total = [], [], 0, 0
    for p in [player, *others]:
        season_log, called = _season_entries(p.club, p, season)
        played = called & {g["match_id"] for g in season_log}
        code = p.club.competition
        entries += [{**g, "code": code} for g in season_log]
        wins = sum(g["won"] for g in season_log)
        by_competition.append({"code": code, "name": p.club.rules.name, "wins": wins,
                               "losses": len(season_log) - wins, "called": len(called), "played": len(played)})
        called_total += len(called)
        played_total += len(played)
    entries.sort(key=lambda g: (g["date"], g["match_id"], g["n_game"]))
    for row in by_competition:
        row["played_pct"] = round(row["played"] / called_total * 100) if called_total else 0
    results = [g["won"] for g in entries]
    wins = sum(results)
    snp_player = next((p for p in [player, *others] if p.club.rules.has_snp), None)
    return {
        "last": results[-LAST_GAMES:],
        "last_games": [{"won": g["won"], "code": g["code"]} for g in entries[-LAST_GAMES:]],
        "by_competition": by_competition if others else [],
        "run": pairs._current_run(results),
        "wins": wins,
        "losses": len(entries) - wins,
        "win_pct": round(wins / len(entries) * 100) if entries else 0,
        "called": called_total,
        "played": played_total,
        "win_arc": round(RING_LENGTH * wins / len(entries), 1) if entries else 0,
        "played_pct": round(played_total / called_total * 100) if called_total else 0,
        "snp": _snp(snp_player, today) if snp_player else None,
        "empty": not results,
    }
