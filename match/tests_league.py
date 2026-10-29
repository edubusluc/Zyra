"""
Enfrentamientos LAPI (espacios, fase 1b): tipos propios (Liga, Playoffs, Fase final), jornada,
puntos de liga (4, 3 o 1) y la regla de las fases finales (mínimo de enfrentamientos de liga).
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.services import create_club
from match.forms import MatchForm
from match.league import finals_shortfall, season_league_points
from match.models import Game, Match
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
        from call.models import Call
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
