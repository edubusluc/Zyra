"""Tarjeta «Frente a la plantilla» de la ficha del jugador (``data_analyse.squad_compare``)."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from data_analyse import squad_compare
from data_analyse.tests_extra import ClubDataMixin


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
        # Tiene 4 convocatorias, pero solo 2 partidos: victorias y sets salen como «Sin datos suficientes».
        self.assertEqual([r["key"] for r in res["rows"] if not r["empty"]], ["signup"])
        self.assertEqual([r["key"] for r in res["rows"] if r["empty"]], ["pct", "sets"])
        self.assertEqual(res["count"], 1)

    def test_signup_needs_three_calls(self):
        self.signup[1] = {"signed": 1, "total": 2, "pct": 50}
        signup = next(r for r in self.compare()["rows"] if r["key"] == "signup")
        self.assertTrue(signup["empty"])
        self.assertEqual(signup["reader"], "Se apunta: sin datos suficientes")

    def test_too_small_squad_has_no_card(self):
        self.log = [entry((1, 2), True)] * 3  # solo 1 y 2 tienen partidos
        self.signup = {}
        self.assertIsNone(self.compare())

    def test_short_season_lowers_the_minimum(self):
        # Liga con 2 jornadas: nadie pasa de 2 partidos, pero se compara con lo que lleva el que más ha jugado.
        self.log = [entry((1, 2), True), entry((1, 3), True), entry((2, 4), False), entry((3, 4), False)]
        self.signup = {p.id: {"signed": 2, "total": 2, "pct": 100} for p in self.squad}
        res = self.compare()
        keys = [r["key"] for r in res["rows"]]
        self.assertIn("pct", keys)
        self.assertIn("sets", keys)
        pct = next(r for r in res["rows"] if r["key"] == "pct")
        self.assertEqual((pct["rank"], pct["of"], pct["base"]), (1, 4, "2 de 2 partidos"))

    def test_maximum_sits_at_the_end_of_the_bar(self):
        res = self.compare(league=({1: 2, 2: 0, 3: 1, 4: 1}, 2))
        row = next(r for r in res["rows"] if r["key"] == "league")
        self.assertEqual((row["pos_me"], row["pos_high"], row["pos_low"]), (98, 98, 2))
        self.assertEqual(row["mean"], "1")

    def test_equal_values_are_centred(self):
        res = self.compare(league=({1: 2, 2: 2, 3: 2, 4: 2}, 2))
        row = next(r for r in res["rows"] if r["key"] == "league")
        self.assertEqual(row["pos_me"], 50)

    def test_player_outside_squad(self):
        self.assertIsNone(squad_compare.compare_to_squad(Fake(99), self.squad, self.log, self.signup))

    def test_snp_row_and_positions_stay_inside_the_bar(self):
        snp = {p.id: {"score": 1000 + 100 * p.id} for p in self.squad}
        res = self.compare(4, snp_rows=snp)
        row = next(r for r in res["rows"] if r["key"] == "snp")
        self.assertEqual(row["rank"], 1)
        self.assertEqual(row["value"].replace("\xa0", " ").replace(".", " "), "1 400 pts")
        for r in (r for r in res["rows"] if not r["empty"]):
            self.assertTrue(all(2 <= r[k] <= 98 for k in ("pos_low", "pos_high", "pos_mean", "pos_me")))
            self.assertEqual(r["range_width"], r["pos_high"] - r["pos_low"])

    def test_league_rounds_replace_points(self):
        res = self.compare(league=({1: 5, 2: 3, 3: 4, 4: 1}, 6))
        row = next(r for r in res["rows"] if r["key"] == "league")
        self.assertEqual((row["value"], row["rank"], row["base"]), ("5", 1, "de 6 jornadas"))


class SquadCardPageTests(ClubDataMixin, TestCase):
    """El club de ``ClubDataMixin`` tiene 4 jugadores con 2 partidos como máximo: se compara con lo que lleva el que más ha jugado."""

    def sheet(self, **params):
        params.update(player=self.a.public_id, season="2025-2026")
        return self.client.get(reverse("player_statistics"), params)

    def test_card_with_a_short_season(self):
        res = self.sheet()
        self.assertContains(res, "Frente a la plantilla")
        card = res.context["squad_compare"]
        self.assertEqual(card["legend"], "A")  # su ficha, vista por el capitán: lleva su nombre
        self.assertEqual(card["rows"][0]["key"], "pct")

    def test_follows_the_season_filter_and_all_seasons(self):
        self.assertContains(self.client.get(reverse("player_statistics"), {"player": self.a.public_id, "season": "todas"}),
                            "Frente a la plantilla")
