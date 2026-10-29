"""
Vistas unidas de varios espacios (opción A): Enfrentamientos, Calendario e Inicio juntan los
espacios con el filtro «Todas · SNP · LAPI»; abrir un enfrentamiento de otro espacio cambia a él y
las acciones siguen el rol de cada espacio.
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.middleware import SESSION_KEY
from core.models import Membership
from core.services import create_club
from match.models import Match
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"


class UnifiedSpacesTests(TestCase):
    """Capitán en SNP y jugador en LAPI."""

    def setUp(self):
        self.user = User.objects.create_user("edu", password=PASSWORD, email="edu@example.com")
        self.snp = create_club("Gladiadores", "Sevilla", self.user)
        other = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.lapi = create_club("Gladiadores LAPI", "Sevilla", other, competition="lapi")
        Membership.objects.create(user=self.user, club=self.lapi, role=Membership.MEMBER)
        today = datetime.date.today()
        self.snp_match = Match.objects.create(
            club=self.snp, local=self.snp.own_team, start_date=today + datetime.timedelta(days=3),
            visiting=Team.objects.create(club=self.snp, name="Iconico", location="X", in_group=True))
        self.lapi_match = Match.objects.create(
            club=self.lapi, local=self.lapi.own_team, start_date=today + datetime.timedelta(days=2),
            visiting=Team.objects.create(club=self.lapi, name="Padel Norte", location="X", in_group=True))
        self.client.login(username="edu", password=PASSWORD)
        session = self.client.session
        session[SESSION_KEY] = self.snp.id
        session.save()

    def test_list_joins_spaces_and_filters(self):
        page = self.client.get(reverse("list_match") + "?season=all")
        self.assertContains(page, "Iconico")
        self.assertContains(page, "Padel Norte")
        self.assertContains(page, "z-comp-badge--lapi\">LAPI")
        self.assertContains(page, "Eres jugador aquí", count=1)
        # Solo puede borrar el de SNP, y el botón de crear dice dónde.
        self.assertContains(page, reverse("delete_match", args=[self.snp_match.public_id]))
        self.assertNotContains(page, reverse("delete_match", args=[self.lapi_match.public_id]))
        self.assertContains(page, "Nuevo enfrentamiento SNP")
        lapi_only = self.client.get(reverse("list_match") + "?season=all&espacio=lapi")
        self.assertNotContains(lapi_only, "Iconico")
        self.assertNotContains(lapi_only, "Nuevo enfrentamiento")
        # Se recuerda la elección.
        self.assertNotContains(self.client.get(reverse("list_match") + "?season=all"), "Iconico")

    def test_single_space_has_no_filter(self):
        Membership.objects.filter(user=self.user, club=self.lapi).delete()
        page = self.client.get(reverse("list_match") + "?season=all")
        self.assertNotContains(page, "z-space-filter")
        self.assertNotContains(page, "z-space-filter")
        self.assertNotContains(page, "Nuevo enfrentamiento SNP")
        self.assertContains(page, "Nuevo enfrentamiento")

    def test_opening_a_match_of_another_space_switches(self):
        page = self.client.get(reverse("call_for_match", args=[self.lapi_match.public_id]), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.client.session[SESSION_KEY], self.lapi.id)
        # Sin aviso: la página ya dice de qué competición es.
        self.assertNotContains(page, "Ahora estás en el espacio")
        # En LAPI es jugador: no puede gestionar aunque sea capitán en SNP.
        self.assertEqual(self.client.get(reverse("create_call", args=[self.lapi_match.public_id])).status_code, 403)

    def test_management_views_do_not_switch_spaces(self):
        response = self.client.get(reverse("create_call", args=[self.lapi_match.public_id]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.session[SESSION_KEY], self.snp.id)

    def test_follow_space_checks_the_role_of_that_space(self):
        self.assertEqual(self.client.get(reverse("create_match") + "?en=lapi").status_code, 403)
        session = self.client.session
        session[SESSION_KEY] = self.lapi.id
        session.save()
        self.assertEqual(self.client.get(reverse("create_match") + "?en=snp").status_code, 200)
        self.assertEqual(self.client.session[SESSION_KEY], self.snp.id)

    def test_calendar_joins_spaces(self):
        page = self.client.get(reverse("calendar_match") + "?month=" + self.lapi_match.start_date.strftime("%Y-%m"))
        self.assertContains(page, "z-cal-comp--lapi")
        self.assertContains(page, "z-space-filter")

    def test_home_pending_only_where_managing(self):
        page = self.client.get(reverse("home"))
        pending = [row["match"] for row in page.context["pending"]]
        self.assertEqual(pending, [self.snp_match])
        self.assertEqual(page.context["next_match"], self.lapi_match)

    def test_captain_in_both_chooses_competition(self):
        Membership.objects.filter(user=self.user, club=self.lapi).update(role=Membership.MANAGER)
        page = self.client.get(reverse("list_match") + "?season=all&espacio=todas")
        self.assertContains(page, "¿En qué competición?")
        self.assertContains(page, reverse("create_match") + "?en=lapi")

    def test_captain_and_player_sees_only_managed_space_in_roster(self):
        session = self.client.session
        session[SESSION_KEY] = self.lapi.id
        session.save()
        page = self.client.get(reverse("list_players"))
        self.assertEqual(page.context["current_club"], self.snp)
        self.assertNotContains(page, "z-space-switcher")
        self.assertEqual(self.client.get(reverse("club_home")).context["current_club"], self.snp)

    def test_captain_in_both_has_space_switcher(self):
        Membership.objects.filter(user=self.user, club=self.lapi).update(role=Membership.MANAGER)
        page = self.client.get(reverse("list_players"))
        self.assertContains(page, "z-space-switcher")
        page = self.client.get(reverse("list_players") + "?en=lapi")
        self.assertEqual(page.context["current_club"], self.lapi)

    def test_player_in_both_does_not_choose(self):
        Membership.objects.filter(user=self.user, club=self.snp).update(role=Membership.MEMBER)
        page = self.client.get(reverse("club_home"))
        self.assertNotContains(page, "z-space-switcher")
        self.assertNotContains(page, "Nuevo enfrentamiento")

    def test_captain_in_both_has_switcher_in_rivals(self):
        Membership.objects.filter(user=self.user, club=self.lapi).update(role=Membership.MANAGER)
        self.assertContains(self.client.get(reverse("list_teams")), "z-space-switcher")

    def test_home_banner_shows_every_team_whatever_the_active_one(self):
        for club in (self.snp, self.lapi):
            session = self.client.session
            session[SESSION_KEY] = club.id
            session.save()
            page = self.client.get(reverse("home"))
            self.assertEqual([t["club"] for t in page.context["home_teams"]], [self.snp, self.lapi])
            self.assertContains(page, "z-home-hero--teams")
            self.assertContains(page, "z-home-team--lapi")

    def test_roster_leaves_the_menu_only_for_player_in_every_team(self):
        url = reverse("list_players")
        self.assertContains(self.client.get(reverse("home")), url)  # capitán en SNP: la ve
        Membership.objects.filter(user=self.user, club=self.snp).update(role=Membership.MEMBER)
        self.assertNotContains(self.client.get(reverse("home")), f'href="{url}"')

    def test_menu_shows_user_name_and_roles(self):
        self.user.first_name = "Edu"
        self.user.save()
        page = self.client.get(reverse("home"))
        self.assertContains(page, '<span class="z-club-name">Edu</span>', html=False)
        self.assertContains(page, "Capitán")
        self.assertContains(page, "<small class=\"text-muted\">Jugador</small>", html=False)

    def _close(self, match, won=True):
        match.draft_mode = False
        match.result = "Victoria Local" if won else "Victoria Visitante"
        match.result_points = "2/1"
        match.save()

    def test_statistics_all_shows_each_space_without_mixing(self):
        self._close(self.snp_match)
        self._close(self.lapi_match, won=False)
        page = self.client.get(reverse("team_statistics") + "?espacio=todas&season=all")
        self.assertTemplateUsed(page, "stats_spaces.html")
        rows = {r["club"]: (r["played"], r["won"]) for r in page.context["rows"]}
        self.assertEqual(rows, {self.snp: (1, 1), self.lapi: (1, 0)})
        self.assertNotContains(page, "Tus partidos")  # sin jugador enlazado no hay «Tus partidos»
        from players.models import Player
        Player.objects.create(club=self.lapi, user=self.user, name="Edu", last_name="B")
        self.assertContains(self.client.get(reverse("team_statistics") + "?espacio=todas&season=all"), "Tus partidos")

    def test_statistics_all_charts_keep_competitions_apart(self):
        self._close(self.snp_match)
        self._close(self.lapi_match)
        page = self.client.get(reverse("team_statistics") + "?espacio=todas&season=all")
        chart = page.context["spaces_chart"]
        self.assertEqual([c["code"] for c in chart["comps"]], ["snp", "lapi"])
        # Ganados por temporada: una serie por competición (se apilan en el gráfico), nunca sumadas aquí.
        season = self.snp_match.season
        self.assertEqual(chart["years"]["labels"], [season])
        self.assertEqual(chart["years"]["won"], [[1], [1]])
        self.assertEqual(len(chart["local"]), 2)
        self.assertEqual(len(chart["attendance"]["series"]), 2)
        self.assertEqual([c["code"] for c in page.context["set_rows"][0]["comps"]], ["snp", "lapi"])
        self.assertContains(page, "spacesYearsChart")
        self.assertContains(page, "js/stats_spaces.js")
        # Con una temporada elegida no hay gráfico por años.
        self.assertNotContains(self.client.get(reverse("team_statistics") + f"?espacio=todas&season={season}"),
                               "spacesYearsChart")

    def test_statistics_of_one_competition_switches_space(self):
        self._close(self.lapi_match)
        page = self.client.get(reverse("team_statistics") + "?espacio=lapi&season=all")
        self.assertEqual(page.context["current_club"], self.lapi)
        self.assertNotContains(page, "sec-snp")

    def test_player_statistics_has_competition_chips(self):
        self._close(self.snp_match)
        page = self.client.get(reverse("player_statistics"))
        self.assertContains(page, "z-space-chip--lapi")
        # Jugador, Parejas y Rivales no mezclan competiciones: sin «Todas».
        for name in ("player_statistics", "pair_statistics", "rival_statistics"):
            self.assertNotContains(self.client.get(reverse(name)), "espacio=todas")


class OtherCompetitionsReportTests(TestCase):
    """Casilla «Incluir datos de otras competiciones»: solo con jugadores enlazados con ficha en otro espacio."""

    def setUp(self):
        from call.models import Call
        from players.models import Player
        self.user = User.objects.create_user("edu", password=PASSWORD, email="edu@example.com")
        self.snp = create_club("Gladiadores", "Sevilla", self.user)
        self.lapi = create_club("Gladiadores LAPI", "Sevilla", self.user, competition="lapi")
        self.me_snp = Player.objects.create(club=self.snp, user=self.user, name="Edu", last_name="B")
        self.client.login(username="edu", password=PASSWORD)
        self.match = Match.objects.create(
            club=self.snp, local=self.snp.own_team, start_date=datetime.date.today(), report_other_competitions=True,
            visiting=Team.objects.create(club=self.snp, name="Iconico", location="X", in_group=True))
        self.call = Call.objects.create(match=self.match)
        self.call.players.set([self.me_snp])

    def test_checkbox_only_with_sheets_in_other_space(self):
        from match.forms import MatchForm
        from players.models import Player
        self.assertFalse(MatchForm(club=self.snp, user=self.user).other_competitions_available)
        Player.objects.create(club=self.lapi, user=self.user, name="Edu", last_name="B")
        self.assertTrue(MatchForm(club=self.snp, user=self.user).other_competitions_available)

    def test_report_lists_other_competitions(self):
        from players.models import Player
        from match.report import build_report
        from match.report_pdf import render_report
        Player.objects.create(club=self.lapi, user=self.user, name="Edu", last_name="B")
        report = build_report(self.call)
        self.assertEqual([(r["player"], r["club"]) for r in report["other_competitions"]], [(self.me_snp, self.lapi)])
        self.assertTrue(render_report(report).startswith(b"%PDF"))
        self.match.report_other_competitions = False
        self.match.save()
        self.assertEqual(build_report(self.call)["other_competitions"], [])
