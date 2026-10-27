"""Pruebas de «Mi forma»: cálculo, quién la ve en el Inicio y el botón Ocultar / Mostrar."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from core.models import UserPreference
from core.services import create_club
from data_analyse import my_form
from match.models import Game, Match
from players.models import Player, SnpScoreHistory, current_season
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"


class MyFormBase(TestCase):
    """Club con un capitán sin jugador y un jugador (``me``) enlazado a su cuenta."""

    def setUp(self):
        self.captain = User.objects.create_user("captain", password=PASSWORD, email="captain@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.user = User.objects.create_user("jugador", password=PASSWORD, email="jugador@example.com")
        from core.models import Membership
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.me = Player.objects.create(club=self.club, name="Ana", last_name="Alpha", user=self.user, snp_score=436)
        self.mate = Player.objects.create(club=self.club, name="Bea", last_name="Beta")
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.day = datetime.date.today()

    def play(self, won, match_type=Match.ENFRENTAMIENTO, called=True, days_ago=1, season=None):
        """Un enfrentamiento cerrado con un partido de ``me`` y ``mate``."""
        match = Match.objects.create(
            club=self.club, local=self.club.own_team, visiting=self.rival, draft_mode=False, match_type=match_type,
            start_date=self.day - datetime.timedelta(days=days_ago), season=season or current_season(),
            result="Victoria Local" if won else "Victoria Visitante")
        Game.objects.create(match=match, n_game=1, score=3, winner="Local" if won else "Visitante", draft_mode=False,
                            player_1_local=self.me, player_2_local=self.mate)
        if called:
            Call.objects.create(match=match, draft_mode=False).players.add(self.me)
        return match


class CalculationTests(MyFormBase):
    def test_empty_without_games(self):
        data = my_form.my_form(self.club, self.me)
        self.assertTrue(data["empty"])
        self.assertEqual(data["last"], [])

    def test_last_five_run_and_season_balance(self):
        for days, won in enumerate([True, True, True, True, True, False, True], start=1):  # del más reciente al más antiguo
            self.play(won, days_ago=days)
        data = my_form.my_form(self.club, self.me)
        self.assertEqual(len(data["last"]), 5)
        self.assertEqual(data["run"], ("V", 5))
        self.assertEqual((data["wins"], data["losses"], data["win_pct"]), (6, 1, 86))
        self.assertEqual((data["called"], data["played"]), (7, 7))

    def test_losing_run(self):
        self.play(True, days_ago=3)
        self.play(False, days_ago=2)
        self.play(False, days_ago=1)
        self.assertEqual(my_form.my_form(self.club, self.me)["run"], ("D", 2))

    def test_friendlies_do_not_count(self):
        self.play(True, match_type=Match.AMISTOSO)
        data = my_form.my_form(self.club, self.me)
        self.assertTrue(data["empty"])
        self.assertEqual(data["called"], 0)

    def test_called_but_not_played(self):
        match = self.play(True)
        Game.objects.filter(match=match).update(player_1_local=self.mate, player_2_local=None, player_1_visiting=None)
        self.play(True, days_ago=2)
        data = my_form.my_form(self.club, self.me)
        self.assertEqual((data["called"], data["played"]), (2, 1))

    def test_not_signed_up_does_not_count(self):
        self.play(True, called=False)
        self.play(True, days_ago=2)
        data = my_form.my_form(self.club, self.me)
        self.assertEqual((data["called"], data["played"], data["played_pct"]), (1, 1, 100))

    def test_ring_arc_and_played_percentage(self):
        self.play(True, days_ago=2)
        self.play(False)
        data = my_form.my_form(self.club, self.me)
        self.assertEqual(data["win_arc"], round(my_form.RING_LENGTH / 2, 1))
        self.assertEqual(data["played_pct"], 100)

    def test_balance_is_this_season_but_last_games_span_seasons(self):
        self.play(True, days_ago=400, season="2020-2021")
        self.play(False)
        data = my_form.my_form(self.club, self.me)
        self.assertEqual(len(data["last"]), 2)
        self.assertEqual((data["wins"], data["losses"]), (0, 1))

    def test_snp_delta_and_line(self):
        for days, score in ((20, 412), (10, 420), (1, 436)):
            SnpScoreHistory.objects.create(player=self.me, date=self.day - datetime.timedelta(days=days), score=score)
        snp = my_form.my_form(self.club, self.me)["snp"]
        self.assertEqual(snp["delta"], 24)
        chart = snp["chart"]
        self.assertEqual(len(chart["line"].split()), 3)
        self.assertEqual((chart["high"], chart["low"]), (436, 412))
        self.assertEqual((chart["start"], chart["end"]), (self.day - datetime.timedelta(days=30), self.day))
        self.assertGreater(chart["dot"]["x"], 90)

    def test_snp_without_history_has_no_delta_and_without_score_is_none(self):
        snp = my_form.my_form(self.club, self.me)["snp"]
        self.assertIsNone(snp["delta"])
        self.assertIsNone(snp["chart"])
        Player.objects.filter(pk=self.me.pk).update(snp_score=None)
        self.me.refresh_from_db()
        self.assertIsNone(my_form.my_form(self.club, self.me)["snp"])


class HomeTests(MyFormBase):
    def test_linked_player_sees_the_card(self):
        self.play(True)
        self.client.login(username="jugador", password=PASSWORD)
        page = self.client.get(reverse("home"))
        self.assertContains(page, "Mi forma")
        self.assertContains(page, "Ocultar")
        self.assertContains(page, reverse("player_statistics") + "?player=" + self.me.public_id)
        self.assertNotContains(page, "Ver mi ficha")

    def test_empty_state_message(self):
        self.client.login(username="jugador", password=PASSWORD)
        self.assertContains(self.client.get(reverse("home")), "Todavía no has jugado ningún partido competitivo")

    def test_unlinked_account_does_not_see_it(self):
        self.client.login(username="captain", password=PASSWORD)
        page = self.client.get(reverse("home"))
        self.assertNotContains(page, "Mi forma")
        self.assertNotContains(page, "Mostrar mi forma")

    def test_hide_and_show_again(self):
        self.play(True)
        self.client.login(username="jugador", password=PASSWORD)
        self.client.post(reverse("toggle_my_form"), {"hide": "1"})
        self.assertTrue(UserPreference.my_form_is_hidden(self.user))
        page = self.client.get(reverse("home"))
        self.assertNotContains(page, 'id="my-form-title"')
        self.assertContains(page, "Mostrar mi forma")
        self.client.post(reverse("toggle_my_form"), {"hide": "0"})
        self.assertFalse(UserPreference.my_form_is_hidden(self.user))
        self.assertContains(self.client.get(reverse("home")), 'id="my-form-title"')

    def test_hiding_only_affects_the_user(self):
        self.client.login(username="jugador", password=PASSWORD)
        self.client.post(reverse("toggle_my_form"), {"hide": "1"})
        self.assertFalse(UserPreference.my_form_is_hidden(self.captain))

    def test_css_numbers_use_a_dot_even_in_spanish(self):
        """El anillo y la gráfica pintan números en CSS/SVG: con coma decimal no valdrían."""
        self.play(True, days_ago=2)
        self.play(True, days_ago=3)
        self.play(False)
        for days, score in ((20, 412), (1, 436)):
            SnpScoreHistory.objects.create(player=self.me, date=self.day - datetime.timedelta(days=days), score=score)
        self.client.login(username="jugador", password=PASSWORD)
        page = self.client.get(reverse("home"), headers={"accept-language": "es"}).content.decode()
        self.assertIn('stroke-dasharray="108.9 163.4"', page)
        self.assertRegex(page, r'left: \d+\.\d%')

    def test_toggle_needs_post_and_login(self):
        self.client.login(username="jugador", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("toggle_my_form")).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("toggle_my_form"), {"hide": "1"}).status_code, 302)
