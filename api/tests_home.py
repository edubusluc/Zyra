"""Tests de ``GET /api/v1/home`` (base del Inicio nativo)."""
from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api.tokens import issue_token
from core.models import Membership
from core.services import create_club
from players.models import Player

User = get_user_model()


class HomeApiTests(TestCase):
    """El Inicio nativo recibe la situación de la cuenta, sus equipos y el rol en cada uno."""

    def setUp(self):
        """Capitán con club y una cuenta sin equipo, cada una con su token."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123", first_name="Ana")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.loner = User.objects.create_user("sola", "sola@example.com", "Clave-Segura-123")
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.loner_token = issue_token(self.loner, "iPhone")

    def get(self, token):
        """GET del Inicio con el token indicado."""
        return self.client.get(reverse("api_home"), HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_home")).status_code, 401)

    def test_post_is_not_allowed(self):
        """Solo se lee: POST da 405 en JSON."""
        response = self.client.post(reverse("api_home"), HTTP_AUTHORIZATION=f"Bearer {self.captain_token}")
        self.assertEqual((response.status_code, response.json()["error"]), (405, "method_not_allowed"))

    def test_captain_with_team(self):
        """El capitán ve su equipo con rol, competición y su ficha de jugador."""
        data = self.get(self.captain_token).json()
        self.assertEqual(data["state"], "ok")
        self.assertEqual(data["user"], {"username": "capi", "display_name": "Ana"})
        self.assertEqual(len(data["teams"]), 1)
        team = data["teams"][0]
        self.assertEqual((team["name"], team["competition"], team["role"], team["can_manage"]),
                         ("Club Norte", "snp", "admin", True))
        self.assertEqual(team["role_label"], "Capitán")
        self.assertTrue(team["has_snp"])
        self.assertTrue(data["has_player"])
        self.assertTrue(data["has_history"])
        self.assertEqual(data["suspended_clubs"], [])

    def test_display_name_falls_back_to_username(self):
        """Sin nombre de pila se saluda con el usuario."""
        self.assertEqual(self.get(self.loner_token).json()["user"]["display_name"], "sola")

    def test_no_team(self):
        """Cuenta sin equipo: ``no_team`` y sin histórico."""
        data = self.get(self.loner_token).json()
        self.assertEqual((data["state"], data["teams"], data["has_player"], data["has_history"]), ("no_team", [], False, False))

    def test_member_role(self):
        """Un jugador (miembro) no gestiona."""
        Membership.objects.create(user=self.loner, club=self.club, role=Membership.MEMBER)
        team = self.get(self.loner_token).json()["teams"][0]
        self.assertEqual((team["role"], team["role_label"], team["can_manage"]), ("member", "Jugador", False))

    def test_has_player_only_with_linked_sheet(self):
        """``has_player`` es cierto solo si la cuenta tiene ficha enlazada en un equipo activo."""
        Membership.objects.create(user=self.loner, club=self.club, role=Membership.MEMBER)
        self.assertFalse(self.get(self.loner_token).json()["has_player"])
        Player.objects.filter(club=self.club).first()  # la ficha del capitán no es suya
        player = Player.objects.create(club=self.club, name="Sola", last_name="Pérez", user=self.loner)
        self.assertTrue(self.get(self.loner_token).json()["has_player"])
        player.delete()

    def test_suspended_club(self):
        """Con el único club suspendido: ``suspended`` y el nombre del club."""
        self.club.suspended_at = timezone.now()
        self.club.save(update_fields=["suspended_at"])
        data = self.get(self.captain_token).json()
        self.assertEqual((data["state"], data["teams"]), ("suspended", []))
        self.assertEqual(data["suspended_clubs"], [{"name": "Club Norte"}])

    def test_two_spaces_in_competition_order(self):
        """Con dos equipos salen los dos, en el orden de las competiciones (SNP antes que LAPI)."""
        create_club("Norte LAPI", "Gijón", self.captain, competition="lapi")
        data = self.get(self.captain_token).json()
        self.assertEqual([t["competition"] for t in data["teams"]], ["snp", "lapi"])
