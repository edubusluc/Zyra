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
        self.snp = create_club("Gladiadores", "Sevilla", self.user, division="500")
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
        self.assertNotContains(page, reverse("delete_match", args=[self.snp_match.public_id]))  # eliminar solo desde la ficha (H-36)
        self.assertNotContains(page, reverse("delete_match", args=[self.lapi_match.public_id]))
        self.assertContains(page, "Nuevo enfrentamiento SNP")
        lapi_only = self.client.get(reverse("list_match") + "?season=all&espacio=lapi")
        self.assertNotContains(lapi_only, "Iconico")
        # El botón de crear no depende del filtro: dice siempre dónde se crea (SNP, el que gestiona).
        self.assertContains(lapi_only, "Nuevo enfrentamiento SNP")
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

    def test_management_views_follow_the_object_and_check_its_role(self):
        # Las páginas de gestión siguen al equipo del enfrentamiento (sin 404) y aplican el rol de ese
        # equipo: aquí es jugador, así que «Sin permiso» dice de qué equipo es.
        response = self.client.get(reverse("create_call", args=[self.lapi_match.public_id]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.session[SESSION_KEY], self.lapi.id)
        self.assertContains(response, "Gladiadores LAPI (LAPI), donde eres jugador", status_code=403)

    def test_management_views_work_after_switching_in_another_tab(self):
        # Capitán en los dos: con SNP activo (otra pestaña), las páginas de un enfrentamiento LAPI funcionan.
        Membership.objects.filter(user=self.user, club=self.lapi).update(role=Membership.MANAGER)
        for name in ("create_call", "enter_results", "edit_match_date"):
            session = self.client.session
            session[SESSION_KEY] = self.snp.id
            session.save()
            response = self.client.get(reverse(name, args=[self.lapi_match.public_id]))
            self.assertNotEqual(response.status_code, 404, name)
            self.assertEqual(self.client.session[SESSION_KEY], self.lapi.id, name)
        player = self.lapi.own_team.team_players.create(club=self.lapi, name="Ana", last_name="L")
        session = self.client.session
        session[SESSION_KEY] = self.snp.id
        session.save()
        self.assertEqual(self.client.get(reverse("show_player", args=[player.public_id])).status_code, 200)

    def test_create_match_asks_the_team_when_managing_several(self):
        Membership.objects.filter(user=self.user, club=self.lapi).update(role=Membership.MANAGER)
        page = self.client.get(reverse("create_match"))
        self.assertTemplateUsed(page, "create_match_choose.html")
        self.assertContains(page, reverse("create_match") + "?en=lapi")
        self.assertContains(page, reverse("create_match") + "?en=snp")
        form = self.client.get(reverse("create_match") + "?en=lapi")
        self.assertTemplateUsed(form, "create_match.html")
        self.assertContains(form, "Cambiar de equipo")
        self.assertContains(form, 'action="/match/create_match?en=lapi"')

    def test_create_match_goes_to_the_only_managed_team(self):
        # Gestiona solo SNP: aunque el activo sea LAPI (donde juega), no pregunta y crea en SNP.
        session = self.client.session
        session[SESSION_KEY] = self.lapi.id
        session.save()
        page = self.client.get(reverse("create_match"))
        self.assertTemplateUsed(page, "create_match.html")
        self.assertEqual(self.client.session[SESSION_KEY], self.snp.id)
        self.assertNotContains(page, "Cambiar de equipo")

    def test_warnings_only_for_managed_teams(self):
        # Capitán en SNP, jugador en LAPI: Advertencias abre SNP y no ofrece LAPI, aunque se pida.
        session = self.client.session
        session[SESSION_KEY] = self.lapi.id
        session.save()
        page = self.client.get(reverse("warnings_statistics") + "?en=lapi")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.client.session[SESSION_KEY], self.snp.id)
        self.assertNotContains(page, "z-space-chip--lapi")
        # Desde una página de LAPI la pestaña sigue a la vista: la tiene quien gestiona algún equipo.
        self.assertTrue(self.client.get(reverse("rival_statistics") + "?en=lapi").context["manages_any"])

    def test_profile_lists_every_team_sheet(self):
        self.snp.own_team.team_players.create(club=self.snp, name="Edu", last_name="B", user=self.user)
        session = self.client.session
        session[SESSION_KEY] = self.lapi.id
        session.save()
        page = self.client.get(reverse("my_profile"))
        self.assertContains(page, "Mis fichas")
        self.assertContains(page, "Tu cuenta está enlazada a este jugador de Gladiadores")
        self.assertContains(page, "Tu cuenta no está enlazada a ningún jugador de Gladiadores LAPI")
        self.assertContains(page, reverse("my_player") + "?en=lapi")

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

    def test_player_in_both_chooses_team_in_club(self):
        Membership.objects.filter(user=self.user, club=self.snp).update(role=Membership.MEMBER)
        page = self.client.get(reverse("club_home"))
        self.assertContains(page, "z-space-switcher")
        self.assertNotContains(page, "Nuevo enfrentamiento")
        lapi = self.client.get(reverse("club_home") + "?en=lapi")
        self.assertEqual(lapi.context["own_team"], self.lapi.own_team)

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
            self.assertContains(page, "Categoría 500")
        self.assertContains(page, "Sin división")  # equipo LAPI sin división

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

    def _me(self):
        """Jugadores de la cuenta en SNP y LAPI, cada uno con un partido ganado en su enfrentamiento."""
        from call.models import Call
        from match.models import Game
        from players.models import Player
        players = []
        for club, match in ((self.snp, self.snp_match), (self.lapi, self.lapi_match)):
            me = Player.objects.create(club=club, user=self.user, name="Edu", last_name="B")
            mate = Player.objects.create(club=club, name="Mate", last_name=club.competition)
            Game.objects.create(match=match, n_game=1, score=1, winner="Local", draft_mode=False,
                                player_1_local=me, player_2_local=mate)
            Call.objects.create(match=match, draft_mode=False).players.add(me)
            self._close(match)
            players.append(me)
        return players

    def test_my_statistics_needs_players_in_several_spaces(self):
        # Con dos equipos y sin jugador enlazado explica cómo enlazarlo (la pestaña se ve); con uno solo: a su ficha.
        page = self.client.get(reverse("my_statistics"))
        self.assertTemplateUsed(page, "stats_mine_link.html")
        self.assertContains(page, "Mis estadísticas")
        from players.models import Player
        me = Player.objects.create(club=self.lapi, user=self.user, name="Edu", last_name="B")
        self.assertRedirects(self.client.get(reverse("my_statistics")),
                             f"{reverse('player_statistics')}?en=lapi&player={me.public_id}",
                             fetch_redirect_response=False)

    def test_my_statistics_all_counts_matches_without_mixing(self):
        self._me()
        home = self.client.get(reverse("home"))
        self.assertContains(home, f'href="{reverse("my_statistics")}"')
        page = self.client.get(reverse("my_statistics") + "?season=all")
        self.assertTemplateUsed(page, "stats_mine.html")
        self.assertEqual(page.context["me"]["played"], 2)
        rows = {r["club"]: (r["played"], r["wins"]) for r in page.context["rows"]}
        self.assertEqual(rows, {self.snp: (1, 1), self.lapi: (1, 1)})
        self.assertEqual([c["code"] for c in page.context["mine_chips"]], ["todas", "snp", "lapi"])
        chart = page.context["spaces_chart"]
        self.assertEqual([c["code"] for c in chart["comps"]], ["snp", "lapi"])
        season = self.snp_match.season
        self.assertEqual(chart["years"]["labels"], [season])
        self.assertEqual(chart["years"]["won"], [[1], [1]])
        self.assertEqual(len(chart["attendance"]["series"]), 2)
        self.assertEqual([c["code"] for c in page.context["set_rows"][0]["comps"]], ["snp", "lapi"])
        self.assertContains(page, "js/stats_spaces.js")
        # Con una temporada elegida no hay victorias por temporada, pero sí las convocatorias de esa temporada.
        chosen = self.client.get(reverse("my_statistics") + f"?season={season}")
        self.assertNotContains(chosen, "spacesYearsChart")
        self.assertContains(chosen, "spacesAttendanceChart")
        self.assertEqual(chosen.context["spaces_chart"]["attendance"]["labels"], [season])

    def test_my_statistics_of_one_competition_opens_own_sheet(self):
        me_snp, me_lapi = self._me()
        page = self.client.get(reverse("my_statistics") + "?espacio=lapi&season=all")
        self.assertRedirects(page, f"{reverse('player_statistics')}?season=all&en=lapi&player={me_lapi.public_id}",
                             fetch_redirect_response=False)
        sheet = self.client.get(page.url)
        self.assertEqual(sheet.context["current_club"], self.lapi)
        self.assertEqual([c["active"] for c in sheet.context["mine_chips"]], [False, False, True])
        # La ficha de otro jugador no lleva los chips de «Mis estadísticas».
        mate = self.lapi.players.exclude(pk=me_lapi.pk).get()
        self.assertNotIn("mine_chips", self.client.get(
            reverse("player_statistics") + f"?player={mate.public_id}").context)

    def test_player_in_every_team_sees_stats_without_player_sheet(self):
        me_snp, me_lapi = self._me()
        Membership.objects.filter(user=self.user, club=self.snp).update(role=Membership.MEMBER)
        listing = self.client.get(reverse("player_statistics") + "?en=lapi")
        self.assertContains(listing, 'name="player"')  # el apartado Jugador con su selector
        mate = self.lapi.players.exclude(pk=me_lapi.pk).get()
        sheet = self.client.get(reverse("player_statistics") + f"?en=lapi&player={mate.public_id}")
        self.assertNotContains(sheet, reverse("show_player", args=[mate.public_id]))  # sin la pestaña «Resumen»
        self.assertRedirects(self.client.get(reverse("show_player", args=[mate.public_id])),
                             f"{reverse('player_statistics')}?player={mate.public_id}", fetch_redirect_response=False)

    def test_team_statistics_never_mixes_competitions(self):
        self._close(self.snp_match)
        self._close(self.lapi_match)
        page = self.client.get(reverse("team_statistics") + "?espacio=todas&season=all")
        self.assertTemplateUsed(page, "team_statistics.html")
        self.assertEqual(page.context["current_club"], self.snp)  # el equipo que gestiona
        self.assertEqual([c["code"] for c in page.context["space_chips"]], ["snp", "lapi"])

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
