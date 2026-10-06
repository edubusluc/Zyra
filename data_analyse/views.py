"""
Estadísticas del club: del equipo, por jugador, por parejas y advertencias.

Todas se calculan sobre los partidos cerrados del club y admiten filtro por temporada
y por tipo de partido.
"""
from django.shortcuts import render
from match.models import Match, Game, Result
from django.db.models import Sum
from django.db.models.functions import Coalesce
from players.models import Player
from team.models import Team
from call.models import Call
from django.db.models import Q, Count
from django.views.decorators.http import require_GET
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.utils.translation import gettext as _
from core.decorators import club_required, club_admin_required
from penalty.models import Penalty
from players.models import current_season
from . import pairs as pair_stats

# ---------------------------------------------------------------
# ESTADÍSTICAS EQUIPO
# ---------------------------------------------------------------
LOCAL_WIN = "Victoria Local"
VISITING_WIN = "Victoria Visitante"
# Empate a puntos en la eliminatoria (p. ej. 6-6): ni victoria ni derrota.
DRAW = "EMPATE"


def get_total_season(matchs):
    """Temporadas distintas de los partidos de ``matchs``."""
    return set(matchs.values_list('season', flat=True).distinct())


# ---------------------------------------------------------------
# FILTRO POR TIPO DE PARTIDO: Todos / Competitivos (enfrentamiento, reto, play off) / Amistosos
# ---------------------------------------------------------------
MATCH_TYPE_PARAM = "match_type"
COMPETITIVE = pair_stats.COMPETITIVE


def selected_match_type(request):
    """Filtro elegido en la URL (?match_type=competitivo, reto, amistoso...); None = todos."""
    value = request.GET.get(MATCH_TYPE_PARAM)
    return value if value in pair_stats.FILTER_VALUES else None


# ---------------------------------------------------------------
# SELECTOR DE TEMPORADAS: Todas + las tres últimas + buscador para el resto
# ---------------------------------------------------------------
SEASON_PARAM = "season"
PAGE_PARAM = "page"
RECENT_SEASONS = 3


def season_filter_context(request, seasons, selected_season, all_value=None, anchor=""):
    """
    Chips "Todas" y las ``RECENT_SEASONS`` temporadas más recientes (``seasons`` de más nueva a
    más antigua); si la elegida es más antigua, aparece también como chip activo. Con más temporadas
    de las que caben en los chips, ``season_search`` lista todas para el buscador. Cada enlace conserva
    el resto de la URL (jugador, tipo de partido) salvo la página, que vuelve a la primera.
    ``all_value`` es el valor de "Todas" en la URL (advertencias y el listado de partidos usan
    ?season=all porque sin parámetro muestran la temporada actual).
    """
    def url(value):
        """URL de la página actual con la temporada ``value`` (sin ella para «Todas»)."""
        params = request.GET.copy()
        params.pop(PAGE_PARAM, None)
        if value:
            params[SEASON_PARAM] = value
        else:
            params.pop(SEASON_PARAM, None)
        query = params.urlencode()
        return f"{request.path}?{query}{anchor}" if query else f"{request.path}{anchor}"

    all_active = selected_season in (None, "", all_value)
    chips = list(seasons[:RECENT_SEASONS])
    if not all_active and selected_season not in chips:
        chips.append(selected_season)
    return {
        'season_all': {'url': url(all_value), 'active': all_active},
        'season_chips': [{'label': s, 'url': url(s), 'active': s == selected_season} for s in chips],
        'season_search': list(seasons) if len(seasons) > RECENT_SEASONS else [],
        # Resto de la URL para el formulario del buscador.
        'season_keep': [(key, value) for key, values in request.GET.lists() if key not in (SEASON_PARAM, PAGE_PARAM)
                        for value in values],
        'season_anchor': anchor,
    }


def match_type_context(request, match_type):
    """
    Filtro por tipo de partido: chips Todos / Competitivos / Amistosos (``match_types``) y, dentro
    de Competitivos, un selector con todos los partidos competitivos o un tipo (``competitive_types``).
    Cada enlace conserva el resto de la URL (jugador, pareja, temporada); ``match_type_qs`` sirve
    para añadir el filtro a los enlaces que ya existían (temporadas).
    """
    def url(value):
        """URL de la página actual con el tipo de partido ``value`` (sin él para «Todos»)."""
        params = request.GET.copy()
        if value:
            params[MATCH_TYPE_PARAM] = value
        else:
            params.pop(MATCH_TYPE_PARAM, None)
        query = params.urlencode()
        return f"{request.path}?{query}" if query else request.path

    competitive = match_type == COMPETITIVE or match_type in dict(Match.COMPETITIVE_TYPES)
    options = [
        {'label': _("Todos"), 'url': url(None), 'active': match_type is None},
        {'label': _("Competitivos"), 'url': url(COMPETITIVE), 'active': competitive},
        {'label': _("Amistosos"), 'url': url(Match.AMISTOSO), 'active': match_type == Match.AMISTOSO},
    ]
    competitive_labels = [(COMPETITIVE, _("Todos los partidos")), (Match.ENFRENTAMIENTO, _("Enfrentamientos")),
                          (Match.RETO, _("Retos")), (Match.PLAYOFF, _("Play offs"))]
    labels = dict(competitive_labels, **{COMPETITIVE: _("Competitivos"), Match.AMISTOSO: _("Amistosos")})
    return {
        'match_types': options,
        'competitive_types': [{'label': label, 'value': value, 'url': url(value), 'active': value == match_type}
                              for value, label in competitive_labels] if competitive else [],
        # Resto de la URL (jugador, pareja, temporada) para el formulario del selector de Competitivos.
        'match_type_keep': [(key, value) for key, values in request.GET.lists() if key != MATCH_TYPE_PARAM
                            for value in values],
        'selected_match_type': match_type,
        'selected_match_type_label': labels.get(match_type),
        'match_type_qs': f"&{MATCH_TYPE_PARAM}={match_type}" if match_type else "",
    }


def _by_type(matches, match_type, prefix=""):
    """Filtra un queryset por el filtro de tipo; ``prefix`` es la ruta hasta Match ('match__')."""
    return matches.filter(**pair_stats.match_type_lookup(match_type, prefix))


def calculate_match_statistics(season, team, match_type=None):
    """
    Enfrentamientos cerrados del club (de la temporada si se indica): (total, ganados,
    empatados, perdidos, % ganados, % empatados, % perdidos). Una eliminatoria empatada a
    puntos cuenta como empate, no como derrota.
    """
    matches = _by_type(Match.objects.filter(club=team.club, draft_mode=False), match_type)
    if season is not None:
        matches = matches.filter(season=season)
    total_matches = matches.count()
    won_local = matches.filter(local=team, result=LOCAL_WIN).count()
    won_visiting = matches.filter(visiting=team, result=VISITING_WIN).count()

    total_won = won_local + won_visiting
    drawn_matches = matches.filter(result=DRAW).count()
    lost_matches = total_matches - total_won - drawn_matches

    def pct(n):
        """``n`` como porcentaje del total, con dos decimales."""
        return round(n / total_matches * 100, 2) if total_matches > 0 else 0

    return (total_matches, total_won, drawn_matches, lost_matches,
            pct(total_won), pct(drawn_matches), pct(lost_matches))


def _games_totals(season, team, own_local, match_type=None):
    """
    Juegos ganados y perdidos por el equipo jugando en casa (own_local) o fuera,
    sumados en la base de datos con una sola consulta.
    """
    results = _by_type(Result.objects.filter(game__match__draft_mode=False), match_type, "game__match__")
    results = results.filter(game__match__local=team) if own_local else results.filter(game__match__visiting=team)
    if season is not None:
        results = results.filter(game__match__season=season)
    sums = results.aggregate(**{
        f"{side}{n}": Coalesce(Sum(f"set{n}_{side}"), 0)
        for side in ("local", "visiting") for n in (1, 2, 3)
    })
    local = sums["local1"] + sums["local2"] + sums["local3"]
    visiting = sums["visiting1"] + sums["visiting2"] + sums["visiting3"]
    won, lost = (local, visiting) if own_local else (visiting, local)
    total = won + lost
    return (
        won, lost,
        round(won / total * 100, 2) if total else 0,
        round(lost / total * 100, 2) if total else 0,
    )


def calculate_local_game_statistics(season, team, match_type=None):
    """Juegos ganados y perdidos (y sus %) del equipo cuando juega en casa."""
    return _games_totals(season, team, own_local=True, match_type=match_type)


def calculate_visiting_game_statistics(season, team, match_type=None):
    """Juegos ganados y perdidos (y sus %) del equipo cuando juega fuera."""
    return _games_totals(season, team, own_local=False, match_type=match_type)


def calculate_matches_won_per_year(team, match_type=None):
    """{temporada: {'won', 'drawn', 'lost'}} en orden, con una sola consulta."""
    dicc_match = {}
    rows = _by_type(Match.objects.filter(club=team.club, draft_mode=False), match_type).values_list('season', 'result', 'local_id', 'visiting_id')
    for season, result, local_id, visiting_id in rows:
        d = dicc_match.setdefault(season, {'won': 0, 'drawn': 0, 'lost': 0})
        if (result == LOCAL_WIN and local_id == team.id) or (result == VISITING_WIN and visiting_id == team.id):
            d['won'] += 1
        elif result == DRAW:
            d['drawn'] += 1
        elif result in (LOCAL_WIN, VISITING_WIN):
            d['lost'] += 1
    return dict(sorted(dicc_match.items()))


def column_chart(club, season, match_type=None):
    """Partidos de 2 y 3 puntos ganados/perdidos por jugador actual (una sola consulta)."""
    players = Player.objects.filter(club=club, in_team=True)
    names = {p.id: p.full_name for p in players}
    dicc = {
        name: {
            'Partidos de 2 puntos ganados': 0,
            'Partidos de 2 puntos perdidos': 0,
            'Partidos de 3 puntos ganados': 0,
            'Partidos de 3 puntos perdidos': 0,
        } for name in names.values()
    }

    games = Game.objects.filter(match__club=club, draft_mode=False, winner__in=("Local", "Visitante"), n_game__in=[1, 2, 3, 4, 5])
    if season:
        games = games.filter(match__season=season)
    games = _by_type(games, match_type, "match__")
    rows = games.values_list('n_game', 'winner', 'player_1_local', 'player_2_local', 'player_1_visiting', 'player_2_visiting')
    for n_game, winner, l1, l2, v1, v2 in rows:
        kind = '3' if n_game in (1, 2) else '2'
        for pid, side in ((l1, "Local"), (l2, "Local"), (v1, "Visitante"), (v2, "Visitante")):
            if pid in names:
                outcome = 'ganados' if winner == side else 'perdidos'
                dicc[names[pid]][f'Partidos de {kind} puntos {outcome}'] += 1

    return dicc


def format_for_chart(dic):
    """Datos de ``column_chart`` como lista de {'player', 'data'} para el gráfico de columnas."""
    players = []
    for player_name, stats in dic.items():
        players.append({
            'player': player_name,
            'data': [
                stats['Partidos de 2 puntos ganados'],
                stats['Partidos de 2 puntos perdidos'],
                stats['Partidos de 3 puntos ganados'],
                stats['Partidos de 3 puntos perdidos'],
            ]
        })
    return players


@club_required
@require_GET
def team_statistics(request):
    """
    Estadísticas del equipo propio: balance de enfrentamientos y juegos, evolución por
    temporada, partidos de 2 y 3 puntos por jugador y top 5 de jugadores y parejas.
    Requiere pertenecer al club y solo GET. Filtra por temporada (``?season=``) y tipo de partido.
    """
    seasons = get_total_season(Match.objects.filter(club=request.club))
    selected_season = request.GET.get("season")
    team = request.club.own_team
    match_type = selected_match_type(request)
    min_games_pair = pair_stats.min_games_pair(match_type)

    seasons = sorted(seasons, key=lambda s: int(s.split('-')[0]), reverse=True)
    if selected_season not in seasons:
        selected_season = None

    dicc = column_chart(request.club, selected_season, match_type)
    column_chart_data = format_for_chart(dicc)

    if not team:
        return render(request, 'team_statistics.html', {"seasons": seasons, **match_type_context(request, match_type),
                                                        **season_filter_context(request, seasons, selected_season)})

    (total_matches, total_won, drawn_matches, lost_matches,
     percentage_won, percentage_drawn, percentage_lost) = calculate_match_statistics(selected_season or None, team, match_type)
    local_games_won, local_games_lost, percentage_local_games_won, percentage_local_games_lost = calculate_local_game_statistics(selected_season or None, team, match_type)
    visiting_games_won, visiting_games_lost, percentage_visiting_games_won, percentage_visiting_games_lost = calculate_visiting_game_statistics(selected_season or None, team, match_type)

    dicc_line_chart = calculate_matches_won_per_year(team, match_type)

    # Top 5 (jugadores actuales del equipo), respetando la temporada y el tipo de partido elegidos
    squad = list(Player.objects.filter(club=request.club, in_team=True))
    log = pair_stats.club_game_log(request.club, selected_season or None, match_type)

    context = {
        **match_type_context(request, match_type),
        **season_filter_context(request, seasons, selected_season),
        'team': team,
        'total_matches': total_matches,
        'won_matches': total_won,
        'drawn_matches': drawn_matches,
        'lost_matches': lost_matches,
        'local_games_won': local_games_won,
        'local_games_lost': local_games_lost,
        'percentage_won': percentage_won,
        'percentage_drawn': percentage_drawn,
        'percentage_lost': percentage_lost,
        'visiting_games_won': visiting_games_won,
        'visiting_games_lost': visiting_games_lost,
        'percentage_local_games_won': percentage_local_games_won,
        'percentage_local_games_lost': percentage_local_games_lost,
        'percentage_visiting_games_won': percentage_visiting_games_won,
        'percentage_visiting_games_lost': percentage_visiting_games_lost,
        'dicc_line_chart': dicc_line_chart,
        "seasons": seasons,
        "selected_season": selected_season,
        "column_chart_data": column_chart_data,
        "top_local_players": pair_stats.top_players(log, squad, local=True),
        "top_visiting_players": pair_stats.top_players(log, squad, local=False),
        "top_local_pairs": pair_stats.top_pairs(log, squad, local=True, min_games=min_games_pair),
        "top_visiting_pairs": pair_stats.top_pairs(log, squad, local=False, min_games=min_games_pair),
        "min_games_player": pair_stats.MIN_GAMES_PLAYER,
        "min_games_pair": min_games_pair,
    }

    return render(request, 'team_statistics.html', context)


# ---------------------------------------------------------------
# ESTADÍSTICAS JUGADORES
# ---------------------------------------------------------------

# Orden cronológico de los partidos del jugador (por fecha, como pairs.club_game_log).
# De esto dependen las rachas.
ORDER = ('match__start_date', 'match_id', 'n_game')

# Peso del "punto de partida" neutro (50 %) en la afinidad, medido en puntos en juego.
PRIOR_POINTS = 6


def degree_of_affinity(player, match_type=None):
    """
    Afinidad (0-100) con cada compañero con el que ha jugado en pareja.
    % de puntos ganados en pareja (cada partido pesa game.score), suavizado
    hacia el 50 % cuando hay pocos partidos.
    Incluye a los compañeros que ya no están en el equipo (in_team=False) y a los
    eliminados (por el nombre guardado en el partido); 'in_team' los distingue.
    Devuelve: [{'name', 'affinity', 'games', 'wins', 'losses', 'in_team'}, ...] de mayor a menor.
    """
    games = Game.objects.filter(
        Q(player_1_local=player) | Q(player_2_local=player) |
        Q(player_1_visiting=player) | Q(player_2_visiting=player),
        draft_mode=False,
        winner__in=('Local', 'Visitante'),
    )
    games = _by_type(games, match_type, "match__")

    people = {p.id: p for p in Player.objects.filter(club=player.club).exclude(id=player.id)}
    acc = {}

    for g in games:
        if player.id in (g.player_1_local_id, g.player_2_local_id):
            side, slots = 'Local', ('player_1_local', 'player_2_local')
        else:
            side, slots = 'Visitante', ('player_1_visiting', 'player_2_visiting')

        partner_slot = slots[1] if getattr(g, slots[0] + '_id') == player.id else slots[0]
        partner_id = getattr(g, partner_slot + '_id')
        if partner_id in people:
            partner = people[partner_id]
            key, name, in_team = partner_id, partner.full_name, partner.in_team
        elif partner_id is None and g.removed_player_names.get(partner_slot):
            # Jugador eliminado: se agrupa por el nombre guardado en el partido
            name = g.removed_player_names[partner_slot].upper()
            key, in_team = ('removed', name), False
        else:
            continue

        won = g.winner == side
        weight = g.score or 1
        a = acc.setdefault(key, {'name': name, 'in_team': in_team, 'games': 0, 'wins': 0, 'stake': 0, 'won_pts': 0})
        a['games'] += 1
        a['wins'] += won
        a['stake'] += weight
        a['won_pts'] += weight if won else 0

    results = []
    for a in acc.values():
        rate = (a['won_pts'] + PRIOR_POINTS * 0.5) / (a['stake'] + PRIOR_POINTS)
        results.append({
            'name': a['name'],
            'affinity': round(rate * 100),
            'games': a['games'],
            'wins': a['wins'],
            'losses': a['games'] - a['wins'],
            'in_team': a['in_team'],
        })

    results.sort(key=lambda r: (r['affinity'], r['games']), reverse=True)
    return results


def build_game_log(player, match_type=None):
    """
    Una sola consulta (+1 prefetch): lista cronológica de los partidos (Game) del jugador.
    Cada elemento: {'season', 'local', 'won', 'points', 'sets_won', 'sets_lost'}
    'sets_*' son los "juegos" que suma el jugador y su rival dentro del partido.
    """
    games = (
        Game.objects
        .filter(
            Q(player_1_local=player) | Q(player_2_local=player) |
            Q(player_1_visiting=player) | Q(player_2_visiting=player),
            draft_mode=False,
        )
        .select_related('match')
        .prefetch_related('results')
        .order_by(*ORDER)
    )
    games = _by_type(games, match_type, "match__")

    log = []
    for g in games:
        if g.winner not in ('Local', 'Visitante'):
            continue  # partido sin cerrar
        is_local = player.id in (g.player_1_local_id, g.player_2_local_id)
        won = (g.winner == 'Local') == is_local

        sets_won = sets_lost = 0
        for r in g.results.all():
            loc = sum(filter(None, [r.set1_local, r.set2_local, r.set3_local]))
            vis = sum(filter(None, [r.set1_visiting, r.set2_visiting, r.set3_visiting]))
            mine, theirs = (loc, vis) if is_local else (vis, loc)
            sets_won += mine
            sets_lost += theirs

        log.append({
            'season': g.match.season,
            'local': is_local,
            'won': won,
            'points': g.score if won else 0,
            'sets_won': sets_won,
            'sets_lost': sets_lost,
        })
    return log


def _sets_text(game, is_local):
    """Sets desde el punto de vista del club ("6-3 4-6 10-8"). Usa game.results prefetched."""
    result = next(iter(game.results.all()), None)
    if not result:
        return ""
    return " ".join(
        f"{loc}-{vis}" if is_local else f"{vis}-{loc}"
        for loc, vis in result.sets() if loc is not None and vis is not None
    )


def season_games(player, season, match_type=None):
    """
    Partidos (Game) cerrados del jugador en una temporada, del más reciente al más antiguo.
    Solo partidos de enfrentamientos de su club: los enlaces llevan a call_for_match,
    que también exige que el enfrentamiento sea del club activo.
    Cada elemento: {'match_id', 'match_public_id', 'n_game', 'date', 'rival', 'local', 'partner', 'sets', 'won', 'points'}
    """
    games = (
        Game.objects
        .filter(
            Q(player_1_local=player) | Q(player_2_local=player) |
            Q(player_1_visiting=player) | Q(player_2_visiting=player),
            draft_mode=False,
            winner__in=('Local', 'Visitante'),
            match__club=player.club,
            match__season=season,
        )
        .select_related('match__local', 'match__visiting',
                        'player_1_local', 'player_2_local', 'player_1_visiting', 'player_2_visiting')
        .prefetch_related('results')
        .order_by('-match__start_date', '-match_id', 'n_game')
    )
    games = _by_type(games, match_type, "match__")

    rows = []
    for g in games:
        is_local = player.id in (g.player_1_local_id, g.player_2_local_id)
        pair = (g.player_1_local, g.player_2_local) if is_local else (g.player_1_visiting, g.player_2_visiting)
        partner = next((p for p in pair if p and p.id != player.id), None)
        won = (g.winner == 'Local') == is_local

        rows.append({
            'match_id': g.match_id,
            'match_public_id': g.match.public_id,
            'n_game': g.n_game,
            'date': g.match.start_date,
            'rival': g.match.visiting_name if is_local else g.match.local_name,
            'local': is_local,
            'partner': partner,
            'sets': _sets_text(g, is_local),
            'won': won,
            'points': g.score if won else 0,
        })
    return rows


def calls_by_season(player, match_type=None):
    """Convocatorias por temporada: ({temporada: a las que se apuntó}, {temporada: total})."""
    base = _by_type(Call.objects.filter(match__club=player.club, draft_mode=False), match_type, "match__")
    total = dict(base.order_by().values_list('match__season').annotate(n=Count('id', distinct=True)))
    present = dict(
        base.filter(players__id=player.id)
        .order_by().values_list('match__season').annotate(n=Count('id', distinct=True))
    )
    return present, total


def _pct(wins, total):
    """Porcentaje con un decimal; 0 si no hay partidos."""
    return round(wins / total * 100, 1) if total else 0


def _longest_run(results, target):
    """Racha más larga de resultados iguales a ``target`` (True: victorias, False: derrotas)."""
    best = run = 0
    for r in results:
        run = run + 1 if r == target else 0
        best = max(best, run)
    return best


def _current_run(results):
    """Devuelve ('V', 4) o ('D', 2). Sin partidos: (None, 0)."""
    if not results:
        return None, 0
    last, n = results[-1], 0
    for r in reversed(results):
        if r != last:
            break
        n += 1
    return ('V' if last else 'D'), n


def summarize(log):
    """Todas las métricas a partir de un log (global o de una temporada)."""
    results = [g['won'] for g in log]
    local_games = [g for g in log if g['local']]
    visiting_games = [g for g in log if not g['local']]
    local = [g['won'] for g in local_games]
    visiting = [g['won'] for g in visiting_games]

    total, wins = len(results), sum(results)
    streak_type, streak_len = _current_run(results)

    local_sets_won = sum(g['sets_won'] for g in local_games)
    local_sets_lost = sum(g['sets_lost'] for g in local_games)
    visiting_sets_won = sum(g['sets_won'] for g in visiting_games)
    visiting_sets_lost = sum(g['sets_lost'] for g in visiting_games)

    return {
        'played': total,
        'wins': wins,
        'losses': total - wins,
        'pct': _pct(wins, total),
        'points': sum(g['points'] for g in log),

        'local_played': len(local),
        'local_wins': sum(local),
        'local_losses': len(local) - sum(local),
        'local_pct': _pct(sum(local), len(local)),
        'local_sets_won': local_sets_won,
        'local_sets_lost': local_sets_lost,
        'local_sets_total': local_sets_won + local_sets_lost,

        'visiting_played': len(visiting),
        'visiting_wins': sum(visiting),
        'visiting_losses': len(visiting) - sum(visiting),
        'visiting_pct': _pct(sum(visiting), len(visiting)),
        'visiting_sets_won': visiting_sets_won,
        'visiting_sets_lost': visiting_sets_lost,
        'visiting_sets_total': visiting_sets_won + visiting_sets_lost,

        'streak_type': streak_type,
        'streak_len': streak_len,
        'best_win_streak': _longest_run(results, True),
        'worst_loss_streak': _longest_run(results, False),
        'best_local_streak': _longest_run(local, True),
        'best_visiting_streak': _longest_run(visiting, True),

        # últimos 5, el más reciente a la derecha
        'form': results[-5:],
    }


def summarize_by_season(log, calls_present, calls_total):
    """Temporadas (ascendente) con métricas, convocatorias y variación de % vs. la anterior."""
    by_season = {}
    for g in log:
        by_season.setdefault(g['season'], []).append(g)

    rows, previous = [], None
    for season in sorted(by_season, key=lambda s: int(s.split('-')[0])):
        games = by_season[season]
        wins = sum(g['won'] for g in games)
        pct = _pct(wins, len(games))
        rows.append({
            'season': season,
            'played': len(games),
            'wins': wins,
            'losses': len(games) - wins,
            'pct': pct,
            'points': sum(g['points'] for g in games),
            'calls_present': calls_present.get(season, 0),
            'calls_total': calls_total.get(season, 0),
            'delta': round(pct - previous, 1) if previous is not None else None,
        })
        previous = pct
    return rows


@club_required
@require_GET
def statistics_per_player(request):
    """
    Estadísticas de un jugador del club (``?player=``): balance, rachas, evolución por
    temporada, afinidad con sus compañeros, puntos SNP y, con ``?season=``, el detalle de esa
    temporada. Sin jugador muestra solo el selector. Requiere pertenecer al club y solo GET.
    """
    players = Player.objects.filter(club=request.club, in_team=True).order_by('name', 'last_name')
    player_id = request.GET.get('player')
    match_type = selected_match_type(request)

    if not player_id:
        return render(request, 'player_statistics.html', {'players': players, **match_type_context(request, match_type)})

    # Solo jugadores del club activo: los de otros clubes dan 404
    player = get_object_or_404(Player, public_id=player_id, club=request.club)

    # Chips de temporada: todas las del club
    all_seasons = sorted(get_total_season(Match.objects.filter(club=request.club)),
                         key=lambda s: int(s.split('-')[0]), reverse=True)
    selected_season = request.GET.get('season')
    if selected_season not in all_seasons:
        selected_season = None

    log = build_game_log(player, match_type)
    summary = summarize(log)
    calls_present, calls_total = calls_by_season(player, match_type)
    rows = summarize_by_season(log, calls_present, calls_total)

    # Detalle de la temporada elegida
    detail = None
    if selected_season:
        detail = summarize([g for g in log if g['season'] == selected_season])
        present = calls_present.get(selected_season, 0)
        total = calls_total.get(selected_season, 0)
        detail.update({
            'calls_present': present,
            'calls_total': total,
            'calls_absent': total - present,
            'games': season_games(player, selected_season, match_type),
        })

    # Puntos SNP de la temporada elegida (o de la actual), uno por actualización semanal
    snp_season = selected_season or current_season()
    snp_history = list(player.snp_history.filter(season=snp_season))

    context = {
        **match_type_context(request, match_type),
        **season_filter_context(request, all_seasons, selected_season, anchor="#temporadas"),
        'players': players,
        'selected_player': player.public_id,
        'player': player,
        'seasons': all_seasons,
        'selected_season': selected_season,
        's': summary,
        'd': detail,
        'seasons_asc': rows,
        'seasons_desc': list(reversed(rows)),
        # enteros para anchos de barra (evita comas decimales en style="")
        'pct_w': round(summary['pct']),
        'local_pct_w': round(summary['local_pct']),
        'visiting_pct_w': round(summary['visiting_pct']),
        # datos de los gráficos (json_script en la plantilla)
        'chart_seasons': {
            'labels': [r['season'] for r in rows],
            'wins': [r['wins'] for r in rows],
            'losses': [r['losses'] for r in rows],
            'pct': [r['pct'] for r in rows],
        },
        'chart_affinity': degree_of_affinity(player, match_type),
        'snp_season': snp_season,
        'chart_snp': {
            'labels': [h.date.strftime('%d/%m') for h in snp_history],
            'scores': [h.score for h in snp_history],
        },
    }
    return render(request, 'player_statistics.html', context)


# ---------------------------------------------------------------
# ESTADÍSTICAS POR PAREJAS
# ---------------------------------------------------------------

@club_required
@require_GET
def statistics_per_pair(request):
    """
    Estadísticas por parejas: mejores y peores parejas del club y, con ``?p1=`` y ``?p2=``,
    el detalle de esa pareja y sus últimos partidos. Un jugador de otro club da 404.
    Requiere pertenecer al club y solo GET.
    """
    club_players = list(Player.objects.filter(club=request.club).order_by('name', 'last_name'))
    by_public_id = {p.public_id: p for p in club_players}
    match_type = selected_match_type(request)
    min_games_pair = pair_stats.min_games_pair(match_type)
    log = pair_stats.club_game_log(request.club, match_type=match_type)
    best_pairs, worst_pairs = pair_stats.best_and_worst_pairs(pair_stats.all_pairs(log, club_players), min_games=min_games_pair)

    p1_id, p2_id = request.GET.get('p1', ''), request.GET.get('p2', '')
    context = {
        **match_type_context(request, match_type),
        'players': club_players,
        'best_pairs': best_pairs,
        'worst_pairs': worst_pairs,
        'min_games_pair': min_games_pair,
        'selected_p1': p1_id or None,
        'selected_p2': p2_id or None,
    }

    if context['selected_p1'] and context['selected_p2']:
        # Solo jugadores del club activo: los de otros clubes dan 404
        p1, p2 = by_public_id.get(context['selected_p1']), by_public_id.get(context['selected_p2'])
        if p1 is None or p2 is None:
            raise Http404("Jugador no encontrado")
        if p1 == p2:
            context['error'] = _("Elige dos jugadores distintos.")
        else:
            summary = pair_stats.pair_summary(log, p1.id, p2.id)
            context.update({
                'p1': p1,
                'p2': p2,
                's': summary,
                'last_games': pair_last_games(request.club, p1, p2, match_type=match_type),
                'pct_w': round(summary['pct']),
                'local_pct_w': round(summary['local_pct']),
                'visiting_pct_w': round(summary['visiting_pct']),
                'chart_seasons': {
                    'labels': [r['season'] for r in summary['seasons']],
                    'wins': [r['wins'] for r in summary['seasons']],
                    'losses': [r['losses'] for r in summary['seasons']],
                    'pct': [r['pct'] for r in summary['seasons']],
                },
            })

    return render(request, 'pair_statistics.html', context)


PAIR_LAST_GAMES = 5


def pair_last_games(club, p1, p2, n=PAIR_LAST_GAMES, match_type=None):
    """
    Últimos `n` partidos (Game) cerrados de la pareja en el club, del más reciente al más antiguo.
    Cada elemento: {'match_id', 'match_public_id', 'n_game', 'date', 'season', 'rival', 'local', 'sets', 'won', 'points'}
    """
    together = (
        Q(player_1_local=p1, player_2_local=p2) | Q(player_1_local=p2, player_2_local=p1) |
        Q(player_1_visiting=p1, player_2_visiting=p2) | Q(player_1_visiting=p2, player_2_visiting=p1)
    )
    games = (
        Game.objects
        .filter(together, draft_mode=False, winner__in=('Local', 'Visitante'), match__club=club,
                **pair_stats.match_type_lookup(match_type, prefix='match__'))
        .select_related('match__local', 'match__visiting')
        .prefetch_related('results')
        .order_by('-match__start_date', '-match_id', '-n_game')[:n]
    )
    rows = []
    for g in games:
        is_local = p1.id in (g.player_1_local_id, g.player_2_local_id)
        won = (g.winner == 'Local') == is_local
        rows.append({
            'match_id': g.match_id,
            'match_public_id': g.match.public_id,
            'n_game': g.n_game,
            'date': g.match.start_date,
            'season': g.match.season,
            'rival': g.match.visiting_name if is_local else g.match.local_name,
            'local': is_local,
            'sets': _sets_text(g, is_local),
            'won': won,
            'points': (g.score or 0) if won else 0,
        })
    return rows


# ---------------------------------------------------------------
# ADVERTENCIAS (solo capitanes)
# ---------------------------------------------------------------

ALL_SEASONS = "all"


@club_admin_required
@require_GET
def warnings_statistics(request):
    """
    Advertencias del club por jugador y su ranking. Solo capitanes y solo GET. Sin
    ``?season=`` muestra la temporada actual; ``?season=all``, todas.
    """
    penalties = (
        Penalty.objects
        .filter(player__club=request.club, call__match__club=request.club)
        .select_related('player', 'call__match__local', 'call__match__visiting')
        .order_by('-call__match__start_date', '-id')
    )

    seasons = set(penalties.values_list('call__match__season', flat=True)) | {current_season()}
    seasons = sorted((x for x in seasons if x and x != "NONE"), reverse=True)
    selected_season = request.GET.get('season') or current_season()
    if selected_season != ALL_SEASONS:
        penalties = penalties.filter(call__match__season=selected_season)
    penalties = list(penalties)

    by_player = {}
    for pen in penalties:
        row = by_player.setdefault(pen.player_id, {'player': pen.player, 'count': 0, 'items': []})
        row['count'] += 1
        row['items'].append(pen)
    ranking = sorted(by_player.values(), key=lambda r: (-r['count'], r['player'].name, r['player'].last_name))

    return render(request, 'warnings_statistics.html', {
        **season_filter_context(request, seasons, selected_season, all_value=ALL_SEASONS),
        'seasons': seasons,
        'selected_season': selected_season,
        'all_seasons': ALL_SEASONS,
        'penalties': penalties,
        'ranking': ranking,
        'total': len(penalties),
        'players_warned': len(by_player),
        'matches_warned': len({p.call.match_id for p in penalties}),
    })
