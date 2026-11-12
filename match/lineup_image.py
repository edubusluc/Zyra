"""
Imagen de la alineación de un enfrentamiento para compartir por WhatsApp (botón de la tarjeta «Parejas»).

Mismo formato y estilo que ``match.result_image`` (JPEG vertical 4:5, 1080×1350 px, fondo de pista, logotipo,
insignia de la competición, escudos), pero en lugar del marcador lleva «VS», un bloque destacado con la fecha,
la hora y el lugar y, en el panel, una fila por partido con las dos personas de la pareja propia en el orden
alineado. En la SNP cada fila suma además los puntos SNP de sus dos jugadores. Reutiliza los dibujos de
``result_image``.
"""
import io

from django.utils.formats import date_format
from django.utils.translation import gettext as _
from PIL import Image, ImageDraw

from match.result_image import (
    BORDER, H, LIME, MUTED, SCALE, SURFACE, TEXT, W,
    _background, _fit, _font, _header, _own_pair, _pill, _s, _spaced_width, _team, _text,
)

EXTRA_BOLD = "Archivo-ExtraBold.ttf"
BOLD = "Archivo-Bold.ttf"
ANTON = "Anton-Regular.ttf"


def _own_players(match, game):
    """Los dos jugadores de la pareja propia de ``game`` (``None`` si se eliminó alguno)."""
    prefix = "local" if match.own_is_local else "visiting"
    return getattr(game, f"player_1_{prefix}"), getattr(game, f"player_2_{prefix}")


def _readable(name):
    """«E. BUSTAMANTE» → «E. Bustamante»: los nombres solo van en mayúsculas en los titulares."""
    return name.title() if name.isupper() else name


def lineup_pairs(match, games):
    """Parejas propias por partido: ``[(n_game, [«A. Montaño», «J. Gamero»], puntos SNP o None)]``.

    Salta los partidos sin pareja propia o con la pareja no presentada. Los puntos son la suma de los
    puntos SNP de los dos jugadores, solo en la SNP y solo si ambos los tienen.
    """
    is_snp = match.club.rules.code == "snp"
    pairs = []
    for game in games:
        pair = [] if game.no_show in ("own", "both") else _own_pair(game, match.own_is_local)
        if not pair:
            continue
        scores = [getattr(p, "snp_score", None) for p in _own_players(match, game)]
        total = sum(scores) if is_snp and all(s is not None for s in scores) else None
        pairs.append((game.n_game, [_readable(n) for n in pair], total))
    return pairs


def _format_points(value):
    """Puntos con separador de miles: 2340 → «2.340»."""
    return f"{value:,.0f}".replace(",", ".")


def _panel(draw, pairs):
    """Panel con una fila por partido: nº, los dos jugadores y, en la SNP, la suma de sus puntos."""
    n = max(len(pairs), 1)
    compact = n > 4
    row_h = 96 if compact else 128
    top = 699
    box = [64, top, W - 64, top + 16 + row_h * n]
    draw.rounded_rectangle([_s(v) for v in box], radius=_s(30), fill=SURFACE + (235,), outline=BORDER, width=_s(2))
    show_points = any(total is not None for _, _, total in pairs)
    for i, (n_game, names, total) in enumerate(pairs):
        y = top + 8 + i * row_h
        cy = y + row_h / 2
        if i:
            draw.line([(_s(92), _s(y)), (_s(W - 92), _s(y))], fill=BORDER, width=_s(2))
        _text(draw, (96, cy), f"P{n_game}", _font(ANTON, 40), LIME, "lm")
        for j, name in enumerate(names):
            font = _fit(draw, name, EXTRA_BOLD, 36 if compact else 40, 520 if show_points else 700)
            _text(draw, (230, cy + (j - 0.5) * (40 if compact else 48)), name, font, TEXT, "lm")
        if total is not None:
            _text(draw, (W - 96, cy - 12), _format_points(total), _font(ANTON, 54), LIME, "rm")
            _text(draw, (W - 96, cy + 32), _("PUNTOS"), _font(BOLD, 18), MUTED, "rm", spacing=3)


def _when_block(canvas, match):
    """Bloque destacado con fecha, hora y lugar, bajo la cabecera."""
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle([_s(64), _s(160), _s(W - 64), _s(290)], radius=_s(24), fill=(0, 0, 0, 110), outline=BORDER,
                           width=_s(2))
    draw.rounded_rectangle([_s(64), _s(160), _s(76), _s(290)], radius=_s(6), fill=LIME)
    day = date_format(match.start_date, "D j M").upper().replace(".", "")
    font = _font(ANTON, 60)
    _text(draw, (104, 205), day, font, LIME, "lm", spacing=1)
    if match.start_time:
        width = _spaced_width(draw, day, font, 1) / SCALE
        _text(draw, (104 + width + 24, 205), f"· {match.start_time:%H:%M}", font, TEXT, "lm", spacing=1)
    if match.location:
        _text(draw, (104, 258), match.location, _fit(draw, match.location, BOLD, 30, W - 128 - 70), TEXT, "lm")
    return draw


def build_lineup_jpeg(match, games):
    """JPEG (bytes) de 1080×1350 con la alineación propia de ``match``; ``games`` son sus partidos ordenados por número."""
    rules = match.club.rules
    canvas = _background()
    draw = ImageDraw.Draw(canvas, "RGBA")

    draw = _header(canvas, draw, match, rules, kicker=False)
    draw = _when_block(canvas, match)

    own_is_local = match.own_is_local
    _team(canvas, draw, 188, 320, match.local_name, _("Local"), own_is_local, match.local)
    _team(canvas, draw, W - 188, 320, match.visiting_name, _("Visitante"), not own_is_local, match.visiting)
    _text(draw, (W / 2, 426), "VS", _font(ANTON, 120), TEXT, "mm")

    label = _("ALINEACIÓN")
    font = _font(EXTRA_BOLD, 30)
    pw = _spaced_width(draw, label, font, 6) / SCALE + 68
    _pill(canvas, [W / 2 - pw / 2, 615, W / 2 + pw / 2, 675], SURFACE + (255,), outline=BORDER, width=2)
    draw = ImageDraw.Draw(canvas, "RGBA")
    _text(draw, (W / 2, 646), label, font, LIME, "mm", spacing=6)

    _panel(draw, lineup_pairs(match, games))

    _text(draw, (W / 2, 1295), "zyrapadel.com", _font(EXTRA_BOLD, 28), LIME, "mm", spacing=1)

    out = io.BytesIO()
    canvas.convert("RGB").resize((W, H), Image.LANCZOS).save(out, "JPEG", quality=92, optimize=True, subsampling=0)
    return out.getvalue()
