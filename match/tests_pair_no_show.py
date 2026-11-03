"""
«Pareja no presentada» en la SNP (normativa 20.2, ``match.pair_no_show``) y lesión y no presentado
de equipo en la SNP (15.10 y 20.3), marcados desde «Poner resultados».
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.services import create_club
from match.models import Game, Match, Result
from players.models import Player
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"
WIN = {"set1_local": "6", "set1_visiting": "2", "set2_local": "6", "set2_visiting": "3"}
LOSS = {"set1_local": "2", "set1_visiting": "6", "set2_local": "3", "set2_visiting": "6"}


class PairNoShowTests(TestCase):
    """Enfrentamiento SNP en casa (somos locales) con los 5 partidos alineados."""

    def setUp(self):
        self.user = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.club = create_club("Gladiadores", "Sevilla", self.user)
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                          start_date=datetime.date.today() - datetime.timedelta(days=1))
        players = [Player.objects.create(club=self.club, name=f"J{i}", last_name="X") for i in range(10)]
        for n in range(1, 6):
            Game.objects.create(match=self.match, n_game=n, score=self.club.rules.points_for(n),
                                player_1_local=players[2 * n - 2], player_2_local=players[2 * n - 1])
        self.client.login(username="capi", password=PASSWORD)

    def close(self, plan):
        """Pone los resultados de ``plan`` ({n: 'W'|'L'|no_show}) y cierra el acta."""
        data = {"action": "close"}
        for n, value in plan.items():
            if value in ("W", "L"):
                data.update({f"g{n}_{k}": v for k, v in (WIN if value == "W" else LOSS).items()})
                data[f"g{n}_no_show"] = ""
            else:
                data[f"g{n}_no_show"] = value
        self.client.post(reverse("enter_results", args=[self.match.public_id]), data)
        self.match.refresh_from_db()
        return self.match

    def scores(self):
        return [g.score for g in self.match.games.order_by("n_game")]

    def test_one_missing_pair_gives_six_and_two_two_one_one(self):
        match = self.close({1: "rival", 2: "W", 3: "L", 4: "W", 5: "L"})
        # Sin la pareja 1 rival: 6 para nosotros; las parejas 2 y 3 (las mejores que jugaron) valen 2.
        self.assertEqual(self.scores(), [6, 2, 2, 1, 1])
        self.assertEqual(match.result_points, "9/3")
        game = match.games.get(n_game=1)
        self.assertEqual((game.winner, game.player_1_local, game.results.count()), ("Local", None, 0))
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "No se presentó la pareja rival")

    def test_six_all_goes_to_the_team_that_won_the_four_played(self):
        match = self.close({1: "W", 2: "W", 3: "W", 4: "W", 5: "own"})
        self.assertEqual(match.result_points, "6/6")
        self.assertEqual(match.result, "Victoria Local")

    def test_two_missing_pairs_lose_twelve_nil(self):
        match = self.close({1: "own", 2: "own", 3: "W", 4: "W", 5: "W"})
        self.assertEqual((match.result_points, match.result), ("0/12", "Victoria Visitante"))

    def test_same_pair_missing_in_both_teams_is_annulled(self):
        match = self.close({1: "W", 2: "L", 3: "W", 4: "W", 5: "both"})
        self.assertEqual(match.result_points, "7/3")

    def test_different_pairs_missing_lose_their_own_game(self):
        match = self.close({1: "own", 2: "rival", 3: "W", 4: "L", 5: "W"})
        # Perdemos la 1 (3), ganamos la 2 (3) y se juegan 3, 4 y 5 normal.
        self.assertEqual(match.result_points, "7/5")

    def test_clearing_the_mark_restores_normal_points(self):
        self.close({1: "rival", 2: "W", 3: "W", 4: "W", 5: "W"})
        self.client.post(reverse("reopen_match", args=[self.match.public_id]))
        self.match.refresh_from_db()
        self.close({1: "W", 2: "W", 3: "W", 4: "W", 5: "W"})
        self.assertEqual(self.scores(), [3, 3, 2, 2, 2])
        self.assertEqual(self.match.result_points, "12/0")
        self.assertFalse(self.match.games.exclude(no_show="").exists())

    def test_snp_injury_completes_for_healthy_pair(self):
        game = self.match.games.get(n_game=1)
        result = Result(game=game, set1_local=6, set1_visiting=1, set2_local=2, set2_visiting=3,
                        retired=True, injured_side="visiting")
        result.result = result.determine_winner()
        result.save()
        self.assertEqual(result.sets(), [(6, 1), (6, 3), (None, None)])
        self.assertEqual(result.result, "Victoria Local")
