"""Equipos de la cuenta para la API: qué equipos cuentan y comprobación de pertenencia y rol por token.

La web guarda el equipo activo en la sesión; la API no tiene sesión, así que cada endpoint de listado o alta recibe el equipo
(``teams/<id>/…``) y lo resuelve aquí. Las rutas de un objeto lo deducen del propio objeto y llaman a ``require_role``.
"""
from django.utils.translation import gettext as _

from core.competitions import COMPETITIONS
from core.models import Membership

from .errors import ApiError


def active_memberships(user):
    """Membresías de la cuenta: (activas, clubes suspendidos), con las activas en el orden de las competiciones.

    Mismo criterio que el middleware de la web: no cuentan los clubes suspendidos ni los archivados.
    """
    memberships = list(Membership.objects.filter(user=user).select_related("club").order_by("club__name"))
    suspended = [m.club for m in memberships if m.club.is_suspended]
    active = [m for m in memberships if not m.club.is_suspended and not m.club.is_archived]
    order = list(COMPETITIONS)
    active.sort(key=lambda m: order.index(m.club.competition) if m.club.competition in order else len(order))
    return active, suspended


def require_role(membership, *, manage=False, admin=False):
    """Lanza 403 ``forbidden`` si la membresía no tiene el rol pedido (``admin`` = capitán, ``manage`` = capitán o gestor)."""
    if admin and not membership.is_admin or manage and not membership.can_manage:
        raise ApiError("forbidden", _("No tienes permiso para hacer esto en este equipo."), 403)
    return membership


def membership_for_team(user, team_id, *, manage=False, admin=False):
    """Membresía de ``user`` en el equipo ``team_id`` (identificador público del club), comprobando el rol pedido.

    Un equipo ajeno, inexistente, suspendido o archivado responde 404 igual que uno que no existe, para no revelar su existencia.
    """
    active, _suspended = active_memberships(user)
    membership = next((m for m in active if str(m.club.public_id) == str(team_id)), None)
    if membership is None:
        raise ApiError("not_found", _("No encontrado."), 404)
    return require_role(membership, manage=manage, admin=admin)
