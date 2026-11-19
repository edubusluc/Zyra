"""Tests de ``/api/v1/invitations/<token>`` (consultar y aceptar) y del fichero de enlaces universales de iOS."""
import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache, caches
from django.test import TestCase, override_settings
from django.urls import reverse

from api.tokens import issue_token
from core.models import Invitation, Membership
from core.services import create_club

User = get_user_model()


class InvitationApiTests(TestCase):
    """Un jugador sin club consulta y acepta la invitación de un capitán desde la app."""

    def setUp(self):
        """Capitán con club, un jugador sin club con su token y una invitación."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123", first_name="Ana", last_name="Ruiz")
        self.club = create_club("Club Norte", "Gijón", self.captain)
        self.player = User.objects.create_user("marta", "marta@example.com", "Clave-Segura-123")
        _, self.token = issue_token(self.player, "iPhone")
        self.invitation = Invitation.objects.create(club=self.club, created_by=self.captain, reusable=True)

    def call(self, method, token=None, path="", auth=True):
        """Llama a la API con el token del jugador."""
        url = reverse("api_invitation", args=[token or self.invitation.token]) if not path else path
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"} if auth else {}
        return getattr(self.client, method)(url, content_type="application/json", **headers)

    def accept(self, token=None):
        """POST de aceptación."""
        return self.call("post", path=reverse("api_invitation_accept", args=[token or self.invitation.token]))

    def test_requires_token(self):
        """Sin token de dispositivo: 401."""
        self.assertEqual(self.call("get", auth=False).status_code, 401)

    def test_info_shows_club_and_captain(self):
        """La consulta devuelve el club, la competición y el capitán, y dice que se puede unir."""
        response = self.call("get")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["club"]["name"], "Club Norte")
        self.assertEqual(data["club"]["competition"], "snp")
        self.assertEqual(data["club"]["captains"], ["Ana Ruiz"])
        self.assertTrue(data["can_join"])

    def test_unknown_token_is_404_and_expired_is_410(self):
        """Token inexistente 404; invitación caducada 410 ``invitation_invalid``."""
        self.assertEqual(self.call("get", token="no-existe").status_code, 404)
        Invitation.objects.filter(pk=self.invitation.pk).update(expires_at="2000-01-01T00:00:00Z")
        response = self.call("get")
        self.assertEqual((response.status_code, response.json()["error"]), (410, "invitation_invalid"))

    def test_accept_joins_as_member_and_points_to_player_choice(self):
        """Aceptar crea la membresía de miembro, manda el correo de bienvenida y apunta a la elección de jugador."""
        response = self.accept()
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["club"], {"name": "Club Norte", "competition": "snp"})
        self.assertEqual(data["team"]["name"], "Club Norte")
        self.assertEqual(data["next_path"], reverse("member_welcome"))
        membership = Membership.objects.get(user=self.player, club=self.club)
        self.assertEqual(membership.role, Membership.MEMBER)
        self.assertEqual(len(mail.outbox), 1)

    def test_single_use_invitation_cannot_be_reused(self):
        """Una invitación de un solo uso da 409 la segunda vez, y ya no se puede consultar."""
        single = Invitation.objects.create(club=self.club, created_by=self.captain, email="marta@example.com")
        self.assertEqual(self.accept(single.token).status_code, 201)
        other = User.objects.create_user("luis", "luis@example.com", "Clave-Segura-123")
        _, other_token = issue_token(other, "iPhone")
        response = self.client.post(reverse("api_invitation_accept", args=[single.token]),
                                    content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {other_token}")
        self.assertEqual((response.status_code, response.json()["error"]), (409, "invitation_error"))

    def test_already_member_and_one_space_per_competition(self):
        """Ya miembro: 409 con el motivo; con equipo en la competición, la consulta dice que no puede unirse."""
        self.assertEqual(self.accept().status_code, 201)
        again = self.accept()
        self.assertEqual((again.status_code, again.json()["error"]), (409, "invitation_error"))
        info = self.call("get").json()
        self.assertFalse(info["can_join"])
        self.assertTrue(info["message"])


class AppleAppSiteAssociationTests(TestCase):
    """``/.well-known/apple-app-site-association``: activado solo con ``APPLE_APP_LINK_IDS``."""

    def test_disabled_by_default(self):
        """Sin ``APPLE_APP_LINK_IDS`` responde 404."""
        with override_settings(APPLE_APP_LINK_IDS=""):
            self.assertEqual(self.client.get("/.well-known/apple-app-site-association").status_code, 404)

    def test_serves_invitation_paths(self):
        """Con el identificador de la app, asocia ``/invite/*`` con ella y responde JSON."""
        with override_settings(APPLE_APP_LINK_IDS="ABCDE12345.com.example.zyra"):
            response = self.client.get("/.well-known/apple-app-site-association")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        details = json.loads(response.content)["applinks"]["details"][0]
        self.assertEqual(details["appIDs"], ["ABCDE12345.com.example.zyra"])
        self.assertEqual(details["components"], [{"/": "/invite/*"}])


class PingTeamTests(TestCase):
    """``GET /ping`` dice a qué equipo pertenece la cuenta (la app detecta así que salió de su club)."""

    def test_team_follows_membership(self):
        """Con club devuelve su equipo; al salir, None."""
        from core.models import Membership
        from api import tokens
        user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        club = create_club("Club A", "Sevilla", user)
        _device, raw = tokens.issue_token(user, "iPhone")
        header = {"HTTP_AUTHORIZATION": f"Bearer {raw}"}
        self.assertEqual(self.client.get(reverse("api_ping"), **header).json()["team"]["name"], "Club A")
        Membership.objects.filter(user=user, club=club).delete()
        self.assertIsNone(self.client.get(reverse("api_ping"), **header).json()["team"])
