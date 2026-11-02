"""Fase 9 de la auditoría de estadísticas (EST-037 a EST-040): lista de enfrentamientos y acta, para capitán y jugador."""
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import Membership
from match import outcomes
from match.models import Match
from match.tests_ux import PAST, UxBase

User = get_user_model()


class ListAndActaTests(UxBase):
    """Lista de una línea por cerrado, aviso de pendientes y acta sin estados repetidos."""

    def closed_match(self):
        """Enfrentamiento cerrado que el propio equipo (local) pierde 4-8 con el rival."""
        match = self.match()
        match.draft_mode = False
        match.result = outcomes.VISITING_WIN
        match.result_points = "4/8"
        match.save()
        return match

    def as_player(self):
        """Entra como un socio sin permisos de gestión (vista de jugador)."""
        member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)

    def test_list_keeps_only_pending_and_a_link_to_the_balance(self):
        self.closed_match()
        self.match(date=PAST.replace(year=2027))
        for login in (lambda: None, self.as_player):
            login()
            page = self.client.get(reverse("list_match") + "?season=all")
            self.assertContains(page, 'class="z-pending-line"')
            self.assertContains(page, "Ver balance")
            self.assertNotContains(page, 'class="z-summary"')
            self.assertEqual(page.context["summary"]["pending"], 1)

    def test_closed_match_is_one_line_with_the_result_from_our_team(self):
        self.closed_match()
        for login in (lambda: None, self.as_player):
            login()
            html = self.client.get(reverse("list_match") + "?season=all").content.decode()
            self.assertIn("z-fixture--closed", html)
            self.assertIn("vs Rival", html)
            self.assertIn("4–8", html)  # nuestro equipo primero (juega de local)
            self.assertNotIn("z-flow4", html)  # el recorrido de cuatro pasos solo en los pendientes

    def test_result_is_read_from_our_side_when_we_are_visiting(self):
        match = self.closed_match()
        match.local, match.visiting = match.visiting, match.local  # ahora jugamos de visitante: 4/8 son 4 del rival y 8 nuestros
        match.save()
        html = self.client.get(reverse("list_match") + "?season=all").content.decode()
        self.assertIn("8–4", html)
        self.assertIn('class="z-fixture-state is-win"', html)  # ganó el visitante, que ahora somos nosotros

    def test_open_match_keeps_the_four_step_track_for_the_captain_only(self):
        self.match()
        self.assertContains(self.client.get(reverse("list_match") + "?season=all"), "z-flow4")
        self.as_player()
        self.assertNotContains(self.client.get(reverse("list_match") + "?season=all"), "z-flow4")

    def test_closed_acta_has_one_state_and_a_history_link_instead_of_the_preview(self):
        earlier = self.closed_match()
        later = self.match(date=PAST.replace(year=2027))
        later.draft_mode = False
        later.result, later.result_points = outcomes.VISITING_WIN, "2/10"
        later.save()
        for login in (lambda: None, self.as_player):
            login()
            page = self.client.get(reverse("call_for_match", args=[later.public_id]))
            self.assertNotContains(page, "z-preview")
            self.assertNotContains(page, "Previa")
            self.assertNotContains(page, "z-status4")
            self.assertNotContains(page, "Acta cerrada</span>")
            self.assertContains(page, "Historial contra Rival")
            self.assertContains(page, "rival_detail")
        self.assertTrue(earlier.pk)

    def test_open_acta_still_shows_the_preview_and_the_phases(self):
        self.closed_match()
        open_match = self.match(date=PAST.replace(year=2027))
        for login in (lambda: None, self.as_player):
            login()
            page = self.client.get(reverse("call_for_match", args=[open_match.public_id]))
            self.assertContains(page, "z-preview")
            self.assertContains(page, "z-status4")
            self.assertNotContains(page, "Historial contra")
        self.assertEqual(Match.objects.count(), 2)
