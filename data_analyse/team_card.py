"""
Piezas de «Estadísticas · Equipo» que no salen del log de partidos: puntos de cada enfrentamiento o
jornada, elegibilidad para las fases finales, no presentados y lesiones.

Todas devuelven datos simples para la plantilla y respetan los mismos filtros de temporada y tipo que el
resto de la página.
"""
from django.db.models import Q

from match.models import Game, Match, Result
from players.models import Player

from . import rivals
from .pairs import match_type_lookup

# Barras que se dibujan en «Puntos de liga» (las últimas jornadas o enfrentamientos).
LAST_BARS = 7


def _short_season(season):
    """«2025-2026» → «25-26» para las etiquetas de las barras."""
    parts = str(season).split('-')
    return '-'.join(p[-2:] for p in parts) if len(parts) == 2 else str(season)


def points_series(club, season=None, match_type=None, last=LAST_BARS):
    """
    Puntos ganados en cada enfrentamiento cerrado (los que dan puntos de liga si la competición tiene liga).

    Devuelve ``{'league', 'by_season', 'labels', 'values', 'total', 'played', 'average', 'possible',
    'best'}``. Con una temporada elegida hay una barra por jornada o enfrentamiento («J1»…, «E1»…); con
    «Todas», una barra por temporada (la suma de sus puntos, las ``last`` últimas). Con liga (LAPI) son
    puntos de liga; sin ella (SNP), los de cada enfrentamiento de los ``possible`` en juego. ``total``,
    ``played`` (jornadas o enfrentamientos), ``average`` (por jornada o enfrentamiento) y ``best``
    (mejor barra y su etiqueta) usan todos. None si no hay ninguno.
    """
    rules = club.rules
    league = bool(rules.league_type)
    rows = []
    for m in rivals.closed_matches(club, season, match_type):
        points = m.league_points if league else rivals.own_points(m)[0]
        if points is not None:
            rows.append((m, points))
    if not rows:
        return None
    by_season = not season
    if by_season:
        sums = {}
        for m, points in rows:
            sums[m.season] = sums.get(m.season, 0) + points
        ordered = sorted(sums, key=lambda s: int(str(s).split('-')[0]))
        labels = [_short_season(s) for s in ordered]
        values = [sums[s] for s in ordered]
    else:
        labels = [f"{'J' if league else 'E'}{m.round_number if league and m.round_number else i}"
                  for i, (m, _points) in enumerate(rows, start=1)]
        values = [points for _m, points in rows]
    best = max(range(len(values)), key=lambda i: values[i])
    total = sum(points for _m, points in rows)
    return {
        'league': league,
        'by_season': by_season,
        'labels': labels[-last:] if by_season else labels,
        'values': values[-last:] if by_season else values,
        'total': total,
        'played': len(rows),
        'average': round(total / len(rows), 1),
        'possible': None if league else rules.total_points,
        'best': {'value': values[best], 'label': labels[best]},
    }


def venue_matches(club, season=None, match_type=None):
    """
    Enfrentamientos cerrados como local y como visitante: ``{'local', 'visiting'}``, cada uno con
    ``{'won', 'lost', 'drawn', 'total'}`` desde el punto de vista del equipo propio.
    """
    out = {'local': dict.fromkeys(('won', 'lost', 'drawn', 'total'), 0),
           'visiting': dict.fromkeys(('won', 'lost', 'drawn', 'total'), 0)}
    for m in rivals.closed_matches(club, season, match_type):
        row = out['local' if m.own_is_local else 'visiting']
        row['total'] += 1
        outcome = rivals.outcome(m)
        row[{rivals.WIN: 'won', rivals.LOSS: 'lost', rivals.DRAW: 'drawn'}[outcome]] += 1
    return out


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
