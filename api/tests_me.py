"""Tests de ``GET /api/v1/me`` (arranque de la app), del ETag opt-in de la API y de la resolución de equipos por token."""
from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse

from api.errors import ApiError
from api.teams import membership_for_team, require_role
from api.tokens import issue_token
from core.models import Membership
from core.services import create_club

User = get_user_model()


class MeApiTests(TestCase):
    """La app recibe cuenta, equipos y rol en una sola llamada, y puede guardarla con ETag."""

    def setUp(self):
        """Capitán con club, un miembro de ese club y una cuenta sin equipo, cada una con su token."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123", first_name="Ana")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.member = User.objects.create_user("miembro", "miembro@example.com", "Clave-Segura-123")
        Membership.objects.create(user=self.member, club=self.club, role=Membership.MEMBER)
        self.loner = User.objects.create_user("sola", "sola@example.com", "Clave-Segura-123")
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.member_token = issue_token(self.member, "iPhone")
        _, self.loner_token = issue_token(self.loner, "iPhone")

    def get(self, token, **extra):
        """GET de ``/me`` con el token indicado."""
        return self.client.get(reverse("api_me"), HTTP_AUTHORIZATION=f"Bearer {token}", **extra)

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_me")).status_code, 401)

    def test_captain_gets_account_teams_and_capabilities(self):
        """El capitán ve su cuenta, su equipo con rol de capitán y las capacidades de gestión y administración."""
        data = self.get(self.captain_token).json()
        self.assertEqual(data["state"], "ok")
        self.assertEqual(data["user"], {"username": "capi", "display_name": "Ana", "email": "capi@example.com"})
        self.assertEqual(len(data["teams"]), 1)
        team = data["teams"][0]
        self.assertEqual(team["id"], str(self.club.public_id))
        self.assertTrue(team["can_manage"])
        self.assertTrue(team["can_admin"])
        self.assertEqual(data["capabilities"], {"can_manage_any": True, "can_admin_any": True, "multi_team": False})
        self.assertTrue(data["has_player"])

    def test_member_cannot_manage(self):
        """Un miembro corriente ve el equipo pero sin gestión ni administración."""
        data = self.get(self.member_token).json()
        team = data["teams"][0]
        self.assertFalse(team["can_manage"])
        self.assertFalse(team["can_admin"])
        self.assertFalse(data["capabilities"]["can_manage_any"])

    def test_account_without_team(self):
        """Una cuenta sin club: ``no_team``, sin equipos y sin capacidades."""
        data = self.get(self.loner_token).json()
        self.assertEqual(data["state"], "no_team")
        self.assertEqual(data["teams"], [])
        self.assertEqual(data["capabilities"], {"can_manage_any": False, "can_admin_any": False, "multi_team": False})

    def test_suspended_club_is_not_a_team(self):
        """Un club suspendido no cuenta como equipo (mismo criterio que la web) y se lista aparte."""
        from django.utils import timezone

        self.club.suspended_at = timezone.now()
        self.club.save(update_fields=["suspended_at"])
        data = self.get(self.captain_token).json()
        self.assertEqual(data["state"], "suspended")
        self.assertEqual(data["teams"], [])
        self.assertEqual(data["suspended_clubs"], [{"name": "Club Norte"}])

    def test_etag_and_not_modified(self):
        """La respuesta lleva ETag y ``private, no-cache``; repetirla con ``If-None-Match`` da 304 sin cuerpo."""
        first = self.get(self.captain_token)
        self.assertEqual(first.status_code, 200)
        tag = first["ETag"]
        self.assertEqual(first["Cache-Control"], "private, no-cache")
        self.assertIn("Authorization", first["Vary"])
        again = self.get(self.captain_token, HTTP_IF_NONE_MATCH=tag)
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b"")
        self.assertEqual(again["ETag"], tag)
        self.assertEqual(again["Cache-Control"], "private, no-cache")

    def test_etag_changes_when_data_changes(self):
        """Si cambia algo (aquí el nombre), el ETag viejo ya no vale y llega la respuesta nueva."""
        tag = self.get(self.captain_token)["ETag"]
        self.captain.first_name = "Marta"
        self.captain.save(update_fields=["first_name"])
        changed = self.get(self.captain_token, HTTP_IF_NONE_MATCH=tag)
        self.assertEqual(changed.status_code, 200)
        self.assertNotEqual(changed["ETag"], tag)
        self.assertEqual(changed.json()["user"]["display_name"], "Marta")

    def test_etag_of_another_account_does_not_match(self):
        """El ETag de otra cuenta no da 304: cada cuenta tiene su propia versión."""
        captain_tag = self.get(self.captain_token)["ETag"]
        self.assertEqual(self.get(self.loner_token, HTTP_IF_NONE_MATCH=captain_tag).status_code, 200)

    def test_other_routes_stay_no_store(self):
        """Solo las vistas que lo piden se guardan: el resto sigue con ``no-store`` y sin ETag."""
        response = self.client.get(reverse("api_ping"), HTTP_AUTHORIZATION=f"Bearer {self.captain_token}")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertFalse(response.has_header("ETag"))

    def test_error_responses_are_never_cached(self):
        """Un 401 de una vista con ETag sigue siendo ``no-store``."""
        response = self.client.get(reverse("api_me"))
        self.assertEqual(response["Cache-Control"], "no-store")


class TeamResolutionTests(TestCase):
    """``membership_for_team`` y ``require_role``: pertenencia y rol por token, sin sesión."""

    def setUp(self):
        """Capitán de un club, miembro corriente y alguien ajeno."""
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.member = User.objects.create_user("miembro", "miembro@example.com", "Clave-Segura-123")
        Membership.objects.create(user=self.member, club=self.club, role=Membership.MEMBER)
        self.stranger = User.objects.create_user("ajeno", "ajeno@example.com", "Clave-Segura-123")

    def test_captain_resolves_with_any_role(self):
        """El capitán pasa los tres niveles."""
        team_id = str(self.club.public_id)
        for kwargs in ({}, {"manage": True}, {"admin": True}):
            self.assertEqual(membership_for_team(self.captain, team_id, **kwargs).club, self.club)

    def test_member_is_forbidden_when_role_is_required(self):
        """Un miembro corriente entra en su equipo pero recibe 403 si se pide gestión o administración."""
        team_id = str(self.club.public_id)
        self.assertEqual(membership_for_team(self.member, team_id).club, self.club)
        for kwargs in ({"manage": True}, {"admin": True}):
            with self.assertRaises(ApiError) as caught:
                membership_for_team(self.member, team_id, **kwargs)
            self.assertEqual((caught.exception.status, caught.exception.code), (403, "forbidden"))

    def test_foreign_or_unknown_team_is_404(self):
        """Un equipo ajeno o inexistente responde igual (404): no revela si existe."""
        for who, team_id in ((self.stranger, str(self.club.public_id)), (self.captain, "CLB000000000000")):
            with self.assertRaises(ApiError) as caught:
                membership_for_team(who, team_id)
            self.assertEqual((caught.exception.status, caught.exception.code), (404, "not_found"))

    def test_require_role_accepts_manager(self):
        """Un gestor pasa ``manage`` pero no ``admin``."""
        manager = Membership.objects.get(user=self.member)
        manager.role = Membership.MANAGER
        manager.save(update_fields=["role"])
        require_role(manager, manage=True)
        with self.assertRaises(ApiError):
            require_role(manager, admin=True)
