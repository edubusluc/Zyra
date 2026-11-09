"""
«Mis estadísticas» al cambiar de equipo: al salir de un club la ficha recuerda la cuenta (``past_user``) y el
día de salida (``left_on``), y «Yo» sigue mostrando esos partidos aunque ya no se esté en el equipo, se esté en
otro de la misma competición o no se tenga ninguno.
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from call.models import Call
from core.models import Membership
from core.services import create_club, remove_membership
from match.models import Game, Match
from players.models import Player
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"


class TeamChangeStatsTests(TestCase):
    """Edu juega en el club A de SNP, lo deja y entra en el club B (también SNP)."""

    def setUp(self):
        self.user = User.objects.create_user("edu", password=PASSWORD, email="edu@example.com")
        self.captain_a = User.objects.create_user("capa", password=PASSWORD, email="capa@example.com")
        self.club_a = create_club("Club A", "Sevilla", self.captain_a, division="500")
        Membership.objects.create(user=self.user, club=self.club_a, role=Membership.MEMBER)
        self.sheet_a = Player.objects.create(club=self.club_a, user=self.user, name="Edu", last_name="B")
        self.match_a = self._closed_match(self.club_a, self.sheet_a, days=-30)
        self.client.login(username="edu", password=PASSWORD)

    def _closed_match(self, club, me, days, won=True):
        """Enfrentamiento cerrado de ``club`` con un partido ganado por ``me`` y una convocatoria a la que se apuntó."""
        rival = Team.objects.create(club=club, name=f"Rival {club.name} {days}", location="X", in_group=True)
        match = Match.objects.create(club=club, local=club.own_team, visiting=rival, draft_mode=False,
                                     result="Victoria Local" if won else "Victoria Visitante", result_points="2/1",
                                     start_date=timezone.localdate() + datetime.timedelta(days=days))
        mate = Player.objects.create(club=club, name="Mate", last_name=f"{club.name}{days}")
        Game.objects.create(match=match, n_game=1, score=1, winner="Local" if won else "Visitante", draft_mode=False,
                            player_1_local=me, player_2_local=mate)
        Call.objects.create(match=match, draft_mode=False).players.add(me)
        return match

    def _leave(self, club):
        remove_membership(Membership.objects.get(user=self.user, club=club))

    def test_leaving_keeps_account_and_day_on_the_sheet(self):
        self._leave(self.club_a)
        self.sheet_a.refresh_from_db()
        self.assertIsNone(self.sheet_a.user)
        self.assertEqual(self.sheet_a.past_user, self.user)
        self.assertEqual(self.sheet_a.left_on, timezone.localdate())

    def test_without_any_team_yo_still_shows_the_past_sheet(self):
        self._leave(self.club_a)
        page = self.client.get(reverse("my_statistics") + "?season=all")
        self.assertEqual(page.status_code, 200)
        self.assertTemplateUsed(page, "stats_mine.html")
        self.assertEqual(page.context["me"]["played"], 1)
        self.assertEqual([r["former"] for r in page.context["rows"]], [True])
        self.assertContains(page, "Equipo anterior")
        self.assertNotContains(page, reverse("team_statistics"))  # sin equipo solo queda la pestaña «Yo»
        self.assertNotContains(page, "?espacio=snp")  # una ficha anterior no tiene ficha propia que abrir
        self.assertEqual([c["code"] for c in page.context["mine_chips"]], ["todas"])
        # Y desde «Sin equipo» se llega a ella.
        self.assertContains(self.client.get(reverse("no_club")), reverse("my_statistics"))

    def test_other_account_never_sees_it(self):
        self._leave(self.club_a)
        User.objects.create_user("otra", password=PASSWORD, email="otra@example.com")
        self.client.logout()
        self.client.login(username="otra", password=PASSWORD)
        self.assertRedirects(self.client.get(reverse("my_statistics")), reverse("no_club"), fetch_redirect_response=False)
        self.assertNotContains(self.client.get(reverse("no_club")), reverse("my_statistics"))

    def test_same_competition_second_club_keeps_both_sheets_apart(self):
        self._leave(self.club_a)
        captain_b = User.objects.create_user("capb", password=PASSWORD, email="capb@example.com")
        club_b = create_club("Club B", "Sevilla", captain_b, division="500")
        Membership.objects.create(user=self.user, club=club_b, role=Membership.MEMBER)
        sheet_b = Player.objects.create(club=club_b, user=self.user, name="Edu", last_name="B")
        self._closed_match(club_b, sheet_b, days=-5, won=False)
        page = self.client.get(reverse("my_statistics") + "?season=all")
        rows = {r["club"]: (r["former"], r["played"], r["wins"]) for r in page.context["rows"]}
        self.assertEqual(rows, {self.club_a: (True, 1, 1), club_b: (False, 1, 0)})
        self.assertEqual(page.context["me"]["played"], 2)
        # Los gráficos juntan las dos fichas en una sola serie SNP; las cifras de cada una no se pisan.
        comps = page.context["spaces_chart"]["comps"]
        self.assertEqual([c["code"] for c in comps], ["snp"])
        self.assertEqual(comps[0]["club"], "Club B, Club A")
        self.assertEqual(page.context["spaces_chart"]["totals"][0]["won"], 1)
        self.assertEqual(page.context["spaces_chart"]["totals"][0]["lost"], 1)
        self.assertEqual(page.context["comp_calls"][0]["calls"]["total"], 2)
        # El chip y «Ver SNP» llevan a la ficha actual, no a la anterior.
        self.assertEqual([c["code"] for c in page.context["mine_chips"]], ["todas", "snp"])
        redirect = self.client.get(reverse("my_statistics") + "?espacio=snp")
        self.assertIn(sheet_b.public_id, redirect.url)

    def test_calls_after_leaving_do_not_count(self):
        self._leave(self.club_a)
        # Una convocatoria posterior a su salida no baja su porcentaje de «te apuntas».
        late = Match.objects.create(
            club=self.club_a, local=self.club_a.own_team, draft_mode=False, result="Victoria Local", result_points="2/1",
            start_date=timezone.localdate() + datetime.timedelta(days=10),
            visiting=Team.objects.create(club=self.club_a, name="Tarde", location="X", in_group=True))
        Call.objects.create(match=late, draft_mode=False)
        page = self.client.get(reverse("my_statistics") + "?season=all")
        self.assertEqual(page.context["rows"][0]["calls"]["total"], 1)
        self.assertEqual(page.context["rows"][0]["calls"]["signed"], 1)

    def test_coming_back_offers_the_previous_sheet_and_clears_the_marks(self):
        self._leave(self.club_a)
        Membership.objects.create(user=self.user, club=self.club_a, role=Membership.MEMBER)
        page = self.client.get(reverse("my_player"))
        self.assertContains(page, "Tu ficha anterior")
        self.client.post(reverse("link_player", args=[self.sheet_a.public_id]))
        self.sheet_a.refresh_from_db()
        self.assertEqual((self.sheet_a.user, self.sheet_a.past_user, self.sheet_a.left_on), (self.user, None, None))

    def test_baja_sets_left_day_and_alta_clears_it(self):
        other = Player.objects.create(club=self.club_a, name="Otro", last_name="Z")
        self.assertIsNone(other.left_on)
        other.in_team = False
        other.save()
        other.refresh_from_db()
        self.assertEqual(other.left_on, timezone.localdate())
        other.in_team = True
        other.save()
        other.refresh_from_db()
        self.assertIsNone(other.left_on)

    def test_manage_roster_sets_and_clears_left_day(self):
        self.client.logout()
        self.client.login(username="capa", password=PASSWORD)
        other = Player.objects.create(club=self.club_a, name="Otro", last_name="Z")
        self.client.post(reverse("manage_roster"), {"in_team": [self.sheet_a.pk]})
        other.refresh_from_db()
        self.assertFalse(other.in_team)
        self.assertEqual(other.left_on, timezone.localdate())
        self.client.post(reverse("manage_roster"), {"in_team": [self.sheet_a.pk, other.pk]})
        other.refresh_from_db()
        self.assertTrue(other.in_team)
        self.assertIsNone(other.left_on)
