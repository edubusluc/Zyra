"""Temporada por defecto común a listados y estadísticas (misma regla en todas las pantallas)."""
from players.models import current_season

ALL_SEASONS = "all"
SESSION_KEY = "season_choice"


def choose_season(request, seasons, default_all=False):
    """
    Devuelve la temporada a mostrar: ``?season=`` si es válida (o ``all``), si no la última
    elegida en esta sesión y, sin ninguna, la temporada actual cuando existe en ``seasons``
    (o «all»). La elección explícita se recuerda en la sesión para el resto de pantallas.
    Con ``default_all`` y sin nada elegido devuelve «all» (buscadores).
    """
    valid = set(seasons)
    asked = request.GET.get("season")
    if asked == ALL_SEASONS or asked in valid:
        request.session[SESSION_KEY] = asked
        return asked
    if default_all:
        return ALL_SEASONS
    remembered = request.session.get(SESSION_KEY)
    if remembered == ALL_SEASONS or remembered in valid:
        return remembered
    now = current_season()
    return now if now in valid else ALL_SEASONS
