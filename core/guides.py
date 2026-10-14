"""
Guías públicas para capitanes (``/guia/``): contenido que atrae búsquedas de la cola larga
(parejas, puntos SNP, convocatorias) y lleva al alta de club. Cada guía existe en español e inglés
(``guides/<slug>.<idioma>.html``); el idioma sale de ``?lang=`` como en el resto de páginas públicas.
"""
import datetime
import io
from dataclasses import dataclass

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.translation import get_language, gettext as _
from django.views.decorators.http import require_safe
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from match.advisor import GAME_VALUES, POINTS_TO_WIN
from . import seo
from match.report_pdf import (
    CONTENT_W, LOGO, MARGIN, PAGE_H, PAGE_W, _register_fonts, draw_made_with,
)

PUBLISHED = datetime.date(2026, 10, 14)
TEMPLATE_PDF = "plantilla-convocatoria-padel.pdf"


@dataclass(frozen=True, eq=False)
class Guide:
    """Una guía: su URL, la palabra clave que ataca y título y descripción por idioma."""

    slug: str
    keyword: str
    title: dict
    description: dict
    published: datetime.date = PUBLISHED
    updated: datetime.date = PUBLISHED

    def title_for(self, language):
        """Título en ``language`` (español si no hay traducción)."""
        return self.title.get(language, self.title["es"])

    def description_for(self, language):
        """Descripción en ``language`` (español si no hay traducción)."""
        return self.description.get(language, self.description["es"])


GUIDES = [
    Guide(
        slug="organizar-parejas-equipo-padel",
        keyword="organizar parejas pádel",
        title={"es": "Cómo organizar las parejas de tu equipo de pádel",
               "en": "How to set the pairs of your padel team"},
        description={
            "es": "Criterios para formar las parejas de un equipo de pádel de liga por equipos: nivel, lados de pista, química y descanso. Con un método paso a paso.",
            "en": "How to pick the pairs of a team-league padel squad: level, court sides, chemistry and rest. A step-by-step method for captains.",
        },
    ),
    Guide(
        slug="puntos-snp-orden-parejas",
        keyword="puntos SNP pádel",
        title={"es": "Cómo funcionan los puntos SNP y el orden de las parejas",
               "en": "How SNP points and the order of the pairs work"},
        description={
            "es": "Qué son los puntos SNP, cómo se ordenan las parejas por la suma de puntos y cuántos puntos valen los 5 partidos de una eliminatoria.",
            "en": "What SNP points are, how pairs are ordered by their points sum and how many points each of the 5 games of a tie is worth.",
        },
    ),
    Guide(
        slug="plantilla-convocatoria-padel",
        keyword="plantilla convocatoria pádel",
        title={"es": "Plantilla de convocatoria de pádel (PDF gratis)",
               "en": "Padel team call-up template (free PDF)"},
        description={
            "es": "Descarga gratis una plantilla de convocatoria de pádel en PDF para imprimir: jugadores, disponibilidad, parejas y resultados. Y cómo hacerla automática.",
            "en": "Download a free printable padel call-up template in PDF: players, availability, pairs and results. And how to make it automatic.",
        },
    ),
]
BY_SLUG = {guide.slug: guide for guide in GUIDES}


def language_code():
    """Idioma activo reducido a los que tienen guía (``es`` o ``en``)."""
    return "en" if (get_language() or "es").startswith("en") else "es"


@require_safe
def guide_index(request):
    """Índice público de guías, con título y descripción en el idioma activo."""
    language = language_code()
    return render(request, "guides/index.html", {
        "guides": [(g, g.title_for(language), g.description_for(language)) for g in GUIDES],
    })


@require_safe
def guide_detail(request, slug):
    """Una guía pública: el texto va en ``guides/<slug>.<idioma>.html``. 404 si no existe."""
    guide = BY_SLUG.get(slug)
    if guide is None:
        raise Http404("Guía no encontrada")
    language = language_code()
    return render(request, "guides/detail.html", {
        "guide": guide,
        "guide_title": guide.title_for(language),
        "guide_description": guide.description_for(language),
        "guide_body": f"guides/{slug}.{language}.html",
        "others": [(g, g.title_for(language)) for g in GUIDES if g is not guide],
        "structured_data": seo.guide_structured_data(request, guide, language),
        "template_pdf": TEMPLATE_PDF,
    })


def _template_story():
    """Contenido de la plantilla: datos del partido, tabla de convocados y tabla de parejas."""
    ink, muted, rule = colors.HexColor("#111111"), colors.HexColor("#666666"), colors.HexColor("#BBBBBB")
    title = ParagraphStyle("t", fontName="Archivo-Black", fontSize=17, leading=21, textColor=ink)
    section = ParagraphStyle("s", fontName="Archivo-Black", fontSize=10.5, leading=13, textColor=ink, spaceBefore=7 * mm,
                             spaceAfter=2 * mm)
    cell = ParagraphStyle("c", fontName="Archivo-Bold", fontSize=8, leading=10, textColor=muted)

    def grid(header, rows, widths):
        """Tabla con cabecera clara, celdas a mano (filas de 9 mm) y rejilla fina."""
        table = Table([[Paragraph(h, cell) for h in header]] + rows, colWidths=widths, rowHeights=[7 * mm] + [9 * mm] * len(rows))
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, rule),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF7C9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONT", (0, 1), (0, -1), "Archivo-Bold", 8),
        ]))
        return table

    details = Table([[Paragraph(label, cell), ""] for label in (_("Rival"), _("Fecha y hora"), _("Lugar"))],
                    colWidths=[28 * mm, CONTENT_W - 28 * mm], rowHeights=[8 * mm] * 3)
    details.setStyle(TableStyle([("LINEBELOW", (1, 0), (1, -1), 0.5, rule), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    players = grid(["Nº", _("Jugador"), _("Puntos SNP"), _("Disponible"), _("Notas")],
                   [[str(n), "", "", "", ""] for n in range(1, 13)],
                   [10 * mm, CONTENT_W - 106 * mm, 28 * mm, 28 * mm, 40 * mm])
    pairs = grid([_("Partido"), _("Jugadores de la pareja"), _("Puntos en juego"), _("Resultado (sets)")],
                 [[str(n), "", str(points), ""] for n, points in enumerate(GAME_VALUES, start=1)],
                 [18 * mm, CONTENT_W - 18 * mm - 30 * mm - 40 * mm, 30 * mm, 40 * mm])
    note = ParagraphStyle("n", fontName="Archivo", fontSize=7.5, leading=10, textColor=muted)
    return [
        Paragraph(_("Convocatoria de pádel por equipos"), title), Spacer(1, 4 * mm), details,
        Paragraph(_("Jugadores convocados"), section), players,
        Paragraph(_("Parejas y resultados"), section), pairs, Spacer(1, 3 * mm),
        Paragraph(_("Los partidos 1 y 2 valen 3 puntos y los 3, 4 y 5 valen 2. Se ordenan por la suma de puntos SNP de cada pareja y se necesitan %(win)s de %(total)s puntos para ganar la eliminatoria.") % {"win": POINTS_TO_WIN, "total": sum(GAME_VALUES)}, note),
    ]


def build_template_pdf():
    """Bytes del PDF en blanco de la plantilla de convocatoria (A4, fondo blanco para imprimir)."""
    _register_fonts()
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=26 * mm,
                          bottomMargin=16 * mm, title=_("Plantilla de convocatoria de pádel"), author="Zyra")

    def on_page(canvas, _doc):
        """Cabecera con el logo y ZYRA y pie «Hecho con Zyra · dominio» enlazado a la web."""
        canvas.saveState()
        if LOGO.exists():
            canvas.drawImage(str(LOGO), MARGIN, PAGE_H - 17 * mm, width=7 * mm, height=7 * mm, mask="auto")
        canvas.setFillColor(colors.HexColor("#111111"))
        canvas.setFont("Syncopate-Italic", 12)
        canvas.drawString(MARGIN + 9 * mm, PAGE_H - 15.5 * mm, "ZYRA")
        canvas.setStrokeColor(colors.HexColor("#B4F100"))
        canvas.setLineWidth(2)
        canvas.line(MARGIN, PAGE_H - 20 * mm, PAGE_W - MARGIN, PAGE_H - 20 * mm)
        canvas.setFillColor(colors.HexColor("#666666"))
        draw_made_with(canvas, PAGE_W / 2)
        canvas.restoreState()

    frame = Frame(MARGIN, 16 * mm, CONTENT_W, PAGE_H - 42 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(frames=[frame], onPage=on_page)])
    doc.build(_template_story())
    return buffer.getvalue()


@require_safe
def callup_template_pdf(request):
    """Plantilla de convocatoria en blanco para imprimir (PDF público, sin registro)."""
    response = HttpResponse(build_template_pdf(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{TEMPLATE_PDF}"'
    return response
