"""
Tarjeta de resultado en imagen (PNG vertical de 1080×1350) para compartir un enfrentamiento cerrado.

Solo dibuja: no consulta la base de datos. ``render_card`` recibe un diccionario ya preparado
(ver ``match.views.result_card_data``) y devuelve los bytes del PNG. Por defecto no muestra los
nombres de los jugadores; el capitán decide si se incluyen.
"""
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext as _
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
MARGIN = 76
FONT_DIR = Path(settings.BASE_DIR) / "static" / "zyra" / "fonts"
# Dominio que aparece en el pie de la tarjeta.
DOMAIN = "zyrapadel.com"

BG, SURFACE, LINE = "#0A0B09", "#141512", "#30322D"
TEXT, MUTED, LIME, DANGER, WARN = "#F4F5F1", "#A4A79E", "#B4F100", "#FF5C63", "#FFC940"
OUTCOME_COLOR = {"V": LIME, "D": DANGER, "E": WARN}
ROW_HEIGHT, ROW_GAP, ROWS_TOP = 120, 16, 520


def own_sets(match, result):
    """Sets de un partido desde el punto de vista del club ('6-3 4-6 6-2'); '' si no hay resultado."""
    if not result:
        return ""
    pairs = [(result.set1_local, result.set1_visiting), (result.set2_local, result.set2_visiting)]
    if result.set3_local is not None:
        pairs.append((result.set3_local, result.set3_visiting))
    return " ".join(f"{a}-{b}" if match.own_is_local else f"{b}-{a}" for a, b in pairs)


def _font(file, size):
    """Fuente de marca (Archivo o Syncopate) al tamaño dado."""
    return ImageFont.truetype(str(FONT_DIR / file), size)


def _fit(draw, text, file, size, max_width, min_size=22):
    """Fuente de ``file`` lo más grande posible (hasta ``size``) para que ``text`` quepa en ``max_width``."""
    while size > min_size and draw.textlength(text, font=_font(file, size)) > max_width:
        size -= 2
    return _font(file, size)


def _wrap(draw, text, font, max_width, max_lines=2):
    """Parte ``text`` en hasta ``max_lines`` líneas que quepan en ``max_width`` (la última se recorta con «…»)."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def _centered(draw, cx, y, text, font, fill):
    """Escribe ``text`` centrado horizontalmente en ``cx`` con su borde superior en ``y``."""
    draw.text((cx - draw.textlength(text, font=font) / 2, y), text, font=font, fill=fill)


def _team(draw, cx, text, label):
    """Nombre del equipo (hasta dos líneas) y su etiqueta Local/Visitante, centrados en ``cx``."""
    font = _font("Archivo-Bold.ttf", 40)
    y = 270
    for line in _wrap(draw, text.upper(), font, 280):
        _centered(draw, cx, y, line, font, TEXT)
        y += 50
    _centered(draw, cx, y + 6, label, _font("Archivo-Regular.ttf", 30), MUTED)


def render_card(data, show_names=False):
    """
    PNG de 1080×1350 con el resultado. ``data``: ``outcome`` ('V', 'D', 'E' o None), ``local_name``,
    ``visiting_name``, ``score_local``, ``score_visiting``, ``date`` (texto), ``kind`` (tipo de
    enfrentamiento), ``friendly`` (bool) y ``rows`` (``n``, ``pair``, ``sets``, ``won`` por partido).
    Con ``show_names`` False las parejas salen como «Pareja 1…5».
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cx = WIDTH / 2

    draw.text((MARGIN, 76), "ZYRA", font=_font("Syncopate-Bold.ttf", 40), fill=LIME)
    kind_font = _font("Archivo-Regular.ttf", 34)
    kind = data["kind"]
    draw.text((WIDTH - MARGIN - draw.textlength(kind, font=kind_font), 80), kind, font=kind_font, fill=MUTED)

    outcome = data["outcome"]
    labels = {"V": _("Victoria"), "D": _("Derrota"), "E": _("Empate")}
    _centered(draw, cx, 160, labels.get(outcome, "").upper(), _font("Syncopate-Bold.ttf", 52), OUTCOME_COLOR.get(outcome, MUTED))

    _team(draw, 200, data["local_name"], _("Local"))
    _team(draw, WIDTH - 200, data["visiting_name"], _("Visitante"))
    score = f"{data['score_local']} - {data['score_visiting']}"
    _centered(draw, cx, 250, score, _fit(draw, score, "Syncopate-Bold.ttf", 120, 380), TEXT)

    meta = data["date"] + (f" · {_('Amistoso')}" if data.get("friendly") else "")
    _centered(draw, cx, 450, meta, _font("Archivo-Regular.ttf", 34), MUTED)

    label_font, sets_font = _font("Syncopate-Bold.ttf", 28), _font("Archivo-Bold.ttf", 40)
    for i, row in enumerate(data["rows"][:5]):
        top = ROWS_TOP + i * (ROW_HEIGHT + ROW_GAP)
        draw.rounded_rectangle((MARGIN, top, WIDTH - MARGIN, top + ROW_HEIGHT), radius=28, fill=SURFACE, outline=LINE, width=2)
        mid = top + ROW_HEIGHT / 2
        draw.text((MARGIN + 34, mid), f"P{row['n']}", font=label_font, fill=MUTED, anchor="lm")
        sets_color = LIME if row["won"] else DANGER
        sets = row["sets"]
        sets_width = draw.textlength(sets, font=sets_font)
        draw.text((WIDTH - MARGIN - 34, mid), sets, font=sets_font, fill=sets_color, anchor="rm")
        name = row["pair"] if show_names and row["pair"] else _("Pareja %(n)s") % {"n": row["n"]}
        room = WIDTH - 2 * MARGIN - 34 * 2 - 90 - sets_width - 24
        draw.text((MARGIN + 34 + 90, mid), name, font=_fit(draw, name, "Archivo-Bold.ttf", 38, room),
                  fill=TEXT if show_names else MUTED, anchor="lm")

    draw.line((MARGIN, 1244, WIDTH - MARGIN, 1244), fill=LINE, width=2)
    foot = _font("Archivo-Regular.ttf", 32)
    made = _("Hecho con")
    draw.text((MARGIN, 1274), made, font=foot, fill=MUTED)
    draw.text((MARGIN + draw.textlength(made + " ", font=foot), 1272), "ZYRA", font=_font("Syncopate-Bold.ttf", 30), fill=LIME)
    draw.text((WIDTH - MARGIN - draw.textlength(DOMAIN, font=foot), 1274), DOMAIN, font=foot, fill=MUTED)

    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
