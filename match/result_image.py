"""
Imagen del resultado de un enfrentamiento para compartir por WhatsApp (botón «Compartir resultado»).

Formato vertical 4:5 (1080×1350 px) con el estilo de la web: fondo oscuro de pista con la red en el
centro, marcador en Anton (lima si se gana, rojo si se pierde, ámbar si se empata), insignia de la
competición, escudos de local y visitante y una fila por partido con la pareja propia, los sets y los
puntos que valía. Solo se guardan los jugadores del lado propio, así que la pareja rival no aparece.

``build_result_png`` dibuja al doble de tamaño y reduce al final para que los bordes salgan suaves.
"""
import io
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext as _
from PIL import Image, ImageDraw, ImageFont

from core.templatetags.zyra_format import crest_initials
from match import outcomes

W, H = 1080, 1350
SCALE = 2
FONT_DIR = Path(settings.BASE_DIR) / "static" / "zyra" / "fonts"

LIME = (180, 241, 0)
INK = (10, 10, 10)
TEXT = (244, 245, 241)
MUTED = (164, 167, 158)
BORDER = (48, 50, 45)
DANGER = (255, 92, 99)
WARNING = (255, 201, 64)
SURFACE = (20, 21, 18)
CREST_BG = (32, 35, 27)
BADGE = {"snp": (219, 164, 0), "lapi": (97, 226, 201)}
OUTCOME_COLOR = {"V": LIME, "D": DANGER, "E": WARNING}

# Polígonos del logotipo (static/zyra/logo.svg, viewBox 553×742).
LOGO_POLYGONS = (
    ((247.4, 742), (475.5, 685.5), (541.5, 541.6), (90.4, 616.1)),
    ((0, 251.1), (0, 543.5), (40.1, 575.7), (419.7, 181.8)),
    ((553, 491), (553, 197.7), (513.9, 166.3), (134.3, 560.2)),
    ((306.6, 0), (78.5, 56.5), (12.5, 200.4), (463.6, 125.9)),
)

_font_cache = {}


def _font(name, size):
    """Fuente de la web (``static/zyra/fonts``) al tamaño dado en píxeles de diseño."""
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONT_DIR / name), int(size * SCALE))
    return _font_cache[key]


def _s(value):
    """Pasa una medida de diseño (1080 px de ancho) a píxeles del lienzo ampliado."""
    return int(round(value * SCALE))


def _spaced_width(draw, text, font, spacing):
    """Ancho de ``text`` con ``spacing`` px de diseño extra entre letras."""
    return sum(draw.textlength(c, font=font) for c in text) + _s(spacing) * max(len(text) - 1, 0)


def _text(draw, xy, text, font, fill, anchor="la", spacing=0):
    """Escribe ``text`` en ``xy`` (px de diseño); con ``spacing`` separa las letras (titulares en versalitas)."""
    x, y = _s(xy[0]), _s(xy[1])
    if not spacing:
        draw.text((x, y), text, font=font, fill=fill, anchor=anchor)
        return
    width = _spaced_width(draw, text, font, spacing)
    x -= {"l": 0, "m": width / 2, "r": width}[anchor[0]]
    for char in text:
        draw.text((x, y), char, font=font, fill=fill, anchor="l" + anchor[1])
        x += draw.textlength(char, font=font) + _s(spacing)


def _fit(draw, text, name, size, max_width, min_size=20):
    """Fuente que hace caber ``text`` en ``max_width`` px de diseño, reduciendo desde ``size``."""
    while size > min_size and draw.textlength(text, font=_font(name, size)) > _s(max_width):
        size -= 1
    return _font(name, size)


def _wrap(draw, text, font, max_width):
    """Divide ``text`` en dos líneas como máximo para que quepa en ``max_width`` px de diseño."""
    if draw.textlength(text, font=font) <= _s(max_width):
        return [text]
    words = text.split()
    best = (text, "")
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if max(draw.textlength(a, font=font), draw.textlength(b, font=font)) < max(
                draw.textlength(best[0], font=font), draw.textlength(best[1], font=font)):
            best = (a, b)
    return [line for line in best if line]


def _background():
    """Lienzo con el degradado de pista de la web, la red en el centro y la línea de saque."""
    img = Image.new("RGB", (_s(W), _s(H)))
    d = ImageDraw.Draw(img)
    top, bottom = (31, 40, 17), (13, 15, 10)
    for y in range(_s(H)):
        t = min(y / (_s(H) * 0.85), 1)
        d.line([(0, y), (_s(W), y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(overlay)
    o.rectangle([_s(W / 2 - 1.5), 0, _s(W / 2 + 1.5), _s(H)], fill=(255, 255, 255, 26))
    o.rectangle([0, _s(H - 200), _s(W), _s(H - 197)], fill=(255, 255, 255, 18))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _logo(draw, x, y, height):
    """Dibuja el logotipo (cuatro polígonos lima) con su esquina superior izquierda en (x, y)."""
    k = height / 742
    for polygon in LOGO_POLYGONS:
        draw.polygon([(_s(x + px * k), _s(y + py * k)) for px, py in polygon], fill=LIME)


def _pill(layer, box, fill, outline=None, width=2):
    """Píldora (rectángulo totalmente redondeado) en ``box`` (px de diseño)."""
    x0, y0, x1, y1 = (_s(v) for v in box)
    ImageDraw.Draw(layer).rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) // 2, fill=fill,
                                            outline=outline, width=_s(width) if outline else 0)


def _short_name(game, slot):
    """«A. Montaño»: inicial del nombre y primer apellido (o los dos primeros tokens si el jugador se eliminó)."""
    player = getattr(game, slot)
    if player:
        return f"{player.name[:1].upper()}. {player.get_first_last_name()}".strip()
    parts = game.player_name(slot).split()
    return f"{parts[0][:1]}. {parts[1]}" if len(parts) > 1 else " ".join(parts)


def _own_pair(game, own_is_local):
    """Los dos nombres cortos de la pareja propia del partido (lista vacía si no se alineó ninguna)."""
    prefix = "local" if own_is_local else "visiting"
    names = [_short_name(game, f"player_1_{prefix}"), _short_name(game, f"player_2_{prefix}")]
    return names if all(names) else []


def _sets(game):
    """Sets del partido como «6-4 6-3» en orden local-visitante; '' si no tiene resultado."""
    result = next(iter(game.results.all()), None)
    if not result:
        return ""
    pairs = [(result.set1_local, result.set1_visiting), (result.set2_local, result.set2_visiting),
             (result.set3_local, result.set3_visiting)]
    return " ".join(f"{a}-{b}" for a, b in pairs if a is not None and b is not None)


def _crest(draw, cx, cy, name, own):
    """Escudo de reserva: círculo con las siglas del equipo (borde y siglas lima si es el propio)."""
    r = 66
    draw.ellipse([_s(cx - r), _s(cy - r), _s(cx + r), _s(cy + r)], fill=CREST_BG, outline=LIME if own else BORDER,
                 width=_s(4))
    _text(draw, (cx, cy + 4), crest_initials(name), _font("Anton-Regular.ttf", 60), LIME if own else TEXT, "mm")


def _team(draw, cx, top, name, side, own):
    """Bloque de un equipo: escudo, nombre (hasta dos líneas) y etiqueta Local / Visitante."""
    _crest(draw, cx, top + 66, name, own)
    font = _font("Archivo-ExtraBold.ttf", 34)
    lines = _wrap(draw, name.upper(), font, 270)
    for i, line in enumerate(lines):
        _text(draw, (cx, top + 168 + i * 38), line, _fit(draw, line, "Archivo-ExtraBold.ttf", 34, 270), TEXT, "ma")
    _text(draw, (cx, top + 168 + len(lines) * 38 + 14), side.upper(), _font("Archivo-Bold.ttf", 20), MUTED, "ma", spacing=3.2)


def _rows(canvas, draw, match, games, own_is_local, rules):
    """Panel con una fila por partido: nº, pareja propia, sets y puntos en el lado de quien ganó."""
    n = max(len(games), 1)
    row_h = 112 if n > 3 else 128
    top = 620
    panel = [64, top, W - 64, top + 16 + row_h * n]
    draw.rounded_rectangle([_s(v) for v in panel], radius=_s(30), fill=SURFACE + (235,), outline=BORDER, width=_s(2))
    x0 = 92
    col_l, col_sets, col_v = (230, 446), (446, 696), (696, 912)
    for i, game in enumerate(games):
        y = top + 8 + i * row_h
        cy = y + row_h / 2
        if i:
            draw.line([(_s(92), _s(y)), (_s(W - 92), _s(y))], fill=BORDER, width=_s(2))
        _text(draw, (x0, cy), f"P{game.n_game}", _font("Anton-Regular.ttf", 34), MUTED, "lm")
        own_side_local = own_is_local
        winner_local = game.winner == outcomes.WINNER_LOCAL
        own_won = winner_local == own_side_local
        own_col = col_l if own_side_local else col_v
        pair = [] if game.no_show in ("own", "both") else _own_pair(game, own_is_local)
        if pair:
            fname = "Archivo-ExtraBold.ttf" if own_won else "Archivo-Bold.ttf"
            width = own_col[1] - own_col[0]
            for j, name in enumerate(pair):
                font = _fit(draw, name, fname, 30, width)
                ny = cy + (j - 0.5) * 36
                if own_side_local:
                    _text(draw, (own_col[1], ny), name, font, TEXT if own_won else MUTED, "rm")
                else:
                    _text(draw, (own_col[0], ny), name, font, TEXT if own_won else MUTED, "lm")
        sets = _sets(game)
        # «No presentada»: en el lado de la pareja que faltó (propia, rival o ambas).
        missing = {"own": [own_side_local], "rival": [not own_side_local], "both": [True, False]}.get(game.no_show, [])
        for local_side in missing:
            col = col_l if local_side else col_v
            label = _("NO PRESENTADA")
            font = _font("Archivo-ExtraBold.ttf", 20)
            tw = _spaced_width(draw, label, font, 1.2) / SCALE + 24
            x1 = col[1] if local_side else col[0] + tw
            xs = x1 - tw
            _pill(canvas, [xs, cy - 18, x1, cy + 18], (0, 0, 0, 0), outline=WARNING, width=2)
            _text(draw, ((xs + x1) / 2, cy + 1), label, font, WARNING, "mm", spacing=1.2)
        if sets and not missing:
            _text(draw, ((col_sets[0] + col_sets[1]) / 2, cy), sets, _fit(draw, sets, "Archivo-ExtraBold.ttf", 32, 240), TEXT, "mm")
        elif not missing:
            _text(draw, ((col_sets[0] + col_sets[1]) / 2, cy), "—", _font("Archivo-ExtraBold.ttf", 32), MUTED, "mm")
        # Puntos en juego (solo en las competiciones con valor distinto por partido): chip junto al ganador.
        if rules.ordered_pairs and game.score:
            label = f"+{game.score}"
            font = _font("Archivo-ExtraBold.ttf", 22)
            tw = draw.textlength(label, font=font) / SCALE + 24
            cx = 192 if winner_local else 950
            _pill(canvas, [cx - tw / 2, cy - 15, cx + tw / 2, cy + 15], LIME if own_won else (42, 44, 39))
            _text(draw, (cx, cy + 1), label, font, INK if own_won else MUTED, "mm")
    return panel[3]


def build_result_png(match, games, outcome):
    """PNG (bytes) de 1080×1350 con el resultado de ``match``; ``games`` son sus partidos ordenados por número
    y ``outcome`` el desenlace del equipo propio (``match.views.match_outcome``: «V», «D», «E» o None).

    Los marcadores van en orden local-visitante, igual que la ficha. El color del marcador y la etiqueta
    (Victoria, Derrota, Empate) son los del equipo propio.
    """
    rules = match.club.rules
    color = OUTCOME_COLOR.get(outcome, TEXT)
    canvas = _background()
    draw = ImageDraw.Draw(canvas, "RGBA")

    _logo(draw, 64, 68, 54)
    _text(draw, (120, 95), "ZYRA", _font("Syncopate-BoldItalic.ttf", 34), TEXT, "lm", spacing=1.4)

    comp = str(rules.name)
    if match.is_friendly or (match.match_type and match.match_type != rules.default_type):
        comp += f" · {match.type_label}"  # el tipo por defecto (enfrentamiento) no se repite
    badge_color = BADGE.get(rules.code, WARNING)
    bfont = _font("Archivo-ExtraBold.ttf", 26)
    bw = _spaced_width(draw, comp.upper(), bfont, 2) / SCALE + 56
    _pill(canvas, [W - 64 - bw, 64, W - 64, 125], (0, 0, 0, 90), outline=badge_color, width=3)
    draw = ImageDraw.Draw(canvas, "RGBA")
    _text(draw, (W - 64 - bw / 2, 95), comp.upper(), bfont, badge_color, "mm", spacing=2)

    when = match.start_date.strftime("%d/%m/%Y") + (f" · {match.start_time:%H:%M}" if match.start_time else "")
    kicker = f"{when} · {match.location}" if match.location else when
    _text(draw, (64, 170), kicker, _fit(draw, kicker, "Archivo-Bold.ttf", 30, W - 128), MUTED, "lm")

    own_is_local = match.own_is_local
    _team(draw, 188, 224, match.local_name, _("Local"), own_is_local)
    _team(draw, W - 188, 224, match.visiting_name, _("Visitante"), not own_is_local)

    points = (match.result_points or "").replace("-", "/").split("/")
    score = "-".join(p.strip() for p in points) if len(points) == 2 else "-"
    size = 300 if all(len(part) == 1 for part in score.split("-")) else 240  # 12-0 o 0-12 no caben a 300
    _text(draw, (W / 2, 380), score, _font("Anton-Regular.ttf", size), color, "mm")

    label = {"V": _("VICTORIA"), "D": _("DERROTA"), "E": _("EMPATE")}.get(outcome, "")
    if label:
        font = _font("Archivo-ExtraBold.ttf", 30)
        pw = _spaced_width(draw, label, font, 6) / SCALE + 68
        _pill(canvas, [W / 2 - pw / 2, 540, W / 2 + pw / 2, 600], SURFACE + (255,), outline=BORDER, width=2)
        draw = ImageDraw.Draw(canvas, "RGBA")
        _text(draw, (W / 2, 571), label, font, color, "mm", spacing=6)

    _rows(canvas, draw, match, games, own_is_local, rules)
    draw = ImageDraw.Draw(canvas, "RGBA")

    _text(draw, (64, 1285), _("Hecho con Zyra"), _font("Archivo-Bold.ttf", 26), MUTED, "lm")
    _text(draw, (W - 64, 1285), "zyrapadel.com", _font("Archivo-ExtraBold.ttf", 26), LIME, "rm", spacing=1)

    out = io.BytesIO()
    canvas.convert("RGB").resize((W, H), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out.getvalue()
