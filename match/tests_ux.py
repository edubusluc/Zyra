"""Pruebas de la auditoría de UX: fase del enfrentamiento, «Poner resultados», cierre del acta,
convocatoria de al menos 10, crear enfrentamiento con rival y lado, y estado del jugador."""
import datetime
import json

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
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
        self.assertIn("8/10", str(p.pending_label))
        call.players.set(self.players[:12])
        call.draft_mode = False
        call.save()
        self.assertEqual(phase.phase_for(match).state, phase.CALLED)
        games = self.lineup(match)
        p = phase.phase_for(match)
        self.assertEqual((p.state, p.action), (phase.LINED_UP, phase.ENTER_RESULTS))
        self.client.post(reverse("enter_results", args=[match.public_id]), self.results_post(games))
        self.assertEqual(phase.phase_for(match).state, phase.PLAYED)
        self.assertEqual(phase.phase_for(match).action, phase.CLOSE_MATCH)
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
        match = self.match()
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Siguiente: Crear convocatoria")
        call = Call.objects.create(match=match)
        call.players.set(self.players[:8])
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Siguiente: Cerrar convocatoria")
        self.assertContains(page, "Faltan 2 convocados")
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
        self.assertContains(page, "Estás convocado")
        self.assertContains(page, "Partido 2")
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

    def test_competition_selector_is_locked_on_snp(self):
        page = self.client.get(reverse("create_match"))
        self.assertContains(page, 'name="competition"')
        self.assertContains(page, "disabled")
        self.assertContains(page, '<option value="snp" selected>SNP</option>', html=True)
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

    def test_player_card_has_tabs_and_form(self):
        response = self.client.get(reverse("show_player", args=[self.players[0].public_id]))
        self.assertContains(response, reverse("player_statistics") + f"?player={self.players[0].public_id}")
        self.assertContains(response, 'aria-current="page"')
        self.assertEqual(response.context["form"], [])

    def test_team_statistics_without_pie_has_index(self):
        match = self.match()
        self.closed_call(match)
        self.lineup(match)
        response = self.client.get(reverse("team_statistics"), {"season": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "myPieChart")
