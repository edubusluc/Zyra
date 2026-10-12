"""
Estadísticas por parejas y rankings (top 5) del equipo.

Todo parte de un único "log" cronológico con los partidos (Game) cerrados del
club. En cada Game solo figuran los jugadores del propio club, en el lado local
o en el visitante, así que la pareja es siempre la del lado que tiene jugadores.
"""
from django.db.models import Q

from match.models import Game, Match

from .sets import own_sets

# Mínimo de partidos para entrar en un top 5 (evita que un 1/1 = 100 % encabece la tabla).
MIN_GAMES_PLAYER = 2
MIN_GAMES_PAIR = 2
TOP_N = 5

# En retos y play off se juegan pocos partidos: sus parejas se muestran sin mínimo.
NO_MINIMUM_MATCH_TYPES = (Match.RETO, Match.PLAYOFF)


# Filtro "Competitivos": todos los tipos de partido competitivo (enfrentamiento, reto, play off).
COMPETITIVE = "competitivo"
FILTER_VALUES = {COMPETITIVE, *dict(Match.MATCH_TYPES)}


def match_type_lookup(match_type, prefix=""):
    """Argumentos de .filter() para un valor del filtro de tipo; ``prefix`` es la ruta hasta Match ('match__')."""
    if not match_type:
        return {}
    if match_type == COMPETITIVE:
        return {f"{prefix}match_type__in": [value for value, _ in Match.COMPETITIVE_TYPES]}
    return {f"{prefix}match_type": match_type}


def min_games_pair(match_type=None):
    """Partidos mínimos de una pareja para salir en rankings según el tipo de partido filtrado."""
    return 1 if match_type in NO_MINIMUM_MATCH_TYPES else MIN_GAMES_PAIR


def pair_key(a_id, b_id):
    """Una pareja es la misma juegue quien juegue en el drive o en el revés."""
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


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
    """('V', 4) o ('D', 2). Sin partidos: (None, 0)."""
    if not results:
        return None, 0
    last, n = results[-1], 0
    for r in reversed(results):
        if r != last:
            break
        n += 1
    return ('V' if last else 'D'), n


def club_game_log(club, season=None, match_type=None):
    """
    Partidos cerrados del club en orden cronológico (de un tipo de partido si se indica). Cada elemento:
    {'pair': (id, id), 'local': bool, 'won': bool, 'season', 'match_id', 'date', 'n_game',
    'points', 'sets'} (``sets``: sets jugados desde el lado del club, ver data_analyse.sets).
    """
    games = (
        Game.objects
        .filter(match__club=club, draft_mode=False, winner__in=('Local', 'Visitante'))
        .select_related('match')
        .prefetch_related('results')
        .order_by('match__start_date', 'match_id', 'n_game')
    )
    if season:
        games = games.filter(match__season=season)
    games = games.filter(**match_type_lookup(match_type, "match__"))

    log = []
    for g in games:
        if g.player_1_local_id and g.player_2_local_id:
            is_local, a, b = True, g.player_1_local_id, g.player_2_local_id
        elif g.player_1_visiting_id and g.player_2_visiting_id:
            is_local, a, b = False, g.player_1_visiting_id, g.player_2_visiting_id
        else:
            continue  # partido sin pareja completa
        won = (g.winner == 'Local') == is_local
        log.append({
            'pair': pair_key(a, b),
            'local': is_local,
            'won': won,
            'season': g.match.season,
            'match_id': g.match_id,
            'date': g.match.start_date,
            'n_game': g.n_game,
            'points': (g.score or 0) if won else 0,
            'sets': own_sets(next(iter(g.results.all()), None), is_local),
        })
    return log


# ---------------------------------------------------------------
# Rankings del equipo
# ---------------------------------------------------------------

def _rank(counts, names, min_games):
    """
    Filas del top 5 a partir de ``counts`` ({clave: (victorias, jugados)}): solo las claves
    con nombre y al menos ``min_games`` partidos, ordenadas por % de victorias.
    """
    rows = []
    for key, (wins, played) in counts.items():
        if played < min_games or key not in names:
            continue
        rows.append({
            'name': names[key],
            'played': played,
            'wins': wins,
            'losses': played - wins,
            'pct': _pct(wins, played),
        })
    rows.sort(key=lambda r: (r['pct'], r['played'], r['wins']), reverse=True)
    return rows[:TOP_N]


def top_players(log, players, local):
    """Top 5 jugadores por % de victorias como local (local=True) o visitante."""
    names = {p.id: p.full_name for p in players}
    counts = {}
    for g in log:
        if g['local'] != local:
            continue
        for pid in g['pair']:
            wins, played = counts.get(pid, (0, 0))
            counts[pid] = (wins + g['won'], played + 1)
    return _rank(counts, names, MIN_GAMES_PLAYER)


def top_pairs(log, players, local, min_games=MIN_GAMES_PAIR):
    """Top 5 parejas por % de victorias como local (local=True) o visitante."""
    by_id = {p.id: p for p in players}
    counts = {}
    for g in log:
        if g['local'] != local:
            continue
        wins, played = counts.get(g['pair'], (0, 0))
        counts[g['pair']] = (wins + g['won'], played + 1)
    names = {
        key: f"{pair_label(by_id[key[0]])} / {pair_label(by_id[key[1]])}"
        for key in counts if key[0] in by_id and key[1] in by_id
    }
    return _rank(counts, names, min_games)


def pair_label(player):
    """Nombre de un jugador dentro de una pareja: nombre y primer apellido."""
    return player.short_name


# ---------------------------------------------------------------
# Detalle de una pareja
# ---------------------------------------------------------------

def all_pairs(log, players):
    """Todas las parejas que han jugado juntas, de más a menos partidos."""
    by_id = {p.id: p for p in players}
    acc = {}
    for g in log:
        a = acc.setdefault(g['pair'], {'played': 0, 'wins': 0})
        a['played'] += 1
        a['wins'] += g['won']
    rows = []
    for (a_id, b_id), a in acc.items():
        if a_id not in by_id or b_id not in by_id:
            continue
        rows.append({
            'p1': by_id[a_id],
            'p2': by_id[b_id],
            'played': a['played'],
            'wins': a['wins'],
            'losses': a['played'] - a['wins'],
            'pct': _pct(a['wins'], a['played']),
        })
    rows.sort(key=lambda r: (r['played'], r['pct']), reverse=True)
    return rows


# Parejas destacadas en la página de parejas (el resto se busca con el buscador).
HIGHLIGHT_N = 3


def best_and_worst_pairs(pairs, n=HIGHLIGHT_N, min_games=MIN_GAMES_PAIR):
    """
    (mejores, peores) de `all_pairs` por % de victorias, solo parejas con al menos
    `min_games` partidos. Si hay menos de 2*n, se reparten entre las dos listas
    para que ninguna pareja salga en ambas.
    """
    ranked = [r for r in pairs if r['played'] >= min_games]
    n_best = min(n, (len(ranked) + 1) // 2)
    n_worst = min(n, len(ranked) - n_best)
    best = sorted(ranked, key=lambda r: (-r['pct'], -r['played'], -r['wins']))[:n_best]
    rest = [r for r in ranked if r not in best]
    worst = sorted(rest, key=lambda r: (r['pct'], -r['played'], r['wins']))[:n_worst]
    return best, worst


def pair_summary(log, p1_id, p2_id):
    """Métricas de una pareja: balance, local/visitante, rachas y temporadas."""
    key = pair_key(p1_id, p2_id)
    games = [g for g in log if g['pair'] == key]
    results = [g['won'] for g in games]
    local = [g['won'] for g in games if g['local']]
    visiting = [g['won'] for g in games if not g['local']]
    played, wins = len(results), sum(results)
    streak_type, streak_len = _current_run(results)

    by_season = {}
    for g in games:
        by_season.setdefault(g['season'], []).append(g)
    seasons, previous = [], None
    for season in sorted(by_season, key=lambda s: int(s.split('-')[0]) if s[:4].isdigit() else 0):
        sg = by_season[season]
        s_wins = sum(g['won'] for g in sg)
        pct = _pct(s_wins, len(sg))
        seasons.append({
            'season': season,
            'played': len(sg),
            'wins': s_wins,
            'losses': len(sg) - s_wins,
            'pct': pct,
            'points': sum(g['points'] for g in sg),
            'matches': len({g['match_id'] for g in sg}),
            'delta': round(pct - previous, 1) if previous is not None else None,
        })
        previous = pct

    return {
        'played': played,
        'wins': wins,
        'losses': played - wins,
        'pct': _pct(wins, played),
        'points': sum(g['points'] for g in games),
        'matches': len({g['match_id'] for g in games}),

        'local_played': len(local),
        'local_wins': sum(local),
        'local_losses': len(local) - sum(local),
        'local_pct': _pct(sum(local), len(local)),
        'visiting_played': len(visiting),
        'visiting_wins': sum(visiting),
        'visiting_losses': len(visiting) - sum(visiting),
        'visiting_pct': _pct(sum(visiting), len(visiting)),

        'streak_type': streak_type,
        'streak_len': streak_len,
        'best_win_streak': _longest_run(results, True),
        'worst_loss_streak': _longest_run(results, False),
        'form': results[-10:],
        'seasons': seasons,
    }


# ---------------------------------------------------------------
# Rachas destacadas (portada)
# ---------------------------------------------------------------

# Victorias seguidas mínimas para destacar a un jugador o una pareja en la portada.
MIN_HOT_STREAK = 2


def _hottest(history):
    """(clave, n) con la racha de victorias activa más larga; desempata la más reciente."""
    best, best_rank = None, None
    for key, h in history.items():
        kind, n = _current_run(h['results'])
        if kind != 'V' or n < MIN_HOT_STREAK:
            continue
        rank = (n, h['last'])
        if best_rank is None or rank > best_rank:
            best, best_rank = (key, n), rank
    return best


def hot_streaks(log, players):
    """
    Jugador y pareja con la racha de victorias activa más larga entre `players`.
    Devuelve (jugador, pareja): {'player', 'streak'} y {'p1', 'p2', 'label', 'streak'}, o None.
    """
    by_id = {p.id: p for p in players}
    by_player, by_pair = {}, {}

    def add(history, key, won, i):
        """Añade un resultado al historial de ``key`` y apunta la posición ``i`` del último partido."""
        h = history.setdefault(key, {'results': [], 'last': i})
        h['results'].append(won)
        h['last'] = i

    for i, g in enumerate(log):
        known = [pid for pid in g['pair'] if pid in by_id]
        for pid in known:
            add(by_player, pid, g['won'], i)
        if len(known) == 2:
            add(by_pair, g['pair'], g['won'], i)

    player = pair = None
    hot = _hottest(by_player)
    if hot:
        player = {'player': by_id[hot[0]], 'streak': hot[1]}
    hot = _hottest(by_pair)
    if hot:
        (a, b), n = hot
        p1, p2 = by_id[a], by_id[b]
        pair = {'p1': p1, 'p2': p2, 'label': f"{pair_label(p1)} / {pair_label(p2)}", 'streak': n}
    return player, pair
