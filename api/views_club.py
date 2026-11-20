"""
Alta de club desde la app: las opciones del formulario y el alta en una sola llamada. Reutiliza los formularios y
servicios de la web (``SignUpForm``, ``ClubForm``, ``CaptainPlayerForm``, ``CaptainSnpForm``, ``create_club``), así
que las reglas son las mismas. Los errores salen por campo (``fields``) para que la app los pinte bajo cada uno.
"""
import base64
import binascii

from allauth.account.adapter import get_adapter
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.translation import gettext as _

from core import email_verification, ratelimit
from core.blocklist import is_user_blocked
from core.competitions import COMPETITIONS
from core.emails import send_welcome_email
from core.forms import CaptainPlayerForm, CaptainSnpForm, ClubForm, SignUpForm
from core.services import SpaceTaken, create_club, ensure_space_free
from core.views import REGISTER_LIMIT, REGISTER_WINDOW
from players import snp_service
from players.models import SnpAccount
from team.models import Team

from . import google, google_accounts
from .errors import ApiError
from .fields import text_field
from .responses import json_ok
from .tokens import issue_token
from .views_auth import team_summary
from .views_base import ApiView

MAX_CREST_LENGTH = 3_000_000  # caracteres en base64 (unos 2,2 MB de imagen)
ACCOUNT_LABEL = "account"


def _labelled(choices):
    """Lista ``[{"code", "label"}]`` a partir de pares ``(código, texto)``."""
    return [{"code": code, "label": str(label)} for code, label in choices]


class ClubOptionsView(ApiView):
    """``GET /api/v1/club/options``: competiciones, categorías, países y divisiones del formulario de alta."""
    public = True

    def get(self, request):
        """Cada competición con sus divisiones y países; ``snp`` indica si admite conectar la cuenta de SNP."""
        divisions = dict(Team.DIVISIONS)
        countries = dict(Team.COUNTRIES)
        competitions = [{
            "code": c.code, "name": str(c.name), "full_name": str(c.full_name), "color": c.color, "snp": c.has_snp,
            "divisions": _labelled((code, divisions[code]) for code in c.divisions),
            "countries": _labelled((code, countries[code]) for code in (c.countries or countries)),
        } for c in COMPETITIONS.values()]
        return json_ok({
            "competitions": competitions, "genders": _labelled(Team.GENDERS), "google": google.enabled(),
            "snp_available": snp_service.is_enabled(),
        })


def _section(body, name):
    """Subobjeto ``name`` del cuerpo (``{}`` si falta); ``invalid_field`` si no es un objeto."""
    value = body.get(name, {})
    if not isinstance(value, dict):
        raise ApiError("invalid_field", _("Campo no válido: %(name)s.") % {"name": name}, 400)
    return value


def _crest(team):
    """Escudo del cuerpo (``crest`` en base64) como fichero subido, o None. ``invalid_field`` si no es base64."""
    raw = team.get("crest")
    if raw in (None, ""):
        return None
    if not isinstance(raw, str) or len(raw) > MAX_CREST_LENGTH:
        raise ApiError("validation_error", _("Revisa los datos del formulario."), 400,
                       extra={"fields": {"team.crest": [_("El escudo es demasiado grande.")]}})
    try:
        content = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError("validation_error", _("Revisa los datos del formulario."), 400,
                       extra={"fields": {"team.crest": [_("El escudo no es una imagen válida.")]}})
    return SimpleUploadedFile("crest.jpg", content, content_type="image/jpeg")


def _collect(errors, prefix, form, rename=None):
    """Añade a ``errors`` los de ``form`` como ``<prefijo>.<campo>`` (``rename`` cambia el nombre de algún campo)."""
    for field, messages in form.errors.items():
        name = (rename or {}).get(field, field)
        key = prefix if field == "__all__" else f"{prefix}.{name}"
        errors.setdefault(key, []).extend(str(m) for m in messages)


class RegisterClubView(ApiView):
    """``POST /api/v1/club/register``: crea la cuenta (o usa la de Google) y su club, y devuelve el token."""
    public = True

    def post(self, request):
        """
        Cuerpo ``{"team": {...}, "captain": {...}, "account": {...} | "google": {...}, "device_name"?}``:

        - ``team``: ``name``, ``location``? (opcional), ``competition``, ``gender``, ``country``, ``division``?, ``default_time``?
          (HH:MM) y ``crest``? (imagen en base64).
        - ``captain``: ``mode`` ``manual`` (con ``name`` y ``last_name``) o ``snp`` (con ``snp_username`` y
          ``snp_password``; solo en competiciones con SNP).
        - ``account``: ``username``? (si falta se genera del email), ``email``, ``password``; o ``google``: ``id_token`` y ``nonce`` para entrar con
          Google (cuenta nueva o existente).

        400 ``validation_error`` con ``fields``; 409 ``space_taken`` si la cuenta ya tiene equipo en esa competición;
        429 si se pasa del límite de altas. 201 como el login, más ``club`` y, con SNP, ``next_path`` (la página web
        donde se elige qué jugador es el capitán).
        """
        if ratelimit.too_many(request, "register", REGISTER_LIMIT, REGISTER_WINDOW):
            raise ApiError("rate_limited", _("Demasiados intentos. Inténtalo más tarde."), 429)
        body = self.json_body(request)
        team, captain = _section(body, "team"), _section(body, "captain")
        account, google_body = _section(body, "account"), _section(body, "google")
        device_name = text_field(body, "device_name", required=False, max_length=100)
        # Con la cuenta ya creada (``CreateClubView``) el club se crea para ella: no se envía ni «account» ni «google».
        existing = not self.public
        if existing and (account or google_body):
            raise ApiError("invalid_field", _("Esta llamada usa tu cuenta: no envíes «account» ni «google»."), 400)
        if not existing and bool(account) == bool(google_body):
            raise ApiError("invalid_field", _("Envía «account» o «google», uno de los dos."), 400)

        photo = _crest(team)
        club_form = ClubForm({k: team.get(k, "") for k in
                              ("name", "location", "competition", "gender", "country", "division", "default_time")},
                             {"photo": photo} if photo else None, competitions=COMPETITIONS.values())
        club_form.uploader = None
        # La app no pide la sede en el alta (se rellena después): en la API es opcional; la web sigue exigiéndola.
        club_form.fields["location"].required = False
        use_snp = club_form.rules.has_snp and captain.get("mode") == CaptainSnpForm.SNP
        snp_form = CaptainSnpForm({"snp-mode": CaptainSnpForm.SNP if use_snp else CaptainSnpForm.MANUAL,
                                   "snp-username": captain.get("snp_username", ""),
                                   "snp-password": captain.get("snp_password", "")}, prefix="snp")
        player_form = CaptainPlayerForm({"player-name": captain.get("name", ""),
                                         "player-last_name": captain.get("last_name", "")}, prefix="player")
        if account and not str(account.get("username") or "").strip():
            # Sin usuario: se genera del email (como ``/auth/register``); la persona lo cambia en el perfil.
            local_part = str(account.get("email") or "").strip().split("@")[0]
            account = {**account, "username": get_adapter().generate_unique_username([local_part, "jugador"])}
        user_form = SignUpForm({"username": account.get("username", ""), "email": account.get("email", ""),
                                "password1": account.get("password", ""),
                                "password2": account.get("password", "")}) if account else None
        forms = [club_form, snp_form] + ([] if use_snp else [player_form]) + ([user_form] if user_form else [])
        for form in forms:
            form.is_valid()
        errors = {}
        _collect(errors, "team", club_form, {"photo": "crest"})
        _collect(errors, "captain", snp_form, {"username": "snp_username", "password": "snp_password", "mode": "mode"})
        if not use_snp:
            _collect(errors, "captain", player_form)
        if user_form:
            _collect(errors, ACCOUNT_LABEL, user_form, {"password1": "password", "password2": "password"})
        if errors:
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400, extra={"fields": errors})

        claims = None
        if google_body:
            claims = self._google_claims(google_body)
        try:
            with transaction.atomic():
                if existing:
                    user = request.user
                else:
                    user = user_form.save() if user_form else google_accounts.resolve_user(claims)
                if is_user_blocked(user):
                    raise ApiError("email_blocked", _("Tu email está bloqueado en Zyra y no puede crear clubes."), 403)
                data = club_form.cleaned_data
                ensure_space_free(user, data["competition"])
                player = {} if use_snp else player_form.cleaned_data
                club = create_club(data["name"], data["location"], user, gender=data["gender"],
                                   country=data["country"], division=data["division"], player_name=player.get("name", ""),
                                   player_last_name=player.get("last_name", ""), competition=data["competition"],
                                   default_time=data.get("default_time"))
                if data.get("photo"):
                    own = club.own_team
                    own.photo.save(data["photo"].name, data["photo"], save=False)
                    own._photo_check_id = getattr(club_form.instance, "_photo_check_id", None)
                    own.save()
                if player and not (user.first_name or user.last_name):
                    user.first_name, user.last_name = player["name"], player["last_name"]
                    user.save(update_fields=["first_name", "last_name"])
                if use_snp:
                    snp_account = SnpAccount(club=club, updated_by=user)
                    snp_account.username = snp_form.cleaned_data["username"].strip()
                    snp_account.password = snp_form.cleaned_data["password"]
                    snp_account.save()
        except SpaceTaken:
            raise ApiError("space_taken", _("Ya tienes un equipo en esa competición."), 409)
        except IntegrityError:
            # Dos altas a la vez con el mismo usuario o email: gana la primera.
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400, extra={"fields": {
                f"{ACCOUNT_LABEL}.username": [SignUpForm.USERNAME_TAKEN]}})
        return self._created(request, user, club, use_snp, device_name, new_password_account=bool(user_form),
                             existing=existing)

    def _google_claims(self, google_body):
        """Datos verificados del ``id_token`` de Google (mismos errores que ``/auth/google``)."""
        if not google.enabled():
            raise ApiError("not_found", _("No encontrado."), 404)
        token = text_field(google_body, "id_token", max_length=8192)
        nonce = text_field(google_body, "nonce", max_length=256)
        try:
            return google.verify_id_token(token, nonce)
        except google.GoogleTokenError:
            raise ApiError("invalid_google_token", _("No se pudo iniciar sesión con Google."), 401)
        except google.GoogleUnavailable:
            raise ApiError("google_unavailable", _("Google no responde. Inténtalo de nuevo en un momento."), 503)

    def _created(self, request, user, club, use_snp, device_name, new_password_account, existing=False):
        """Correos, importación de SNP y respuesta 201 (con token de dispositivo salvo con la cuenta ya creada)."""
        if new_password_account:
            email_verification.start_verification(request, user)
        send_welcome_email(user, club, created=True, site_url=request.build_absolute_uri("/"))
        if existing:
            data = {"user": {"username": user.get_username(), "email": user.email}, "team": team_summary(user),
                    "club": {"name": club.name, "competition": club.competition}}
        else:
            device, token = issue_token(user, device_name)
            data = {
                "token": token, "device": device.public_id, "expires_at": device.expires_at.isoformat(),
                "user": {"username": user.get_username(), "email": user.email},
                "team": team_summary(user),
                "club": {"name": club.name, "competition": club.competition},
            }
        if use_snp:
            if snp_service.is_enabled():
                from players import snp_import
                team_import = snp_import.start_search(club, user, auto_confirm=True)
                data["next_path"] = reverse("complete_team_welcome", args=[team_import.public_id])
            else:
                data["snp_unavailable"] = True
        return json_ok(data, status=201)


class CreateClubView(RegisterClubView):
    """``POST /api/v1/club/create``: crea el club de una cuenta que ya tiene sesión en la app (p. ej. un jugador sin club
    que decide registrar su equipo). Mismo cuerpo que ``club/register`` sin ``account`` ni ``google``; usa el token del
    dispositivo y no emite otro. 409 ``space_taken`` si la cuenta ya tiene equipo en esa competición."""
    public = False
