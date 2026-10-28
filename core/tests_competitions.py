"""
Ficha de reglas de cada competición (``core.competitions``): la SNP conserva sus números y el
ciclo del enfrentamiento lee de la ficha en lugar de dar por hecho «5 partidos» o «10 convocados».
"""
import datetime
import json
from contextlib import ExitStack
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from core.competitions import DEFAULT, SNP, Competition, competition_for, get_competition
from core.services import create_club
from match import advisor
from match.models import Game, Match
from match.phase import phase_for
from players.models import Player
from team.models import Team

User = get_user_model()

# Competición de prueba con el formato de 3 partidos de 1 punto y 6 convocados.
THREE_GAMES = Competition(code="test3", name="Prueba", game_points=(1, 1, 1), min_call_players=6, tiebreak_game=2)


class CompetitionRulesTests(TestCase):
    """La ficha de la SNP mantiene exactamente las reglas que había fijas en el código."""

    def test_snp_rules(self):
        self.assertEqual(SNP.games, 5)
        self.assertEqual([SNP.points_for(n) for n in range(1, 6)], [3, 3, 2, 2, 2])
        self.assertEqual(SNP.total_points, 12)
        self.assertEqual(SNP.min_call_players, 10)
        self.assertEqual(SNP.players_per_lineup, 10)
        self.assertEqual(SNP.tiebreak_game, 3)

    def test_default_and_lookup(self):
        self.assertIs(DEFAULT, SNP)
        self.assertIs(get_competition("snp"), SNP)
        self.assertIs(get_competition("no-existe"), SNP)
        self.assertIs(competition_for(), SNP)

    def test_advisor_uses_snp_format(self):
        self.assertEqual(advisor.GAME_VALUES, (3, 3, 2, 2, 2))
        self.assertEqual(advisor.POINTS_TO_WIN, 7)
        self.assertEqual(advisor.PLAYERS_PER_LINEUP, 10)


class MatchCycleReadsRulesTests(TestCase):
    """Con otra ficha, convocatoria, alineación, fase y cierre de acta siguen sus números."""

    def setUp(self):
        self.user = User.objects.create_user("capi", email="capi@example.com", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"Jug{i:02d}", last_name="X") for i in range(8)]
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date(2026, 1, 10))
        self.client.login(username="capi", password="pass-12345")
        stack = ExitStack()
        for module in ("match.views", "match.lineup", "match.phase"):
            stack.enter_context(mock.patch(f"{module}.competition_for", return_value=THREE_GAMES))
        self.addCleanup(stack.close)
        stack.__enter__()

    def test_three_game_cycle(self):
        # 6 convocados bastan para crear y cerrar la convocatoria
        self.client.post(reverse("create_call", args=[self.match.public_id]),
                         {"players": [p.id for p in self.players[:6]]})
        call = Call.objects.get(match=self.match)
        self.assertEqual(phase_for(self.match).missing_players, 0)
        self.client.post(reverse("close_call", args=[self.match.public_id]))
        call.refresh_from_db()
        self.assertFalse(call.draft_mode)

        # La pantalla de parejas pide 3 parejas
        response = self.client.get(reverse("create_game", args=[self.match.public_id]))
        self.assertEqual(response.content.decode().count("data-slot "), 3)

        # Se guardan 3 partidos de 1 punto
        pairs = [{"player1Id": self.players[i].id, "player2Id": self.players[i + 1].id} for i in (0, 2, 4)]
        self.client.post(reverse("create_game", args=[self.match.public_id]), {"ordered_games": json.dumps(pairs)})
        games = list(self.match.games.order_by("n_game"))
        self.assertEqual([g.score for g in games], [1, 1, 1])
        self.assertEqual(phase_for(self.match).total_games, 3)

    def test_five_pairs_rejected_when_competition_has_three(self):
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.set(self.players)
        pairs = [{"player1Id": self.players[0].id, "player2Id": self.players[1].id}] * 5
        self.client.post(reverse("create_game", args=[self.match.public_id]), {"ordered_games": json.dumps(pairs)})
        self.assertFalse(Game.objects.filter(match=self.match).exists())


class SnpCycleUnchangedTests(TestCase):
    """Sin tocar nada, la SNP sigue pidiendo 10 convocados y 5 parejas."""

    def setUp(self):
        self.user = User.objects.create_user("capi", email="capi@example.com", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"Jug{i:02d}", last_name="X") for i in range(10)]
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date(2026, 1, 10))
        self.client.login(username="capi", password="pass-12345")

    def test_snp_needs_ten_and_five_pairs(self):
        self.client.post(reverse("create_call", args=[self.match.public_id]),
                         {"players": [p.id for p in self.players[:9]]})
        self.assertFalse(Call.objects.filter(match=self.match).exists())
        self.client.post(reverse("create_call", args=[self.match.public_id]),
                         {"players": [p.id for p in self.players]})
        self.client.post(reverse("close_call", args=[self.match.public_id]))
        response = self.client.get(reverse("create_game", args=[self.match.public_id]))
        self.assertEqual(response.content.decode().count("data-slot "), 5)
        self.assertContains(response, "Hacen falta al menos 10 convocados", count=0)
