"""
Récords del equipo y ranking de puntos SNP de la plantilla.

Los récords salen de los enfrentamientos cerrados del club y del log de partidos
(data_analyse.pairs.club_game_log), con los mismos filtros de temporada y tipo que el
resto de la página de equipo.
"""
from match.models import Match
from players.models import Player, SnpScoreHistory

from . import pairs as pair_stats

LOCAL_WIN = "Victoria Local"
VISITING_WIN = "Victoria Visitante"
DRAW = "EMPATE"

# Una temporada necesita al menos estos enfrentamientos para ser "la mejor".
MIN_MATCHES_BEST_SEASON = 3


def _outcome(match):
    """'V', 'E' o 'D' del enfrentamiento desde el punto de vista del club; None si no tiene resultado."""
    if match.result == DRAW:
        return 'E'
    if match.result == LOCAL_WIN:
        return 'V' if match.own_is_local else 'D'
    if match.result == VISITING_WIN:
        return 'D' if match.own_is_local else 'V'
    return None


def _points(match):
    """(puntos del club, puntos del rival) sumando el valor de los partidos ganados por cada lado."""
    own = rival = 0
    for g in match.games.all():
        if g.winner not in ('Local', 'Visitante') or not g.score:
            continue
        if (g.winner == 'Local') == match.own_is_local:
            own += g.score
        else:
            rival += g.score
    return own, rival


def _longest(seq, accept):
    """Racha más larga de elementos de ``seq`` que cumplen ``accept``: (n, primero, último) o None."""
    best, run = None, []
    for item in seq:
        if accept(item):
            run.append(item)
            if best is None or len(run) > best[0]:
                best = (len(run), run[0], run[-1])
        else:
            run = []
    return best


def team_records(club, season=None, match_type=None, log=None):
    """
    Récords del equipo con los filtros dados. Devuelve un diccionario con las claves que
    tengan datos: 'win_streak' y 'unbeaten' ({'n', 'from', 'to'}), 'biggest_win' y
    'worst_defeat' ({'own', 'rival', 'name', 'date', 'public_id'}), 'best_season'
    ({'season', 'pct', 'played', 'wins'}), 'game_streak' (partidos seguidos ganados),
    'top_player' y 'top_pair' ({'name', 'n'}: más victorias) y 'most_games' ({'name', 'n'}).
    """
    matches = (
        Match.objects.filter(club=club, draft_mode=False, **pair_stats.match_type_lookup(match_type))
        .select_related('local', 'visiting').prefetch_related('games')
        .order_by('start_date', 'id')
    )
    if season:
        matches = matches.filter(season=season)

    rows = []
    for m in matches:
        outcome = _outcome(m)
        if outcome is None:
            continue
        own, rival = _points(m)
        rows.append({'match': m, 'outcome': outcome, 'own': own, 'rival': rival})

    records = {}
    streak = _longest(rows, lambda r: r['outcome'] == 'V')
    if streak and streak[0] >= 2:
        records['win_streak'] = {'n': streak[0], 'from': streak[1]['match'].start_date, 'to': streak[2]['match'].start_date}
    unbeaten = _longest(rows, lambda r: r['outcome'] in ('V', 'E'))
    if unbeaten and unbeaten[0] >= 2 and unbeaten[0] != (streak or (0,))[0]:
        records['unbeaten'] = {'n': unbeaten[0], 'from': unbeaten[1]['match'].start_date, 'to': unbeaten[2]['match'].start_date}

    def score_row(r):
        """Datos de un enfrentamiento para la tarjeta de récord."""
        m = r['match']
        return {'own': r['own'], 'rival': r['rival'], 'name': m.rival_label, 'date': m.start_date, 'public_id': m.public_id}

    wins = [r for r in rows if r['outcome'] == 'V' and r['own'] + r['rival']]
    if wins:
        records['biggest_win'] = score_row(max(wins, key=lambda r: (r['own'] - r['rival'], r['match'].start_date)))
    losses = [r for r in rows if r['outcome'] == 'D' and r['own'] + r['rival']]
    if losses:
        records['worst_defeat'] = score_row(max(losses, key=lambda r: (r['rival'] - r['own'], r['match'].start_date)))

    if not season:
        by_season = {}
        for r in rows:
            s = by_season.setdefault(r['match'].season, [0, 0])
            s[0] += 1
            s[1] += r['outcome'] == 'V'
        ranked = [(wins / played, played, s, wins) for s, (played, wins) in by_season.items()
                  if played >= MIN_MATCHES_BEST_SEASON]
        if len(ranked) >= 2:
            pct, played, s, wins = max(ranked)
            records['best_season'] = {'season': s, 'pct': round(pct * 100), 'played': played, 'wins': wins}

    if log is None:
        log = pair_stats.club_game_log(club, season, match_type)
    game_streak = _longest(log, lambda g: g['won'])
    if game_streak and game_streak[0] >= 2:
        records['game_streak'] = {'n': game_streak[0], 'from': game_streak[1]['date'], 'to': game_streak[2]['date']}

    people = {p.id: p for p in Player.objects.filter(club=club)}
    player_wins, player_games, pair_wins = {}, {}, {}
    for g in log:
        for pid in g['pair']:
            player_games[pid] = player_games.get(pid, 0) + 1
            player_wins[pid] = player_wins.get(pid, 0) + g['won']
        if g['won']:
            pair_wins[g['pair']] = pair_wins.get(g['pair'], 0) + 1

    def top(counts, name):
        """{'name', 'n'} con más cuenta entre las claves que tienen nombre (empate: por nombre); None si no hay."""
        named = [(-n, name(key)) for key, n in counts.items() if n and name(key)]
        if not named:
            return None
        n, label = min(named)
        return {'name': label, 'n': -n}

    player_name = lambda pid: people[pid].full_name if pid in people else None  # noqa: E731
    pair_name = lambda key: (f"{pair_stats.pair_label(people[key[0]])} / {pair_stats.pair_label(people[key[1]])}"  # noqa: E731
                             if key[0] in people and key[1] in people else None)
    for key, counts, name in (('top_player', player_wins, player_name), ('most_games', player_games, player_name),
                              ('top_pair', pair_wins, pair_name)):
        value = top(counts, name)
        if value:
            records[key] = value
    return records


def snp_ranking(club, season):
    """
    Ranking de puntos SNP de la plantilla actual y media del equipo en la temporada ``season``.

    Devuelve {'rows', 'chart', 'average', 'riser'}: cada fila es {'pos', 'player', 'score',
    'first', 'delta'} (``delta``: variación desde la primera actualización de la temporada,
    None con menos de dos); ``chart`` es la media del equipo en cada actualización
    ({'labels', 'average'}); ``riser``, la fila que más ha subido (o None).
    """
    squad = list(Player.objects.filter(club=club, in_team=True))
    history = (SnpScoreHistory.objects.filter(player__in=squad, season=season)
               .order_by('date').values_list('player_id', 'date', 'score'))
    first, last, by_date = {}, {}, {}
    for pid, date, score in history:
        first.setdefault(pid, score)
        last[pid] = score
        by_date.setdefault(date, []).append(score)

    rows = []
    for p in squad:
        score = p.snp_score if p.snp_score is not None else last.get(p.id)
        if score is None:
            continue
        delta = round(last[p.id] - first[p.id], 1) if p.id in first and last[p.id] != first[p.id] else (0 if p.id in first else None)
        rows.append({'player': p, 'score': round(score, 1), 'first': first.get(p.id), 'delta': delta})
    rows.sort(key=lambda r: (-r['score'], r['player'].name, r['player'].last_name))
    for i, r in enumerate(rows, start=1):
        r['pos'] = i

    risers = [r for r in rows if r['delta']]
    riser = max(risers, key=lambda r: r['delta']) if risers else None
    dates = sorted(by_date)
    return {
        'rows': rows,
        'average': round(sum(r['score'] for r in rows) / len(rows), 1) if rows else None,
        'riser': riser if riser and riser['delta'] > 0 else None,
        'chart': {
            'labels': [d.strftime('%d/%m') for d in dates],
            'average': [round(sum(by_date[d]) / len(by_date[d]), 1) for d in dates],
        },
    }
