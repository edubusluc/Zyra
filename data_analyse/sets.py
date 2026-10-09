"""
Estadísticas a partir del resultado set a set y del número de partido.

Reglas de pádel que se aplican (las mismas que valida match.scoring):

- Un partido es al mejor de 3 sets. Un set se gana 6-0 ... 6-4, 7-5 o 7-6.
- A 6-6 se juega un tie-break: el set acaba 7-6. Esos sets son los "tie-breaks".
- El tercer set solo se juega con un set para cada pareja; es el set decisivo y puede
  ser un set normal o un super tie-break a 10 puntos con 2 de diferencia (10-8, 11-9...).
- Un 6-0 es un "rosco".
- Remontada: ganar el partido tras perder el primer set. Lo contrario (ganar el primer
  set y perder el partido) es una "ventaja perdida".

Cada partido llega como un diccionario con al menos ``won`` (bool) y ``sets``: lista de
tuplas (juegos propios, juegos del rival) de los sets jugados, sin el tercero si no se
jugó. Los resultados antiguos guardan el tercer set sin jugar como 0-0: se ignora.
"""
from match import scoring

GAME_NUMBERS = (1, 2, 3, 4, 5)


def own_sets(result, is_local):
    """Sets jugados de un Result desde el punto de vista de la pareja del club: [(propios, rival), ...]."""
    if result is None:
        return []
    sets = []
    for n, (loc, vis) in enumerate(result.sets(), start=1):
        if loc is None or vis is None:
            continue
        if n == 3 and loc == 0 and vis == 0:
            continue  # tercer set sin jugar guardado como 0-0 (resultados antiguos)
        sets.append((loc, vis) if is_local else (vis, loc))
    return sets


def _pct(wins, total):
    """Porcentaje entero; None si no hay casos (la plantilla muestra «—»)."""
    return round(wins / total * 100) if total else None


def _rate(wins, total):
    """{'wins', 'losses', 'total', 'pct'} de un tipo de situación."""
    return {'wins': wins, 'losses': total - wins, 'total': total, 'pct': _pct(wins, total)}


def is_tiebreak_set(own, rival):
    """True si el set se decidió en un tie-break a 6-6 (7-6 o 6-7)."""
    return {own, rival} == {7, 6}


def is_super_tiebreak(own, rival):
    """True si el set es un super tie-break (no es un set normal y llega a 10 con 2 de diferencia)."""
    return not scoring.is_valid_set(own, rival) and scoring.is_valid_super_tiebreak(own, rival)


def set_stats(games):
    """
    Métricas de sets de una lista de partidos (equipo, jugador o pareja).

    Devuelve un diccionario con ``played`` (partidos con resultado), sets y juegos a favor y
    en contra, y cada situación como {'wins', 'losses', 'total', 'pct'}: ``third`` (set
    decisivo), ``super_tb`` (decisivos jugados a super tie-break), ``tiebreak`` (sets
    7-6), ``comeback`` (partidos que empiezan perdiendo el primer set), ``first_set``
    (partidos que empiezan ganándolo: % que se cierran), ``close`` (sets 7-5 y 7-6), y
    ``bagels_for`` / ``bagels_against`` (roscos dados y recibidos).
    """
    played = sets_won = sets_lost = games_won = games_lost = 0
    third_w = third_n = stb_w = stb_n = tb_w = tb_n = 0
    come_w = come_n = first_w = first_n = close_w = close_n = 0
    bagels_for = bagels_against = 0

    for g in games:
        sets = g.get('sets') or []
        if len(sets) < 2:
            continue
        played += 1
        won = g['won']
        for i, (own, rival) in enumerate(sets):
            set_won = own > rival
            sets_won += set_won
            sets_lost += not set_won
            if i == 2 and is_super_tiebreak(own, rival):
                # El super tie-break cuenta como set, pero sus puntos no son juegos
                stb_n += 1
                stb_w += set_won
                continue
            games_won += own
            games_lost += rival
            if is_tiebreak_set(own, rival):
                tb_n += 1
                tb_w += set_won
            if max(own, rival) == 7:
                close_n += 1
                close_w += set_won
            if (own, rival) == (6, 0):
                bagels_for += 1
            elif (own, rival) == (0, 6):
                bagels_against += 1
        if len(sets) == 3:
            third_n += 1
            third_w += won
        if sets[0][0] > sets[0][1]:
            first_n += 1
            first_w += won
        else:
            come_n += 1
            come_w += won

    return {
        'played': played,
        'sets_won': sets_won,
        'sets_lost': sets_lost,
        'sets_pct': _pct(sets_won, sets_won + sets_lost),
        'games_won': games_won,
        'games_lost': games_lost,
        'third': _rate(third_w, third_n),
        'third_share': _pct(third_n, played),
        'super_tb': _rate(stb_w, stb_n),
        'tiebreak': _rate(tb_w, tb_n),
        'close': _rate(close_w, close_n),
        'comeback': _rate(come_w, come_n),
        'first_set': _rate(first_w, first_n),
        'bagels_for': bagels_for,
        'bagels_against': bagels_against,
    }


def by_game_number(games):
    """
    Balance por número de partido (1 a 5): los partidos 1 y 2 valen 3 puntos y el resto 2.
    Devuelve [{'n', 'value', 'played', 'wins', 'losses', 'pct', 'points', 'stake'}, ...]
    con los cinco números aunque alguno no tenga partidos.
    """
    acc = {n: [0, 0] for n in GAME_NUMBERS}
    for g in games:
        n = g.get('n_game')
        if n in acc:
            acc[n][0] += 1
            acc[n][1] += g['won']
    rows = []
    for n in GAME_NUMBERS:
        played, wins = acc[n]
        value = 3 if n in (1, 2) else 2
        rows.append({
            'n': n,
            'value': value,
            'played': played,
            'wins': wins,
            'losses': played - wins,
            'pct': _pct(wins, played),
            'points': wins * value,
            'stake': played * value,
        })
    return rows


def best_and_worst_number(rows, min_games=2):
    """(mejor, peor) fila de ``by_game_number`` con al menos ``min_games`` partidos; None si no hay dos."""
    ranked = [r for r in rows if r['played'] >= min_games]
    if len(ranked) < 2:
        return None, None
    best = max(ranked, key=lambda r: (r['pct'], r['played']))
    worst = min(ranked, key=lambda r: (r['pct'], -r['played']))
    if best is worst or best['pct'] == worst['pct']:
        return None, None
    return best, worst
