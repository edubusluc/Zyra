"""
«Copiar jugadores» entre los equipos de una misma cuenta en competiciones distintas (SNP ↔ LAPI).

Copia la ficha (nombre, apellidos, foto, posición y mano) al otro equipo y la marca con
``Player.copied_from``; las estadísticas, los puntos SNP y las convocatorias se quedan en el
equipo de origen. Si la ficha de origen tiene cuenta, la copia no se enlaza: se crea una
invitación a ese equipo para esa ficha (``Invitation.player``), que llega por correo y se ve en
el Inicio. Al aceptarla, la cuenta entra como jugador y la ficha queda enlazada; mientras tanto ya
se puede convocar. Las fichas enlazadas a una cuenta comparten nombre, apellidos y foto
(``sync_linked_sheets``); la posición es de cada equipo.
"""
import datetime

from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from core.emails import build_email, logger as email_logger
from core.models import Invitation, Membership
from core.blocklist import is_user_blocked
from core.services import club_of
from core.similarity import same_name
from .models import Player, current_season

# Una invitación de ficha copiada dura más que la de email (24 h): el jugador puede tardar en verla.
COPY_INVITATION_TTL = datetime.timedelta(days=30)

# Estado de cada jugador en la pantalla de copiar.
ALREADY, OTHER_TEAM, MEMBER, INVITE, COPY = "already", "other_team", "member", "invite", "copy"


def managed_pairs(request):
    """
    Equipos de otra competición desde los que el usuario puede copiar al club activo: los que
    gestiona (capitán o gestor) en las demás competiciones, si también gestiona el activo.
    """
    membership = getattr(request, "membership", None)
    if not membership or not membership.can_manage:
        return []
    return [m.club for m in getattr(request, "user_memberships", [])
            if m.can_manage and m.club_id != request.club.pk and m.club.competition != request.club.competition]


def _same_person(player, others):
    """La ficha de ``others`` que es la misma persona que ``player`` (copia, cuenta o nombre), o None."""
    for other in others:
        if other.copied_from_id == player.pk or player.copied_from_id == other.pk:
            return other
        if player.user_id and other.user_id == player.user_id:
            return other
        if same_name(f"{player.name} {player.last_name}", f"{other.name} {other.last_name}"):
            return other
    return None


def candidates(source, target):
    """
    Jugadores de la plantilla de ``source`` con su estado para copiarlos a ``target``:
    ``[{"player", "status", "match"}]``. ``already``: ya tiene ficha en ``target`` (``match``);
    ``other_team``: su cuenta ya está en otro equipo de esa competición; ``member``: su cuenta ya
    está en ``target`` sin ficha y la copia se enlaza directamente; ``invite``: tiene cuenta y
    recibirá una invitación; ``copy``: sin cuenta, se copia la ficha.
    """
    existing = list(Player.objects.filter(club=target))
    rows = []
    for player in Player.objects.filter(club=source, in_team=True).select_related("user").order_by("name", "last_name"):
        match = _same_person(player, existing)
        if match is not None:
            status = ALREADY
        elif player.user_id and club_of(player.user, target.competition) not in (None, target):
            status = OTHER_TEAM
        elif player.user_id and club_of(player.user, target.competition) == target:
            status = MEMBER
        elif player.user_id:
            status = INVITE
        else:
            status = COPY
        rows.append({"player": player, "status": status, "match": match})
    return rows


def roster_size(club):
    """Jugadores en la plantilla de ``club``."""
    return Player.objects.filter(club=club, in_team=True).count()


def send_copy_invitation(invitation, url):
    """Correo de la invitación de una ficha copiada. Devuelve True si el correo salió."""
    inviter = invitation.created_by
    source = invitation.player.copied_from
    context = {
        "club": invitation.club,
        "competition": invitation.club.rules.name,
        "player": invitation.player,
        "source_club": source.club if source else None,
        "inviter": (inviter.get_full_name() or inviter.username) if inviter else "",
        "url": url,
    }
    email = build_email(
        _("Te han añadido a %(club)s en Zyra") % {"club": invitation.club.name},
        render_to_string("emails/player_copy_invitation.txt", context),
        render_to_string("emails/player_copy_invitation.html", context),
        to=[invitation.email],
        reply_to=[inviter.email] if inviter and inviter.email else None,
    )
    try:
        email.send(fail_silently=False)
    except Exception:  # SMTP caído, credenciales mal configuradas...
        email_logger.exception("No se pudo enviar la invitación de ficha copiada a %s", invitation.email)
        return False
    return True


def copy_players(source, target, ids, by_user, site_url=""):
    """
    Copia a ``target`` los jugadores de ``source`` con id en ``ids`` que se pueden copiar
    (``member``, ``invite`` o ``copy`` en ``candidates``). Devuelve ``{"copied", "invited", "skipped"}``
    (listas de fichas nuevas, las que recibirán invitación y nombres que no se copiaron).
    Los correos salen al confirmar la transacción.
    """
    wanted = {int(i) for i in ids if str(i).isdigit()}
    copied, invited, skipped = [], [], []
    with transaction.atomic():
        for row in candidates(source, target):
            player = row["player"]
            if player.pk not in wanted:
                continue
            if row["status"] not in (MEMBER, INVITE, COPY):
                skipped.append(player.full_name)
                continue
            copy = Player.objects.create(
                club=target, team=target.own_team, name=player.name, last_name=player.last_name,
                position=player.position, skillfull_hand=player.skillfull_hand, photo=player.photo.name or None,
                joined_season=current_season(), copied_from=player,
            )
            copied.append(copy)
            if row["status"] == MEMBER:
                _link(copy, player.user)
            if row["status"] == INVITE and player.user.email:
                invitation = Invitation.objects.create(
                    club=target, email=player.user.email, created_by=by_user, player=copy,
                    expires_at=timezone.now() + COPY_INVITATION_TTL,
                )
                invited.append(copy)
                url = site_url.rstrip("/") + reverse("invitation", args=[invitation.token])
                transaction.on_commit(lambda inv=invitation, u=url: send_copy_invitation(inv, u))
    return {"copied": copied, "invited": invited, "skipped": skipped}


def pending_for(user):
    """Invitaciones de fichas copiadas pendientes para ``user`` (por su email), con club y ficha."""
    if not user.is_authenticated or not user.email:
        return []
    return list(
        Invitation.objects.pending().filter(player__isnull=False, email__iexact=user.email, player__user__isnull=True)
        .exclude(club__memberships__user=user).select_related("club", "player", "created_by")
    )


def decline(invitation):
    """Rechaza la invitación de una ficha copiada: la ficha se queda sin enlazar y el capitán puede borrarla."""
    invitation.delete()


def _link(sheet, user):
    """
    Enlaza ``sheet`` a ``user`` tomando el nombre, los apellidos y la foto de su otra ficha
    enlazada (la de la cuenta manda); al guardar, ``sync_linked_sheets`` deja todas iguales.
    """
    current = Player.objects.filter(user=user).exclude(pk=sheet.pk).first()
    if current is not None:
        sheet.name, sheet.last_name, sheet.photo = current.name, current.last_name, current.photo.name or None
    sheet.user = user
    sheet.save(update_fields=["user", "name", "last_name", "photo"])


def link_player(invitation, user):
    """Tras aceptar la invitación de una ficha copiada, enlaza la ficha a ``user`` si sigue libre."""
    player = invitation.player
    if player is not None and player.user_id is None and player.club_id == invitation.club_id \
            and not Player.objects.filter(club=invitation.club, user=user).exists():
        _link(player, user)


def sync_linked_sheets(player):
    """
    Copia nombre, apellidos y foto de ``player`` a las demás fichas de su cuenta (una por equipo):
    al final es la misma persona. La posición y la mano son de cada equipo y no se tocan.
    """
    if not player.user_id:
        return 0
    from core.images import _delete_later
    others = Player.objects.filter(user_id=player.user_id).exclude(pk=player.pk)
    photo = player.photo.name or ""
    for old in others.exclude(photo=photo).exclude(photo="").exclude(photo__isnull=True).values_list("photo", flat=True):
        _delete_later(player.photo.storage, Player, "photo", old)
    return others.exclude(name=player.name, last_name=player.last_name, photo=photo).update(
        name=player.name, last_name=player.last_name, photo=photo)


def related_unlinked(user):
    """
    Fichas sin cuenta de otros equipos que son copia (o el origen) de las fichas enlazadas de
    ``user``, en competiciones en las que aún no tiene equipo: Mi perfil le propone enlazarlas.
    """
    mine = list(Player.objects.filter(user=user))
    if not mine:
        return []
    ids = [p.pk for p in mine]
    origins = [p.copied_from_id for p in mine if p.copied_from_id]
    taken = set(Membership.objects.filter(user=user).values_list("club__competition", flat=True))
    sheets = (Player.objects.filter(user__isnull=True, in_team=True)
              .filter(Q(copied_from_id__in=ids) | Q(pk__in=origins))
              .exclude(club__competition__in=taken).select_related("club", "copied_from__club"))
    return [s for s in sheets if not s.club.is_suspended]


class LinkError(Exception):
    """La ficha no se puede enlazar; el mensaje explica el motivo."""


@transaction.atomic
def join_and_link(user, sheet):
    """
    Desde Mi perfil: ``user`` entra como jugador en el equipo de ``sheet`` (una copia de su ficha
    hecha antes de tener cuenta) y la ficha queda enlazada a su cuenta.
    """
    sheet = Player.objects.select_for_update().select_related("club").get(pk=sheet.pk)
    if sheet not in related_unlinked(user):
        raise LinkError(_("Esa ficha ya no se puede enlazar a tu cuenta."))
    if is_user_blocked(user):
        raise LinkError(_("Tu email está bloqueado en Zyra y no puede unirse a clubes."))
    Membership.objects.create(user=user, club=sheet.club, role=Membership.MEMBER)
    _link(sheet, user)
    return sheet


def not_mine(user, sheet):
    """«No es mía» en Mi perfil: la ficha deja de considerarse copia de la suya."""
    if sheet in related_unlinked(user):
        if sheet.copied_from_id and sheet.copied_from.user_id == user.pk:
            Player.objects.filter(pk=sheet.pk).update(copied_from=None)
        else:
            Player.objects.filter(user=user, copied_from=sheet).update(copied_from=None)
