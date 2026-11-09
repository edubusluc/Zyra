"""
Operaciones de negocio sobre clubes y cuentas que usan varias vistas: crear un club, aceptar
una invitación, dar de baja a un miembro, traspasar la capitanía y eliminar una cuenta. Cada una se ejecuta en una transacción.

Cada club es el «espacio» de una competición (``Club.competition``) y una cuenta tiene como
mucho un espacio por competición: quien ya es miembro (o capitán) de un club SNP no puede
registrar ni unirse a otro club SNP, pero sí a uno LAPI (``club_of``). Los clubes suspendidos
no cuentan, porque ya no se pueden usar.
"""
import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from players.models import Player, SnpAccount
from team.models import Team
from .blocklist import is_user_blocked
from .competitions import COMPETITIONS
from .emails import send_rejoin_email, send_removed_email
from .models import Club, Invitation, Membership

User = get_user_model()


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


class SpaceTaken(Exception):
    """La cuenta ya tiene un equipo en esa competición (un espacio por competición)."""
    pass


def ensure_space_free(user, competition):
    """
    Dentro de una transacción: bloquea la cuenta ``user`` y comprueba que no tiene equipo en
    ``competition``; si no, lanza ``SpaceTaken``. El bloqueo hace que dos envíos a la vez del
    formulario de alta (doble clic, dos pestañas) no creen dos equipos en la misma competición.
    """
    User.objects.select_for_update().get(pk=user.pk)
    if club_of(user, competition) is not None:
        raise SpaceTaken(competition)


@transaction.atomic
def create_club(name, location, admin_user, gender="", country="", division="",
                player_name="", player_last_name="", competition="snp", default_time=None):
    """
    Crea un club (el espacio de la competición ``competition``) con su equipo propio y deja a
    admin_user como capitán. Con
    ``player_name`` y ``player_last_name`` crea también el jugador del capitán en el
    equipo propio, enlazado a su cuenta. ``default_time`` es la hora habitual de juego del equipo.
    """
    club = Club.objects.create(name=name, competition=competition)
    own_team = Team.objects.create(club=club, name=name, location=location, gender=gender, country=country,
                                   division=division, is_own=True, in_group=True, default_time=default_time)
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
    if invitation.player_id and invitation.player.past_user_id not in (None, user.pk):
        # Invitación para volver: es de la cuenta que fue titular de la ficha, no de quien tenga el enlace.
        raise InvitationError(_("Esta invitación es para otra cuenta."))
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
    único miembro, abandonar el club (que se cierra y conserva tus estadísticas). Las cuentas del personal
    de Zyra no se eliminan desde la web.
    """
    if user.is_staff or user.is_superuser:
        return _("Las cuentas del personal de Zyra no se pueden eliminar desde aquí.")
    captaincies = Membership.objects.filter(user=user, role=Membership.ADMIN).select_related("club")
    for membership in captaincies:
        if is_only_member(membership):
            return _("Eres el único miembro de %(club)s. Abandona el club desde el menú (se cerrará y tus "
                     "estadísticas se conservan) y después podrás eliminar tu cuenta.") % {"club": membership.club.name}
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
    Borra para siempre el club y todo lo que cuelga de él: equipo propio y rivales, jugadores, partidos,
    convocatorias, sanciones, cuenta SNP, invitaciones y miembros. Las fotos se borran del
    almacenamiento con las señales de core.images. Las cuentas de usuario se conservan. Solo lo usa el
    personal (back-office); al abandonar el último miembro el club se archiva (``archive_club``).
    """
    club.delete()


@transaction.atomic
def archive_club(club):
    """
    Cierra el club sin perder el historial de las personas que jugaron en él. Quita lo vivo (miembros,
    invitaciones y cuenta SNP, que lleva credenciales cifradas), deja las fichas enlazadas como fichas
    anteriores de su cuenta (``past_user``, ``left_on``) y borra las fotos de las fichas sin cuenta. Se
    conservan jugadores, partidos, convocatorias y resultados. Ya no puede entrar nadie: para borrarlo del
    todo está ``delete_club`` (solo el personal, desde el back-office).
    """
    today = timezone.localdate()
    for player in Player.objects.filter(club=club, user__isnull=False):
        Player.objects.filter(pk=player.pk).update(user=None, past_user=player.user_id, left_on=player.left_on or today)
    for player in Player.objects.filter(club=club, user__isnull=True, past_user__isnull=True).exclude(photo="").exclude(photo__isnull=True):
        player.photo = None
        player.save(update_fields=["photo"])
    club.invitations.all().delete()
    SnpAccount.objects.filter(club=club).delete()
    club.memberships.all().delete()
    club.archived_at = timezone.now()
    club.save(update_fields=["archived_at"])


def leave_open_matches(player_ids):
    """
    Quita a los jugadores ``player_ids`` de lo que aún está por jugar: las convocatorias y las alineaciones
    sin resultado de los enfrentamientos abiertos (acta sin cerrar). Lo ya jugado, con resultado, y los
    enfrentamientos cerrados no se tocan: sus estadísticas se conservan. Devuelve cuántos enfrentamientos
    abiertos han cambiado.
    """
    from call.models import Call
    from match.models import Game

    player_ids = list(player_ids)
    if not player_ids:
        return 0
    touched = set()
    for call in Call.objects.filter(match__draft_mode=True, players__in=player_ids).distinct():
        call.players.remove(*player_ids)
        touched.add(call.match_id)
    for slot in Game.PLAYER_SLOTS:
        games = Game.objects.filter(match__draft_mode=True, results__isnull=True, **{f"{slot}__in": player_ids})
        touched.update(games.values_list("match_id", flat=True))
        Game.objects.filter(pk__in=list(games.values_list("pk", flat=True))).update(**{slot: None})
    return len(touched)


@transaction.atomic
def remove_membership(membership):
    """
    Saca al usuario del club (lo quita el capitán o lo abandona él) y desenlaza su cuenta
    del jugador que tuviera en ese club: si vuelve a entrar, elige de nuevo quién es.
    El jugador y sus estadísticas se conservan, y la ficha recuerda la cuenta (``past_user``) y el día de
    salida (``left_on``) para que la persona siga viendo sus estadísticas y su porcentaje de convocatorias
    no baje con las que se crean después. Salir del club es una baja de la plantilla (``in_team=False``) y
    el jugador desaparece de las convocatorias y alineaciones por jugar (``leave_open_matches``).
    """
    from players.models import Player

    today = timezone.localdate()
    sheets = Player.objects.filter(club=membership.club, user=membership.user)
    leave_open_matches(sheets.values_list("pk", flat=True))
    sheets.update(user=None, past_user=membership.user, in_team=False)
    # Una baja anterior (``left_on`` ya puesto) manda: salir del club después no vuelve a contar las convocatorias intermedias.
    Player.objects.filter(club=membership.club, past_user=membership.user, left_on__isnull=True).update(left_on=today)
    membership.delete()


def notify_removal(membership, by=None, site_url=""):
    """
    Avisa por correo al jugador de que lo han dado de baja del equipo (lo hace el capitán o un gestor; quien
    abandona él mismo no recibe nada). No sale si la cuenta no tiene email o si el capitán le bloqueó los correos
    del club. Se envía al confirmar la transacción, así una baja que se deshace no avisa de nada.
    """
    user, club = membership.user, membership.club
    if not user.email:
        return
    if Player.objects.filter(club=club, user=user, emails_muted=True).exists():
        return
    transaction.on_commit(lambda: send_removed_email(user, club, by, site_url=site_url))


class RemovalError(Exception):
    """La baja no se puede hacer; el mensaje explica el motivo al usuario."""
    pass


def removal_blocker(player, by=None):
    """
    Motivo por el que ``player`` no se puede dar de baja, o None si se puede. El capitán no se puede dar de baja
    (antes traspasa la capitanía). Si se indica quién la hace (``by``): dar de baja a una ficha con cuenta es echar
    a esa persona del equipo y solo lo hace el capitán (un gestor solo da de baja fichas sin cuenta), y nadie se
    da de baja a sí mismo por aquí (se sale con «Abandonar el club»).
    """
    if not player.user_id:
        return None
    if Membership.objects.filter(club=player.club, user_id=player.user_id, role=Membership.ADMIN).exists():
        return _("%(player)s es el capitán del equipo: traspasa antes la capitanía para darlo de baja.") % {"player": player.short_name}
    if by is not None:
        if by.pk == player.user_id:
            return _("No puedes darte de baja a ti mismo desde aquí: usa «Abandonar el club» en el menú.")
        if not Membership.objects.filter(club=player.club, user=by, role=Membership.ADMIN).exists():
            return _("Solo el capitán puede dar de baja a %(player)s: tiene una cuenta enlazada y saldría del equipo.") % {"player": player.short_name}
    return None


@transaction.atomic
def dar_de_baja(player, by=None, site_url=""):
    """
    Baja de la plantilla de ``player`` (la hace el capitán o un gestor). Dar de baja a un jugador con cuenta
    enlazada es echarlo del equipo: se le quita la membresía (``remove_membership``), así que deja de ver
    el equipo y queda libre para unirse a otro de esa competición; sus estadísticas siguen en «Mis
    estadísticas». Sea con cuenta o sin ella, desaparece de las convocatorias y alineaciones por jugar y
    la ficha queda fuera de la plantilla con el día de baja. El capitán no puede darse de baja: antes
    tiene que traspasar la capitanía (``RemovalError``). Devuelve la membresía quitada, o None si la
    ficha no tenía cuenta. Con cuenta, avisa al jugador por correo (``notify_removal``; ``by`` es quien lo da de baja).
    """
    blocker = removal_blocker(player, by)
    if blocker:
        raise RemovalError(blocker)
    membership = None
    if player.user_id:
        membership = Membership.objects.select_related("user", "club").filter(club=player.club, user_id=player.user_id).first()
    if membership is not None:
        notify_removal(membership, by, site_url)
        remove_membership(membership)
    else:
        leave_open_matches([player.pk])
    Player.objects.filter(pk=player.pk, in_team=True).update(in_team=False)
    Player.objects.filter(pk=player.pk, left_on__isnull=True).update(left_on=timezone.localdate())
    return membership


# Cuánto vale la invitación para volver al equipo (como la de una ficha copiada).
REJOIN_INVITATION_TTL = datetime.timedelta(days=30)


class AltaError(Exception):
    """El alta no se puede hacer; el mensaje explica el motivo al usuario."""
    pass


def alta_blocker(player):
    """
    Motivo por el que no se puede dar de alta a ``player`` (o None). Solo importa en una ficha que dejó una
    cuenta (``past_user``): volver al equipo exige invitar a esa cuenta por email, así que hace falta un email
    que no esté bloqueado, que no sea ya miembro del equipo y que no tenga ya otro equipo en la competición
    (un equipo por competición, comprobado por email de la cuenta).
    """
    if player.user_id or not player.past_user_id:
        return None
    account = player.past_user
    if not account.email:
        return _("La cuenta de %(player)s no tiene email: no se le puede invitar a volver.") % {"player": player.short_name}
    if is_user_blocked(account):
        return _("No se puede invitar a este email.")
    if Membership.objects.filter(club=player.club, user=account).exists():
        return _("%(player)s ya es miembro del equipo: puede enlazar su ficha anterior desde «Mi perfil».") % {"player": player.short_name}
    if club_of(account, player.club.competition) is not None:
        return _("Ese email ya tiene un equipo en %(competition)s y solo se puede tener uno por competición.") % {
            "competition": player.club.rules.name}
    return None


@transaction.atomic
def dar_de_alta(player, by=None, site_url=""):
    """
    Alta en la plantilla de ``player`` (la hace el capitán o un gestor). Una ficha sin cuenta anterior solo vuelve a
    la plantilla. Si la ficha dejó una cuenta (``past_user``), esa cuenta tiene que aceptar: se le envía una
    invitación por email ya vinculada a la ficha (``Invitation.player``) y, al aceptar, entra en el club y
    recupera su ficha y sus estadísticas (``players.copy.link_player``). No se puede si el email ya tiene equipo
    en esa competición (``AltaError``). Devuelve la invitación enviada, o None si no hacía falta.
    """
    blocker = alta_blocker(player)
    if blocker:
        raise AltaError(blocker)
    Player.objects.filter(pk=player.pk).update(in_team=True, left_on=None)
    if player.user_id or not player.past_user_id:
        return None
    Invitation.objects.filter(club=player.club, player=player, used_at__isnull=True).delete()
    invitation = Invitation.objects.create(
        club=player.club, created_by=by, email=player.past_user.email, player=player,
        expires_at=timezone.now() + REJOIN_INVITATION_TTL,
    )
    url = site_url.rstrip("/") + reverse("invitation", args=[invitation.token])
    transaction.on_commit(lambda: send_rejoin_email(invitation, url))
    return invitation
