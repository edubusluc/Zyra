"""
Datos de la cabecera y de las tarjetas propias de la ficha de estadísticas de un jugador (Mis estadísticas ·
SNP/LAPI y Jugador): papel en el equipo, pareja habitual, puesto en el ranking SNP, jornadas de liga jugadas
(elegibilidad a fases finales, LAPI) y puntos SNP al cierre de cada temporada.
"""
from core.models import Membership
from match.models import Game, Match
from players.models import Player

SLOTS = ("player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting")


def role_label(player):
    """Papel de la persona en el equipo (Capitán, Gestor o Jugador); Jugador si la ficha no tiene cuenta."""
    if not player.user_id:
        return Membership(role=Membership.MEMBER).team_role_label
    member = Membership.objects.filter(user_id=player.user_id, club_id=player.club_id).first()
    return member.team_role_label if member else Membership(role=Membership.MEMBER).team_role_label


def usual_partner(affinity):
    """
    Nombre del compañero con el que más partidos ha jugado entre los que siguen en el equipo
    (``degree_of_affinity``); desempata la afinidad. None si no ha jugado en pareja.
    """
    rows = [a for a in affinity if a.get("in_team")]
    if not rows:
        return None
    return max(rows, key=lambda a: (a["games"], a["affinity"]))["name"]


def snp_rank(player):
    """Puesto (1 = más puntos) de ``player`` entre los jugadores del equipo con puntos SNP; None si no tiene."""
    if player.snp_score is None:
        return None
    better = Player.objects.filter(club=player.club, in_team=True, snp_score__gt=player.snp_score).count()
    return better + 1


def league_rounds(player, season=None):
    """
    Jornadas de liga cerradas del equipo en las que ha jugado ``player``: ``{"played", "total", "minimum",
    "eligible"}`` (``season`` None = todas). None si la competición no tiene liga.
    """
    rules = player.club.rules
    if not rules.league_type:
        return None
    matches = Match.objects.filter(club=player.club, draft_mode=False, match_type=rules.league_type)
    if season:
        matches = matches.filter(season=season)
    total = matches.count()
    games = Game.objects.filter(match__in=matches, draft_mode=False)
    played = set()
    for row in games.values("match_id", *(f"{s}_id" for s in SLOTS)):
        if player.id in (row[f"{s}_id"] for s in SLOTS):
            played.add(row["match_id"])
    minimum = rules.finals_min_regular or 0
    return {"played": len(played), "total": total, "minimum": minimum, "eligible": len(played) >= minimum}


def snp_by_season(player):
    """Puntos SNP al cierre de cada temporada (la última actualización): ``{"labels", "scores"}`` cronológico."""
    last = {}
    for row in player.snp_history.order_by("date"):
        last[row.season] = row.score
    seasons = sorted(last, key=lambda s: int(s.split("-")[0]))
    return {"labels": seasons, "scores": [last[s] for s in seasons]}
