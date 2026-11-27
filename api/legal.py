"""Textos legales para la app: las páginas de la web (privacidad, términos y cookies) convertidas en bloques de texto."""
import re
from html.parser import HTMLParser

from django.conf import settings
from django.template.loader import render_to_string

from core.views import LEGAL_UPDATED

# Slug en la API → plantilla y título. El texto legal solo existe en español (es el que vale legalmente).
DOCUMENTS = {
    "privacy": ("legal/privacy.html", "Política de privacidad"),
    "terms": ("legal/terms.html", "Términos y condiciones"),
    "cookies": ("legal/cookies.html", "Política de cookies"),
}

_ARTICLE = re.compile(r"<article[^>]*z-legal[^>]*>(.*?)</article>", re.S)


class _Blocks(HTMLParser):
    """Convierte el HTML de un documento en bloques ``heading``, ``paragraph`` y ``list`` con texto en Markdown (negrita y enlaces)."""

    def __init__(self, base_url):
        """Guarda la URL base para los enlaces relativos y prepara el estado del análisis."""
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.blocks = []
        self._tag = None
        self._buffer = []
        self._items = None
        self._link = None

    def handle_starttag(self, tag, attrs):
        """Abre un bloque en títulos, párrafos y elementos, y marca negritas y enlaces."""
        if tag in ("h1", "h2", "h3", "p", "li"):
            self._tag, self._buffer = tag, []
            if tag == "li" and self._items is None:
                self._items = []
        elif tag in ("ul", "ol"):
            self._items = []
        elif tag in ("strong", "b") and self._tag:
            self._buffer.append("**")
        elif tag == "a" and self._tag:
            href = dict(attrs).get("href", "")
            self._link = href if href.startswith(("mailto:", "http")) else self.base_url.rstrip("/") + href
            self._buffer.append("[")

    def handle_endtag(self, tag):
        """Cierra negritas, enlaces y bloques, y guarda el bloque terminado."""
        if tag in ("strong", "b") and self._tag:
            self._buffer.append("**")
        elif tag == "a" and self._tag and self._link is not None:
            self._buffer.append(f"]({self._link})")
            self._link = None
        elif tag in ("h1", "h2", "h3", "p") and self._tag == tag:
            text = self._text()
            if text:
                self.blocks.append({"type": "heading" if tag != "p" else "paragraph", "level": int(tag[1]) if tag != "p" else None,
                                    "text": text})
            self._tag = None
        elif tag == "li" and self._tag == "li":
            text = self._text()
            if text and self._items is not None:
                self._items.append(text)
            self._tag = None
        elif tag in ("ul", "ol") and self._items is not None:
            if self._items:
                self.blocks.append({"type": "list", "items": self._items})
            self._items = None

    def handle_data(self, data):
        """Acumula el texto mientras haya un bloque abierto."""
        if self._tag:
            self._buffer.append(data)

    def _text(self):
        """Texto del bloque con los espacios y saltos de línea del HTML reducidos a uno."""
        return re.sub(r"\s+", " ", "".join(self._buffer)).strip()


def list_documents():
    """``[{"slug", "title"}]`` de los documentos legales."""
    return [{"slug": slug, "title": title} for slug, (_template, title) in DOCUMENTS.items()]


def document(request, slug):
    """Documento ``slug`` como ``{"slug", "title", "updated", "blocks"}``, o ``None`` si no existe."""
    if slug not in DOCUMENTS:
        return None
    template, title = DOCUMENTS[slug]
    html = render_to_string(template, {
        "legal": {"owner_name": settings.LEGAL_OWNER_NAME, "owner_id": settings.LEGAL_OWNER_ID,
                  "owner_address": settings.LEGAL_OWNER_ADDRESS},
        "legal_updated": LEGAL_UPDATED, "contact_email": settings.CONTACT_EMAIL,
    }, request=request)
    match = _ARTICLE.search(html)
    parser = _Blocks(request.build_absolute_uri("/"))
    parser.feed(match.group(1) if match else html)
    blocks = parser.blocks
    # El título del documento va aparte (``title``) y la fecha de actualización también.
    if blocks and blocks[0]["type"] == "heading" and blocks[0]["level"] == 1:
        blocks = blocks[1:]
    return {"slug": slug, "title": title, "updated": LEGAL_UPDATED.isoformat(), "blocks": blocks}
