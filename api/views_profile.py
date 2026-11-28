"""Vistas de ``/api/v1/me/...`` del perfil: cuenta, preferencias, contraseña, sesiones y traspaso de capitanía."""
import base64
import binascii

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils.translation import gettext as _, ngettext

from core import email_verification, ratelimit, sessions
from core.data_export import EXPORT_LIMIT, EXPORT_WINDOW, export_user_data
from core.forms import EmailChangeForm
from core.models import REPORT_SCOPES, Membership, UserPreference
from core.services import CaptaincyError, eligible_successors, transfer_captaincy
from core.views import email_needs_confirmation
from players.forms import OwnPlayerForm
from players.models import Player

from . import tokens
from .errors import ApiError
from .fields import invalid, text_field
from .responses import json_ok
from .teams import active_memberships
from .views_base import ApiView
from .views_home import _team

MAX_PASSWORD_LENGTH = 128
MAX_PHOTO_LENGTH = 3_000_000  # caracteres en base64 (unos 2,2 MB de imagen)
SCOPES = [code for code, _label in REPORT_SCOPES]


def _preferences(user, is_captain):
    """Preferencias de la cuenta como las ve «Mi perfil»; ``report_scope`` solo lo ve y cambia el capitán."""
    monthly, monthly_scope = UserPreference.monthly_for(user)
    prefs = {
        "match_result_email": UserPreference.match_result_for(user),
        "news_email": user.pk not in UserPreference.news_opted_out(),
        "monthly_report": monthly,
        "monthly_scope": monthly_scope,
        "match_stage_view": UserPreference.match_stage_for(user),
    }
    if is_captain:
        prefs["report_scope"] = UserPreference.report_scope_for(user)
    return prefs


def _sheets(user, memberships):
    """Una ficha por equipo de la cuenta: el jugador enlazado (o ``None``) en cada uno."""
    players = {p.club_id: p for p in Player.objects.filter(club__in=[m.club for m in memberships], user=user)}
    out = []
    for m in memberships:
        player = players.get(m.club_id)
        out.append({"team": _team(m),
                    "player": {"id": str(player.public_id), "name": player.full_name,
                               "photo": player.photo.url if player.photo else None,
                               "position": player.position, "hand": player.skillfull_hand} if player else None})
    return out


def _captaincies(memberships):
    """Equipos que capitanea la cuenta, con los miembros a quienes se puede traspasar la capitanía."""
    return [{"team": str(m.club.public_id), "name": m.club.name,
             "successors": [{"id": s.pk, "name": s.user.get_full_name() or s.user.get_username()}
                            for s in eligible_successors(m.club)]}
            for m in memberships if m.is_admin]


class ProfileView(ApiView):
    """``GET /api/v1/me/profile``: todo lo que enseña «Mi perfil» en una sola llamada."""

    def get(self, request):
        """
        ``account`` (usuario, email, ``email_verified``, ``has_password``, ``uses_google``), ``sheets`` (jugador enlazado por
        equipo), ``preferences`` y ``captaincies`` (equipos que capitanea, con los posibles sucesores).
        """
        user = request.user
        active, _suspended = active_memberships(user)
        is_captain = any(m.is_admin for m in active)
        return json_ok({
            "account": {"username": user.get_username(), "email": user.email,
                         "email_verified": not email_needs_confirmation(user), "has_password": user.has_usable_password(),
                         "uses_google": SocialAccount.objects.filter(user=user, provider="google").exists()},
            "sheets": _sheets(user, active),
            "preferences": _preferences(user, is_captain),
            "captaincies": _captaincies(active),
        })


class PreferencesView(ApiView):
    """``PATCH /api/v1/me/preferences``: cambia las preferencias de la cuenta."""

    def patch(self, request):
        """
        Cuerpo con cualquiera de ``match_result_email``, ``news_email``, ``monthly_report``, ``match_stage_view`` (booleanos),
        ``monthly_scope`` y ``report_scope`` (``todos`` o ``competitivos``; este último solo el capitán, si no se ignora).
        Devuelve las preferencias resultantes.
        """
        body = self.json_body(request)
        active, _suspended = active_memberships(request.user)
        is_captain = any(m.is_admin for m in active)
        values = {}
        for name in ("match_result_email", "news_email", "monthly_report", "match_stage_view"):
            if name in body:
                if not isinstance(body[name], bool):
                    raise invalid(name)
                values[name] = body[name]
        for name in ("monthly_scope", "report_scope"):
            if name in body:
                if body[name] not in SCOPES:
                    raise invalid(name)
                if name != "report_scope" or is_captain:
                    values[name] = body[name]
        if values:
            UserPreference.objects.update_or_create(user=request.user, defaults=values)
        return json_ok({"preferences": _preferences(request.user, is_captain)})


class EmailChangeView(ApiView):
    """``POST /api/v1/me/email``: cambia el email de la cuenta (pide la contraseña actual) y envía el enlace de confirmación."""

    def post(self, request):
        """
        Cuerpo ``{"email", "current_password"}`` con las reglas de ``EmailChangeForm``. 409 ``no_password`` en las cuentas
        sin contraseña (Google gestiona su email); 400 ``validation_error`` con ``fields``; 429 tras 5 intentos por hora.
        """
        user = request.user
        if not user.has_usable_password():
            raise ApiError("no_password", _("Tu cuenta entra con Google: el email lo gestiona Google."), 409)
        if ratelimit.too_many_user(request, "email-change", 5, 60 * 60):
            raise ApiError("rate_limited", _("Demasiadas peticiones. Espera un momento."), 429)
        body = self.json_body(request)
        form = EmailChangeForm({"email": text_field(body, "email"),
                                "current_password": text_field(body, "current_password", max_length=MAX_PASSWORD_LENGTH)}, user=user)
        if not form.is_valid():
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400,
                           extra={"fields": {f: [str(e) for e in errs] for f, errs in form.errors.items()}})
        user.email = form.cleaned_data["email"]
        user.save(update_fields=["email"])
        from allauth.account.models import EmailAddress
        EmailAddress.objects.filter(user=user).exclude(email__iexact=user.email).delete()
        email_verification.start_verification(request, user)
        return json_ok({"email": user.email, "email_verified": False})


class PasswordView(ApiView):
    """``POST /api/v1/me/password``: cambia o añade la contraseña y cierra el resto de sesiones."""

    def post(self, request):
        """
        Cuerpo ``{"new_password", "current_password"?}``; la actual es obligatoria si ya hay contraseña (403
        ``wrong_password`` si no coincide) y se valida la nueva con las reglas de Django (400 ``weak_password``).
        Revoca los demás dispositivos y las sesiones de la web, pero deja este: la app sigue con su token.
        """
        user = request.user
        new = text_field(self.json_body(request), "new_password", max_length=MAX_PASSWORD_LENGTH)
        if user.has_usable_password():
            if ratelimit.too_many_user(request, "password-change", 5, 60 * 60):
                raise ApiError("rate_limited", _("Demasiadas peticiones. Espera un momento."), 429)
            current = text_field(self.json_body(request), "current_password", max_length=MAX_PASSWORD_LENGTH)
            if not user.check_password(current):
                raise ApiError("wrong_password", _("La contraseña actual no es correcta."), 403)
        try:
            password_validation.validate_password(new, user)
        except ValidationError as exc:
            raise ApiError("weak_password", " ".join(exc.messages), 400)
        with transaction.atomic():
            user.set_password(new)
            user.save(update_fields=["password"])
        _close_other_sessions(user, request.device_token)
        return json_ok({"changed": True})


def _close_other_sessions(user, keep_device):
    """Cierra las sesiones de la web y revoca los demás dispositivos de la app; devuelve cuántos cerró en total."""
    closed = sessions.end_other_sessions(user, None)
    for device in list(tokens.DeviceToken.objects.active().filter(user=user).exclude(pk=keep_device.pk)):
        tokens.revoke_token(device)
        closed += 1
    return closed


class RevokeOthersView(ApiView):
    """``POST /api/v1/me/sessions/revoke-others``: cierra la sesión en los demás dispositivos."""

    def post(self, request):
        """Devuelve ``{"closed": n}``: sesiones web y dispositivos de la app cerrados (no este)."""
        return json_ok({"closed": _close_other_sessions(request.user, request.device_token)})


class TransferCaptaincyView(ApiView):
    """``POST /api/v1/teams/<id>/transfer-captaincy``: traspasa la capitanía a otro miembro."""

    def post(self, request, team_id):
        """
        Cuerpo ``{"member"}`` con el ``id`` de ``captaincies[].successors``. Solo el capitán (404 si no lo es de ese
        equipo); 409 ``cannot_transfer`` con el motivo de la web. El anterior capitán queda como miembro.
        """
        member = self.json_body(request).get("member")
        if not isinstance(member, int) or isinstance(member, bool):
            raise invalid("member")
        active, _suspended = active_memberships(request.user)
        current = next((m for m in active if m.is_admin and str(m.club.public_id) == team_id), None)
        if current is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        target = Membership.objects.filter(pk=member, club=current.club).first()
        if target is None:
            raise ApiError("cannot_transfer", _("Elige a otro miembro del club."), 409)
        try:
            with transaction.atomic():
                transfer_captaincy(current.club, current, target)
        except CaptaincyError as exc:
            raise ApiError("cannot_transfer", str(exc), 409)
        return json_ok({"transferred": True})


class OwnPlayerView(ApiView):
    """``PATCH /api/v1/teams/<id>/me/player``: la persona edita su propia ficha (posición, mano hábil y foto)."""

    def patch(self, request, team_id):
        """
        Cuerpo con cualquiera de ``position`` (``Derecha``, ``Revés``, ``Mixto`` o ``NONE``), ``hand`` (``Diestro``,
        ``Zurdo`` o ``NONE``), ``photo`` (imagen en base64) y ``remove_photo`` (booleano). Usa ``OwnPlayerForm`` de la web, así
        que la foto se reduce, se pasa a WebP y se modera igual. 404 si la cuenta no tiene ficha enlazada en ese equipo; 400
        ``validation_error`` con ``fields``. Devuelve la ficha como en ``GET /me/profile`` (``sheets[].player``).
        """
        body = self.json_body(request)
        active, _suspended = active_memberships(request.user)
        membership = next((m for m in active if str(m.club.public_id) == team_id), None)
        player = Player.objects.filter(club=membership.club, user=request.user).first() if membership else None
        if player is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        remove = body.get("remove_photo", False)
        if not isinstance(remove, bool):
            raise invalid("remove_photo")
        data = {"position": body.get("position", player.position), "skillfull_hand": body.get("hand", player.skillfull_hand)}
        files = {}
        photo = decode_photo(body.get("photo"))
        if photo is not None:
            files["photo"] = photo
        form = OwnPlayerForm(data, files, instance=player)
        form.uploader = request.user
        if not form.is_valid():
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400,
                           extra={"fields": {("hand" if f == "skillfull_hand" else f): [str(e) for e in errs]
                                             for f, errs in form.errors.items()}})
        form.save()
        if remove and not files:
            player.photo = None
            player.save(update_fields=["photo"])
        return json_ok({"player": _sheets(request.user, [membership])[0]["player"]})


def _photo_error(message):
    """400 ``validation_error`` con el mensaje en el campo ``photo``."""
    return ApiError("validation_error", _("Revisa los datos del formulario."), 400, extra={"fields": {"photo": [message]}})


def decode_photo(raw):
    """Foto en base64 del cuerpo como fichero subido, o ``None`` si no viene. 400 ``validation_error`` si no es una imagen válida."""
    if raw in (None, ""):
        return None
    if not isinstance(raw, str) or len(raw) > MAX_PHOTO_LENGTH:
        raise _photo_error(_("La foto es demasiado grande."))
    try:
        return SimpleUploadedFile("photo.jpg", base64.b64decode(raw, validate=True), content_type="image/jpeg")
    except (binascii.Error, ValueError):
        raise _photo_error(_("La foto no es una imagen válida."))


class ExportView(ApiView):
    """``GET /api/v1/me/export``: los datos personales de la cuenta (RGPD, acceso y portabilidad)."""

    def get(self, request):
        """
        ``generated_at``, ``account``, ``preferences``, ``memberships``, ``player_sheets`` (con ``snp_history``),
        ``monthly_reports`` y ``app_devices``, lo mismo que descarga la web en «Mi perfil». Sin contraseña ni tokens.
        429 tras 5 peticiones por hora.
        """
        if ratelimit.too_many_user(request, "export-data", EXPORT_LIMIT, EXPORT_WINDOW):
            raise ApiError("rate_limited", _("Demasiadas peticiones. Espera un momento."), 429,
                           {"Retry-After": str(EXPORT_WINDOW)})
        return json_ok(export_user_data(request.user))
