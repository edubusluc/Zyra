"""
«Mi forma»: resumen personal de un jugador para la tarjeta del Inicio.

Solo cuenta partidos competitivos (los amistosos no entran en nada). Los últimos partidos y la racha miran
todas las temporadas, porque la forma no se reinicia en agosto; el balance y las convocatorias son de la
temporada actual. Los puntos SNP salen del histórico que ya se guarda en ``SnpScoreHistory``.
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
    ``start`` y ``end`` (fechas del periodo) y ``delta`` (cambio entre la primera y la última); vacía si
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
    }
    return data


def my_form(club, player, today=None):
    """
    Datos de «Mi forma» de ``player``: ``last`` (últimos 5 partidos, True = victoria, del más antiguo al
    más reciente), ``run`` (``('V' | 'D', n)``, o ``(None, 0)``), ``season`` (ganados, perdidos, %), ``called``
    y ``played`` (a cuántos enfrentamientos cerrados de la temporada se apuntó y en cuántos de ellos jugó),
    ``win_arc`` (largo del arco de victorias del anillo del balance), ``played_pct``, ``snp`` y ``empty``.
    """
    today = today or datetime.date.today()
    season = current_season()
    log = [g for g in pairs.club_game_log(club, match_type=pairs.COMPETITIVE) if player.id in g["pair"]]
    results = [g["won"] for g in log]
    season_log = [g for g in log if g["season"] == season]
    wins = sum(g["won"] for g in season_log)
    called = set(Call.objects.filter(
        match__club=club, match__season=season, match__draft_mode=False, players=player,
        match__match_type__in=[value for value, _label in Match.COMPETITIVE_TYPES],
    ).values_list("match_id", flat=True))
    played = called & {g["match_id"] for g in season_log}
    return {
        "last": results[-LAST_GAMES:],
        "run": pairs._current_run(results),
        "wins": wins,
        "losses": len(season_log) - wins,
        "win_pct": round(wins / len(season_log) * 100) if season_log else 0,
        "called": len(called),
        "played": len(played),
        "win_arc": round(RING_LENGTH * wins / len(season_log), 1) if season_log else 0,
        "played_pct": round(len(played) / len(called) * 100) if called else 0,
        "snp": _snp(player, today),
        "empty": not results,
    }
