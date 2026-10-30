"""
Operaciones de negocio sobre clubes y cuentas que usan varias vistas: crear un club, aceptar
una invitación, dar de baja a un miembro, traspasar la capitanía y eliminar una cuenta. Cada una se ejecuta en una transacción.

Cada club es el «espacio» de una competición (``Club.competition``) y una cuenta tiene como
mucho un espacio por competición: quien ya es miembro (o capitán) de un club SNP no puede
registrar ni unirse a otro club SNP, pero sí a uno LAPI (``club_of``). Los clubes suspendidos
no cuentan, porque ya no se pueden usar.
"""
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from players.models import Player, SnpAccount
from team.models import Team
from .blocklist import is_user_blocked
from .competitions import COMPETITIONS
from .models import Club, Invitation, Membership


def club_of(user, competition=None):
    """Club (no suspendido) al que pertenece ``user`` en la competición ``competition`` (código),
    o en cualquiera si no se indica; None si no tiene ninguno."""
    memberships = Membership.objects.filter(user=user, club__suspended_at__isnull=True)
    if competition is not None:
        memberships = memberships.filter(club__competition=competition)
    membership = memberships.select_related("club").order_by("pk").first()
    return membership.club if membership else None


def free_competitions(user):
    """Competiciones (fichas) en las que ``user`` aún no tiene espacio, en el orden del registro."""
    taken = set(Membership.objects.filter(user=user, club__suspended_at__isnull=True)
                .values_list("club__competition", flat=True)) if user.is_authenticated else set()
    return [c for c in COMPETITIONS.values() if c.code not in taken]


def one_space_message(club):
    """Aviso de que ya tiene el espacio ``club`` en su competición y no puede tener otro."""
    return _("Ya tienes el equipo %(club)s en %(competition)s y solo se puede tener un equipo por "
             "competición. Abandónalo antes de unirte o crear otro de %(competition)s.") % {
        "club": club.name, "competition": club.rules.name}


@transaction.atomic
def create_club(name, location, admin_user, gender="", country="", division="",
                player_name="", player_last_name="", competition="snp"):
    """
    Crea un club (el espacio de la competición ``competition``) con su equipo propio y deja a
    admin_user como capitán. Con
    ``player_name`` y ``player_last_name`` crea también el jugador del capitán en el
    equipo propio, enlazado a su cuenta.
    """
    club = Club.objects.create(name=name, competition=competition)
    own_team = Team.objects.create(club=club, name=name, location=location, gender=gender, country=country,
                                   division=division, is_own=True, in_group=True)
    Membership.objects.create(user=admin_user, club=club, role=Membership.ADMIN)
    if player_name and player_last_name:
        Player.objects.create(club=club, team=own_team, name=player_name, last_name=player_last_name,
                              user=admin_user)
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
    compartidos (``reusable``) siguen valiendo para más personas. Si es la invitación de una
    ficha copiada (``Invitation.player``), enlaza esa ficha a la cuenta.
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
    current = club_of(user, invitation.club.competition)
    if current is not None:
        raise InvitationError(one_space_message(current))
    membership = Membership.objects.create(user=user, club=invitation.club, role=Membership.MEMBER)
    invitation.used_by = user
    invitation.used_at = timezone.now()
    invitation.use_count += 1
    invitation.save(update_fields=["used_by", "used_at", "use_count"])
    if invitation.player_id:
        # Invitación de una ficha copiada de otro equipo: la cuenta queda enlazada a esa ficha.
        from players.copy import link_player
        link_player(invitation, user)
    return membership


def is_last_admin(membership):
    """True si ``membership`` es el capitán de su club (cada club tiene uno solo, así que es «el último»)."""
    return membership.is_admin and not membership.club.memberships.filter(role=Membership.ADMIN).exclude(pk=membership.pk).exists()


def eligible_successors(club, exclude_user=None):
    """
    Miembros a los que se puede traspasar la capitanía: los que no son capitán y tienen su
    cuenta enlazada a un jugador del club. Ordenados por nombre de usuario.
    """
    linked = Player.objects.filter(club=club, user__isnull=False).values("user_id")
    members = club.memberships.filter(user_id__in=linked).exclude(role=Membership.ADMIN)
    if exclude_user is not None:
        members = members.exclude(user=exclude_user)
    return members.select_related("user").order_by("user__username")


class CaptaincyError(Exception):
    """La capitanía no se puede traspasar; el mensaje explica el motivo al usuario."""
    pass


@transaction.atomic
def transfer_captaincy(club, current, target):
    """
    Traspasa la capitanía de ``club`` de la membresía ``current`` a ``target``: el nuevo
    capitán pasa a serlo y el anterior queda como miembro. El nuevo capitán tiene que ser otro
    miembro con su cuenta enlazada a un jugador del club. Un club tiene un solo capitán.
    """
    current = Membership.objects.select_for_update().get(pk=current.pk)
    if current.club_id != club.pk or not current.is_admin:
        raise CaptaincyError(_("Solo el capitán del club puede traspasar la capitanía."))
    if target.club_id != club.pk or target.pk == current.pk:
        raise CaptaincyError(_("Elige a otro miembro del club."))
    if not eligible_successors(club).filter(pk=target.pk).exists():
        raise CaptaincyError(_("Solo se puede traspasar la capitanía a un miembro enlazado a un jugador del club."))
    current.role = Membership.MEMBER
    current.save(update_fields=["role"])
    target.role = Membership.ADMIN
    target.save(update_fields=["role"])
    # Las credenciales SNP eran del capitán saliente: se borran y el nuevo capitán ve de nuevo
    # «Primeros pasos» con la tarea de registrar las suyas.
    SnpAccount.objects.filter(club=club).delete()
    if club.onboarding_dismissed_at is not None:
        club.onboarding_dismissed_at = None
        club.save(update_fields=["onboarding_dismissed_at"])
    return target


class ManagerError(Exception):
    """El rol de gestor no se puede cambiar; el mensaje explica el motivo al usuario."""
    pass


@transaction.atomic
def set_manager(club, current, target, enable):
    """
    Hace gestor a ``target`` (``enable=True``) o lo devuelve a miembro (``enable=False``). Solo lo hace
    el capitán ``current`` y solo sobre miembros del mismo club que no sean el capitán; un club tiene
    como mucho ``Membership.MAX_MANAGERS`` gestores.
    """
    current = Membership.objects.select_for_update().get(pk=current.pk)
    if current.club_id != club.pk or not current.is_admin:
        raise ManagerError(_("Solo el capitán del club puede nombrar gestores."))
    if target.club_id != club.pk or target.is_admin:
        raise ManagerError(_("Elige a otro miembro del club."))
    if enable and not target.is_manager:
        if club.memberships.filter(role=Membership.MANAGER).count() >= Membership.MAX_MANAGERS:
            raise ManagerError(_("Un equipo puede tener como máximo %(n)s gestores.") % {"n": Membership.MAX_MANAGERS})
        target.role = Membership.MANAGER
        target.manager_welcome_pending = True
    elif not enable and target.is_manager:
        target.role = Membership.MEMBER
        target.manager_welcome_pending = False
    target.save(update_fields=["role", "manager_welcome_pending"])
    return target


def account_delete_blocker(user):
    """
    Motivo (texto para el usuario) por el que ``user`` aún no puede eliminar su cuenta, o None si
    puede. Un capitán tiene que traspasar antes la capitanía a otro jugador enlazado; si es el
    único miembro, abandonar el club (que se elimina con sus datos). Las cuentas del personal
    de Zyra no se eliminan desde la web.
    """
    if user.is_staff or user.is_superuser:
        return _("Las cuentas del personal de Zyra no se pueden eliminar desde aquí.")
    captaincies = Membership.objects.filter(user=user, role=Membership.ADMIN).select_related("club")
    for membership in captaincies:
        if is_only_member(membership):
            return _("Eres el único miembro de %(club)s. Abandona el club desde el menú (se eliminará con todos "
                     "sus datos) y después podrás eliminar tu cuenta.") % {"club": membership.club.name}
        return _("Eres el capitán de %(club)s. Traspasa antes la capitanía a otro jugador enlazado desde "
                 "«Miembros»; si quieres cerrar el club, quita antes a todos los miembros.") % {"club": membership.club.name}
    return None


@transaction.atomic
def delete_account(user, delete_player=False):
    """
    Elimina la cuenta de ``user`` y sus datos personales: membresías, preferencias, correos
    verificados, cuenta de Google e historial de envíos mensuales. Su ficha de jugador pierde el
    enlace y la foto y se conserva en el club (los partidos y las estadísticas son del club); con
    ``delete_player`` se elimina también (los partidos jugados se conservan con su nombre).
    Lanza ``CaptaincyError`` si todavía es capitán.
    """
    blocker = account_delete_blocker(user)
    if blocker:
        raise CaptaincyError(blocker)
    for player in Player.objects.filter(user=user):
        if delete_player:
            player.delete()
        else:
            player.user = None
            player.photo = None
            player.save()
    user.delete()


def is_only_member(membership):
    """True si ``membership`` es el único miembro (de cualquier rol) de su club."""
    return not membership.club.memberships.exclude(pk=membership.pk).exists()


def club_name_matches(club, typed):
    """True si ``typed`` es el nombre del club, sin distinguir mayúsculas ni espacios de los extremos."""
    return (typed or "").strip().casefold() == club.name.strip().casefold()


@transaction.atomic
def delete_club(club):
    """
    Borra el club y todo lo que cuelga de él: equipo propio y rivales, jugadores, partidos,
    convocatorias, sanciones, cuenta SNP, invitaciones y miembros. Las fotos se borran del
    almacenamiento con las señales de core.images. Las cuentas de usuario se conservan.
    """
    club.delete()


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
