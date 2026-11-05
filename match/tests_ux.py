"""Pruebas de la auditoría de UX: fase del enfrentamiento, «Poner resultados», cierre del acta,
convocatoria de al menos 10, crear enfrentamiento con rival y lado, y estado del jugador."""
import datetime
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from call.models import Call
from core.models import Membership
from core.services import create_club
from match import phase
from match.models import Game, Match
from players.models import Player
from team.models import Team

User = get_user_model()
PAST = datetime.date(2026, 10, 10)
FUTURE = datetime.date(2027, 3, 1)


def texts(response):
    """Mensajes que la respuesta dejó para mostrar (toasts y popups)."""
    return [str(m) for m in get_messages(response.wsgi_request)]


class UxBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("capi", email="capi@example.com", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.own = self.club.own_team
        self.rival = Team.objects.create(club=self.club, name="Rival", location="Madrid", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"Jug{i:02d}", last_name="X", snp_score=1000 - i)
                        for i in range(12)]
        self.client.login(username="capi", password="pass-12345")

    def match(self, date=PAST):
        return Match.objects.create(club=self.club, local=self.own, visiting=self.rival, start_date=date)

    def closed_call(self, match, n=12):
        call = Call.objects.create(match=match, draft_mode=False)
        call.players.set(self.players[:n])
        return call

    def lineup(self, match):
        data = [{"player1Id": self.players[2 * i].id, "player2Id": self.players[2 * i + 1].id} for i in range(5)]
        self.client.post(reverse("create_game", args=[match.public_id]), {"ordered_games": json.dumps(data)})
        return list(match.games.order_by("n_game"))

    def results_post(self, games, only=None, **extra):
        data = {}
        for g in games:
            if only is not None and g.n_game not in only:
                continue
            data.update({f"g{g.n_game}_set1_local": "6", f"g{g.n_game}_set1_visiting": "2",
                         f"g{g.n_game}_set2_local": "6", f"g{g.n_game}_set2_visiting": "3"})
        return {**data, **extra}


class PhaseTests(UxBase):
    def test_each_stage_has_one_state_and_one_next_action(self):
        match = self.match()
        self.assertEqual(phase.phase_for(match).action, phase.CREATE_CALL)
        call = Call.objects.create(match=match)
        call.players.set(self.players[:8])
        p = phase.phase_for(match)
        self.assertEqual((p.state, p.action, p.missing_players), (phase.DRAFT, phase.CLOSE_CALL, 2))
        self.assertEqual(str(p.pending_label), "Faltan 2 para cerrar la convocatoria (8 de 10)")
        self.assertEqual(str(p.label), "Convocatoria abierta")
        call.players.set(self.players[:12])
        self.assertEqual(str(phase.phase_for(match).pending_label), "Cerrar convocatoria · 12 apuntados (mín. 10)")
        call.draft_mode = False
        call.save()
        self.assertEqual(phase.phase_for(match).state, phase.CALLED)
        self.assertEqual(str(phase.phase_for(match).label), "Por alinear")
        games = self.lineup(match)
        p = phase.phase_for(match)
        self.assertEqual((p.state, p.action), (phase.LINED_UP, phase.ENTER_RESULTS))
        self.assertEqual(str(p.label), "Faltan 5 resultados")
        self.assertEqual(str(p.pending_label), "Poner resultados · faltan 5")
        self.client.post(reverse("enter_results", args=[match.public_id]), self.results_post(games))
        self.assertEqual(phase.phase_for(match).state, phase.PLAYED)
        self.assertEqual(phase.phase_for(match).action, phase.CLOSE_MATCH)
        self.assertEqual(str(phase.phase_for(match).label), "Acta por cerrar")
        self.client.post(reverse("close_match", args=[match.public_id]))
        match.refresh_from_db()
        self.assertEqual(phase.phase_for(match).state, phase.CLOSED)


class CallMinimumTests(UxBase):
    def test_call_needs_at_least_ten_players(self):
        match = self.match()
        url = reverse("create_call", args=[match.public_id])
        response = self.client.post(url, {"players": [p.id for p in self.players[:9]]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Call.objects.filter(match=match).exists())
        self.assertIn("al menos 10", " ".join(texts(response)))
        response = self.client.post(url, {"players": [p.id for p in self.players[:10]]})
        self.assertRedirects(response, reverse("call_for_match", args=[match.public_id]), fetch_redirect_response=False)
        self.assertIn("Convocatoria creada", " ".join(texts(response)))

    def test_editing_a_call_cannot_go_below_ten(self):
        match = self.match()
        call = self.closed_call(match, 10)
        call.draft_mode = True
        call.save()
        response = self.client.post(reverse("edit_call", args=[call.public_id]),
                                    {"players": [p.id for p in self.players[:9]]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(call.players.count(), 10)


class MatchPageTests(UxBase):
    def test_next_step_button_follows_the_phase(self):
        from core.models import UserPreference
        UserPreference.objects.update_or_create(user=self.user, defaults={"match_stage_view": False})
        match = self.match()
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Siguiente: Crear convocatoria")
        call = Call.objects.create(match=match)
        call.players.set(self.players[:8])
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Siguiente: Cerrar convocatoria")
        self.assertContains(page, "Faltan 2 apuntados para cerrar la convocatoria (8 de 10)")
        self.assertContains(page, "disabled")
        call.players.set(self.players[:12])
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Se enviará el informe PDF a: capi@example.com")
        call.draft_mode = False
        call.save()
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Siguiente: Alinear parejas")
        self.assertNotContains(page, 'class="btn btn-danger btn-sm"')

    def test_title_shows_teams_and_closed_page_shows_outcome_and_share(self):
        from core.models import UserPreference
        UserPreference.objects.update_or_create(user=self.user, defaults={"match_stage_view": False})
        match = self.match()
        self.closed_call(match)
        games = self.lineup(match)
        self.client.post(reverse("enter_results", args=[match.public_id]), self.results_post(games))
        self.client.post(reverse("close_match", args=[match.public_id]))
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "<h1>%s – Rival</h1>" % self.own.name)
        self.assertContains(page, "Victoria")
        self.assertContains(page, "Acta cerrada: Victoria 12-0")
        self.assertContains(page, "Compartir resultado")
        self.assertContains(page, "wa.me")

    def test_member_sees_if_he_is_called_up_and_with_whom(self):
        match = self.match()
        self.closed_call(match)
        games = self.lineup(match)
        member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.players[2].user = member
        self.players[2].save()
        self.client.force_login(member)
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Estás convocado · Partido 2 · con %s" % self.players[3].short_name)
        self.assertContains(page, '<li class="is-me"><span>Partido 2')
        self.assertContains(page, self.players[3].full_name)
        self.assertNotContains(page, "Siguiente:")
        # un jugador no convocado
        other = User.objects.create_user("otro", password="pass-12345")
        Membership.objects.create(user=other, club=self.club, role=Membership.MEMBER)
        outsider = Player.objects.create(club=self.club, name="Fuera", last_name="Y", user=other)
        self.client.force_login(other)
        self.assertContains(self.client.get(reverse("call_for_match", args=[match.public_id])), "No estás convocado")
        self.assertTrue(games)


class EnterResultsTests(UxBase):
    def setUp(self):
        super().setUp()
        self.m = self.match()
        self.closed_call(self.m)
        self.games = self.lineup(self.m)
        self.url = reverse("enter_results", args=[self.m.public_id])

    def test_page_shows_the_five_games(self):
        page = self.client.get(self.url)
        for n in range(1, 6):
            self.assertContains(page, f'name="g{n}_set1_local"')

    def test_saves_filled_games_and_leaves_empty_ones(self):
        response = self.client.post(self.url, self.results_post(self.games, only={1, 3}))
        self.assertRedirects(response, reverse("call_for_match", args=[self.m.public_id]), fetch_redirect_response=False)
        self.assertEqual([g.results.count() for g in Game.objects.filter(match=self.m).order_by("n_game")],
                         [1, 0, 1, 0, 0])
        self.assertEqual(Game.objects.get(match=self.m, n_game=1).winner, "Local")
        self.assertIn("Resultados guardados", " ".join(texts(response)))

    def test_an_invalid_game_saves_nothing(self):
        data = self.results_post(self.games, only={1, 2})
        data["g2_set1_visiting"] = "5"  # 6-5 no es un set válido
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sum(g.results.count() for g in self.games), 0)
        self.assertContains(response, "no se ha guardado nada")

    def test_save_and_close_closes_the_report(self):
        response = self.client.post(self.url, self.results_post(self.games, action="close"))
        self.assertRedirects(response, reverse("call_for_match", args=[self.m.public_id]), fetch_redirect_response=False)
        self.m.refresh_from_db()
        self.assertFalse(self.m.draft_mode)
        self.assertEqual(self.m.result_points, "12/0")
        self.assertIn("Acta cerrada: Victoria 12-0", " ".join(texts(response)))

    def test_close_with_missing_results_stays_on_the_results_page(self):
        response = self.client.post(self.url, self.results_post(self.games, only={1, 2, 3}, action="close"))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.m.refresh_from_db()
        self.assertTrue(self.m.draft_mode)
        self.assertEqual(sum(g.results.count() for g in self.games), 3)
        self.assertIn("falta el resultado de Partido 4 y Partido 5", " ".join(texts(response)))

    def test_results_page_disables_close_until_all_results_and_lists_one_game_per_row(self):
        page = self.client.get(self.url)
        self.assertContains(page, "data-close-match")
        self.assertContains(page, "data-close-hint")

    def test_competitions_only_have_draws_when_the_points_allow_it(self):
        from core.competitions import LAPI, SNP
        self.assertTrue(SNP.has_draws)
        self.assertFalse(LAPI.has_draws)

    def test_future_match_needs_confirmation_to_close(self):
        self.m.start_date = timezone.localdate() + datetime.timedelta(days=7)
        self.m.save()
        page = self.client.get(self.url)
        self.assertContains(page, "confirm_future")
        response = self.client.post(self.url, self.results_post(self.games, action="close"))
        self.m.refresh_from_db()
        self.assertTrue(self.m.draft_mode)
        self.assertIn("aún no se ha jugado", " ".join(texts(response)))
        self.client.post(self.url, self.results_post(self.games, action="close", confirm_future="1"))
        self.m.refresh_from_db()
        self.assertFalse(self.m.draft_mode)

    def test_close_match_keeps_user_on_the_match_and_requires_confirmation_for_future_dates(self):
        self.client.post(self.url, self.results_post(self.games))
        self.m.start_date = timezone.localdate() + datetime.timedelta(days=1)
        self.m.save()
        close = reverse("close_match", args=[self.m.public_id])
        response = self.client.post(close)
        self.assertRedirects(response, reverse("call_for_match", args=[self.m.public_id]), fetch_redirect_response=False)
        self.m.refresh_from_db()
        self.assertTrue(self.m.draft_mode)
        self.client.post(close, {"confirm_future": "1"})
        self.m.refresh_from_db()
        self.assertFalse(self.m.draft_mode)

    def test_single_result_form_returns_to_the_game_with_a_message(self):
        game = self.games[0]
        response = self.client.post(reverse("create_result", args=[game.public_id]), {
            "set1_local": "6", "set1_visiting": "1", "set2_local": "6", "set2_visiting": "1"})
        self.assertRedirects(response, reverse("call_for_match", args=[self.m.public_id]) + "#partido-1",
                             fetch_redirect_response=False)
        self.assertIn("Resultado del partido 1 guardado", " ".join(texts(response)))

    def test_members_cannot_use_the_results_page(self):
        member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class CreateMatchFormTests(UxBase):
    def test_rival_with_away_side_and_time_and_place(self):
        response = self.client.post(reverse("create_match"), {
            "mode": "competitivo", "match_type": Match.ENFRENTAMIENTO, "rival": self.rival.id, "own_side": "visiting",
            "start_date": "2026-11-15", "start_time": "18:30", "location": "Pista central"})
        match = Match.objects.get()
        self.assertRedirects(response, reverse("call_for_match", args=[match.public_id]), fetch_redirect_response=False)
        self.assertEqual((match.local, match.visiting), (self.rival, self.own))
        self.assertEqual(match.start_time, datetime.time(18, 30))
        self.assertEqual(match.location, "Pista central")
        self.assertIn("Enfrentamiento creado", " ".join(texts(response)))

    def test_default_place_is_the_local_team_place(self):
        self.client.post(reverse("create_match"), {
            "mode": "competitivo", "rival": self.rival.id, "own_side": "visiting", "start_date": "2026-11-15"})
        self.assertEqual(Match.objects.get().location, "Madrid")

    def test_missing_rival_shows_an_error_under_the_card(self):
        response = self.client.post(reverse("create_match"), {"mode": "competitivo", "start_date": "2026-11-15"})
        self.assertContains(response, "Elige el equipo rival")
        self.assertContains(response, "has-error")
        self.assertContains(response, "novalidate")
        self.assertFalse(Match.objects.exists())

    def test_competition_is_shown_as_data(self):
        # La competición es la del equipo: se muestra como dato, no como un selector bloqueado.
        page = self.client.get(reverse("create_match"))
        self.assertNotContains(page, 'name="competition"')
        self.assertContains(page, "z-create-in")
        self.assertContains(page, "Se creará en")
        self.assertNotContains(page, "Cambiar de equipo")
        form = page.context["form"]
        self.assertTrue(form.fields["competition"].disabled)

    def test_competition_cannot_be_tampered_with(self):
        self.client.post(reverse("create_match"), {
            "mode": "competitivo", "competition": "otra", "rival": self.rival.id, "start_date": "2026-11-15"})
        self.assertEqual(Match.objects.count(), 1)

    def test_form_has_cancel_and_report_options_folded(self):
        page = self.client.get(reverse("create_match"))
        self.assertContains(page, "Cancelar")
        self.assertContains(page, "Más opciones")


class MoreMenuMobileTests(SimpleTestCase):
    """El menú «Más» se ancla al borde derecho y se cierra con Escape/fuera (filter-menu.js)."""

    def test_mobile_menu_is_right_aligned_and_bounded(self):
        css = (Path(settings.BASE_DIR) / "static" / "style.css").read_text(encoding="utf-8")
        rule = next(line for line in css.splitlines() if line.strip().startswith(".z-more ul { bottom:"))
        self.assertIn("right: 0", rule)
        self.assertIn("max-width: calc(100vw", rule)

    def test_more_menus_close_with_escape(self):
        for name in ("match/templates/includes/ficha_more.html", "match/templates/includes/player_selector.html"):
            html = (Path(settings.BASE_DIR) / name).read_text(encoding="utf-8")
            self.assertIn('class="z-more', html)
            self.assertRegex(html, r'<details class="z-more[^"]*" data-filter-menu>')


class ClubAndSharedPiecesTests(UxBase):
    """Sección Club, temporada por defecto común, formato SNP y ficha del jugador con pestañas."""

    def test_club_hub_lists_the_four_entries(self):
        response = self.client.get(reverse("club_home"))
        self.assertEqual(response.status_code, 200)
        for name in ("club_members", "list_teams", "snp_account"):
            self.assertContains(response, f'href="{reverse(name)}"')
        self.assertEqual(response.context["nav_section"], "club")

    def test_snp_points_filter(self):
        from core.templatetags.zyra_format import snp_points
        self.assertEqual("".join(c for c in snp_points(1234.4) if c.isdigit()), "1234")
        self.assertEqual(len(snp_points(1234.4)), 5)  # con separador de miles
        self.assertEqual(snp_points(None), "Sin SNP")
        self.assertEqual(snp_points("", "–"), "–")

    def test_choose_season_remembers_last_choice(self):
        closed = self.match(datetime.date(2024, 11, 2))
        # Sin enfrentamientos cerrados las estadísticas son una sola tarjeta (sin filtro de temporada).
        Match.objects.filter(pk=closed.pk).update(draft_mode=False)
        url = reverse("team_statistics")
        self.client.get(url, {"season": "2024-2025"})
        self.assertEqual(self.client.get(url).context["selected_season"], "2024-2025")
        self.client.get(url, {"season": "all"})
        self.assertIsNone(self.client.get(url).context["selected_season"])

    def test_player_sheet_is_the_statistics_sheet(self):
        """EST-013: Plantilla y Estadísticas enlazan a una única ficha de jugador."""
        sheet = reverse("player_statistics") + f"?player={self.players[0].public_id}"
        self.assertRedirects(self.client.get(reverse("show_player", args=[self.players[0].public_id])), sheet,
                             fetch_redirect_response=False)
        response = self.client.get(sheet)
        self.assertContains(response, "st-hero")
        self.assertContains(response, reverse("edit_player", args=[self.players[0].public_id]))

    def test_team_statistics_without_pie_has_index(self):
        match = self.match()
        self.closed_call(match)
        self.lineup(match)
        response = self.client.get(reverse("team_statistics"), {"season": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "myPieChart")


class FichaPreviewTests(UxBase):
    """Previa de la ficha: escudos 3D y tarjeta central según la fase."""

    def ficha(self, m):
        return self.client.get(reverse("call_for_match", args=[m.public_id]))

    def test_crests_render_for_both_teams_with_initials_without_photo(self):
        page = self.ficha(self.match(FUTURE))
        self.assertContains(page, "z-crest-front", count=2)
        self.assertContains(page, "z-crest-back", count=2)
        self.assertContains(page, ">RI<")  # el rival sin foto muestra sus iniciales

    def test_no_card_without_a_call(self):
        self.assertNotContains(self.ficha(self.match(FUTURE)), "z-stage-card")

    def test_open_call_shows_signed_up_players(self):
        m = self.match(FUTURE)
        call = Call.objects.create(match=m, draft_mode=True)
        call.players.set(self.players[:3])
        page = self.ficha(m)
        self.assertContains(page, "is-open")
        self.assertContains(page, "Jug00")

    def test_closed_call_lists_called_players(self):
        m = self.match(FUTURE)
        self.closed_call(m)
        page = self.ficha(m)
        self.assertContains(page, "is-called")

    def test_lineup_replaces_the_call_with_pairs(self):
        m = self.match(FUTURE)
        self.closed_call(m)
        self.lineup(m)
        page = self.ficha(m)
        self.assertContains(page, "is-pairs")
        self.assertContains(page, "Jug00 X / Jug01 X")
        self.assertNotContains(page, "is-called")

    def test_long_call_lists_every_name_for_paging(self):
        m = self.match(FUTURE)
        call = Call.objects.create(match=m, draft_mode=True)
        extra = [Player.objects.create(club=self.club, name=f"Extra{i}", last_name="Z", snp_score=10 + i) for i in range(5)]
        call.players.set(self.players + extra)
        page = self.ficha(m)
        self.assertContains(page, "data-stage-list")
        self.assertContains(page, "Extra4")

    def test_own_name_is_highlighted_and_the_status_pill_says_you_signed_up(self):
        m = self.match(FUTURE)
        Call.objects.create(match=m, draft_mode=True).players.set(self.players[:3])
        Player.objects.filter(id=self.players[0].id).update(user=self.user)
        page = self.ficha(m)
        self.assertContains(page, 'class="is-me"')
        self.assertContains(page, "z-stage-me is-in")
        self.assertContains(page, "Te has apuntado")

    def test_classic_view_without_crests_or_card_when_the_switch_is_off(self):
        from core.models import UserPreference
        m = self.match(FUTURE)
        self.closed_call(m)
        UserPreference.objects.update_or_create(user=self.user, defaults={"match_stage_view": False})
        page = self.ficha(m)
        self.assertNotContains(page, "z-crest-front")
        self.assertNotContains(page, "z-stage-card")
        self.assertNotContains(page, "z-versus--stage")

    def test_profile_switch_turns_the_stage_view_off_and_on(self):
        from core.models import UserPreference
        url = reverse("my_profile")
        self.client.post(url, {"stage_form": "1"})  # casilla sin marcar
        self.assertFalse(UserPreference.match_stage_for(self.user))
        self.client.post(url, {"stage_form": "1", "match_stage_view": "on"})
        self.assertTrue(UserPreference.match_stage_for(self.user))

    def test_action_cards_link_to_the_next_steps(self):
        m = self.match(FUTURE)
        page = self.ficha(m)
        self.assertContains(page, "z-menu-card", count=5)  # cuatro fases y «Más»
        self.assertContains(page, 'href="%s"' % reverse("create_call", args=[m.public_id]))
        self.assertContains(page, "siguiente paso")

    def test_stage_view_drops_the_side_panel_and_keeps_the_preview_below_the_cards(self):
        m = self.match(FUTURE)
        page = self.ficha(m)
        self.assertNotContains(page, "z-ficha-side")
        self.assertContains(page, "z-stage-kicker")

    def test_classic_view_keeps_the_side_panel_and_phase_bar(self):
        from core.models import UserPreference
        UserPreference.objects.update_or_create(user=self.user, defaults={"match_stage_view": False})
        page = self.ficha(self.match(FUTURE))
        self.assertContains(page, "z-ficha-side")
        self.assertContains(page, "z-status4")
        self.assertNotContains(page, "z-menu-card")

    def test_close_call_is_a_card_with_the_confirmation_form(self):
        m = self.match(FUTURE)
        call = Call.objects.create(match=m, draft_mode=True)
        call.players.set(self.players[:10])
        page = self.ficha(m)
        self.assertContains(page, reverse("close_call", args=[m.public_id]))
        self.assertContains(page, "Cerrar convocatoria")
        self.assertNotContains(page, "z-next-main")  # el botón «Siguiente» ya no existe en la vista nueva

    def test_stage_view_hides_the_page_title_and_the_lists_below(self):
        m = self.match(FUTURE)
        self.closed_call(m)
        self.lineup(m)
        page = self.ficha(m)
        self.assertNotContains(page, "z-page-head")
        self.assertContains(page, '<h1 class="visually-hidden">')
        self.assertNotContains(page, "z-call-head")
        self.assertNotContains(page, "z-game-head")

    def test_head_to_head_shows_a_first_meeting_line_without_history(self):
        page = self.ficha(self.match(FUTURE))
        self.assertContains(page, "z-first-meeting")
        self.assertContains(page, "Primer enfrentamiento contra Rival")

    def test_category_is_shown_under_each_team_name(self):
        self.own.division = "1000"
        self.own.save()
        page = self.ficha(self.match(FUTURE))
        self.assertContains(page, "Local · 1000")

    def test_fallback_crest_uses_word_initials_and_a_team_hue(self):
        from core.templatetags.zyra_format import crest_hue, crest_initials
        self.assertEqual(crest_initials("Atlético Isleño"), "AI")
        self.assertEqual(crest_initials("NorthPadel"), "NO")
        self.assertEqual(crest_initials(""), "")
        self.assertEqual(crest_hue("Rival"), crest_hue("rival"))
        self.assertNotEqual(crest_hue("Rival"), crest_hue("Otro club"))
        self.assertContains(self.ficha(self.match(FUTURE)), "--h: ")

    def test_phases_are_an_ordered_list_and_unavailable_ones_are_locked(self):
        page = self.ficha(self.match(FUTURE))
        self.assertContains(page, '<ol class="z-menu">')
        self.assertContains(page, 'aria-current="step"')
        self.assertContains(page, "is-locked", count=3)  # parejas, resultados y acta aún no están disponibles
        self.assertContains(page, 'aria-disabled="true"', count=3)
        self.assertContains(page, "Cierra antes la convocatoria")

    def test_signed_up_player_sees_their_own_status_pill(self):
        m = self.match(FUTURE)
        call = Call.objects.create(match=m, draft_mode=True)
        call.players.set(self.players[:2])
        Player.objects.filter(id=self.players[0].id).update(user=self.user)
        self.assertContains(self.ficha(m), "Te has apuntado")
        call.players.remove(self.players[0])
        self.assertContains(self.ficha(m), "Todavía no te has apuntado")

    def test_stage_has_a_countdown_and_the_roster_sits_outside_the_stage(self):
        import datetime
        from django.utils import timezone
        m = self.match(timezone.localdate() + datetime.timedelta(days=3))
        call = Call.objects.create(match=m, draft_mode=True)
        call.players.set(self.players[:4])
        page = self.ficha(m)
        self.assertContains(page, "Faltan 3 días")
        html = page.content.decode()
        stage_end = html.index("z-menu")
        self.assertGreater(html.index('class="z-stage-card'), stage_end)  # la lista ya no va dentro del escenario
        m.start_date = timezone.localdate()
        m.save()
        self.assertContains(self.ficha(m), 'class="z-stage-count">Hoy')

    def test_no_countdown_for_a_played_match(self):
        self.assertNotContains(self.ficha(self.match(PAST)), "z-stage-count")
