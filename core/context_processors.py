"""
Procesadores de contexto: variables disponibles en todas las plantillas (club activo,
sección de la navegación y si el inicio de sesión con Google está activado).
"""
from django.conf import settings
from django.utils.text import get_text_list
from django.utils.translation import gettext as _

from . import seo
from .competitions import COMPETITIONS
from .spaces import linked_players, plays_only
from .services import is_last_admin, is_only_member


def club(request):
    """
    Club activo, clubes del usuario (sus espacios), sus equipos para «Tus equipos» del menú (en el
    orden de las competiciones), competiciones en las que aún no tiene equipo, si es capitán
    (``is_club_admin``) o capitán/gestor (``can_manage``) del club activo y si al abandonarlo se
    eliminaría el club (es su único miembro). Esto último y ``team_competitions`` se calculan solo
    si la plantilla los usa, igual que ``my_stats_available`` (tiene «Mis estadísticas»).
    """
    membership = getattr(request, "membership", None)
    memberships = getattr(request, "user_memberships", [])
    order = list(COMPETITIONS)
    teams = sorted(memberships, key=lambda m: order.index(m.club.competition)
                   if m.club.competition in order else len(order))
    return {
        "current_club": getattr(request, "club", None),
        "user_memberships": memberships,
        "user_teams": teams,
        "is_club_admin": bool(membership and membership.is_admin),
        # Competiciones en las que aún no tiene equipo («Añadir equipo LAPI» en el menú, una entrada por competición).
        "free_competitions": [c for code, c in COMPETITIONS.items()
                              if code not in {m.club.competition for m in memberships}],
        # «Ya tienes equipo en SNP y LAPI» cuando ya no le queda competición libre.
        "team_competitions": lambda: get_text_list([str(m.club.rules.name) for m in teams], _("y")),
        "can_manage": bool(membership and membership.can_manage),
        # Capitán o gestor en alguno de sus equipos (pestaña Advertencias de Estadísticas).
        "manages_any": any(m.can_manage for m in memberships) or bool(membership and membership.can_manage),
        # Jugador en todos sus equipos (y tiene varios): Plantilla y el listado de jugadores de
        # Estadísticas no le aportan nada y salen del menú.
        "hide_roster_nav": plays_only(request),
        # «Mis estadísticas» (y Estadísticas abre en ella) con jugador enlazado en dos o más equipos.
        "my_stats_available": lambda: len(memberships) > 1 and len(linked_players(request)) > 1,
        "leaving_deletes_club": lambda: bool(membership and is_last_admin(membership) and is_only_member(membership)),
    }


def sync_bar(request):
    """
    La sincronización con SNP en marcha del club (solo para capitanes): la barra de progreso de
    ``includes/sync_bar.html`` se ve en toda la web mientras dura. Una consulta por página de capitán.
    """
    membership = getattr(request, "membership", None)
    if not (membership and membership.is_admin):
        return {"sync_running": None}
    from players.models import SnpTeamImport
    return {"sync_running": SnpTeamImport.objects.filter(
        club=request.club, source=SnpTeamImport.WEB, status=SnpTeamImport.RUNNING).first()}


# Sección de la navegación a la que pertenece cada app
NAV_SECTIONS = {
    "players": "players",
    "team": "club",
    "match": "matches",
    "call": "matches",
    "callLog": "matches",
    "penalty": "matches",
    "data_analyse": "stats",
}


# Vistas que cuelgan de «Club» aunque vivan en otra app: miembros, invitaciones y cuenta SNP.
CLUB_URL_NAMES = {
    "club_home", "club_members", "create_invitation", "create_invitation_link", "revoke_invitation",
    "snp_account", "snp_account_delete", "complete_team_start", "complete_team_status",
    "complete_team_confirm", "complete_team_cancel", "sync_status",
}


def navigation(request):
    """Sección de la navegación que se marca como activa, según la app de la vista."""
    match = getattr(request, "resolver_match", None)
    if match and match.url_name == "home":
        return {"nav_section": "home"}
    if match and match.url_name in CLUB_URL_NAMES:
        return {"nav_section": "club"}
    app = match.func.__module__.split(".")[0] if match else ""
    return {"nav_section": NAV_SECTIONS.get(app, "")}


def google_login(request):
    """Si se muestra el botón de iniciar sesión con Google."""
    return {"google_login_enabled": settings.GOOGLE_LOGIN_ENABLED}


def site(request):
    """
    URL canónica de la página (SITE_URL o el dominio de la petición, sin parámetros salvo
    ``?lang=`` en inglés), sus versiones en cada idioma para hreflang, la ruta a la que
    vuelve el selector de idioma y el correo de contacto, para el <head> y el pie.
    """
    base = seo.site_base(request)
    alternates = seo.alternate_urls(request)
    language = seo.url_language(request)
    return {
        "site_url": base,
        "canonical_url": dict(alternates)[language] if language else base + request.path,
        "alternate_urls": alternates,
        "default_language_url": base + request.path,
        "language_next": seo.path_without_language(request),
        "contact_email": settings.CONTACT_EMAIL,
    }
