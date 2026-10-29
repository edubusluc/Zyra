"""
Enfrentamientos LAPI (espacios, fases 1b y 1c): tipos propios (Liga, Playoffs, Fase final), jornada,
puntos de liga (4, 3 o 1), la regla de las fases finales (mínimo de enfrentamientos de liga),
«No presentado», lesión completada para la pareja sana y las estadísticas que no aplican.
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.services import create_club
from match.forms import MatchForm
from match.league import finals_shortfall, season_league_points
from call.models import Call
from data_analyse.attendance import signup_attendance
from match.models import Game, Match, Result
from players.models import Player
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"


class LapiMatchTests(TestCase):
    """Capitán de un equipo LAPI con una plantilla de 7."""

    def setUp(self):
        self.user = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.club = create_club("Gladiadores LAPI", "Sevilla", self.user, competition="lapi")
        self.rival = Team.objects.create(club=self.club, name="Padel Norte", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, team=self.club.own_team, name=f"J{i}", last_name="L")
                        for i in range(7)]
        self.client.login(username="capi", password=PASSWORD)
        self.day = datetime.date(2026, 10, 10)

    def _match(self, match_type=Match.LIGA, days=0, **extra):
        return Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                    start_date=self.day + datetime.timedelta(days=days), match_type=match_type, **extra)

    def _close(self, match, own, rival, pairs=None):
        """Cierra ``match`` con ``own``-``rival`` partidos y las parejas ``pairs`` (por defecto 0-1, 2-3, 4-5)."""
        pairs = pairs or [(0, 1), (2, 3), (4, 5)]
        for n, (a, b) in enumerate(pairs, start=1):
            Game.objects.create(match=match, n_game=n, score=1, draft_mode=False,
                                winner="Local" if n <= own else "Visitante",
                                player_1_local=self.players[a], player_2_local=self.players[b])
        match.result_points = f"{own}/{rival}"
        match.result = "Victoria Local" if own > rival else "Victoria Visitante"
        match.draft_mode = False
        match.save()
        return match

    def test_form_offers_lapi_types_and_round(self):
        form = MatchForm(club=self.club)
        self.assertEqual([v for v, _l in form.fields['match_type'].choices], ["liga", "playoff", "fase_final"])
        self.assertEqual(form.initial['match_type'], "liga")
        self.assertIn('round_number', form.fields)
        self.assertNotIn('round_number', MatchForm(club=create_club("SNP", "Sevilla", self.user)).fields)
        page = self.client.get(reverse("create_match"))
        self.assertContains(page, "Playoffs")
        self.assertContains(page, "data-round-row")
        self.assertNotContains(page, ">Reto<")

    def test_round_only_kept_in_league(self):
        data = {"mode": "competitivo", "match_type": "playoff", "round_number": "4", "rival": self.rival.pk,
                "own_side": "local", "start_date": "2026-11-01", "location": "X"}
        form = MatchForm(data, club=self.club)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["round_number"])
        form = MatchForm({**data, "match_type": "liga"}, club=self.club)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["round_number"], 4)

    def test_league_points(self):
        self.assertEqual(self._close(self._match(), 3, 0).league_points, 4)
        self.assertEqual(self._close(self._match(days=7), 2, 1).league_points, 3)
        self.assertEqual(self._close(self._match(days=14), 1, 2).league_points, 1)
        self.assertIsNone(self._close(self._match(Match.PLAYOFF, days=21), 3, 0).league_points)
        self.assertIsNone(self._match(days=28).league_points)  # acta abierta
        league = season_league_points(self.club, "2026-2027")
        self.assertEqual((league["total"], league["played"]), (8, 3))
        page = self.client.get(reverse("team_statistics") + "?season=2026-2027")
        self.assertContains(page, "Puntos de liga")

    def test_type_label_and_round_in_list(self):
        self._match(Match.PLAYOFF)
        self._match(days=3, round_number=5)
        page = self.client.get(reverse("list_match") + "?season=all")
        self.assertContains(page, "Playoffs")
        self.assertContains(page, "Jornada 5")
        self.assertNotContains(page, "Play Off<")

    def test_finals_rule_needs_two_league_matches(self):
        # J0..J5 juegan dos jornadas; J6, ninguna.
        self._close(self._match(), 2, 1)
        self._close(self._match(days=7), 2, 1)
        final = self._match(Match.PLAYOFF, days=14)
        short = finals_shortfall(final, self.players)
        self.assertEqual([(p, n) for p, n in short], [(self.players[6], 0)])
        self.assertEqual(finals_shortfall(self._match(days=21), self.players), [])  # liga: sin regla
        url = reverse("create_call", args=[final.public_id])
        page = self.client.get(url)
        self.assertContains(page, "z-finals-rule")
        ids = [str(p.id) for p in self.players]
        page = self.client.post(url, {"players": ids})
        self.assertContains(page, "Convocarlos igualmente")
        self.assertFalse(Call.objects.filter(match=final).exists())
        self.client.post(url, {"players": ids, "force_finals": "1"})
        self.assertTrue(Call.objects.filter(match=final).exists())

    def test_existing_lapi_matches_become_league(self):
        from importlib import import_module
        from django.apps import apps
        match = self._match(Match.ENFRENTAMIENTO)
        import_module("match.migrations.0015_match_lapi_types_round").lapi_types(apps, None)
        match.refresh_from_db()
        self.assertEqual(match.match_type, Match.LIGA)

    def test_no_show_rival_closes_with_full_win(self):
        match = self._match()
        call = Call.objects.create(match=match, draft_mode=False)
        call.players.set(self.players)
        Game.objects.create(match=match, n_game=1, score=1, player_1_local=self.players[0], player_2_local=self.players[1])
        self.client.post(reverse("mark_no_show", args=[match.public_id]), {"side": "rival"})
        match.refresh_from_db()
        self.assertEqual((match.no_show, match.draft_mode, match.result_points), ("rival", False, "3/0"))
        self.assertEqual(match.league_points, 4)
        self.assertFalse(match.games.exists())  # no cuenta para jugadores ni parejas
        self.assertIsNone(signup_attendance(self.club, match.season)["average"])  # ni para la asistencia
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "No presentado: Padel Norte")
        self.assertContains(page, "Quitar no presentado")
        self.assertNotContains(page, "Reabrir acta")
        self.client.post(reverse("undo_no_show", args=[match.public_id]))
        match.refresh_from_db()
        self.assertEqual((match.no_show, match.draft_mode, match.result_points), ("", True, "NONE"))

    def test_no_show_own_gives_zero_league_points(self):
        match = self._match(days=3)
        self.assertContains(self.client.get(reverse("call_for_match", args=[match.public_id])), "No nos presentamos")
        self.client.post(reverse("mark_no_show", args=[match.public_id]), {"side": "own"})
        match.refresh_from_db()
        self.assertEqual((match.result_points, match.result, match.league_points), ("0/3", "Victoria Visitante", 0))
        self.assertEqual(season_league_points(self.club, match.season)["total"], 0)

    def test_no_show_only_in_competitions_that_have_it(self):
        other = User.objects.create_user("snp", password=PASSWORD, email="snp@example.com")
        snp = create_club("SNP", "Sevilla", other)
        rival = Team.objects.create(club=snp, name="Rival", location="X", in_group=True)
        match = Match.objects.create(club=snp, local=snp.own_team, visiting=rival, start_date=self.day)
        self.client.login(username="snp", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("call_for_match", args=[match.public_id])), "No nos presentamos")
        self.client.post(reverse("mark_no_show", args=[match.public_id]), {"side": "rival"})
        match.refresh_from_db()
        self.assertEqual(match.no_show, "")
        self.assertTrue(match.draft_mode)

    def test_injury_completes_games_for_healthy_pair(self):
        match = self._match()
        game = Game.objects.create(match=match, n_game=1, score=1, player_1_local=self.players[0], player_2_local=self.players[1])
        result = Result(game=game, set1_local=6, set1_visiting=4, set2_local=3, set2_visiting=2, retired=True, injured_side="local")
        result.result = result.determine_winner()
        result.save()
        self.assertEqual(result.sets(), [(6, 4), (3, 6), (0, 6)])
        self.assertEqual(result.result, "Victoria Visitante")
        page = self.client.get(reverse("edit_result", args=[game.public_id]))
        self.assertContains(page, "¿Qué pareja se lesionó?")

    def test_lapi_statistics_hide_order_based_charts(self):
        self._close(self._match(), 2, 1)
        page = self.client.get(reverse("team_statistics") + "?season=2026-2027")
        self.assertContains(page, "Partidos y sets")
        self.assertNotContains(page, "Por número de partido")
        self.assertNotContains(page, "Balance de partidos por jugador")
        page = self.client.get(reverse("player_statistics") + f"?player={self.players[0].public_id}&season=2026-2027")
        self.assertContains(page, "Sets clutch")
        self.assertNotContains(page, "Por número de partido")

    def test_injury_from_all_results_screen(self):
        match = self._match()
        Call.objects.create(match=match, draft_mode=False).players.set(self.players)
        games = [Game.objects.create(match=match, n_game=n, score=1, player_1_local=self.players[2 * n - 2],
                                     player_2_local=self.players[2 * n - 1]) for n in (1, 2, 3)]
        url = reverse("enter_results", args=[match.public_id])
        page = self.client.get(url)
        self.assertContains(page, 'name="g1_injured_side"')
        self.assertNotContains(page, "{#")
        self.client.post(url, {"g1_set1_local": "1", "g1_set1_visiting": "6", "g1_set2_local": "2",
                               "g1_set2_visiting": "3", "g1_retired": "on", "g1_injured_side": "visiting",
                               "action": "save"})
        result = Result.objects.get(game=games[0])
        self.assertEqual(result.sets(), [(1, 6), (6, 3), (6, 0)])
        self.assertEqual((result.retired, result.injured_side, result.result), (True, "visiting", "Victoria Local"))
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Lesión · Padel Norte")
