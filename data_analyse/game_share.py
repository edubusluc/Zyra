"""
Tarjeta «Reparto por partidos» de la ficha del jugador (solo SNP): gráfico circular con los partidos que ha
jugado como partido 1, 2, 3, 4 y 5 de la alineación. Parte de ``sets.by_game_number`` y solo prepara la
geometría del anillo; la vista no calcula nada y la plantilla solo dibuja.

Estados: ``empty`` (ningún partido), ``few`` (menos de ``MIN_SAMPLE``: anillo gris con el total y los recuentos,
sin porcentajes) y ``full`` (anillo con un sector por partido jugado).
"""
import math

# Partidos mínimos para dibujar los sectores (el mismo mínimo que «Frente a la plantilla»).
MIN_SAMPLE = 3
RADIUS = 46
CIRCUMFERENCE = 2 * math.pi * RADIUS
# Hueco entre sectores (en unidades del trazo) y fracción mínima del sector para escribir su número dentro.
GAP = 2.5
MIN_LABEL_SHARE = 0.07


def _num(value):
    """Número con punto decimal (apto para atributos SVG, sin la coma del idioma activo)."""
    return f"{value:.2f}"


def game_share(rows):
    """
    Reparto de partidos por número de partido a partir de ``sets.by_game_number``.

    Devuelve ``{'state', 'total', 'min', 'circumference', 'single', 'segments'}``. Cada elemento de ``segments``
    (uno por partido del 1 al 5, aunque sea 0) lleva ``n``, ``value`` (puntos en juego), ``played``, ``pct``
    (``None`` si el anillo no se dibuja) y, si ``played`` y el estado es ``full``, la geometría del sector:
    ``dash`` y ``offset`` (trazo del círculo) y ``label_x``/``label_y`` (donde va el número dentro; no existen
    si el sector es muy pequeño). ``single`` indica que solo hay un partido con datos (anillo completo, sin huecos).
    """
    total = sum(r['played'] for r in rows)
    state = 'empty' if not total else ('few' if total < MIN_SAMPLE else 'full')
    used = sum(1 for r in rows if r['played'])
    gap = GAP if used > 1 else 0
    segments, done = [], 0.0
    for r in rows:
        seg = {'n': r['n'], 'value': r['value'], 'played': r['played'], 'pct': None, 'dash': None}
        if state == 'full':
            share = r['played'] / total
            seg['pct'] = round(share * 100)
            if r['played']:
                seg['dash'] = _num(max(share * CIRCUMFERENCE - gap, 0.1))
                seg['offset'] = _num(-done * CIRCUMFERENCE)
                angle = (done + share / 2) * 2 * math.pi - math.pi / 2
                if share >= MIN_LABEL_SHARE:
                    seg['label_x'] = _num(60 + RADIUS * math.cos(angle))
                    seg['label_y'] = _num(60 + RADIUS * math.sin(angle))
                done += share
        segments.append(seg)
    return {
        'state': state,
        'total': total,
        'min': MIN_SAMPLE,
        'circumference': _num(CIRCUMFERENCE),
        'single': used == 1,
        'segments': segments,
    }
