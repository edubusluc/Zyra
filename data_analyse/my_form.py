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
    Puntos SNP actuales y su gráfica de los últimos 30 días (o None sin puntos). Los puntos solo cambian
    cuando hay una actualización, así que la gráfica es escalonada: cada valor se mantiene (línea horizontal)
    hasta la siguiente actualización y el último llega hasta hoy. Si hay una actualización anterior a los 30
    días, su valor es el de partida; si el histórico es más reciente, la gráfica empieza en su primera
    actualización (el eje no deja un hueco vacío). ``line`` y ``area`` (puntos SVG de un lienzo de
    ``CHART_WIDTH`` x ``CHART_HEIGHT``), ``dot`` (posición en % del valor de hoy), ``high`` y ``low``,
    ``start`` y ``end`` (fechas del eje), ``points`` (cada actualización con su posición en %, puntos y
    fecha, para el indicador al pasar el ratón) y ``delta`` (variación de la última actualización respecto a la
    anterior, igual que la columna «Evolución» de la tabla de plantilla); sin gráfica si no hay al menos dos
    días de histórico.
    """
    if player.snp_score is None:
        return None
    window_start = today - datetime.timedelta(days=SNP_WINDOW_DAYS)
    history = player.snp_history.filter(date__lte=today)
    inside = list(history.filter(date__gte=window_start).order_by("date"))
    before = history.filter(date__lt=window_start).order_by("-date").first()
    known = ([before] if before else []) + inside
    data = {"score": player.snp_score, "delta": None, "chart": None}
    if not known:
        return data
    if len(known) >= 2:
        data["delta"] = round(known[-1].score - known[-2].score, 1)
    start = window_start if before else known[0].date
    days = (today - start).days
    if days < 1:
        return data
    scores = [h.score for h in known]
    low, high = min(scores), max(scores)
    span = high - low

    def x_of(date):
        """Posición horizontal de ``date`` en el lienzo (las anteriores al eje quedan en el borde izquierdo)."""
        return max(date - start, datetime.timedelta(0)).days / days * CHART_WIDTH

    def y_of(score):
        """Posición vertical de ``score`` (línea centrada si no hay variación, con margen arriba y abajo)."""
        if not span:
            return CHART_HEIGHT / 2
        return CHART_PAD + (high - score) / span * (CHART_HEIGHT - 2 * CHART_PAD)

    xs = [x_of(h.date) for h in known]
    ys = [y_of(h.score) for h in known]
    path = [(xs[0], ys[0])]
    for x, y in zip(xs[1:], ys[1:]):
        path += [(x, path[-1][1]), (x, y)]
    path.append((CHART_WIDTH, ys[-1]))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in path)
    data["chart"] = {
        "line": line,
        "area": f"{line} {CHART_WIDTH},{CHART_HEIGHT} {path[0][0]:.1f},{CHART_HEIGHT}",
        "dot": {"x": 100.0, "y": round(ys[-1] / CHART_HEIGHT * 100, 1)},
        "high": high, "low": low, "start": start, "end": today,
        "points": [{"x": round(x / CHART_WIDTH * 100, 1), "y": round(y / CHART_HEIGHT * 100, 1),
                    "score": h.score, "date": h.date}
                   for x, y, h in zip(xs, ys, known) if h.date >= window_start],
    }
    return data


def _season_entries(club, player, season):
    """Partidos competitivos de ``player`` en ``club`` esta temporada (orden cronológico) y los enfrentamientos a los que se apuntó."""
    log = [g for g in pairs.club_game_log(club, match_type=pairs.COMPETITIVE) if player.id in g["pair"]]
    season_log = [g for g in log if g["season"] == season]
    called = set(Call.objects.filter(
        match__club=club, match__season=season, match__draft_mode=False, match__no_show="", players=player,
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
        "last_games": [{"won": g["won"], "code": g["code"], "rival": g["rival"], "date": g["date"].isoformat() if g["date"] else None}
                       for g in entries[-LAST_GAMES:]],
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
