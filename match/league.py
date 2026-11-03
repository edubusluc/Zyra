"""
Liga regular de las competiciones que la tienen (LAPI): puntos de liga de la temporada y la regla de
las fases finales (reglamento LAPI 8.2: solo juega Playoffs o Fase final quien ha jugado al menos 2
enfrentamientos de liga con el equipo esa temporada). Las reglas salen de ``core.competitions``.
"""
from django.db.models import Q

from .models import Game, Match


def season_league_points(club, season=None):
    """
    Puntos de liga del equipo en la temporada ``season`` (todas con None): ``{"total", "played",
    "average"}`` con los enfrentamientos de liga cerrados; None si la competición no tiene liga.
    """
    rules = club.rules
    if not rules.league_type:
        return None
    matches = Match.objects.filter(club=club, draft_mode=False, match_type=rules.league_type).select_related(
        "local", "visiting", "club")
    if season:
        matches = matches.filter(season=season)
    points = [p for p in (m.league_points for m in matches) if p is not None]
    return {
        "total": sum(points),
        "played": len(points),
        "average": round(sum(points) / len(points), 1) if points else None,
    }


def applies_finals_rule(match):
    """True si ``match`` es de una fase final con mínimo de enfrentamientos de liga (LAPI: Playoffs, Fase final)."""
    rules = match.club.rules
    return bool(rules.finals_min_regular) and match.match_type in rules.final_types


def regular_played(match, players):
    """
    Enfrentamientos de liga cerrados de la temporada de ``match`` que ha jugado cada jugador de
    ``players`` con el equipo: ``{player_id: n}`` (los que no han jugado ninguno no aparecen).
    """
    ids = [p.id if hasattr(p, "id") else p for p in players]
    slots = ("player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting")
    games = Game.objects.filter(
        match__club=match.club, match__season=match.season, match__draft_mode=False,
        match__match_type=match.club.rules.league_type,
    ).exclude(match=match)
    # Un jugador puede salir en dos huecos del mismo enfrentamiento: se cuentan enfrentamientos distintos.
    per_player = {}
    for game in games.filter(Q(player_1_local__in=ids) | Q(player_2_local__in=ids) |
                             Q(player_1_visiting__in=ids) | Q(player_2_visiting__in=ids)).values(
            "match_id", *(f"{slot}_id" for slot in slots)):
        for slot in slots:
            pid = game[f"{slot}_id"]
            if pid in ids:
                per_player.setdefault(pid, set()).add(game["match_id"])
    return {pid: len(matches) for pid, matches in per_player.items()}


def finals_shortfall(match, players):
    """
    Jugadores de ``players`` que no cumplen el mínimo de liga para la fase final ``match``:
    ``[(player, jugados)]`` en el orden recibido; vacía si la regla no se aplica.
    """
    if not applies_finals_rule(match):
        return []
    players = list(players)
    played = regular_played(match, players)
    minimum = match.club.rules.finals_min_regular
    return [(p, played.get(p.id, 0)) for p in players if played.get(p.id, 0) < minimum]
