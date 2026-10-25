"""Pruebas de la imagen del resultado de un enfrentamiento cerrado."""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.urls import reverse
from PIL import Image

from core.services import create_club
from match.result_card import WIDTH, HEIGHT, render_card
from match.tests_ux import UxBase

User = get_user_model()


class ResultCardTests(UxBase):
    """Vista ``result_card`` y dibujo de la tarjeta."""

    def closed_match(self):
        match = self.match()
        self.closed_call(match)
        games = self.lineup(match)
        self.client.post(reverse("enter_results", args=[match.public_id]), self.results_post(games))
        self.client.post(reverse("close_match", args=[match.public_id]))
        return match

    def card(self, match, **params):
        return self.client.get(reverse("result_card", args=[match.public_id]), params)

    def test_png_has_expected_size(self):
        response = self.card(self.closed_match())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(Image.open(BytesIO(response.content)).size, (WIDTH, HEIGHT))

    def test_open_match_has_no_card(self):
        self.assertEqual(self.card(self.match()).status_code, 404)

    def test_names_are_optional(self):
        match = self.closed_match()
        self.assertNotEqual(self.card(match).content, self.card(match, names="1").content)

    def test_other_club_cannot_see_it(self):
        match = self.closed_match()
        other = User.objects.create_user("otro", email="otro@example.com", password="pass-12345")
        create_club("Club B", "Madrid", other)
        self.client.login(username="otro", password="pass-12345")
        self.assertEqual(self.card(match).status_code, 404)

    def test_button_shown_on_closed_match(self):
        match = self.closed_match()
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, reverse("result_card", args=[match.public_id]))

    def test_render_handles_long_names_and_missing_sets(self):
        data = {"outcome": "E", "local_name": "Club de Tenis y Pádel " * 4, "visiting_name": "X",
                "score_local": "6", "score_visiting": "6", "date": "01/01/2026", "kind": "Amistoso",
                "rows": [{"n": i, "pair": "", "sets": "", "won": False} for i in range(1, 6)]}
        self.assertEqual(Image.open(BytesIO(render_card(data, show_names=True))).size, (WIDTH, HEIGHT))
