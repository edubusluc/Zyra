"""
Imagen de la alineación de un enfrentamiento para compartir por WhatsApp (botón de la tarjeta «Parejas»).

Mismo formato y estilo que ``match.result_image`` (JPEG vertical 4:5, 1080×1350 px, fondo de pista, logotipo,
insignia de la competición, escudos), pero en lugar del marcador lleva «VS» y, en el panel, una fila por partido
con las dos personas de la pareja propia en el orden alineado. Reutiliza los dibujos de ``result_image``.
"""
import io

from django.utils.translation import gettext as _
from PIL import Image, ImageDraw

from match.result_image import (
    BORDER, H, LIME, MUTED, SCALE, SURFACE, TEXT, W,
    _background, _fit, _font, _header, _own_pair, _pill, _s, _spaced_width, _team, _text,
)


def lineup_pairs(match, games):
    """Parejas propias por partido: ``[(n_game, [«A. Montaño», «J. Gamero»])]``, sin los partidos sin pareja propia o no presentados."""
    pairs = []
    for game in games:
        pair = [] if game.no_show in ("own", "both") else _own_pair(game, match.own_is_local)
        if pair:
            pairs.append((game.n_game, pair))
    return pairs


def _panel(draw, pairs):
    """Panel con una fila por partido: nº y los dos jugadores de la pareja."""
    n = max(len(pairs), 1)
    row_h = 116 if n > 4 else 136
    top = 600
    box = [64, top, W - 64, top + 16 + row_h * n]
    draw.rounded_rectangle([_s(v) for v in box], radius=_s(30), fill=SURFACE + (235,), outline=BORDER, width=_s(2))
    for i, (n_game, names) in enumerate(pairs):
        y = top + 8 + i * row_h
        cy = y + row_h / 2
        if i:
            draw.line([(_s(92), _s(y)), (_s(W - 92), _s(y))], fill=BORDER, width=_s(2))
        _text(draw, (96, cy), f"P{n_game}", _font("Anton-Regular.ttf", 40), LIME, "lm")
        for j, name in enumerate(names):
            font = _fit(draw, name, "Archivo-ExtraBold.ttf", 40, W - 128 - 240)
            _text(draw, (230, cy + (j - 0.5) * 48), name, font, TEXT, "lm")


def build_lineup_jpeg(match, games):
    """JPEG (bytes) de 1080×1350 con la alineación propia de ``match``; ``games`` son sus partidos ordenados por número."""
    rules = match.club.rules
    canvas = _background()
    draw = ImageDraw.Draw(canvas, "RGBA")

    draw = _header(canvas, draw, match, rules)

    own_is_local = match.own_is_local
    _team(draw, 188, 224, match.local_name, _("Local"), own_is_local)
    _team(draw, W - 188, 224, match.visiting_name, _("Visitante"), not own_is_local)
    _text(draw, (W / 2, 330), "VS", _font("Anton-Regular.ttf", 120), TEXT, "mm")

    label = _("ALINEACIÓN")
    font = _font("Archivo-ExtraBold.ttf", 30)
    pw = _spaced_width(draw, label, font, 6) / SCALE + 68
    _pill(canvas, [W / 2 - pw / 2, 500, W / 2 + pw / 2, 560], SURFACE + (255,), outline=BORDER, width=2)
    draw = ImageDraw.Draw(canvas, "RGBA")
    _text(draw, (W / 2, 531), label, font, LIME, "mm", spacing=6)

    _panel(draw, lineup_pairs(match, games))

    _text(draw, (64, 1285), _("Hecho con Zyra"), _font("Archivo-Bold.ttf", 26), MUTED, "lm")
    _text(draw, (W - 64, 1285), "zyrapadel.com", _font("Archivo-ExtraBold.ttf", 26), LIME, "rm", spacing=1)

    out = io.BytesIO()
    canvas.convert("RGB").resize((W, H), Image.LANCZOS).save(out, "JPEG", quality=92, optimize=True, subsampling=0)
    return out.getvalue()
