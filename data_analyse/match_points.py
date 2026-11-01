"""
Puntos ganados en cada enfrentamiento del equipo, para el gráfico «Puntos de liga» de Estadísticas › Equipo,
y los resúmenes propios de la liga LAPI (no presentados, lesiones y elegibilidad a fases finales).

En SNP son los puntos del marcador del enfrentamiento (de ``sum(game_points)`` = 12 posibles); en una
competición con liga regular (LAPI) son los puntos de liga 4/3/1/0 de cada jornada (``Match.league_points``).
"""
from match.models import Game, Match, Result
from players.models import Player

from . import pairs as pair_stats


def _own_points(match):
    """Puntos del marcador ganados por el equipo propio en ``match``; None si no hay marcador válido."""
    parts = (match.result_points or "").replace("-", "/").split("/")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        return None
    local, visiting = (int(p) for p in parts)
    return local if match.own_is_local else visiting


def points_per_match(club, season=None, match_type=None):
    """
    Puntos de cada enfrentamiento cerrado del equipo en orden cronológico:
    ``{"kind", "max", "total", "played", "average", "rows"}``. ``kind`` es ``"league"`` (puntos de liga
    de la jornada, solo enfrentamientos de liga) o ``"score"`` (puntos del marcador, todos los tipos que
    pasen el filtro). Cada fila: ``{"label", "points", "rival", "date"}`` (``label`` = J3 / E3).
    Devuelve None si no hay ninguno.
    """
    rules = club.rules
    league = bool(rules.league_type)
    matches = Match.objects.filter(club=club, draft_mode=False).filter(
        **pair_stats.match_type_lookup(match_type, "")).select_related("local", "visiting", "club")
    if season:
        matches = matches.filter(season=season)
    if league:
        matches = matches.filter(match_type=rules.league_type)
    rows = []
    for match in matches.order_by("start_date", "id"):
        points = match.league_points if league else _own_points(match)
        if points is None:
            continue
        prefix = "J" if league else "E"
        number = match.round_number if league and match.round_number else len(rows) + 1
        rows.append({"label": f"{prefix}{number}", "points": points, "rival": match.rival_label,
                     "date": match.start_date})
    if not rows:
        return None
    total = sum(r["points"] for r in rows)
    return {
        "kind": "league" if league else "score",
        "max": rules.league_points[0] if league else sum(rules.game_points),
        "total": total,
        "played": len(rows),
        "average": round(total / len(rows), 1),
        "rows": rows,
    }


CHART_BARS = 7  # barras del gráfico (las últimas jornadas o enfrentamientos), como en el diseño


def chart_data(series):
    """Datos para el gráfico (``json_script``) de las últimas ``CHART_BARS`` jornadas: etiquetas, puntos, rival, máximo y tipo; vacío sin series."""
    if not series:
        return {}
    rows = series["rows"][-CHART_BARS:]
    return {"labels": [r["label"] for r in rows], "points": [r["points"] for r in rows],
            "rivals": [r["rival"] for r in rows], "max": series["max"], "kind": series["kind"]}


def league_extras(club, season=None):
    """
    Resúmenes de la liga LAPI de la temporada: enfrentamientos no presentados (``no_show_rival``,
    ``no_show_own``), partidos que acabaron por lesión (``injuries``), plantilla actual y máximo
    (``roster``, ``max_roster``) y jugadores actuales con al menos ``finals_min_regular`` enfrentamientos
    de liga jugados (``eligible``; ``ineligible`` lleva sus nombres). None si la competición no tiene liga.
    """
    rules = club.rules
    if not rules.league_type:
        return None
    matches = Match.objects.filter(club=club, draft_mode=False)
    games = Game.objects.filter(match__club=club, match__draft_mode=False)
    if season:
        matches, games = matches.filter(season=season), games.filter(match__season=season)
    squad = list(Player.objects.filter(club=club, in_team=True))
    minimum = rules.finals_min_regular
    result = {
        "no_show_rival": matches.filter(no_show=Match.NO_SHOW_RIVAL).count(),
        "no_show_own": matches.filter(no_show=Match.NO_SHOW_OWN).count(),
        "injuries": Result.objects.filter(game__in=games, retired=True).count(),
        "roster": len(squad),
        "max_roster": rules.max_roster,
        "minimum": minimum,
    }
    if minimum:
        league_games = games.filter(match__match_type=rules.league_type)
        slots = ("player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting")
        played = {p.id: set() for p in squad}
        for row in league_games.values("match_id", *(f"{s}_id" for s in slots)):
            for slot in slots:
                if row[f"{slot}_id"] in played:
                    played[row[f"{slot}_id"]].add(row["match_id"])
        ineligible = [p.short_name for p in squad if len(played[p.id]) < minimum]
        result.update({"eligible": len(squad) - len(ineligible), "ineligible": ineligible})
    return result
