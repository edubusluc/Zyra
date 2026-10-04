"""
Operaciones de negocio sobre clubes que usan varias vistas: crear un club, aceptar
una invitación y dar de baja a un miembro. Cada una se ejecuta en una transacción.

Cada cuenta pertenece a un solo club: quien ya es miembro (o capitán) de uno no puede
registrar otro ni unirse a otro (``club_of``). Los clubes suspendidos no cuentan, porque
ya no se pueden usar.
"""
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from team.models import Team
from .blocklist import is_user_blocked
from .models import Club, Invitation, Membership


def club_of(user):
    """Club (no suspendido) al que pertenece ``user``, o None si no tiene ninguno."""
    membership = (
        Membership.objects.filter(user=user, club__suspended_at__isnull=True)
        .select_related("club").order_by("pk").first()
    )
    return membership.club if membership else None


@transaction.atomic
def create_club(name, location, admin_user, gender="", country="", division=""):
    """Crea un club con su equipo propio y deja a admin_user como capitán."""
    club = Club.objects.create(name=name)
    Team.objects.create(club=club, name=name, location=location, gender=gender, country=country,
                        division=division, is_own=True, in_group=True)
    Membership.objects.create(user=admin_user, club=club, role=Membership.ADMIN)
    return club


class InvitationError(Exception):
    """La invitación no se puede aceptar; el mensaje explica el motivo al usuario."""
    pass


@transaction.atomic
def accept_invitation(invitation, user):
    """
    Da de alta a ``user`` como miembro del club de la invitación y apunta el uso. La
    invitación se bloquea mientras tanto, así una invitación de un solo uso (las de
    email) no puede usarse dos veces aunque lleguen dos peticiones a la vez. Los enlaces
    compartidos (``reusable``) siguen valiendo para más personas.
    """
    invitation = Invitation.objects.select_for_update().select_related("club").get(pk=invitation.pk)
    if not invitation.is_valid:
        raise InvitationError(_("Esta invitación ya se ha usado o ha caducado."))
    if invitation.club.is_suspended:
        raise InvitationError(_("Este club está suspendido y no admite nuevos miembros."))
    if is_user_blocked(user):
        raise InvitationError(_("Tu email está bloqueado en Zyra y no puede unirse a clubes."))
    if Membership.objects.filter(user=user, club=invitation.club).exists():
        raise InvitationError(_("Ya eres miembro de %(club)s.") % {"club": invitation.club.name})
    current = club_of(user)
    if current is not None:
        raise InvitationError(_("Ya perteneces a %(club)s y solo se puede pertenecer a un club. "
                                "Abandona ese club antes de unirte a otro.") % {"club": current.name})
    membership = Membership.objects.create(user=user, club=invitation.club, role=Membership.MEMBER)
    invitation.used_by = user
    invitation.used_at = timezone.now()
    invitation.use_count += 1
    invitation.save(update_fields=["used_by", "used_at", "use_count"])
    return membership


def is_last_admin(membership):
    """True si ``membership`` es el único capitán de su club."""
    return membership.is_admin and not membership.club.memberships.filter(role=Membership.ADMIN).exclude(pk=membership.pk).exists()


@transaction.atomic
def remove_membership(membership):
    """
    Saca al usuario del club (lo quita el capitán o lo abandona él) y desenlaza su cuenta
    del jugador que tuviera en ese club: si vuelve a entrar, elige de nuevo quién es.
    El jugador y sus estadísticas se conservan.
    """
    from players.models import Player

    Player.objects.filter(club=membership.club, user=membership.user).update(user=None)
    membership.delete()
