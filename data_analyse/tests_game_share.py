"""Tarjeta «Reparto por partidos» de la ficha del jugador (``data_analyse.game_share``)."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from data_analyse.game_share import game_share
from data_analyse.sets import by_game_number
from data_analyse.tests_extra import ClubDataMixin


def share(played):
    """Reparto a partir de los partidos jugados en cada número de partido (todos ganados)."""
    games = [{'n_game': n, 'won': True} for n, count in enumerate(played, start=1) for _ in range(count)]
    return game_share(by_game_number(games))


class GameShareLogicTests(SimpleTestCase):
    def test_empty(self):
        res = share([0, 0, 0, 0, 0])
        self.assertEqual((res['state'], res['total']), ('empty', 0))
        self.assertTrue(all(s['dash'] is None and s['pct'] is None for s in res['segments']))

    def test_few_matches_have_counts_but_no_slices(self):
        res = share([0, 1, 1, 0, 0])
        self.assertEqual((res['state'], res['total']), ('few', 2))
        self.assertEqual([s['played'] for s in res['segments']], [0, 1, 1, 0, 0])
        self.assertTrue(all(s['dash'] is None and s['pct'] is None for s in res['segments']))

    def test_full_has_slices_and_percentages(self):
        res = share([2, 5, 11, 8, 2])
        self.assertEqual((res['state'], res['total'], res['single']), ('full', 28, False))
        self.assertEqual([s['pct'] for s in res['segments']], [7, 18, 39, 29, 7])
        self.assertEqual([s['value'] for s in res['segments']], [3, 3, 2, 2, 2])
        self.assertTrue(all(s['dash'] for s in res['segments']))
        # El primer sector empieza arriba (offset 0) y el siguiente donde acaba el anterior.
        self.assertEqual(res['segments'][0]['offset'], '-0.00')
        self.assertLess(float(res['segments'][1]['offset']), 0)

    def test_small_slices_have_no_number(self):
        res = share([1, 0, 30, 0, 0])
        self.assertNotIn('label_x', res['segments'][0])
        self.assertIn('label_x', res['segments'][2])

    def test_single_slice_is_a_full_ring_without_gap(self):
        res = share([0, 0, 14, 0, 0])
        self.assertTrue(res['single'])
        self.assertEqual(res['segments'][2]['dash'], res['circumference'])
        self.assertEqual(res['segments'][2]['pct'], 100)


class GameSharePageTests(ClubDataMixin, TestCase):
    """El club de ``ClubDataMixin`` es SNP: A juega el partido 1 en sus dos enfrentamientos."""

    def sheet(self, **params):
        params.update(player=self.a.public_id, season="2025-2026")
        return self.client.get(reverse("player_statistics"), params)

    def test_card_is_on_the_sheet_next_to_the_existing_chart(self):
        res = self.sheet()
        self.assertContains(res, "Reparto por partidos")
        self.assertContains(res, "Por número de partido")
        self.assertContains(res, "game-share.js")
        share_ctx = res.context["game_share"]
        self.assertEqual((share_ctx["state"], share_ctx["total"]), ("few", 2))
        self.assertEqual(share_ctx["segments"][0]["played"], 2)

    def test_follows_the_all_seasons_filter(self):
        res = self.client.get(reverse("player_statistics"), {"player": self.a.public_id, "season": "todas"})
        self.assertEqual(res.context["game_share"]["total"], 2)

    def test_player_without_matches_shows_the_empty_state(self):
        res = self.client.get(reverse("player_statistics"), {"player": self.e.public_id, "season": "2025-2026"})
        self.assertEqual(res.context["game_share"]["state"], "empty")
        self.assertContains(res, "Reparto por partidos")
