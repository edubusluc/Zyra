"""Vistas de la API v1."""
from django.http import Http404

from .responses import json_ok
from .views_base import ApiView


class PingView(ApiView):
    """``GET /api/v1/ping``: comprueba que el token sirve y cuándo caduca, y si la cuenta sigue en algún club."""

    def get(self, request):
        """
        Devuelve el identificador público del dispositivo, su caducidad y ``team`` (nombre y escudo del primer club, o None):
        la app lo usa para saber si la cuenta salió de su equipo o entró en uno desde la web.
        """
        from .views_auth import team_summary

        device = request.device_token
        return json_ok({"device": device.public_id, "expires_at": device.expires_at.isoformat(),
                        "team": team_summary(request.user)})


class NotFoundView(ApiView):
    """Cualquier otra ruta de ``/api/v1/``: 404 en JSON en lugar de la página HTML de la web."""
    public = True

    def get(self, request, *args, **kwargs):
        """Siempre 404 (la base da el formato JSON, el idioma y el límite por IP)."""
        raise Http404

    post = put = patch = delete = get
