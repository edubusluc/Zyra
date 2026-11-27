"""Tests de la plantilla en la API: lista, alta, edición, baja, alta y borrado de jugadores."""
from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse

from api.tokens import issue_token
from core.models import Membership
from core.services import create_club
from players.models import Player

User = get_user_model()
PASSWORD = "Clave-Segura-123"


class RosterApiTests(TestCase):
    """Capitán, un miembro con ficha enlazada y un jugador sin cuenta."""

    def setUp(self):
        """Crea el club, los jugadores y los tokens."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", PASSWORD)
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.user = User.objects.create_user("jug", "jug@example.com", PASSWORD)
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.linked = Player.objects.create(club=self.club, name="Luis", last_name="Gil", user=self.user, in_team=True)
        self.free = Player.objects.create(club=self.club, name="Sergio", last_name="Pardo", in_team=True)
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.user_token = issue_token(self.user, "iPhone")
        self.team = str(self.club.public_id)

    def call(self, method, name, token, data=None, args=None):
        """Llama al endpoint ``name`` con el token indicado."""
        return getattr(self.client, method)(reverse(name, args=args or []), data=data, content_type="application/json",
                                            HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_roster_for_manager_lists_everyone(self):
        """El capitán ve la plantilla con roles, contador y máximo."""
        data = self.call("get", "api_roster", self.captain_token, args=[self.team]).json()
        self.assertTrue(data["can_manage"])
        names = {p["full_name"]: p for p in data["players"]}
        self.assertEqual(names["Ana Ruiz"]["role"], "captain")
        self.assertTrue(names["Luis Gil"]["linked"])
        self.assertEqual(data["in_team"], 3)

    def test_roster_for_member_hides_left_players(self):
        """Un miembro solo ve a quienes siguen en la plantilla."""
        self.free.in_team = False
        self.free.save()
        data = self.call("get", "api_roster", self.user_token, args=[self.team]).json()
        self.assertFalse(data["can_manage"])
        self.assertNotIn("Sergio Pardo", [p["full_name"] for p in data["players"]])

    def test_roster_requires_membership(self):
        """Una cuenta ajena: 404."""
        other = User.objects.create_user("otro", "otro@example.com", PASSWORD)
        _, token = issue_token(other, "iPhone")
        self.assertEqual(self.call("get", "api_roster", token, args=[self.team]).status_code, 404)

    def test_create_player_and_similar_check(self):
        """Crea un jugador; uno parecido pide confirmación y el chequeo no crea nada."""
        r = self.call("post", "api_create_player", self.captain_token, {"name": "Nacho", "last_name": "Vega"}, args=[self.team])
        self.assertEqual(r.status_code, 201, r.content)
        again = {"name": "Nacho", "last_name": "Vega"}
        r = self.call("post", "api_create_player", self.captain_token, {**again, "check": True}, args=[self.team])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["similar"]), 1)
        r = self.call("post", "api_create_player", self.captain_token, again, args=[self.team])
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"], "similar_players")
        r = self.call("post", "api_create_player", self.captain_token, {**again, "confirm_similar": True}, args=[self.team])
        self.assertEqual(r.status_code, 201)

    def test_create_player_requires_manager(self):
        """Un miembro no puede crear jugadores: 403."""
        r = self.call("post", "api_create_player", self.user_token, {"name": "A", "last_name": "B"}, args=[self.team])
        self.assertEqual(r.status_code, 403)

    def test_edit_player(self):
        """Edita posición y nombre; lo no enviado se conserva."""
        r = self.call("patch", "api_player", self.captain_token, {"position": "Revés", "name": "Sergi"}, args=[self.free.public_id])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["player"]["position"], "Revés")
        self.assertEqual(r.json()["player"]["name"], "Sergi")
        self.assertTrue(r.json()["player"]["in_team"])

    def test_edit_invalid(self):
        """Posición inválida: 400 con el campo."""
        r = self.call("patch", "api_player", self.captain_token, {"position": "Portero"}, args=[self.free.public_id])
        self.assertEqual(r.status_code, 400)
        self.assertIn("position", r.json()["fields"])

    def test_leave_and_join(self):
        """Baja y alta de un jugador sin cuenta."""
        r = self.call("post", "api_player_leave", self.captain_token, args=[self.free.public_id])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["player"]["in_team"])
        self.assertEqual(self.call("post", "api_player_leave", self.captain_token, args=[self.free.public_id]).status_code, 409)
        r = self.call("post", "api_player_join", self.captain_token, args=[self.free.public_id])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["player"]["in_team"])

    def test_captain_cannot_be_removed(self):
        """El capitán no se da de baja: 409."""
        captain_player = Player.objects.get(club=self.club, user=self.captain)
        r = self.call("post", "api_player_leave", self.captain_token, args=[captain_player.public_id])
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"], "cannot_leave")

    def test_delete_player(self):
        """Elimina una ficha sin cuenta ni partidos; una ficha con cuenta, no."""
        r = self.call("post", "api_player_delete", self.captain_token, args=[self.linked.public_id])
        self.assertEqual(r.status_code, 409)
        r = self.call("post", "api_player_delete", self.captain_token, args=[self.free.public_id])
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Player.objects.filter(pk=self.free.pk).exists())

    def test_foreign_player_is_404(self):
        """Un jugador de otro club: 404."""
        other = User.objects.create_user("otro", "otro@example.com", PASSWORD)
        create_club("Club Sur", "Gijón", other, player_name="Eva", player_last_name="Mon")
        _, token = issue_token(other, "iPhone")
        self.assertEqual(self.call("patch", "api_player", token, {"name": "X"}, args=[self.free.public_id]).status_code, 404)


class CopyPlayersApiTests(TestCase):
    """Copiar jugadores del equipo SNP al de LAPI de la misma cuenta."""

    def setUp(self):
        """Un capitán con dos equipos (SNP y LAPI) y jugadores en el de SNP."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi2", "capi2@example.com", PASSWORD)
        self.snp = create_club("Club SNP", "Gijón", self.captain, competition="snp", player_name="Ana", player_last_name="Ruiz")
        self.lapi = create_club("Club LAPI", "Gijón", self.captain, competition="lapi", player_name="Ana", player_last_name="Ruiz")
        self.free = Player.objects.create(club=self.snp, name="Sergio", last_name="Pardo", in_team=True)
        _, self.token = issue_token(self.captain, "iPhone")
        self.team = str(self.lapi.public_id)

    def call(self, method, data=None, team=None):
        """Llama a copiar jugadores del equipo ``team`` (por defecto, el de LAPI)."""
        return getattr(self.client, method)(reverse("api_copy_players", args=[team or self.team]), data=data,
                                            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_candidates_list_status_of_each_player(self):
        """Sergio se puede copiar y Ana ya tiene ficha en LAPI."""
        data = self.call("get").json()
        status = {c["full_name"]: c["status"] for c in data["candidates"]}
        self.assertEqual(status["Sergio Pardo"], "copy")
        self.assertEqual(status["Ana Ruiz"], "already")
        self.assertEqual(data["source"]["id"], str(self.snp.public_id))

    def test_copy_creates_the_sheet(self):
        """Copiar a Sergio crea su ficha en LAPI marcada como copia."""
        res = self.call("post", {"from": str(self.snp.public_id), "players": [str(self.free.public_id)]}).json()
        self.assertEqual(res["copied"], 1)
        self.assertTrue(Player.objects.filter(club=self.lapi, name="Sergio", copied_from=self.free).exists())

    def test_roster_reports_can_copy(self):
        """La plantilla avisa de que hay de dónde copiar."""
        res = self.client.get(reverse("api_roster", args=[self.team]), HTTP_AUTHORIZATION=f"Bearer {self.token}").json()
        self.assertTrue(res["can_copy"])

    def test_without_another_team_is_404(self):
        """Quien solo tiene un equipo no puede copiar: 404."""
        other = User.objects.create_user("solo", "solo@example.com", PASSWORD)
        club = create_club("Solo", "Gijón", other, competition="snp", player_name="Eva", player_last_name="Gil")
        _, token = issue_token(other, "iPhone")
        res = self.client.get(reverse("api_copy_players", args=[str(club.public_id)]), HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, 404)

    def test_invalid_players_is_400(self):
        """Una lista con ids que no son ids: 400."""
        self.assertEqual(self.call("post", {"players": ["x"]}).status_code, 400)
