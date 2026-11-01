"""
Piezas de «Estadísticas · Equipo» que no salen del log de partidos: puntos de cada enfrentamiento o
jornada, elegibilidad para las fases finales, no presentados y lesiones, y puntos SNP del equipo por temporada.

Todas devuelven datos simples para la plantilla y respetan los mismos filtros de temporada y tipo que el
resto de la página.
"""
from django.db.models import Q

from match.models import Game, Match, Result
from players.models import Player, SnpScoreHistory

from . import rivals
from .pairs import match_type_lookup

# Barras que se dibujan en «Puntos de liga» (las últimas jornadas o enfrentamientos).
LAST_BARS = 7


def points_series(club, season=None, match_type=None, last=LAST_BARS):
    """
    Puntos ganados en cada enfrentamiento cerrado (los que dan puntos de liga si la competición tiene liga).

    Devuelve ``{'league', 'labels', 'values', 'total', 'played', 'average', 'possible', 'best'}``: con liga
    (LAPI) son los puntos de liga de cada jornada («J1»…); sin ella (SNP), los puntos de cada enfrentamiento
    («E1»…) de los ``possible`` en juego. ``labels`` y ``values`` son solo los ``last`` últimos; ``total``,
    ``average`` y ``best`` (mejor valor y su etiqueta) usan todos. None si no hay ninguno.
    """
    rules = club.rules
    league = bool(rules.league_type)
    matches = rivals.closed_matches(club, season, match_type)
    rows = []
    for m in matches:
        if league:
            points = m.league_points
            if points is None:
                continue
        else:
            points = rivals.own_points(m)[0]
            if points is None:
                continue
        rows.append((m, points))
    if not rows:
        return None
    labels, values = [], []
    for i, (m, points) in enumerate(rows, start=1):
        number = (m.round_number if league and m.round_number else i)
        labels.append(f"{'J' if league else 'E'}{number}")
        values.append(points)
    best = max(range(len(values)), key=lambda i: values[i])
    return {
        'league': league,
        'labels': labels[-last:],
        'values': values[-last:],
        'total': sum(values),
        'played': len(values),
        'average': round(sum(values) / len(values), 1),
        'possible': None if league else rules.total_points,
        'best': {'value': values[best], 'label': labels[best]},
    }


def finals_roster(club, season):
    """
    Plantilla y elegibilidad para las fases finales (reglamento LAPI 8.2: haber jugado al menos
    ``finals_min_regular`` enfrentamientos de liga con el equipo esa temporada).

    ``{'squad', 'max', 'eligible', 'minimum', 'missing'}``; ``missing`` son los nombres de quienes aún no
    llegan. None si la competición no tiene esa regla.
    """
    rules = club.rules
    if not (rules.finals_min_regular and rules.league_type):
        return None
    squad = list(Player.objects.filter(club=club, in_team=True))
    slots = ('player_1_local', 'player_2_local', 'player_1_visiting', 'player_2_visiting')
    games = Game.objects.filter(match__club=club, match__season=season, match__draft_mode=False,
                                match__match_type=rules.league_type, draft_mode=False)
    played = {}
    for row in games.values('match_id', *(f'{s}_id' for s in slots)):
        for slot in slots:
            if row[f'{slot}_id']:
                played.setdefault(row[f'{slot}_id'], set()).add(row['match_id'])
    short = [p for p in squad if len(played.get(p.id, ())) < rules.finals_min_regular]
    return {
        'squad': len(squad),
        'max': rules.max_roster,
        'eligible': len(squad) - len(short),
        'minimum': rules.finals_min_regular,
        'missing': [p.short_name for p in short],
    }


def walkovers(club, season=None, match_type=None):
    """
    No presentados y lesiones de los enfrentamientos cerrados: ``{'rival', 'own', 'injuries'}`` (rival o
    nuestro equipo sin presentarse y partidos terminados por lesión). None si la competición no tiene ni
    «No presentado» ni lesiones que completar.
    """
    rules = club.rules
    if not (rules.no_show or rules.injury_completes):
        return None
    matches = Match.objects.filter(club=club, draft_mode=False, **match_type_lookup(match_type))
    if season:
        matches = matches.filter(season=season)
    injuries = Result.objects.filter(game__match__in=matches, game__draft_mode=False).exclude(
        Q(injured_side='') | Q(injured_side__isnull=True)).values('game_id').distinct().count()
    return {
        'rival': matches.filter(no_show=Match.NO_SHOW_RIVAL).count(),
        'own': matches.filter(no_show=Match.NO_SHOW_OWN).count(),
        'injuries': injuries,
    }


def snp_by_season(club):
    """
    Puntos SNP de la plantilla actual sumados al cierre de cada temporada (la última actualización de
    cada jugador): ``{'labels', 'scores'}`` cronológico.
    """
    squad = Player.objects.filter(club=club, in_team=True)
    last = {}
    for row in SnpScoreHistory.objects.filter(player__in=squad).order_by('date'):
        last.setdefault(row.season, {})[row.player_id] = row.score
    seasons = sorted(last, key=lambda s: int(s.split('-')[0]))
    return {'labels': seasons, 'scores': [round(sum(last[s].values())) for s in seasons]}
