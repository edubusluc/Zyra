"""
PDF del informe mensual de un jugador, con el mismo estilo que el informe de convocatoria
(fondo oscuro, acento lima). Cabe en una página A4: indicadores del mes, sets, parejas y
el detalle de sus partidos (los que no caben se cuentan en una nota).
"""
import io

from django.utils.formats import date_format
from django.utils.translation import gettext as _, pgettext
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from .monthly_report import MAX_GAME_ROWS
from .report_pdf import (
    BG, BORDER, BOTTOM_MARGIN, CONTENT_W, GUTTER, HEADING_GAP, LOGO, MARGIN, MUTED, PAGE_H, PAGE_W,
    SECTION_GAP, TEXT, TOP_MARGIN, _data_table, _fit, _kpis, _panel, _pips, _record, _register_fonts,
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
    canvas.setFillColor(BG)
    canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    top = PAGE_H - 11 * mm
    if LOGO.exists():
        canvas.drawImage(str(LOGO), MARGIN, top - 3.2 * mm, width=7 * mm, height=7 * mm, mask="auto")
    canvas.setFillColor(TEXT)
    canvas.setFont("Syncopate", 12)
    canvas.drawString(MARGIN + 9 * mm, top - 1.3 * mm, "ZYRA")
    canvas.setFont("Archivo-Bold", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(PAGE_W - MARGIN, top, report["club"].name.upper())
    canvas.drawRightString(PAGE_W - MARGIN, top - 3.8 * mm, month_label(report["month"]).upper())
    canvas.setStrokeColor(BORDER)
    canvas.line(MARGIN, top - 6 * mm, PAGE_W - MARGIN, top - 6 * mm)
    canvas.setFont("Archivo", 7)
    canvas.drawString(MARGIN, 8 * mm, _("Informe mensual automático · Zyra"))
    canvas.restoreState()


def _sets_text(sets):
    """'6-4 3-6 10-8' a partir de los sets propios (propios-rival)."""
    return " ".join(f"{own}-{rival}" for own, rival in sets)


def _rate(rate):
    """'2V-1D' de un tipo de situación; vacío si no se ha dado."""
    return f"{rate['wins']}V-{rate['losses']}D" if rate["total"] else ""


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
    for label, key in ((_("Tercer set"), "third"), (_("Tie-breaks"), "tiebreak"), (_("Remontadas"), "comeback")):
        if sets[key]["total"]:
            right.append(Paragraph(esc(f"{label}: {_rate(sets[key])}"), st["body"]))
    if sets["bagels_for"] or sets["bagels_against"]:
        right.append(Paragraph(esc(_("Roscos: %(f)s dados, %(a)s recibidos")
                                   % {"f": sets["bagels_for"], "a": sets["bagels_against"]}), st["body"]))
    cards = Table([[left, right]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    cards.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [_panel(cards), Spacer(1, SECTION_GAP)]

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
