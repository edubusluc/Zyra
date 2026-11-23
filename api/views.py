"""Vistas de la API v1."""
from django.http import Http404

from .responses import json_ok
from .views_base import ApiView


class PingView(ApiView):
    """``GET /api/v1/ping``: comprueba que el token sirve y cuándo caduca, y si la cuenta sigue en algún club."""

    def get(self, request):
        """
        Devuelve el identificador público del dispositivo, su caducidad, ``team`` (nombre y escudo del primer club, o None) y
        ``has_history`` (tiene fichas actuales o de equipos anteriores: hay «Mis estadísticas» que ver). La app lo usa para
        saber si la cuenta salió de su equipo o entró en uno desde la web, y si ofrece sus estadísticas sin equipo.
        """
        from django.db.models import Q
        from players.models import Player

        from .views_auth import team_summary

        device = request.device_token
        return json_ok({"device": device.public_id, "expires_at": device.expires_at.isoformat(),
                        "team": team_summary(request.user),
                        "has_history": Player.objects.filter(Q(user=request.user) | Q(past_user=request.user)).exists()})


class NotFoundView(ApiView):
    """Cualquier otra ruta de ``/api/v1/``: 404 en JSON en lugar de la página HTML de la web."""
    public = True

    def get(self, request, *args, **kwargs):
        """Siempre 404 (la base da el formato JSON, el idioma y el límite por IP)."""
        raise Http404

    post = put = patch = delete = get


class MeView(ApiView):
    """
    ``GET /api/v1/me``: arranque de la app. Cuenta, equipos con el rol en cada uno, temporada y capacidades; es lo que una pantalla
    necesita saber de quién es el usuario sin repetirlo en cada llamada (la app lo guarda y lo refresca al volver a primer plano).
    Lleva ``ETag``: si no ha cambiado responde 304. Los datos de cada pantalla (próximos partidos, pendientes…) siguen en su endpoint.
    """
    etag = True

    def get(self, request):
        """``state`` (``ok``, ``no_team``, ``suspended``), ``user``, ``season``, ``teams`` y banderas de la cuenta."""
        from django.db.models import Q

        from players.models import Player, current_season

        from .teams import active_memberships
        from .views_home import _display_name, _team

        user = request.user
        active, suspended = active_memberships(user)
        players = Player.objects.filter(Q(user=user) | Q(past_user=user))
        teams = [{**_team(m), "can_admin": m.is_admin} for m in active]
        return json_ok({
            "state": "ok" if active else ("suspended" if suspended else "no_team"),
            "user": {"username": user.get_username(), "display_name": _display_name(user), "email": user.email},
            "season": current_season(),
            "teams": teams,
            "suspended_clubs": [{"name": club.name} for club in suspended],
            "capabilities": {"can_manage_any": any(t["can_manage"] for t in teams),
                             "can_admin_any": any(t["can_admin"] for t in teams),
                             "multi_team": len(teams) > 1},
            "has_player": players.filter(user=user, club__in=[m.club_id for m in active]).exists(),
            "has_history": players.exists(),
        })
