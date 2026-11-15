"""Tarjeta «Frente a la plantilla» de la ficha del jugador (``data_analyse.squad_compare``)."""
import datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from data_analyse import pairs as pair_stats
from data_analyse import roster_table, squad_compare
from data_analyse.tests_extra import ClubDataMixin
from match.models import Game, Match, Result
from players.models import Player


class Fake:
    """Jugador mínimo para probar la lógica sin base de datos."""
    def __init__(self, pid):
        self.id = pid


def entry(pair, won, sets=((6, 4), (6, 4))):
    return {"pair": pair, "won": won, "sets": list(sets)}


class CompareLogicTests(SimpleTestCase):
    def setUp(self):
        self.squad = [Fake(i) for i in (1, 2, 3, 4)]
        # 1 gana 3 de 3 (100 %); 2 gana 2 de 4 (50 %); 3 gana 2 de 5 (40 %); 4 solo juega 2 (no cuenta).
        log = [entry((1, 2), True), entry((1, 3), True), entry((1, 2), True),
               entry((2, 3), False), entry((2, 3), False), entry((3, 4), True), entry((3, 4), False, ((4, 6), (6, 3), (2, 6)))]
        self.log = log
        self.signup = {p.id: {"signed": s, "total": 4, "pct": round(100 * s / 4)} for p, s in zip(self.squad, (4, 2, 3, 1))}

    def compare(self, who=1, **kw):
        return squad_compare.compare_to_squad(self.squad[who - 1], self.squad, self.log, self.signup, **kw)

    def test_rank_mean_and_range(self):
        res = self.compare()
        pct = next(r for r in res["rows"] if r["key"] == "pct")
        self.assertEqual((pct["rank"], pct["of"]), (1, 3))  # el jugador 4 no llega a 3 partidos
        self.assertEqual(pct["value"], "100 %")
        self.assertEqual(pct["low"], "40 %")
        self.assertEqual(pct["tone"], "up")
        self.assertIn("sobre la media", pct["delta"])
        self.assertTrue(pct["top"])
        self.assertEqual(pct["base"], "3 de 3 partidos")

    def test_below_average_and_sets_base(self):
        res = self.compare(3)
        pct = next(r for r in res["rows"] if r["key"] == "pct")
        self.assertEqual((pct["rank"], pct["tone"]), (3, "down"))
        self.assertIn("bajo la media", pct["delta"])
        self.assertEqual(res["above"], 1)  # por encima en convocatorias, por debajo en victorias
        self.assertFalse(res["none_above"])

    def test_player_without_sample_has_no_row(self):
        res = self.compare(4)
        self.assertEqual([r["key"] for r in res["rows"]], ["signup"])  # tiene 4 convocatorias, pero solo 2 partidos

    def test_signup_needs_three_calls(self):
        self.signup[1] = {"signed": 1, "total": 2, "pct": 50}
        self.assertNotIn("signup", [r["key"] for r in self.compare()["rows"]])

    def test_too_small_squad_has_no_card(self):
        self.log = [entry((1, 2), True)] * 3  # solo 1 y 2 tienen partidos
        self.signup = {}
        self.assertIsNone(self.compare())

    def test_player_outside_squad(self):
        self.assertIsNone(squad_compare.compare_to_squad(Fake(99), self.squad, self.log, self.signup))

    def test_snp_row_and_positions_stay_inside_the_bar(self):
        snp = {p.id: {"score": 1000 + 100 * p.id} for p in self.squad}
        res = self.compare(4, snp_rows=snp)
        row = next(r for r in res["rows"] if r["key"] == "snp")
        self.assertEqual(row["rank"], 1)
        self.assertEqual(row["value"].replace("\xa0", " ").replace(".", " "), "1 400 pts")
        for r in res["rows"]:
            self.assertTrue(all(2 <= r[k] <= 98 for k in ("pos_low", "pos_high", "pos_mean", "pos_me")))
            self.assertEqual(r["range_width"], r["pos_high"] - r["pos_low"])

    def test_league_rounds_replace_points(self):
        res = self.compare(league=({1: 5, 2: 3, 3: 4, 4: 1}, 6))
        row = next(r for r in res["rows"] if r["key"] == "league")
        self.assertEqual((row["value"], row["rank"], row["base"]), ("5", 1, "de 6 jornadas"))


class SquadCardPageTests(ClubDataMixin, TestCase):
    """El club de ``ClubDataMixin`` solo tiene 4 jugadores con partidos y unos pocos cada uno: con MIN_SAMPLE no hay tarjeta."""

    def sheet(self, **params):
        params.update(player=self.a.public_id, season="2025-2026")
        return self.client.get(reverse("player_statistics"), params)

    def test_no_card_with_few_games(self):
        self.assertEqual(self.sheet().status_code, 200)
        self.assertNotContains(self.sheet(), "Frente a la plantilla")

    def test_card_appears_with_enough_games_and_follows_filters(self):
        # Tres enfrentamientos más con A+B y C+D ganando y perdiendo.
        for i in range(3):
            m = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                     start_date=datetime.date(2025, 12, 1 + i), draft_mode=False, result="VICTORIA")
            for n, (p1, p2, won) in enumerate(((self.a, self.b, True), (self.c, self.d, i % 2 == 0)), start=1):
                g = Game.objects.create(match=m, n_game=n, score=3, winner="Local" if won else "Visitante", draft_mode=False,
                                        player_1_local=p1, player_2_local=p2)
                Result.objects.create(game=g, draft_mode=False, set1_local=6 if won else 3, set1_visiting=3 if won else 6,
                                      set2_local=6 if won else 3, set2_visiting=3 if won else 6)
        res = self.sheet()
        self.assertContains(res, "Frente a la plantilla")
        card = res.context["squad_compare"]
        self.assertEqual(card["legend"], "A")  # su ficha, vista por el capitán: lleva su nombre
        self.assertEqual(card["rows"][0]["key"], "pct")
        # Sin temporada elegida cuenta el historial completo y la tarjeta no desaparece.
        self.assertContains(self.client.get(reverse("player_statistics"), {"player": self.a.public_id, "season": "todas"}),
                            "Frente a la plantilla")

    def test_pair_history_unaffected(self):
        log = pair_stats.club_game_log(self.club)
        signup = roster_table.signup_by_player(self.club, list(Player.objects.filter(club=self.club)))
        self.assertIsNone(squad_compare.compare_to_squad(self.a, list(Player.objects.filter(club=self.club)), log, signup))
