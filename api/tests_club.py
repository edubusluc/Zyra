"""Tests de ``/api/v1/club/options`` y ``/api/v1/club/register``: alta de club desde la app."""
import base64
import io
import json
from unittest import mock

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache, caches
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from api.models import DeviceToken
from api.tests_google import CLIENT_ID, NONCE, make_token, jwks
from core.models import BlockedEmail, Club, Membership
from core.moderation import Moderation
from core.models import PhotoCheck
from players.models import Player, SnpAccount, SnpTeamImport

User = get_user_model()


def body(**changes):
    """Cuerpo de alta válido (SNP, capitán escrito a mano) con los cambios indicados por sección."""
    data = {
        "team": {"name": "Club Norte", "location": "Gijón", "competition": "snp", "gender": "M", "country": "ES",
                 "division": "500", "default_time": "20:30"},
        "captain": {"mode": "manual", "name": "Ana", "last_name": "Ruiz"},
        "account": {"username": "capi", "email": "capi@example.com", "password": "Clave-Segura-123"},
        "device_name": "iPhone",
    }
    for section, value in changes.items():
        data[section] = value if not isinstance(value, dict) or section == "account" and not value else {
            **data.get(section, {}), **value}
    return data


class ClubTestCase(TestCase):
    """Base: cachés limpias y rutas."""

    def setUp(self):
        """Limpia cachés."""
        cache.clear()
        caches["ratelimit"].clear()
        self.url = reverse("api_club_register")

    def post(self, data):
        """POST con cuerpo JSON."""
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def fields(self, response):
        """Errores por campo de una respuesta 400."""
        self.assertEqual((response.status_code, response.json()["error"]), (400, "validation_error"))
        return response.json()["fields"]


class OptionsTests(ClubTestCase):
    """Las opciones del formulario salen de las fichas de competición."""

    def test_options(self):
        """SNP con sus divisiones y países; LAPI con las suyas y solo España."""
        response = self.client.get(reverse("api_club_options"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        snp, lapi = data["competitions"]
        self.assertEqual((snp["code"], snp["snp"], lapi["code"], lapi["snp"]), ("snp", True, "lapi", False))
        self.assertEqual([d["code"] for d in snp["divisions"]], ["future", "500", "1000", "grand_slam"])
        self.assertEqual([c["code"] for c in lapi["countries"]], ["ES"])
        self.assertEqual([g["code"] for g in data["genders"]], ["M", "F"])

    def test_requires_no_token_but_only_get(self):
        """Público; otro método es 405."""
        self.assertEqual(self.client.post(reverse("api_club_options")).status_code, 405)


class RegisterTests(ClubTestCase):
    """Alta con cuenta nueva."""

    def test_creates_account_club_and_token(self):
        """Cuenta, club con su equipo y jugador del capitán, token y correos."""
        response = self.post(body())
        self.assertEqual(response.status_code, 201)
        data = response.json()
        user = User.objects.get(username="capi")
        club = Club.objects.get(name="Club Norte")
        self.assertTrue(Membership.objects.get(user=user, club=club).is_admin)
        self.assertEqual((club.own_team.division, club.own_team.country), ("500", "ES"))
        self.assertEqual(str(club.own_team.default_time), "20:30:00")
        self.assertEqual(Player.objects.get(club=club).user, user)
        self.assertTrue(DeviceToken.objects.filter(user=user, device_name="iPhone").exists())
        self.assertEqual((data["club"]["name"], data["team"]["name"], data["team"]["crest"]), ("Club Norte", "Club Norte", None))
        self.assertTrue(data["token"])
        self.assertTrue(len(mail.outbox) >= 1)

    def test_location_and_username_are_optional(self):
        """Sin sede ni usuario el alta sale: la sede queda vacía y el usuario se genera del email."""
        data = body(team={"location": ""}, account={"email": "ana.ruiz@example.com", "password": "Clave-Segura-123"})
        del data["account"]["username"]
        response = self.post(data)
        self.assertEqual(response.status_code, 201)
        club = Club.objects.get(name="Club Norte")
        self.assertEqual(club.own_team.location, "")
        user = User.objects.get(email="ana.ruiz@example.com")
        self.assertEqual(response.json()["user"]["username"], user.username)
        self.assertTrue(user.username.startswith("ana"))

    def test_lapi_does_not_ask_division_country(self):
        """LAPI exige su división; sin ella, error en ``team.division``."""
        response = self.post(body(team={"competition": "lapi", "division": ""}))
        self.assertIn("team.division", self.fields(response))

    def test_field_errors_by_section(self):
        """Los errores salen como ``seccion.campo``; no se crea nada."""
        response = self.post(body(team={"name": ""}, captain={"name": ""},
                                  account={"username": "x", "email": "no-es-email", "password": "123"}))
        fields = self.fields(response)
        self.assertIn("team.name", fields)
        self.assertIn("captain.name", fields)
        self.assertIn("account.email", fields)
        self.assertIn("account.password", fields)
        self.assertEqual((User.objects.count(), Club.objects.count()), (0, 0))

    def test_existing_email_and_blocked_email(self):
        """Email ya usado o bloqueado: error en ``account.email``."""
        User.objects.create_user("otra", "capi@example.com", "x-Clave-12345")
        self.assertIn("account.email", self.fields(self.post(body())))
        BlockedEmail.objects.create(email="bloqueado@example.com")
        self.assertIn("account.email", self.fields(self.post(body(account={
            "username": "b", "email": "bloqueado@example.com", "password": "Clave-Segura-123"}))))

    def test_needs_account_or_google_not_both(self):
        """Sin ``account`` ni ``google`` (o con los dos) es un campo no válido."""
        data = body()
        del data["account"]
        self.assertEqual(self.post(data).json()["error"], "invalid_field")

    def test_crest_is_saved(self):
        """El escudo en base64 se valida, se procesa y queda en el equipo."""
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), "green").save(buffer, "PNG")
        crest = base64.b64encode(buffer.getvalue()).decode()
        approved = Moderation(PhotoCheck.APPROVED)
        with mock.patch("core.moderation.moderate", return_value=approved):
            response = self.post(body(team={"crest": crest}))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(Club.objects.get(name="Club Norte").own_team.photo)
        self.assertTrue(response.json()["team"]["crest"])

    def test_bad_crest(self):
        """Un escudo que no es base64 o no es una imagen da error en ``team.crest``."""
        self.assertIn("team.crest", self.fields(self.post(body(team={"crest": "###"}))))
        junk = base64.b64encode(b"no soy una imagen").decode()
        self.assertIn("team.crest", self.fields(self.post(body(team={"crest": junk}))))

    @override_settings(FIELD_ENCRYPTION_KEY="", SNP_IMPORT_INLINE=True)
    def test_snp_brings_the_team(self):
        """Con SNP se guarda la cuenta, se trae el equipo y se devuelve la página donde elegir quién eres."""
        team = [{"name": "ANA RUIZ PEREZ 500", "score": 40.0}]
        with mock.patch("players.snp_import.scrape_scores", return_value=team):
            response = self.post(body(captain={"mode": "snp", "snp_username": "capi", "snp_password": "secreto"}))
        self.assertEqual(response.status_code, 201)
        club = Club.objects.get(name="Club Norte")
        team_import = SnpTeamImport.objects.get(club=club)
        self.assertEqual(response.json()["next_path"], reverse("complete_team_welcome", args=[team_import.public_id]))
        self.assertEqual(SnpAccount.objects.get(club=club).username, "capi")
        self.assertFalse(Player.objects.filter(club=club, user__isnull=False).exists())

    def test_snp_needs_credentials(self):
        """Con SNP, usuario y contraseña de SNP son obligatorios."""
        fields = self.fields(self.post(body(captain={"mode": "snp"})))
        self.assertIn("captain.snp_username", fields)
        self.assertIn("captain.snp_password", fields)

    def test_lapi_ignores_snp(self):
        """En LAPI no hay SNP: se pide el nombre del capitán aunque se envíe ``snp``."""
        response = self.post(body(team={"competition": "lapi", "division": "lapi_1"}, captain={"mode": "snp", "name": ""}))
        self.assertIn("captain.name", self.fields(response))


@override_settings(GOOGLE_IOS_CLIENT_IDS=CLIENT_ID)
class RegisterWithGoogleTests(ClubTestCase):
    """Alta usando Google en vez de usuario y contraseña."""

    def setUp(self):
        """Claves de Google simuladas."""
        super().setUp()
        patcher = mock.patch("api.google.fetch_jwks", return_value=jwks())
        patcher.start()
        self.addCleanup(patcher.stop)

    def google(self, **claims):
        """Cuerpo de alta con Google."""
        data = body()
        del data["account"]
        data["google"] = {"id_token": make_token(**claims), "nonce": NONCE}
        return data

    def test_new_google_account_gets_club(self):
        """Cuenta nueva de Google: sin contraseña, con su club y sin correo de confirmación."""
        response = self.post(self.google())
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="ana@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(SocialAccount.objects.filter(user=user, provider="google").exists())
        self.assertTrue(Membership.objects.filter(user=user, club__name="Club Norte").exists())

    def test_existing_account_without_club_gets_club(self):
        """Cuenta ya existente (Google sin club) crea su club."""
        user = User.objects.create_user("ana", "ana@example.com", "x-Clave-12345")
        EmailAddress.objects.create(user=user, email="ana@example.com", verified=True, primary=True)
        self.assertEqual(self.post(self.google()).status_code, 201)
        self.assertTrue(Membership.objects.filter(user=user, club__name="Club Norte").exists())

    def test_space_taken_rolls_back_new_account(self):
        """Con equipo ya en esa competición: 409 y no queda nada a medias."""
        self.assertEqual(self.post(self.google(jti="1")).status_code, 201)
        response = self.post(self.google(jti="2"))
        self.assertEqual((response.status_code, response.json()["error"]), (409, "space_taken"))
        self.assertEqual(Club.objects.count(), 1)

    def test_invalid_token_creates_nothing(self):
        """Token mal: 401 y ni cuenta ni club."""
        data = self.google()
        data["google"]["nonce"] = "otro"
        self.assertEqual(self.post(data).status_code, 401)
        self.assertEqual((User.objects.count(), Club.objects.count()), (0, 0))

    @override_settings(GOOGLE_IOS_CLIENT_IDS="")
    def test_disabled(self):
        """Sin Google configurado, 404."""
        self.assertEqual(self.post(self.google()).status_code, 404)
