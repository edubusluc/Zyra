"""
Decoradores de acceso para las vistas de los clubes.

Se apoyan en request.club y request.membership, que rellena
core.middleware.CurrentClubMiddleware en cada petición.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _


def _team_reason(request, captain_only=False):
    """
    Motivo del «Sin permiso» para quien tiene equipos en varias competiciones: dice de qué equipo es la
    página y qué papel tiene en él («Esto es de Gladiadores LAPI (LAPI), donde eres jugador…»). Vacío
    con un solo equipo (se usa el texto general).
    """
    if len(getattr(request, "user_memberships", [])) < 2:
        return ""
    if captain_only:
        text = _("Esto es de %(team)s (%(competition)s), donde eres %(role)s: solo el capitán de ese equipo "
                 "puede verlo o hacerlo.")
    else:
        text = _("Esto es de %(team)s (%(competition)s), donde eres %(role)s: solo el capitán o los gestores "
                 "de ese equipo pueden verlo o hacerlo.")
    return text % {
        "team": request.club.name, "competition": request.club.rules.name,
        "role": request.membership.team_role_label.lower()}


def club_required(view_func):
    """El usuario debe haber iniciado sesión y pertenecer a algún club."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Redirige a no_club si el usuario no tiene club activo."""
        if request.club is None:
            return redirect("no_club")
        return view_func(request, *args, **kwargs)
    return wrapper


def club_admin_required(view_func):
    """
    Como club_required, pero además el usuario debe ser capitán del club activo.
    A un miembro se le muestra la página «Sin permiso» (403, core/templates/403.html).
    """
    @club_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Lanza PermissionDenied (403) si el usuario no es capitán del club activo."""
        if not request.membership.is_admin:
            raise PermissionDenied(_team_reason(request, captain_only=True) or
                                   _("Solo los capitanes del club pueden ver esta página o realizar esta acción."))
        return view_func(request, *args, **kwargs)
    return wrapper


def club_manager_required(view_func):
    """
    Como club_required, pero además el usuario debe ser capitán o gestor del club activo (lo deportivo:
    enfrentamientos, convocatorias, resultados, jugadores y equipos). Un miembro ve «Sin permiso» (403).
    Lo que solo hace el capitán (miembros, SNP, reabrir actas, eliminar) usa ``club_admin_required``.
    """
    @club_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Lanza PermissionDenied (403) si el usuario no es capitán ni gestor del club activo."""
        if not request.membership.can_manage:
            raise PermissionDenied(_team_reason(request) or
                                   _("Solo el capitán o los gestores del club pueden ver esta página o realizar esta acción."))
        return view_func(request, *args, **kwargs)
    return wrapper


def not_while_syncing(view_func):
    """
    Bloquea las altas de jugadores, equipos y enfrentamientos mientras el club está sincronizando su
    equipo con SNP (``snp_import.active_import`` en marcha): la sincronización crea jugadores y equipos y
    podría duplicar lo creado a mano. Redirige al inicio con un aviso; se navega con normalidad.
    Va debajo de ``club_admin_required`` o ``club_manager_required``.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Redirige a home con un aviso si hay una sincronización en marcha."""
        from players import snp_import
        current = snp_import.active_import(request.club)
        if current is not None and current.status == current.RUNNING:
            messages.warning(request, _("Estamos sincronizando tu equipo con SNP (%(progress)s%%). "
                                        "Podrás crear jugadores, equipos y enfrentamientos cuando termine.")
                             % {"progress": current.progress})
            return redirect("home")
        return view_func(request, *args, **kwargs)
    return wrapper
