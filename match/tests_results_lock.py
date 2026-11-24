"""Con algún resultado guardado, la convocatoria y las parejas con resultado no se tocan; «Borrar resultado» las libera."""
import json

from django.urls import reverse

from call.models import Call
from match import phase
from match.models import Game, Result
from match.tests_ux import UxBase


class ResultsLockTests(UxBase):
    def setUp(self):
        super().setUp()
        self.m = self.match()
        self.call = self.closed_call(self.m)
        self.games = self.lineup(self.m)
        self.client.post(reverse("create_result", args=[self.games[0].public_id]), {
            "set1_local": "6", "set1_visiting": "2", "set2_local": "6", "set2_visiting": "3"})

    def _lineup(self, order):
        """Alineación del formulario: el partido k-ésimo (por su id) lleva la pareja ``order[k-1]``."""
        return json.dumps([{"gameId": self.games[k].id, "player1Id": self.players[2 * i].id,
                            "player2Id": self.players[2 * i + 1].id} for k, i in enumerate(order)])

    def test_has_results(self):
        self.assertTrue(phase.has_results(self.m))
        other = self.match()
        self.assertFalse(phase.has_results(other))

    def test_edit_call_is_refused_once_there_is_a_result(self):
        url = reverse("edit_call", args=[self.call.public_id])
        response = self.client.post(url, {"players": [p.id for p in self.players]})
        self.assertRedirects(response, reverse("call_for_match", args=[self.m.public_id]), fetch_redirect_response=False)
        self.assertEqual(self.call.players.count(), 12)
        self.assertRedirects(self.client.get(url), reverse("call_for_match", args=[self.m.public_id]),
                             fetch_redirect_response=False)

    def test_edit_call_button_shows_a_popup_listing_the_games_with_result(self):
        page = self.client.get(reverse("call_for_match", args=[self.m.public_id]))
        self.assertContains(page, "data-info-popup")
        self.assertContains(page, "Partido 1.")
        self.assertNotContains(page, "Partido 2.")

    def test_enter_results_has_a_delete_button_only_for_saved_results(self):
        page = self.client.get(reverse("enter_results", args=[self.m.public_id]))
        self.assertContains(page, 'data-delete-form="delete-result-1"')
        self.assertNotContains(page, 'data-delete-form="delete-result-2"')
        self.assertContains(page, "data-clear-result", count=5)  # también limpia lo escrito sin guardar
        response = self.client.post(reverse("delete_result", args=[self.games[0].public_id]), {"next": "results"})
        self.assertRedirects(response, reverse("enter_results", args=[self.m.public_id]) + "#partido-1",
                             fetch_redirect_response=False)

    def test_cannot_move_a_pair_with_result(self):
        before = [(g.n_game, g.player_1_local_id) for g in self.m.games.order_by("n_game")]
        self.client.post(reverse("edit_games_match", args=[self.m.public_id]), {"ordered_games": self._lineup([1, 0, 2, 3, 4])})
        after = [(g.n_game, g.player_1_local_id) for g in self.m.games.order_by("n_game")]
        self.assertEqual(before, after)

    def test_can_still_change_pairs_without_result(self):
        # Los partidos 4 y 5 (sin resultado) intercambian parejas; el 1 se queda igual.
        self.client.post(reverse("edit_games_match", args=[self.m.public_id]), {"ordered_games": self._lineup([0, 1, 2, 4, 3])})
        game4 = self.m.games.get(n_game=4)
        self.assertEqual(game4.player_1_local_id, self.players[8].id)

    def test_delete_call_refused_with_pairs(self):
        self.client.post(reverse("delete_call", args=[self.m.public_id]))
        self.assertTrue(Call.objects.filter(match=self.m).exists())

    def test_delete_result_frees_the_call(self):
        game = self.games[0]
        self.client.post(reverse("delete_result", args=[game.public_id]))
        self.assertFalse(Result.objects.filter(game=game).exists())
        game.refresh_from_db()
        self.assertIsNone(game.winner)
        self.assertEqual(self.client.get(reverse("edit_call", args=[self.call.public_id])).status_code, 200)

    def test_delete_result_requires_post_and_open_acta(self):
        url = reverse("delete_result", args=[self.games[0].public_id])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.m.draft_mode = False
        self.m.save()
        self.client.post(url)
        self.assertTrue(Result.objects.filter(game=self.games[0]).exists())

    def test_delete_buttons_do_not_ask_for_confirmation_and_the_popup_does_not_hit_the_server_error(self):
        results = self.client.get(reverse("enter_results", args=[self.m.public_id])).content.decode()
        form = results[results.index('id="delete-result-1"'):][:300]
        self.assertNotIn("data-confirm=", form)
        # El aviso no apunta a edit_call (su rechazo saldría como un segundo mensaje de error).
        self.assertContains(self.client.get(reverse("call_for_match", args=[self.m.public_id])), "data-info-popup")

    def test_ajax_delete_answers_json_without_leaving_messages(self):
        response = self.client.post(reverse("delete_result", args=[self.games[0].public_id]),
                                    headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(Result.objects.filter(game=self.games[0]).exists())
        self.assertNotContains(self.client.get(reverse("call_for_match", args=[self.m.public_id])), "borrado.")


class SectionOrderTests(UxBase):
    """Con el acta cerrada los resultados van antes que los convocados."""

    def _order(self, match):
        html = self.client.get(reverse("call_for_match", args=[match.public_id])).content.decode()
        return html.index('id="partido-1"'), html.index('class="z-call"')

    def test_closed_report_shows_results_before_call(self):
        m = self.match()
        self.closed_call(m)
        games = self.lineup(m)
        self.client.post(reverse("enter_results", args=[m.public_id]), self.results_post(games, action="close"))
        m.refresh_from_db()
        self.assertFalse(m.draft_mode)
        games_pos, call_pos = self._order(m)
        self.assertLess(games_pos, call_pos)
