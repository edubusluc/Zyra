"""Tests de ``GET /api/v1/matches/<id>`` (ficha nativa de un enfrentamiento)."""
import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse

from api.tokens import issue_token
from call.models import Availability, Call
from core.models import Membership
from core.services import create_club
from match import outcomes
from match.models import Game, Match, Result
from players.models import Player
from team.models import Team

User = get_user_model()


class MatchApiTests(TestCase):
    """La ficha trae estado, fases, convocados y lo que toca a cada rol."""

    def setUp(self):
        """Capitán con club, un jugador con ficha enlazada y un enfrentamiento abierto dentro de 3 días."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123", first_name="Ana")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.user = User.objects.create_user("jug", "jug@example.com", "Clave-Segura-123")
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.me = Player.objects.create(club=self.club, name="Luis", last_name="Gil", user=self.user, in_team=True)
        self.rival = Team.objects.create(club=self.club, name="Club Este", location="X", in_group=True)
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date.today() + datetime.timedelta(days=3))
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.user_token = issue_token(self.user, "iPhone")
        self.stranger = User.objects.create_user("otro", "otro@example.com", "Clave-Segura-123")
        _, self.stranger_token = issue_token(self.stranger, "iPhone")

    def get(self, token, match=None):
        """GET de la ficha con el token indicado."""
        match = match or self.match
        return self.client.get(reverse("api_match", args=[match.public_id]), HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_match", args=[self.match.public_id])).status_code, 401)

    def test_other_account_gets_404(self):
        """Una cuenta ajena al equipo no ve el enfrentamiento."""
        self.assertEqual(self.get(self.stranger_token).status_code, 404)

    def test_captain_without_call(self):
        """Sin convocatoria el capitán ve «Por convocar» y la acción «Crear convocatoria»."""
        data = self.get(self.captain_token).json()
        self.assertEqual(data["match"]["status_label"], "Por convocar")
        self.assertEqual(data["primary"]["key"], "create_call")
        self.assertTrue(data["primary"]["enabled"])
        self.assertIsNone(data["call"])
        self.assertIsNone(data["outcome"])
        self.assertEqual([s["state"] for s in data["steps"]], ["cur", "todo", "todo", "todo"])
        self.assertTrue(data["can_manage"])

    def test_player_has_no_primary_action(self):
        """El jugador no recibe acciones de gestión y puede responder si puede jugar."""
        data = self.get(self.user_token).json()
        self.assertFalse(data["can_manage"])
        self.assertIsNone(data["primary"])
        self.assertNotIn("availability", data)
        self.assertEqual(data["me"]["state"], "no_call")

    def test_open_call_blocks_close_with_reason(self):
        """Con pocos apuntados «Cerrar convocatoria» sale desactivado y dice cuántos faltan."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.me)
        data = self.get(self.captain_token).json()
        self.assertEqual(data["match"]["status_label"], "Convocatoria abierta")
        self.assertEqual(data["primary"]["key"], "close_call")
        self.assertFalse(data["primary"]["enabled"])
        self.assertIn("Falta", data["primary"]["reason"])
        self.assertEqual(data["call"]["count"], 1)
        self.assertEqual(data["call"]["players"][0]["name"], self.me.short_name)
        self.assertEqual(data["availability"]["counts"], {"yes": 0, "no": 0, "maybe": 0})

    def test_my_answer_is_returned(self):
        """La respuesta del jugador y si aún puede cambiarla."""
        Availability.objects.create(match=self.match, player=self.me, answer="maybe", comment="El jueves")
        data = self.get(self.user_token).json()
        self.assertEqual(data["answer"]["value"], "maybe")
        self.assertEqual(data["answer"]["comment"], "El jueves")
        self.assertTrue(data["answer"]["can_answer"])

    def test_closed_match_has_outcome(self):
        """Con el acta cerrada sale el desenlace y no hay respuesta posible."""
        self.match.draft_mode = False
        self.match.result = outcomes.LOCAL_WIN
        self.match.result_points = "7/5"
        self.match.save()
        data = self.get(self.user_token).json()
        self.assertEqual(data["outcome"]["code"], "V")
        self.assertEqual((data["outcome"]["own"], data["outcome"]["rival"]), ("7", "5"))
        self.assertFalse(data["answer"]["can_answer"])
        self.assertEqual(data["match"]["status_label"], "Acta cerrada")

    def test_players_do_not_see_the_call_list_by_default(self):
        """Sin el ajuste del equipo, el jugador no recibe la lista de la convocatoria (sí quien gestiona)."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.me)
        self.assertIsNone(self.get(self.user_token).json()["call"])
        self.assertIsNotNone(self.get(self.captain_token).json()["call"])

    def test_actions_only_for_managers_and_locked_with_results(self):
        """Las acciones solo las recibe quien gestiona; con resultados guardados editar la convocatoria sale bloqueada."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.me)
        self.assertEqual(self.get(self.user_token).json()["actions"], [])
        actions = {a["key"]: a for a in self.get(self.captain_token).json()["actions"]}
        self.assertFalse(actions["edit_call"]["locked"])
        self.assertIn("edit_date", actions)
        self.assertTrue(actions["delete"]["danger"])
        game = Game.objects.create(match=self.match, n_game=1, score=3, player_1_local=self.me,
                                   player_2_local=Player.objects.create(club=self.club, name="Ana", last_name="Gil", in_team=True))
        Result.objects.create(game=game, result=outcomes.LOCAL_WIN, set1_local=6, set1_visiting=3, set2_local=6, set2_visiting=4)
        actions = {a["key"]: a for a in self.get(self.captain_token).json()["actions"]}
        self.assertTrue(actions["edit_call"]["locked"])
        self.assertTrue(actions["edit_call"]["reason"])


class CloseCallApiTests(TestCase):
    """``POST /matches/<id>/close-call``: cerrar la convocatoria desde la ficha nativa."""

    setUp = MatchApiTests.setUp

    def post(self, token, body=None, match=None):
        """POST con el token indicado."""
        match = match or self.match
        return self.client.post(reverse("api_match_close_call", args=[match.public_id]), data=body or {},
                                content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    def _call(self, n):
        """Convocatoria abierta con ``n`` jugadores."""
        call = Call.objects.create(match=self.match)
        players = [Player.objects.create(club=self.club, name=f"J{i}", last_name="X", in_team=True) for i in range(n)]
        call.players.set(players)
        return call

    def test_closes_with_enough_players(self):
        """Con los mínimos, cierra de verdad y deja la convocatoria cerrada."""
        from core.competitions import competition_for
        call = self._call(competition_for(self.match).min_call_players)
        response = self.post(self.captain_token)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["closed"])
        call.refresh_from_db()
        self.assertFalse(call.draft_mode)

    def test_player_cannot_close(self):
        """Un jugador sin gestión recibe 404 y no se cierra nada."""
        call = self._call(3)
        self.assertEqual(self.post(self.user_token).status_code, 404)
        call.refresh_from_db()
        self.assertTrue(call.draft_mode)

    def test_no_call_is_404(self):
        """Sin convocatoria no hay nada que cerrar."""
        self.assertEqual(self.post(self.captain_token).status_code, 404)

    def test_empty_call_cannot_close(self):
        """Sin apuntados: 409 y sigue abierta."""
        call = Call.objects.create(match=self.match)
        response = self.post(self.captain_token)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "cannot_close")
        call.refresh_from_db()
        self.assertTrue(call.draft_mode)

    def test_closing_twice_conflicts(self):
        """Cerrar una convocatoria ya cerrada da 409."""
        from core.competitions import competition_for
        self._call(competition_for(self.match).min_call_players)
        self.assertEqual(self.post(self.captain_token).status_code, 200)
        self.assertEqual(self.post(self.captain_token).status_code, 409)

    def test_rejects_non_boolean_flags(self):
        """Las marcas deben ser booleanos."""
        self._call(3)
        self.assertEqual(self.post(self.captain_token, {"allow_short": "si"}).status_code, 400)
