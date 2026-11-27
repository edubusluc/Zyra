"""Equipo en la API: miembros, roles, invitaciones y abandonar el equipo (lo que hace la web en «Miembros»)."""
import datetime

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from core.emails import send_invitation_email
from core.forms import InviteMemberForm
from core.models import Club, Invitation, Membership
from core.services import (CaptaincyError, ManagerError, archive_club, club_name_matches, eligible_successors, is_last_admin,
                           is_only_member, notify_removal, remove_membership, set_manager, transfer_captaincy)

from .errors import ApiError
from .fields import invalid
from .responses import json_ok
from .teams import membership_for_team
from .views_base import ApiView

# Mismo margen que la web contra el doble toque: la misma invitación no se repite dentro de este plazo.
DOUBLE_SUBMIT_WINDOW = datetime.timedelta(seconds=30)
ROLE_NAMES = {Membership.ADMIN: "captain", Membership.MANAGER: "manager"}


def _invitation_url(request, invitation):
    """Enlace de una invitación (el mismo que se envía por correo)."""
    return request.build_absolute_uri(reverse("invitation", args=[invitation.token]))


def _invitation(request, invitation, club):
    """Una invitación pendiente: ``email`` (nulo en el enlace compartido), ``url``, ``share_text`` y caducidad."""
    url = _invitation_url(request, invitation)
    return {
        "id": str(invitation.public_id), "email": invitation.email or None, "reusable": invitation.reusable, "url": url,
        "share_text": _("Únete a %(club)s en Zyra: %(url)s") % {"club": club.name, "url": url},
        "expires_at": invitation.expires_at.isoformat(),
    }


def _member(membership, me, successors, managers_full, *, admin):
    """Un miembro. El capitán ve además su email y qué puede hacer con él; el resto, solo usuario y rol."""
    data = {"id": str(membership.public_id), "username": membership.user.username,
            "role": ROLE_NAMES.get(membership.role, "member"), "is_me": membership.pk == me.pk}
    if admin:
        data["email"] = membership.user.email or None
        data["can_make_manager"] = not membership.is_admin and not membership.is_manager and not managers_full
        data["can_remove_manager"] = membership.is_manager
        data["can_transfer"] = membership.pk in successors
        data["can_remove"] = not membership.is_admin
    return data


def _admin_member(user, team_id, member_id):
    """Membresía de ``member_id`` en el equipo ``team_id`` y la del capitán; 403 si no es capitán y 404 si el miembro no es del equipo."""
    current = membership_for_team(user, team_id, admin=True)
    target = Membership.objects.select_related("user").filter(public_id=member_id, club=current.club).first()
    if target is None:
        raise ApiError("not_found", _("No encontrado."), 404)
    return current, target


class MembersView(ApiView):
    """``GET /api/v1/teams/<id>/members``: miembros del equipo, con roles e invitaciones pendientes para el capitán."""

    def get(self, request, team_id):
        """
        ``team`` (``id``, ``name``, ``competition``, ``competition_name``), ``role`` (el de quien pregunta), ``is_captain``,
        ``members`` y, solo para el capitán, ``managers_full`` (ya hay dos gestores), ``invitations`` (pendientes, con ``url`` y
        ``share_text``) y ``link`` (el enlace compartido vigente o ``null``). El capitán ve el email de cada miembro y qué
        acciones se pueden hacer (``can_make_manager``, ``can_remove_manager``, ``can_transfer``, ``can_remove``).
        """
        me = membership_for_team(request.user, team_id)
        club = me.club
        members = list(club.memberships.select_related("user").order_by("user__username"))
        admin = me.is_admin
        managers = sum(m.is_manager for m in members)
        successors = set(eligible_successors(club).values_list("pk", flat=True)) if admin else set()
        data = {
            "team": {"id": str(club.public_id), "name": club.name, "competition": club.competition,
                     "competition_name": club.rules.name},
            "role": ROLE_NAMES.get(me.role, "member"), "is_captain": admin,
            "members": [_member(m, me, successors, managers >= Membership.MAX_MANAGERS, admin=admin) for m in members],
        }
        if admin:
            pending = list(club.invitations.pending().order_by("-created_at", "-id"))
            link = next((i for i in pending if i.reusable), None)
            data.update({
                "managers_full": managers >= Membership.MAX_MANAGERS,
                "invitations": [_invitation(request, i, club) for i in pending if not i.reusable and i.player_id is None],
                "link": _invitation(request, link, club) if link else None,
            })
        return json_ok(data)


class InvitationsView(ApiView):
    """``POST /api/v1/teams/<id>/invitations``: invita a un jugador por email (capitán)."""

    def post(self, request, team_id):
        """
        Cuerpo ``{"email"}``. 400 ``validation_error`` si el email no vale (ya es miembro, bloqueado o con equipo en la
        competición); 502 ``email_failed`` si no pudo salir el correo. Volver a invitar al mismo email sustituye la invitación
        pendiente. Devuelve la invitación (201).
        """
        club = membership_for_team(request.user, team_id, admin=True).club
        form = InviteMemberForm({"email": self.json_body(request).get("email", "")}, club=club)
        if not form.is_valid():
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400,
                           extra={"fields": {"email": [str(e) for e in form.errors.get("email", [])]}})
        email = form.cleaned_data["email"]
        with transaction.atomic():
            Club.objects.select_for_update().get(pk=club.pk)
            recent = timezone.now() - DOUBLE_SUBMIT_WINDOW
            repeated = club.invitations.filter(email__iexact=email, used_at__isnull=True, player__isnull=True,
                                               created_at__gte=recent).first()
            if repeated is not None:
                return json_ok({"invitation": _invitation(request, repeated, club)}, status=200)
            club.invitations.filter(email__iexact=email, used_at__isnull=True, player__isnull=True).delete()
            invitation = Invitation.objects.create(club=club, created_by=request.user, email=email)
        if not send_invitation_email(invitation, _invitation_url(request, invitation)):
            invitation.delete()
            raise ApiError("email_failed", _("No se pudo enviar el correo a %(email)s. Inténtalo de nuevo más tarde.")
                           % {"email": email}, 502)
        return json_ok({"invitation": _invitation(request, invitation, club)}, status=201)


class InvitationLinkView(ApiView):
    """``POST /api/v1/teams/<id>/invitations/link``: genera el enlace compartido (capitán); el anterior deja de valer."""

    def post(self, request, team_id):
        """Devuelve ``{"invitation", "replaced"}`` (201); ``replaced`` avisa de que había otro enlace vigente que ya no funciona."""
        club = membership_for_team(request.user, team_id, admin=True).club
        with transaction.atomic():
            Club.objects.select_for_update().get(pk=club.pk)
            recent = timezone.now() - DOUBLE_SUBMIT_WINDOW
            repeated = club.invitations.pending().filter(reusable=True, created_at__gte=recent).first()
            if repeated is not None:
                return json_ok({"invitation": _invitation(request, repeated, club), "replaced": False})
            replaced = club.invitations.pending().filter(reusable=True).update(expires_at=timezone.now())
            invitation = Invitation.objects.create(club=club, created_by=request.user, reusable=True)
        return json_ok({"invitation": _invitation(request, invitation, club), "replaced": bool(replaced)}, status=201)


class RevokeInvitationView(ApiView):
    """``POST /api/v1/teams/<id>/invitations/<invitation_id>/revoke``: anula una invitación pendiente (capitán)."""

    def post(self, request, team_id, invitation_id):
        """404 si no está pendiente. Devuelve ``{"revoked": true}``."""
        club = membership_for_team(request.user, team_id, admin=True).club
        invitation = club.invitations.pending().filter(public_id=invitation_id).first()
        if invitation is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        invitation.delete()
        return json_ok({"revoked": True})


class MemberManagerView(ApiView):
    """``POST /api/v1/teams/<id>/members/<member_id>/manager``: hace gestor a un miembro o le quita el rol (capitán)."""

    def post(self, request, team_id, member_id):
        """Cuerpo ``{"enable": bool}``. 409 ``cannot_change`` con el motivo de la web (por ejemplo, ya hay dos gestores)."""
        enable = self.json_body(request).get("enable")
        if not isinstance(enable, bool):
            raise invalid("enable")
        current, target = _admin_member(request.user, team_id, member_id)
        try:
            set_manager(current.club, current, target, enable)
        except ManagerError as exc:
            raise ApiError("cannot_change", str(exc), 409)
        return json_ok({"role": "manager" if enable else "member"})


class MemberTransferView(ApiView):
    """``POST /api/v1/teams/<id>/members/<member_id>/transfer``: traspasa la capitanía a ese miembro (capitán)."""

    def post(self, request, team_id, member_id):
        """409 ``cannot_transfer`` con el motivo de la web. El anterior capitán queda como miembro."""
        current, target = _admin_member(request.user, team_id, member_id)
        try:
            transfer_captaincy(current.club, current, target)
        except CaptaincyError as exc:
            raise ApiError("cannot_transfer", str(exc), 409)
        return json_ok({"transferred": True})


class MemberRemoveView(ApiView):
    """``POST /api/v1/teams/<id>/members/<member_id>/remove``: da de baja a un miembro del equipo (capitán)."""

    def post(self, request, team_id, member_id):
        """409 ``cannot_remove`` si es el capitán o uno mismo (se abandona con ``/leave``). Se avisa por correo a la persona."""
        current, target = _admin_member(request.user, team_id, member_id)
        if target.is_admin or target.pk == current.pk:
            raise ApiError("cannot_remove", _("No puedes quitar al capitán: traspasa antes la capitanía."), 409)
        with transaction.atomic():
            notify_removal(target, request.user, request.build_absolute_uri("/").rstrip("/"))
            remove_membership(target)
        return json_ok({"removed": True})


class LeaveTeamView(ApiView):
    """``POST /api/v1/teams/<id>/leave``: la persona abandona el equipo."""

    def post(self, request, team_id):
        """
        El capitán con más miembros no puede irse (409 ``cannot_leave``: traspasa antes). Si es el único miembro, el equipo se
        cierra y hay que escribir su nombre en ``confirm_name`` (409 ``confirm_name`` si no coincide). Devuelve
        ``{"left": true, "closed": bool}``.
        """
        membership = membership_for_team(request.user, team_id)
        club = membership.club
        if is_last_admin(membership) and is_only_member(membership):
            if not club_name_matches(club, self.json_body(request).get("confirm_name")):
                raise ApiError("confirm_name", _("Para eliminar el equipo escribe su nombre exactamente: %(club)s.")
                               % {"club": club.name}, 409)
            archive_club(club)
            return json_ok({"left": True, "closed": True})
        if is_last_admin(membership):
            raise ApiError("cannot_leave", _("Eres el capitán de %(club)s: traspasa la capitanía a otro jugador enlazado antes de "
                                             "abandonar el club. Para eliminar el club, quita antes a todos los miembros.")
                           % {"club": club.name}, 409)
        remove_membership(membership)
        return json_ok({"left": True, "closed": False})
