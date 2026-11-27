"""Legal en la API: ``GET /legal`` y ``GET /legal/<slug>`` con los textos de la web para leerlos dentro de la app."""
from django.utils.translation import gettext as _

from . import legal
from .errors import ApiError
from .responses import json_ok
from .views_base import ApiView


class LegalListView(ApiView):
    """``GET /api/v1/legal``: los documentos legales."""

    def get(self, request):
        """``{"documents": [{"slug", "title"}]}``: ``privacy``, ``terms`` y ``cookies``."""
        return json_ok({"documents": legal.list_documents()})


class LegalDocumentView(ApiView):
    """``GET /api/v1/legal/<slug>``: un documento legal en bloques."""

    def get(self, request, slug):
        """``slug``, ``title``, ``updated`` (fecha ISO) y ``blocks``: ``heading`` (``level``, ``text``), ``paragraph`` (``text``)
        y ``list`` (``items``), con negrita y enlaces en Markdown. Siempre en español, que es el texto con validez legal. 404 si no existe."""
        data = legal.document(request, slug)
        if data is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        return json_ok(data)
