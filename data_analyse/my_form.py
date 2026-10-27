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
SNP_POINTS = 10


def _snp(player, today):
    """Puntos SNP actuales, diferencia en los últimos 30 días y puntos de la mini gráfica (o None sin puntos)."""
    if player.snp_score is None:
        return None
    history = list(player.snp_history.filter(date__gte=today - datetime.timedelta(days=SNP_WINDOW_DAYS)).order_by("date"))
    scores = [h.score for h in history][-SNP_POINTS:]
    delta = player.snp_score - scores[0] if len(scores) >= 2 else None
    return {"score": player.snp_score, "delta": delta, "line": _line(scores)}


def _line(scores, width=120, height=28):
    """Puntos (``"x,y x,y …"``) de la mini gráfica SVG de ``scores``; vacío si hay menos de dos."""
    if len(scores) < 2:
        return ""
    low, high = min(scores), max(scores)
    span = (high - low) or 1
    step = width / (len(scores) - 1)
    return " ".join(f"{i * step:.1f},{height - 2 - (score - low) / span * (height - 4):.1f}" for i, score in enumerate(scores))


def my_form(club, player, today=None):
    """
    Datos de «Mi forma» de ``player``: ``last`` (últimos 5 partidos, True = victoria, del más antiguo al
    más reciente), ``run`` (``('V' | 'D', n)``, o ``(None, 0)``), ``season`` (ganados, perdidos, %), ``called``
    y ``played`` (convocatorias cerradas de la temporada y en cuántas jugó), ``snp`` y ``empty``.
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
        "snp": _snp(player, today),
        "empty": not results,
    }
