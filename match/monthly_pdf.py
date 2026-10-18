"""
PDF del informe mensual de un jugador, con el mismo estilo que el informe de convocatoria
(fondo oscuro, acento lima). Ocupa 2 páginas A4: indicadores del mes, sets clutch, convocatorias,
evolución de puntos SNP, parejas y el detalle de sus partidos (los que no caben se cuentan en una nota).
"""
import io

from django.utils.formats import date_format
from django.utils.translation import gettext as _, pgettext
from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, String
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, KeepTogether, Paragraph, Spacer, Table, TableStyle

from .monthly_report import CALL_ABSENT, CALL_BENCHED, CALL_PLAYED, MAX_CALL_ROWS, MAX_GAME_ROWS
from .report_pdf import (
    draw_made_with, draw_page_header, BOTTOM_MARGIN, CONTENT_W, GUTTER, HEADING_GAP, MARGIN, PAGE_H, PAGE_W,
    BORDER, LIME, MUTED, SECTION_GAP, TOP_MARGIN, _data_table, _fit, _kpis, _panel, _pips, _record, _register_fonts,
    _streak_label, _styles, esc,
)
from core.models import REPORT_SCOPE_COMPETITIVE


def month_label(month):
    """Mes y año en el idioma activo, p. ej. «septiembre de 2026»."""
    return date_format(month, "F Y")


def report_filename(report):
    """Nombre del PDF, p. ej. 'informe-mensual-2026-09.pdf'."""
    return f"informe-mensual-{report['month']:%Y-%m}.pdf"


def scope_label(report):
    """Qué partidos cuenta el informe, en una frase."""
    if report["scope"] == REPORT_SCOPE_COMPETITIVE:
        return _("Solo partidos competitivos")
    return _("Todos los partidos, amistosos incluidos")


def _on_page(canvas, doc, report):
    """Fondo, cabecera (logo, club y mes) y pie del informe mensual."""
    canvas.saveState()
    draw_page_header(canvas, report["club"].name, month_label(report["month"]).upper())
    canvas.setFont("Archivo", 7)
    canvas.drawString(MARGIN, 8 * mm, _("Informe mensual automático · Zyra"))
    draw_made_with(canvas, PAGE_W - MARGIN, align="right")
    canvas.restoreState()


def _sets_text(sets):
    """'6-4 3-6 10-8' a partir de los sets propios (propios-rival)."""
    return " ".join(f"{own}-{rival}" for own, rival in sets)


def _rate(rate):
    """'2V-1D' de un tipo de situación; vacío si no se ha dado."""
    return f"{rate['wins']}V-{rate['losses']}D" if rate["total"] else ""


def _score(value):
    """Puntos SNP con separador de miles («68 500»)."""
    return f"{value:,.0f}".replace(",", " ")


def _snp_chart(points, width, height=34 * mm):
    """
    Gráfica de la evolución de los puntos SNP del mes (línea lima sobre rejilla tenue).

    ``points`` es [(fecha, puntos)] ordenado. Con un solo punto dibuja solo el punto. El eje
    vertical va de mínimo a máximo (con un margen) y el horizontal, de la primera a la
    última fecha del mes con datos.
    """
    drawing = Drawing(width, height)
    left, right, bottom, top = 30, 8, 14, 6
    plot_w, plot_h = width - left - right, height - bottom - top
    values = [score for _date, score in points]
    low, high = min(values), max(values)
    pad = (high - low) * 0.1 or max(abs(high) * 0.01, 1)
    low, high = low - pad, high + pad
    first, last = points[0][0], points[-1][0]
    span = max((last - first).days, 1)

    def x(day):
        """Posición horizontal de una fecha."""
        return left + (plot_w / 2 if last == first else (day - first).days / span * plot_w)

    def y(score):
        """Posición vertical de unos puntos."""
        return bottom + (score - low) / (high - low) * plot_h

    for frac in (0, 0.5, 1):
        level = low + (high - low) * frac
        drawing.add(Line(left, y(level), left + plot_w, y(level), strokeColor=BORDER, strokeWidth=0.4))
        drawing.add(String(left - 4, y(level) - 2.5, _score(level), fontName="Archivo", fontSize=6.5,
                           fillColor=MUTED, textAnchor="end"))
    if len(points) > 1:
        drawing.add(PolyLine([c for d, sc in points for c in (x(d), y(sc))], strokeColor=LIME, strokeWidth=1.6))
    for day, score in points:
        drawing.add(Circle(x(day), y(score), 2, fillColor=LIME, strokeColor=LIME))
    drawing.add(String(left, 3, f"{first:%d/%m}", fontName="Archivo", fontSize=6.5, fillColor=MUTED))
    if last != first:
        drawing.add(String(left + plot_w, 3, f"{last:%d/%m}", fontName="Archivo", fontSize=6.5,
                           fillColor=MUTED, textAnchor="end"))
    return drawing


def _snp_section(report, st):
    """Título, resumen y gráfica de la evolución SNP del mes (o un aviso si no hay datos)."""
    points = report["snp"]
    story = [Paragraph(esc(_("Evolución de tus puntos SNP")), st["section"])]
    if not points:
        return story + [Paragraph(esc(_("No hay actualizaciones de puntos SNP este mes.")), st["muted"])]
    start, end = points[0][1], points[-1][1]
    if len(points) > 1:
        delta = end - start
        summary = _("De %(start)s a %(end)s puntos (%(delta)s)") % {
            "start": _score(start), "end": _score(end), "delta": f"{'+' if delta > 0 else ''}{_score(delta)}"}
    else:
        summary = _("%(end)s puntos a fecha %(date)s") % {"end": _score(end), "date": f"{points[0][0]:%d/%m}"}
    return story + [Paragraph(esc(summary), st["body"]), Spacer(1, HEADING_GAP),
                    _panel(_snp_chart(points, CONTENT_W - 2 * 9))]


def _clutch_section(report, st):
    """Panel «Sets clutch» de las estadísticas del jugador: decisivo, tie-breaks, remontadas y más, con su V-D."""
    sets = report["sets"]
    story = [Paragraph(esc(_("Sets clutch")), st["section"]),
             Paragraph(esc(_("Cómo respondes en los momentos decisivos: tercer set, tie-breaks y remontadas.")),
                       st["muted"]), Spacer(1, HEADING_GAP)]
    situations = [(_("Set decisivo"), "third"), (_("Tie-breaks"), "tiebreak"), (_("Remontadas"), "comeback"),
                  (_("Cerrar el partido"), "first_set"), (_("Sets ajustados"), "close")]
    if sets["super_tb"]["total"]:
        situations.append((_("Super tie-break"), "super_tb"))
    cells = []
    for label, key in situations:
        rate = sets[key]
        pct = f"{rate['pct']}%" if rate["pct"] is not None else "—"
        cells.append([Paragraph(esc(label).upper(), st["subsection"]),
                      Paragraph(f"<b>{pct}</b> · {esc(_rate(rate)) if rate['total'] else esc(_('Ninguno'))}", st["body"])])
    cols = 3
    while len(cells) % cols:
        cells.append("")
    grid = Table([cells[i:i + cols] for i in range(0, len(cells), cols)], colWidths=[CONTENT_W / cols - 6] * cols)
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    facts = _("Llegan al tercer set: %(share)s %%") % {"share": sets["third_share"] or 0}
    return story + [_panel([grid, Paragraph(esc(facts), st["muted"])])]


def _calls_section(report, st):
    """Convocatorias del mes: totales por estado y listado (apuntado y convocado, apuntado y no convocado, no apuntado)."""
    counts, calls = report["call_counts"], report["calls"]
    story = [Paragraph(esc(_("Convocatorias del mes")), st["section"])]
    if not calls:
        return story + [Paragraph(esc(_("No hubo convocatorias cerradas este mes.")), st["muted"])]
    signed = counts[CALL_PLAYED] + counts[CALL_BENCHED]
    story += [_kpis([
        (_("Apuntado"), f"{signed}/{len(calls)}"),
        (_("Convocado"), str(counts[CALL_PLAYED])),
        (_("No convocado"), str(counts[CALL_BENCHED])),
        (_("No apuntado"), str(counts[CALL_ABSENT])),
    ], st), Spacer(1, HEADING_GAP)]
    labels = {CALL_PLAYED: _("Apuntado y convocado"), CALL_BENCHED: _("Apuntado, no convocado"),
              CALL_ABSENT: _("No apuntado")}
    rows = [[Paragraph(f"{c['date']:%d/%m}", st["cell"]),
             Paragraph(esc(_fit(c["rival"], 55 * mm, "Archivo-Bold", 8)), st["cell_bold"]),
             Paragraph(esc(c["match_type"]), st["cell"]),
             Paragraph(esc(labels[c["status"]]), st["cell_bold"] if c["status"] == CALL_PLAYED else st["cell"])]
            for c in calls[:MAX_CALL_ROWS]]
    story.append(_data_table([_("Fecha"), _("Rival"), _("Tipo"), _("Tu estado")], rows,
                             [16 * mm, 62 * mm, 40 * mm, CONTENT_W - 118 * mm], st))
    extra = len(calls) - MAX_CALL_ROWS
    if extra > 0:
        story += [Spacer(1, HEADING_GAP), Paragraph(esc(_("Y %(n)s convocatorias más.") % {"n": extra}), st["muted"])]
    return story


def _story(report):
    """Flowables del informe."""
    st = _styles()
    story = [
        Paragraph(esc(_("Tu mes en pista")).upper(), st["title"]),
        Spacer(1, 1.5 * mm),
        Paragraph(f"{esc(report['player'].full_name)} · {esc(month_label(report['month']))}", st["subtitle"]),
        Paragraph(esc(scope_label(report)), st["muted"]),
        Spacer(1, SECTION_GAP),
    ]
    sets = report["sets"]
    story += [
        _kpis([
            (_("Partidos"), str(report["played"])),
            (_("Victorias"), f"{report['wins']}"),
            (_("% victorias"), f"{report['pct']}%"),
            (_("Puntos"), str(report["points"])),
        ], st),
        Spacer(1, SECTION_GAP),
    ]

    # Forma del mes y sets en dos tarjetas
    kind, n = report["streak"]
    form = Table([[_pips(report["form"][-10:])]], colWidths=[CONTENT_W / 2 - GUTTER])
    form.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    left = [Paragraph(esc(_("Forma")).upper(), st["subsection"]), form,
            Spacer(1, 2 * mm),
            Paragraph(esc(_("Racha actual: %(streak)s") % {"streak": _streak_label(kind, n)} if kind else ""),
                      st["body"]),
            Paragraph(esc(_("Enfrentamientos jugados: %(n)s") % {"n": report["matches"]}), st["body"])]
    right = [Paragraph(esc(_("Sets")).upper(), st["subsection"]),
             Paragraph(esc(_("Sets: %(w)s ganados, %(l)s perdidos") % {"w": sets["sets_won"], "l": sets["sets_lost"]}),
                       st["body"]),
             Paragraph(esc(_("Juegos: %(w)s a favor, %(l)s en contra") % {"w": sets["games_won"], "l": sets["games_lost"]}),
                       st["body"])]
    if sets["bagels_for"] or sets["bagels_against"]:
        right.append(Paragraph(esc(_("Roscos: %(f)s dados, %(a)s recibidos")
                                   % {"f": sets["bagels_for"], "a": sets["bagels_against"]}), st["body"]))
    cards = Table([[left, right]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    cards.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [_panel(cards), Spacer(1, SECTION_GAP)]
    for section in (_clutch_section, _snp_section, _calls_section):
        story += [KeepTogether(section(report, st)), Spacer(1, SECTION_GAP)]

    # Parejas
    if report["partners"]:
        story.append(Paragraph(esc(_("Tus parejas")), st["section"]))
        rows = [[Paragraph(esc(_fit(p["name"], 90 * mm)), st["cell_bold"]), Paragraph(str(p["played"]), st["cell"]),
                 Paragraph(esc(_record(p["wins"], p["played"])), st["cell"])] for p in report["partners"][:6]]
        story += [_data_table([_("Pareja"), _("Jugados"), _("Balance")], rows,
                              [CONTENT_W - 70 * mm, 25 * mm, 45 * mm], st, highlight_first=True),
                  Spacer(1, SECTION_GAP)]

    # Detalle
    story.append(Paragraph(esc(_("Tus partidos")), st["section"]))
    rows = []
    for g in report["games"][:MAX_GAME_ROWS]:
        rows.append([
            Paragraph(f"{g['date']:%d/%m}", st["cell"]),
            Paragraph(esc(_fit(g["rival"], 31 * mm, "Archivo-Bold", 8)), st["cell_bold"]),
            Paragraph(esc(g["match_type"]), st["cell"]),
            Paragraph(esc(_fit(g["partner"], 35 * mm, "Archivo", 8)), st["cell"]),
            Paragraph(f"{g['n_game'] or ''}", st["cell"]),
            Paragraph(esc(_sets_text(g["sets"])), st["cell"]),
            Paragraph(pgettext("abreviatura de victoria", "V") if g["won"] else pgettext("abreviatura de derrota", "D"),
                      st["cell_bold"]),
        ])
    story.append(_data_table(
        [_("Fecha"), _("Rival"), _("Tipo"), _("Pareja"), _("Nº"), _("Sets"), ""], rows,
        [16 * mm, 36 * mm, 30 * mm, 40 * mm, 10 * mm, CONTENT_W - 144 * mm, 12 * mm], st))
    extra = len(report["games"]) - MAX_GAME_ROWS
    if extra > 0:
        story += [Spacer(1, HEADING_GAP),
                  Paragraph(esc(_("Y %(n)s partidos más.") % {"n": extra}), st["muted"])]
    return story


def render_monthly_report(report):
    """Devuelve los bytes del PDF del informe mensual."""
    _register_fonts()
    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN, author="Zyra",
        title=_("Informe mensual · %(month)s") % {"month": month_label(report["month"])},
    )
    frame = Frame(MARGIN, BOTTOM_MARGIN, CONTENT_W, PAGE_H - TOP_MARGIN - BOTTOM_MARGIN,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(frames=[frame], onPage=lambda c, d: _on_page(c, d, report))])
    doc.build(_story(report))
    return buffer.getvalue()
