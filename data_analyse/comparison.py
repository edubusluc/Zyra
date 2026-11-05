"""
Piezas comunes de las comparaciones de estadísticas (fase 6 de la auditoría).

Un mismo conjunto de situaciones de set, un mismo bloque «Local y visitante» con su unidad y las
reglas de muestra mínima de las tendencias, para que Equipo, Jugador, Pareja y «Mis estadísticas»
midan y nombren lo mismo.
"""
from django.utils.translation import gettext_lazy as _

# Partidos que necesita una temporada para entrar en una tendencia (evolución o cambio de % entre temporadas).
MIN_TREND_GAMES = 5

# Partidos juntos que necesita una pareja para que su ficha enseñe más que el resumen y los últimos partidos.
MIN_PAIR_SHEET_GAMES = 2

# Situaciones de set que ve cada vista: (clave de set_stats, título literal, explicación). «bagels» no sale de
# set_stats: su % es sobre los sets jugados (ver set_situation_rows).
SET_ROWS = (
    ('first_set', _("Tras ganar el 1.er set"), _("Partidos ganados tras ganar el primer set.")),
    ('comeback', _("Tras perder el 1.er set"), _("Partidos ganados tras perder el primer set.")),
    ('tiebreak', _("Tie-breaks"), _("Sets que llegan a 6-6 y acaban 7-6.")),
    ('third', _("Set decisivo"), _("Tercer set, a set normal o a super tie-break.")),
    ('bagels', _("Roscos a favor"), _("Sets ganados por 6-0.")),
)


def bagels_situation(st):
    """
    Los roscos a favor de ``st`` (set_stats) con la forma de una situación de set:
    ``{'wins', 'losses', 'total', 'pct'}`` sobre los sets jugados (``pct`` None sin sets).
    """
    total = st['sets_won'] + st['sets_lost']
    wins = st['bagels_for']
    return {'wins': wins, 'losses': total - wins, 'total': total,
            'pct': round(100 * wins / total) if total else None}


# Unidad sobre la que se cuenta cada situación de set («N de M <unidad>»): partidos o sets.
SET_UNITS = {'first_set': 'games', 'comeback': 'games', 'third': 'games', 'tiebreak': 'sets', 'bagels': 'sets'}


def set_situation_rows(st):
    """
    Filas ``(título, explicación, situación)`` de ``SET_ROWS`` para un set_stats ``st``; las mismas en todas
    las vistas. Las situaciones sin ningún caso no se incluyen.
    """
    rows = []
    for key, label, hint in SET_ROWS:
        situation = bagels_situation(st) if key == 'bagels' else st[key]
        if situation['total']:
            rows.append((label, hint, dict(situation, unit=SET_UNITS[key])))
    return rows


def _share(won, total):
    """% entero de ``won`` sobre ``total``; None sin casos."""
    return round(100 * won / total) if total else None


def venue_split(local, visiting, unit):
    """
    Bloque «Local y visitante» de `includes/venue_split.html`. ``local`` y ``visiting`` son diccionarios con
    ``won`` y ``lost`` (y ``drawn`` si hay empates); ``unit``: 'matches' (enfrentamientos) o 'games' (partidos).
    Devuelve ``{'unit', 'rows'}``; cada fila lleva ``label``, ``won``, ``lost``, ``drawn``, ``total`` y ``pct``.
    """
    rows = []
    for label, side in ((_("Como local"), local), (_("Como visitante"), visiting)):
        won, lost, drawn = side.get('won', 0), side.get('lost', 0), side.get('drawn', 0)
        total = won + lost + drawn
        rows.append({'label': label, 'won': won, 'lost': lost, 'drawn': drawn, 'total': total, 'pct': _share(won, total)})
    return {'unit': unit, 'rows': rows}


def is_reliable(played):
    """True si una temporada con ``played`` partidos tiene muestra para figurar en una tendencia."""
    return played >= MIN_TREND_GAMES


def trend(rows):
    """
    Evolución del % de victorias por temporada para el gráfico: solo las temporadas con muestra suficiente
    (``MIN_TREND_GAMES``). ``rows``: temporadas ascendentes con ``season``, ``played`` y ``pct``.
    Devuelve ``{'labels', 'pct', 'played'}``, o None con menos de dos temporadas válidas (no hay tendencia).
    """
    valid = [r for r in rows if is_reliable(r['played'])]
    if len(valid) < 2:
        return None
    return {'labels': [r['season'] for r in valid], 'pct': [r['pct'] for r in valid], 'played': [r['played'] for r in valid]}


def partner_rows(affinity, limit=None):
    """
    Compañeros para la lista «Compañeros» de la ficha: los que siguen en el equipo, con su balance y su % real de
    victorias (la afinidad suavizada solo ordena a igualdad de partidos). Más partidos primero, así que el
    primero es la pareja habitual del encabezado. ``affinity``: salida de ``degree_of_affinity``.
    Cada fila añade ``pct`` a lo que ya trae; ``best``/``worst`` marcan el mejor y el peor % entre quienes
    tienen ``MIN_TREND_GAMES`` partidos o más (si hay al menos dos).
    """
    rows = [dict(a, pct=_share(a['wins'], a['games'])) for a in affinity if a.get('in_team')]
    rows.sort(key=lambda r: (-r['games'], -r['affinity'], r['name']))
    valid = [r for r in rows if is_reliable(r['games'])]
    if len(valid) >= 2:
        ranked = sorted(valid, key=lambda r: (-r['pct'], -r['games'], r['name']))
        if ranked[0]['pct'] != ranked[-1]['pct']:
            ranked[0]['best'] = True
            ranked[-1]['worst'] = True
    return rows[:limit] if limit else rows


# Orden de la lista de parejas (?orden=): más partidos, mejor %, peor % o nombre.
PAIR_SORT_PLAYED, PAIR_SORT_BEST, PAIR_SORT_WORST, PAIR_SORT_NAME = 'jugados', 'mejor', 'peor', 'nombre'
PAIR_SORTS = (PAIR_SORT_PLAYED, PAIR_SORT_BEST, PAIR_SORT_WORST, PAIR_SORT_NAME)


def pair_name(row):
    """Nombre de una pareja de ``pairs.all_pairs`` («Nombre Apellido / Nombre Apellido») para buscar y ordenar."""
    return f"{row['p1'].short_name} / {row['p2'].short_name}"


def sort_pairs(rows, sort, search=''):
    """
    Lista de parejas de ``pairs.all_pairs`` filtrada por ``search`` (texto en el nombre de cualquiera de los dos,
    sin distinguir mayúsculas) y ordenada por ``sort`` (``PAIR_SORTS``; otro valor, el de partidos). Todas las
    parejas que han jugado juntas, sin mínimo: la base va en cada fila y el % solo ordena.
    """
    if search:
        needle = search.casefold()
        rows = [r for r in rows if needle in pair_name(r).casefold()]
    if sort == PAIR_SORT_BEST:
        key = lambda r: (-r['pct'], -r['played'], pair_name(r).casefold())  # noqa: E731
    elif sort == PAIR_SORT_WORST:
        key = lambda r: (r['pct'], -r['played'], pair_name(r).casefold())  # noqa: E731
    elif sort == PAIR_SORT_NAME:
        key = lambda r: pair_name(r).casefold()  # noqa: E731
    else:
        key = lambda r: (-r['played'], -r['pct'], pair_name(r).casefold())  # noqa: E731
    return sorted(rows, key=key)
