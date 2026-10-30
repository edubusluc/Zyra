"""Pruebas de los pendientes de la auditoría de espacios: jornada propuesta, hora en 24 h, filtro de
rival, vista previa de «pareja no presentada», reabrir el acta un gestor, convocar a una ficha copiada
pendiente, datos de otras competiciones solo de equipos que se gestionan y «Mis estadísticas» sin ficha."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from core.models import Invitation, Membership
from core.services import create_club
from match import outcomes
from match.forms import MatchForm
from match.models import Match
from match.report import can_share_other_competition, other_competitions
from players.models import Player
from team.models import Team

User = get_user_model()


class RoundAndTimeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("capi", email="c@example.com", password="pass-12345")
        self.club = create_club("Gladiadores LAPI", "Sevilla", self.user, competition="lapi")
        self.rival = Team.objects.create(club=self.club, name="Rival", location="Madrid", in_group=True)
        self.client.force_login(self.user)

    def test_the_next_round_is_proposed_after_the_last_league_match(self):
        Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                             start_date=datetime.date(2026, 10, 1), match_type="liga", round_number=3)
        form = MatchForm(club=self.club, user=self.user)
        self.assertEqual(form.initial["round_number"], 4)

    def test_no_round_is_proposed_with_no_league_matches(self):
        form = MatchForm(club=self.club, user=self.user)
        self.assertNotIn("round_number", form.initial)

    def test_time_field_is_a_24h_text_input(self):
        response = self.client.get(reverse("create_match"))
        self.assertContains(response, 'data-time-24h')
        self.assertContains(response, 'placeholder="20:30"')


class ReopenAndCopyTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capitan", "c@example.com", "pass-12345")
        self.club = create_club("Club", "Sevilla", self.captain, gender="M")
        self.manager = User.objects.create_user("gestor", "g@example.com", "pass-12345")
        Membership.objects.create(user=self.manager, club=self.club, role=Membership.MANAGER)
        rival = Team.objects.create(club=self.club, name="Rival", location="Huelva")
        self.match = Match.objects.create(
            club=self.club, local=self.club.own_team, visiting=rival, start_date=datetime.date(2026, 10, 1),
            draft_mode=False, result=outcomes.LOCAL_WIN, result_points="4-2")

    def test_a_manager_can_reopen_the_acta_and_it_is_logged(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("reopen_match", args=[self.match.public_id]))
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        self.assertTrue(self.match.draft_mode)
        self.assertEqual(self.match.reopened_by, self.manager)

    def test_a_plain_member_cannot_reopen_the_acta(self):
        member = User.objects.create_user("jugador", "j@example.com", "pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)
        response = self.client.post(reverse("reopen_match", args=[self.match.public_id]))
        self.assertEqual(response.status_code, 403)

    def test_a_copied_sheet_waiting_for_acceptance_is_marked_in_the_call_selector(self):
        waiting = Player.objects.create(club=self.club, name="Copia", last_name="Pendiente")
        Invitation.objects.create(club=self.club, email="copia@example.com", created_by=self.captain, player=waiting)
        Player.objects.create(club=self.club, name="Normal", last_name="Jugador")
        match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.match.visiting,
                                     start_date=datetime.date(2026, 11, 1))
        self.client.force_login(self.captain)
        response = self.client.get(reverse("create_call", args=[match.public_id]))
        self.assertContains(response, "Pendiente de aceptar", count=1)


class OtherCompetitionsTests(TestCase):
    """Los informes solo llevan datos de otro equipo si todos sus destinatarios lo gestionan."""

    def setUp(self):
        self.captain = User.objects.create_user("capitan", "c@example.com", "pass-12345")
        self.snp = create_club("Gladiadores", "Sevilla", self.captain)
        self.lapi = create_club("Gladiadores LAPI", "Sevilla", self.captain, competition="lapi")
        self.player_user = User.objects.create_user("ana", "a@example.com", "pass-12345")
        self.sheet = Player.objects.create(club=self.snp, name="Ana", last_name="Lopez", user=self.player_user)
        Player.objects.create(club=self.lapi, name="Ana", last_name="Lopez", user=self.player_user)
        rival = Team.objects.create(club=self.snp, name="Rival", location="Madrid", in_group=True)
        self.match = Match.objects.create(club=self.snp, local=self.snp.own_team, visiting=rival,
                                          start_date=datetime.date(2026, 10, 1), report_other_competitions=True)

    def test_shared_when_every_recipient_also_manages_the_other_team(self):
        self.assertTrue(can_share_other_competition(self.snp, self.lapi))
        self.assertEqual(len(other_competitions([self.sheet], self.match)), 1)

    def test_hidden_when_a_recipient_does_not_manage_the_other_team(self):
        manager = User.objects.create_user("gestor", "g@example.com", "pass-12345")
        Membership.objects.create(user=manager, club=self.snp, role=Membership.MANAGER)
        self.assertFalse(can_share_other_competition(self.snp, self.lapi))
        self.assertEqual(other_competitions([self.sheet], self.match), [])

    def test_the_checkbox_is_not_offered_when_it_cannot_apply(self):
        manager = User.objects.create_user("gestor", "g@example.com", "pass-12345")
        Membership.objects.create(user=manager, club=self.snp, role=Membership.MANAGER)
        form = MatchForm(club=self.snp, user=self.captain)
        self.assertFalse(form.other_competitions_available)


class MyStatsLinkTests(TestCase):
    def test_the_tab_explains_how_to_link_the_sheet_with_two_teams_and_no_sheet(self):
        user = User.objects.create_user("capi", email="c@example.com", password="pass-12345")
        create_club("Gladiadores", "Sevilla", user)
        create_club("Gladiadores LAPI", "Sevilla", user, competition="lapi")
        self.client.force_login(user)
        response = self.client.get(reverse("my_statistics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enlaza tu ficha para verlas")
