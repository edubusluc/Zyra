"""Tests del botón «Alineación sugerida» del formulario de parejas."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from core.services import create_club
from match.models import Match
from players.models import Player
from team.models import Team

User = get_user_model()


class SuggestedLineupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"P{i}", last_name="X", snp_score=i) for i in range(11)]
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                          start_date=datetime.date(2025, 10, 1))
        self.call = Call.objects.create(match=self.match, draft_mode=False)
        self.call.players.set(self.players)
        self.url = reverse("suggested_lineup", args=[self.match.public_id])
        self.client.login(username="admin", password="pass-12345")

    def test_returns_five_pairs_of_called_players(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        lineups = response.json()["lineups"]
        self.assertEqual(lineups[0]["key"], "A")
        pairs = lineups[0]["pairs"]
        self.assertEqual(len(pairs), 5)
        ids = [pid for pair in pairs for pid in pair]
        self.assertEqual(len(set(ids)), 10)
        self.assertTrue(set(ids) <= {p.id for p in self.players})
        self.assertTrue(0 <= lineups[0]["win"] <= 100)

    def test_lineup_form_has_button(self):
        response = self.client.get(reverse("create_game", args=[self.match.public_id]))
        self.assertContains(response, "Alineación sugerida")
        self.assertContains(response, self.url)

    def test_needs_closed_call_with_ten_players(self):
        self.call.players.set(self.players[:9])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_other_club_gets_404(self):
        other = User.objects.create_user("other", password="pass-12345")
        create_club("Club B", "Madrid", other)
        self.client.login(username="other", password="pass-12345")
        self.assertEqual(self.client.get(self.url).status_code, 404)
