"""
PDF del informe de convocatoria con el estilo de Zyra (fondo oscuro, acento lima).
Pensado para caber en dos páginas A4: la primera con el contexto del partido y
los convocados; la segunda con parejas y las dos alineaciones recomendadas.

Con convocatorias grandes ``render_report`` prueba distribuciones cada vez más
compactas (``LAYOUTS``) hasta que el informe cabe en dos páginas. Si ni la más
compacta cabe, el contenido fluye de una página a la siguiente sin saltos forzados
para no dejar huecos grandes.
"""
import io
from dataclasses import dataclass, replace
from xml.sax.saxutils import escape as xml_escape
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from reportlab.graphics.shapes import Circle, Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.doctemplate import LayoutError
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)

# Paleta de la web
BG = colors.HexColor("#0B0B0B")
SURFACE = colors.HexColor("#151515")
SURFACE_2 = colors.HexColor("#1D1D1D")
BORDER = colors.HexColor("#333333")
LIME = colors.HexColor("#B4F100")
INK = colors.HexColor("#0A0A0A")
TEXT = colors.HexColor("#F4F4F4")
MUTED = colors.HexColor("#A3A3A3")
CORAL = colors.HexColor("#FF5C63")

FONT_DIR = Path(settings.BASE_DIR) / "static" / "zyra" / "fonts"
LOGO = Path(settings.BASE_DIR) / "static" / "zyra" / "logo.png"
PAGE_W, PAGE_H = A4
MARGIN = 14 * mm
TOP_MARGIN = 24 * mm       # deja aire bajo la línea de la cabecera
BOTTOM_MARGIN = 16 * mm    # y sobre el pie
CONTENT_W = PAGE_W - 2 * MARGIN

# Escala de espaciado vertical: todos los bloques usan estos valores para que el
# ritmo sea el mismo en las dos páginas.
SECTION_GAP = 6 * mm       # entre secciones
HEADING_GAP = 2.5 * mm     # título de sección -> su contenido
NOTE_GAP = 2 * mm          # tabla -> nota aclaratoria
GUTTER = 6 * mm            # separación entre columnas
PANEL_PAD = 9              # relleno interior de las tarjetas (pt)
CELL_PAD = 3.5             # relleno vertical de las filas de las tablas (pt)

# Anchos de la tabla de convocados (Jugador, SNP, Como sede, Global, Jug./Conv., Último, Racha, Forma):
# el SNP (hasta «14062.5») y los registros caben en una sola línea; el nombre se abrevia solo
PLAYER_COLS = [36 * mm, 17 * mm, 29 * mm, 29 * mm, 20 * mm, 18 * mm, 15 * mm, 18 * mm]
assert abs(sum(PLAYER_COLS) - CONTENT_W) < 0.01

MAX_PLAYERS_TABLE = 16     # filas de convocados en las distribuciones más apretadas
MAX_BENCH_NAMES = 8        # nombres en «Descansan»; el resto se cuenta
MIN_ROWS_AFTER_HEADING = 22 * mm  # sin salto forzado, un título no se queda solo al pie


@dataclass(frozen=True)
class Layout:
    """Densidad y reparto del informe.

    Los valores por defecto son la distribución normal; las demás de ``LAYOUTS``
    aprietan el espaciado y la letra, dejan fluir el contenido sin salto forzado y,
    en último caso, limitan las filas de convocados.
    """
    section_gap: float = SECTION_GAP
    heading_gap: float = HEADING_GAP
    note_gap: float = NOTE_GAP
    panel_pad: float = PANEL_PAD
    cell_pad: float = CELL_PAD
    cell_size: float = 9.5        # cuerpo de letra de las celdas
    body_size: float = 9.5        # cuerpo de letra del texto corrido
    max_players: int = None       # filas de convocados (None = todos)
    flow: bool = False            # sin salto de página forzado ni bloques indivisibles


_COMPACT = Layout(section_gap=4 * mm, heading_gap=1.8 * mm, note_gap=1.5 * mm, panel_pad=6,
                  cell_pad=2, cell_size=8.5, body_size=9)
LAYOUTS = (
    Layout(),
    _COMPACT,
    replace(_COMPACT, flow=True),
    *(replace(_COMPACT, max_players=n) for n in (24, 20, MAX_PLAYERS_TABLE)),
    # La última fluye sin huecos: si tampoco cabe en dos páginas, es la que se envía
    replace(_COMPACT, max_players=MAX_PLAYERS_TABLE, flow=True),
)

_fonts_ready = False


def _register_fonts():
    """Registra en reportlab las fuentes de Zyra (solo la primera vez)."""
    global _fonts_ready
    if _fonts_ready:
        return
    for name, file in (("Archivo", "Archivo-Regular.ttf"), ("Archivo-Bold", "Archivo-Bold.ttf"),
                       ("Archivo-Black", "Archivo-ExtraBold.ttf"), ("Syncopate", "Syncopate-Bold.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    _fonts_ready = True


def _styles(layout=Layout()):
    """Estilos de párrafo del informe, por nombre, con los cuerpos de letra de ``layout``."""
    size, cell = layout.body_size, layout.cell_size
    base = dict(fontName="Archivo", fontSize=size, leading=size * 1.3, textColor=TEXT, alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("title", fontName="Syncopate", fontSize=17, leading=21, textColor=TEXT),
        "subtitle": ParagraphStyle("subtitle", **{**base, "fontSize": 11, "leading": 14, "textColor": MUTED}),
        "section": ParagraphStyle("section", fontName="Archivo-Black", fontSize=11, leading=14,
                                  textColor=TEXT, spaceAfter=layout.heading_gap),
        "subsection": ParagraphStyle("subsection", fontName="Archivo-Bold", fontSize=7.5, leading=9,
                                     textColor=MUTED, spaceAfter=1.5 * mm),
        "body": ParagraphStyle("body", **base),
        "list": ParagraphStyle("list", **{**base, "spaceAfter": 2}),
        "muted": ParagraphStyle("muted", **{**base, "textColor": MUTED, "fontSize": 8.5, "leading": 11}),
        "cell": ParagraphStyle("cell", **{**base, "fontSize": cell, "leading": cell * 1.25}),
        "cell_bold": ParagraphStyle("cell_bold", **{**base, "fontName": "Archivo-Bold", "fontSize": cell,
                                                    "leading": cell * 1.25}),
        "kpi_value": ParagraphStyle("kpi_value", fontName="Archivo-Black", fontSize=17, leading=19, textColor=TEXT),
        "kpi_label": ParagraphStyle("kpi_label", fontName="Archivo-Bold", fontSize=7.5, leading=9, textColor=MUTED),
        "lineup_title": ParagraphStyle("lineup_title", fontName="Archivo-Black", fontSize=11, leading=14,
                                       textColor=LIME, spaceAfter=layout.heading_gap),
    }


def _pips(results, size=6.5):
    """Últimos resultados como círculos (lima = victoria, coral = derrota)."""
    d = Drawing(5 * (size + 2), size + 2)
    for i, won in enumerate(results):
        d.add(Circle(i * (size + 2) + size / 2 + 1, size / 2 + 1, size / 2,
                     fillColor=LIME if won else CORAL, strokeColor=None))
    return d


def _badge(text, fill=LIME, fg=INK, width=16 * mm):
    """Etiqueta redondeada con texto centrado (p. ej. VICTORIA / DERROTA)."""
    d = Drawing(width, 12)
    d.add(Rect(0, 0, width, 12, rx=6, ry=6, fillColor=fill, strokeColor=None))
    d.add(String(width / 2, 3.2, text, fontName="Archivo-Black", fontSize=7, fillColor=fg, textAnchor="middle"))
    return d


def _wl(wins, losses):
    """'3V-2D' (victorias-derrotas) en el idioma activo."""
    return _("%(wins)sV-%(losses)sD") % {"wins": wins, "losses": losses}


def _record(wins, played):
    """'3V-2D · 60%' a partir de victorias y jugados; vacío si no hay partidos."""
    if not played:
        return ""
    return f"{_wl(wins, played - wins)} · {round(wins / played * 100)}%"


def _streak_label(kind, n):
    """'3V' / '2D' (racha de victorias o derrotas) en el idioma activo."""
    return (_("%(n)sV") if kind == "V" else _("%(n)sD")) % {"n": n}


def _streak(streak):
    """Texto de una racha ('3V', '2D'); vacío si no hay (mejor una celda en blanco que un guion)."""
    kind, n = streak
    return _streak_label(kind, n) if kind else ""


def _columns(left, right, left_w):
    """Dos columnas alineadas arriba, sin relleno y separadas por GUTTER."""
    t = Table([[left, right]], colWidths=[left_w + GUTTER, CONTENT_W - left_w - GUTTER])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), GUTTER),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _panel(content, padding=PANEL_PAD):
    """Tarjeta oscura con borde fino (como .z-card)."""
    t = Table([[content]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("LEFTPADDING", (0, 0), (-1, -1), padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
    ]))
    return t


def _data_table(header, rows, col_widths, st, highlight_first=False, pad=CELL_PAD):
    """Tabla con cabecera y filas al estilo de la web.

    ``highlight_first`` marca con una línea lima las dos primeras filas de datos y
    ``pad`` es el relleno vertical de cada fila.
    """
    data = [[Paragraph(h.upper(), st["kpi_label"]) for h in header]] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), SURFACE_2),
        ("BACKGROUND", (0, 1), (-1, -1), SURFACE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if highlight_first:
        style.append(("LINEBEFORE", (0, 1), (0, 2), 2.5, LIME))
    t.setStyle(TableStyle(style))
    return t


def _kpis(items, st):
    """Fila de indicadores (etiqueta y valor grande) dentro de una tarjeta; un valor vacío se deja en blanco."""
    cells = [[Paragraph(esc(label.upper()), st["kpi_label"]), Paragraph(value or "&nbsp;", st["kpi_value"])] for label, value in items]
    widths = [CONTENT_W / len(items)] * len(items)
    inner = [Table([[c[0]], [c[1]]], colWidths=[widths[0] - 8]) for c in cells]
    for t in inner:
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    t = Table([inner], colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, BORDER),
        ("LINEBEFORE", (0, 0), (0, -1), 3, LIME),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _on_page(canvas, doc, report, total):
    """Dibuja el fondo, la cabecera (logo, club y fecha) y el pie («Página n de ``total``»)."""
    canvas.saveState()
    canvas.setFillColor(BG)
    canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    # Cabecera: logo + ZYRA a la izquierda, club y fecha a la derecha
    top = PAGE_H - 11 * mm
    if LOGO.exists():
        canvas.drawImage(str(LOGO), MARGIN, top - 3.2 * mm, width=7 * mm, height=7 * mm, mask="auto")
    canvas.setFillColor(TEXT)
    canvas.setFont("Syncopate", 12)
    canvas.drawString(MARGIN + 9 * mm, top - 1.3 * mm, "ZYRA")
    canvas.setFont("Archivo-Bold", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(PAGE_W - MARGIN, top, report["club"].name.upper())
    canvas.drawRightString(PAGE_W - MARGIN, top - 3.8 * mm,
                           _("Generado el %(date)s") % {"date": timezone.localtime().strftime("%d/%m/%Y %H:%M")})
    canvas.setStrokeColor(BORDER)
    canvas.line(MARGIN, top - 6 * mm, PAGE_W - MARGIN, top - 6 * mm)
    # Pie
    canvas.setFont("Archivo", 7)
    canvas.drawString(MARGIN, 8 * mm, _("Informe automático de convocatoria · Zyra"))
    canvas.drawRightString(PAGE_W - MARGIN, 8 * mm, _("Página %(page)s de %(total)s") % {"page": doc.page, "total": total})
    canvas.restoreState()


CELL_X_PAD = 10  # relleno horizontal de una celda (5 pt por lado)


def _fit(text, width, font="Archivo-Bold", size=8):
    """Recorta ``text`` con «…» para que quepa en una línea de ``width`` puntos."""
    text = str(text)
    if pdfmetrics.stringWidth(text, font, size) <= width:
        return text
    while text and pdfmetrics.stringWidth(text.rstrip() + "…", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _player_label(player, width, font="Archivo-Bold", size=8):
    """Nombre corto del jugador en una sola línea de ``width`` puntos.

    Si no cabe entero se abrevia el nombre de pila («F. J. FERNÁNDEZ») y, como
    último recurso, se recorta con «…»: así cada jugador ocupa una fila y la
    tabla no crece con los nombres largos.
    """
    full = player.short_name
    if pdfmetrics.stringWidth(full, font, size) <= width:
        return full
    initials = " ".join(f"{part[0]}." for part in player.name.split() if part)
    return _fit(f"{initials} {player.get_first_last_name()}".strip().upper(), width, font, size)


def _pair_label(pair, width, font="Archivo-Bold", size=8):
    """'JUGADOR A / JUGADOR B' en una línea de ``width`` puntos (cada nombre en su mitad si no cabe)."""
    if pdfmetrics.stringWidth(pair.name, font, size) <= width:
        return pair.name
    half = (width - pdfmetrics.stringWidth(" / ", font, size)) / 2
    return f"{_player_label(pair.a.player, half, font, size)} / {_player_label(pair.b.player, half, font, size)}"


def esc(value):
    """Texto escrito por los usuarios (nombres de equipos y jugadores) dentro de un Paragraph:
    reportlab interpreta < > & como etiquetas, así que sin escaparlos un nombre podía meter
    formato en el PDF o hacer fallar su generación (y con ella el envío del informe)."""
    return xml_escape(str(value))


def _story(report, layout):
    """Flowables del informe con la densidad y el reparto de ``layout``."""
    st = _styles(layout)
    match, venue = report["match"], report["venue_label"]
    own = match.local if match.own_is_local else match.visiting
    cell_size, pad = layout.cell_size, layout.cell_pad
    story = []

    def section(text):
        """Título de sección; sin saltos forzados no se queda solo al pie de una página."""
        if layout.flow:
            story.append(CondPageBreak(MIN_ROWS_AFTER_HEADING))
        story.append(Paragraph(text, st["section"]))

    # ---------------- Página 1 ----------------
    story.append(Paragraph(_("INFORME DE CONVOCATORIA"), st["title"]))
    story.append(Spacer(1, 1 * mm))
    story.append(Paragraph(
        _("<b>%(own)s</b> vs <b>%(rival)s</b> · %(date)s · "
          "jugáis como <font color='#B4F100'><b>%(venue)s</b></font> · temporada %(season)s") % {
            "own": esc(own), "rival": esc(report['rival']), "date": f"{match.start_date:%d/%m/%Y}",
            "venue": venue.upper(), "season": match.season},
        st["subtitle"]))
    story.append(Spacer(1, 5 * mm if layout.section_gap >= SECTION_GAP else 3 * mm))

    s = report["season"]
    prec = report["precedents"]
    prec_w = sum(p["outcome"] == "V" for p in prec)
    story.append(_kpis([
        (_("Convocados"), str(len(report["called"]))),
        (_("Temporada"), _wl(s['won'], s['played'] - s['won'])),
        (_("Como %(venue)s") % {"venue": venue}, _wl(s['venue_won'], s['venue_played'] - s['venue_won'])),
        ((_("Vs %(rival)s") % {"rival": report['rival']})[:22], _wl(prec_w, len(prec) - prec_w) if prec else ""),
    ], st))

    # Precedentes y rachas, en dos columnas
    prec_col_w = CONTENT_W * 0.56 - GUTTER
    if prec:
        prec_rows = [[Paragraph(f"{p['date']:%d/%m/%Y}", st["cell"]), Paragraph(p["venue"], st["cell"]),
                      Paragraph(f"<b>{p['score']}</b>", st["cell"]),
                      _badge(_("VICTORIA") if p["outcome"] == "V" else _("DERROTA") if p["outcome"] == "D" else _("EMPATE"),
                             fill=LIME if p["outcome"] == "V" else CORAL if p["outcome"] == "D" else MUTED)]
                     for p in prec]
        prec_block = [Paragraph(_("PRECEDENTES CONTRA %(rival)s") % {"rival": esc(str(report['rival']).upper())}, st["section"]),
                      _data_table([_("Fecha"), _("Sede"), _("Puntos"), ""], prec_rows,
                                  [22 * mm, 22 * mm, 18 * mm, prec_col_w - 62 * mm], st, pad=pad)]
    else:
        prec_block = [Paragraph(_("PRECEDENTES CONTRA %(rival)s") % {"rival": esc(str(report['rival']).upper())}, st["section"]),
                      Paragraph(_("Primer enfrentamiento contra este equipo."), st["muted"])]

    streak_w = CONTENT_W - prec_col_w - GUTTER - 18  # columna derecha menos la etiqueta «3V»

    def streak_lines(items, color):
        """Una línea por jugador en racha, o un aviso si no hay ninguno."""
        if not items:
            return [Paragraph(_("Nadie con 2 o más resultados seguidos."), st["muted"])]
        return [Paragraph(f"<font color='{color}'><b>{_streak_label(f.streak[0], f.streak[1])}</b></font>  "
                          f"{esc(_player_label(f.player, streak_w, 'Archivo', layout.body_size))}", st["list"])
                for f in items]

    streak_block = [Paragraph(_("JUGADORES EN RACHA"), st["section"]),
                    *streak_lines(report["hot"], "#B4F100"),
                    Spacer(1, 3 * mm if layout.section_gap >= SECTION_GAP else 2 * mm),
                    Paragraph(_("EN MALA RACHA"), st["subsection"]),
                    *streak_lines(report["cold"], "#FF5C63")]
    story.append(Spacer(1, layout.section_gap))
    story.append(_columns(prec_block, streak_block, prec_col_w))

    # Convocados
    players = report["players"]
    shown = players[:layout.max_players] if layout.max_players else players
    story.append(Spacer(1, layout.section_gap))
    section(_("CONVOCADOS · RENDIMIENTO COMO %(venue)s") % {"venue": venue.upper()})
    widths = PLAYER_COLS
    name_w = widths[0] - CELL_X_PAD
    usage = report["usage"]

    def last_played(f):
        """Fecha del último partido disputado por el convocado; vacía si aún no ha jugado."""
        last = usage[f.player.id]["last"]
        return f"{last:%d/%m/%y}" if last else ""

    player_rows = [[
        Paragraph(f"<b>{esc(_player_label(f.player, name_w, size=cell_size))}</b>", st["cell"]),
        Paragraph(f"{f.snp:g}" if f.snp else "", st["cell"]),
        Paragraph(_record(f.venue_wins, f.venue_played), st["cell"]),
        Paragraph(_record(f.wins, f.played), st["cell"]),
        Paragraph(f"<b>{usage[f.player.id]['games']}</b>/{usage[f.player.id]['calls']}", st["cell"]),
        Paragraph(last_played(f), st["cell"]),
        Paragraph(f"<font color='{'#B4F100' if f.streak[0] == 'V' else '#FF5C63'}'><b>{_streak(f.streak)}</b></font>", st["cell"]),
        _pips(f.form),
    ] for f in shown]
    story.append(_data_table(
        [_("Jugador"), "SNP", _("Como %(venue)s") % {"venue": venue}, _("Global"), _("Jug./Conv."), _("Último"),
         _("Racha"), _("Forma")],
        player_rows, widths, st, pad=pad))
    note = _("Jug./Conv.: partidos jugados / convocatorias en las que se apuntó esta temporada, sin contar "
             "esta convocatoria ni este partido. Último: fecha del último partido disputado.")
    if len(players) > len(shown):
        note += " " + _("%(n)s convocados más no caben en la tabla.") % {"n": len(players) - len(shown)}
    story.append(Spacer(1, layout.note_gap))
    story.append(Paragraph(note, st["muted"]))

    # ---------------- Página 2 ----------------
    if layout.flow:
        story.append(Spacer(1, layout.section_gap))
    else:
        story.append(PageBreak())
    section(_("PAREJAS CON HISTORIAL ENTRE LOS CONVOCADOS"))
    if report["pairs"]:
        pair_name_w = 84 * mm - CELL_X_PAD
        pair_rows = [[
            Paragraph(f"<b>{esc(_pair_label(p, pair_name_w, size=cell_size))}</b>", st["cell"]),
            Paragraph(f"{p.snp_sum:g}", st["cell"]),
            Paragraph(_record(p.venue_wins, p.venue_played), st["cell"]),
            Paragraph(_record(p.wins, p.played), st["cell"]),
            Paragraph(_streak(p.streak), st["cell"]),
        ] for p in report["pairs"]]
        story.append(_data_table([_("Pareja"), _("Suma SNP"), _("Como %(venue)s") % {"venue": venue}, _("Juntos"), _("Racha")],
                                 pair_rows, [84 * mm, 18 * mm, 30 * mm, 30 * mm, 20 * mm], st, pad=pad))
    else:
        story.append(Paragraph(_("Ninguna pareja de convocados ha jugado junta todavía."), st["muted"]))

    story.append(Spacer(1, layout.section_gap))
    section(_("ALINEACIONES RECOMENDADAS"))
    if not report["enough_players"]:
        story.append(Paragraph(_("Hacen falta al menos 10 convocados para proponer una alineación."), st["body"]))
    # Sin saltos forzados las alineaciones van sin tarjeta para que su tabla pueda partirse entre páginas
    lineup_w = CONTENT_W - (0 if layout.flow else 2 * layout.panel_pad)
    pair_col_w = lineup_w - 80 * mm
    for i, item in enumerate(report["lineups"]):
        if i:
            story.append(Spacer(1, layout.section_gap if layout.flow else 4 * mm))
        lineup = item["lineup"]
        rows = [[
            Paragraph(f"<b>{row['n']}</b>", st["cell_bold"]),
            _badge(_("%(n)s PTS") % {"n": row['value']}, fill=LIME if row['value'] == 3 else SURFACE_2,
                   fg=INK if row['value'] == 3 else TEXT, width=13 * mm),
            Paragraph(f"<b>{esc(_pair_label(row['pair'], pair_col_w - CELL_X_PAD, size=cell_size))}</b>", st["cell"]),
            Paragraph(f"{row['pair'].snp_sum:g}", st["cell"]),
            Paragraph(f"<b>{row['pct']}%</b>", st["cell"]),
        ] for row in lineup.rows]
        table = _data_table([_("Partido"), _("Valor"), _("Pareja"), _("Suma SNP"), _("Victoria est.")], rows,
                            [16 * mm, 18 * mm, pair_col_w, 20 * mm, 26 * mm], st, highlight_first=True, pad=pad)
        title = Paragraph(_("%(title)s · %(pct)s%% DE GANAR LA ELIMINATORIA") % {
            "title": item['title'].upper(), "pct": round(lineup.win * 100)}, st["lineup_title"])
        if layout.flow:
            story.append(CondPageBreak(MIN_ROWS_AFTER_HEADING))
        block = [title, table, Spacer(1, 3 * mm if layout.section_gap >= SECTION_GAP else 2 * mm),
                 Paragraph(esc(item["explanation"]), st["body"])]
        if lineup.bench:
            block.append(Spacer(1, layout.note_gap))
            names = ", ".join(f.name for f in lineup.bench[:MAX_BENCH_NAMES])
            if len(lineup.bench) > MAX_BENCH_NAMES:
                names = _("%(names)s y %(n)s más") % {"names": names, "n": len(lineup.bench) - MAX_BENCH_NAMES}
            block.append(Paragraph(_("Descansan: %(names)s") % {"names": esc(names)}, st["muted"]))
        story.extend(block if layout.flow else [KeepTogether([_panel(block, layout.panel_pad)])])

    story.append(Spacer(1, layout.section_gap))
    story.append(Paragraph(
        _("Formato SNP: 5 partidos; los partidos 1 y 2 valen 3 puntos y los 3, 4 y 5 valen 2. Las parejas se "
          "ordenan por la suma de puntos SNP de sus jugadores y se necesitan 7 de 12 puntos para ganar la "
          "eliminatoria. Las estimaciones se basan en el historial del club y son orientativas."),
        st["muted"]))
    return story


def _build(report, layout, total=2):
    """Maqueta el informe con ``layout``; devuelve (bytes del PDF, número de páginas)."""
    match = report["match"]
    own = match.local if match.own_is_local else match.visiting
    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        title=_("Informe de convocatoria · %(own)s vs %(rival)s") % {"own": own, "rival": report['rival']}, author="Zyra",
    )
    # Marco sin relleno: los títulos y las tablas (que miden CONTENT_W) quedan alineados al mismo margen
    frame = Frame(MARGIN, BOTTOM_MARGIN, CONTENT_W, PAGE_H - TOP_MARGIN - BOTTOM_MARGIN,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(frames=[frame], onPage=lambda c, d: _on_page(c, d, report, total))])
    doc.build(_story(report, layout))
    return buffer.getvalue(), doc.page


def render_report(report):
    """Devuelve los bytes del PDF.

    Usa la primera distribución de ``LAYOUTS`` que cabe en dos páginas; si ninguna
    cabe, la última (el contenido sigue de una página a otra sin huecos). El pie
    numera sobre el total real de páginas.
    """
    _register_fonts()
    for layout in LAYOUTS[:-1]:
        try:
            pdf, pages = _build(report, layout)
        except LayoutError:  # un bloque indivisible más alto que una página: solo cabe fluyendo
            continue
        if pages <= 2:
            return pdf
    layout = LAYOUTS[-1]
    pdf, pages = _build(report, layout)
    return pdf if pages == 2 else _build(report, layout, total=pages)[0]
