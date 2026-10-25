"""Tests del cara a cara por rival: balance, ficha, «Previa» y aislamiento entre clubes."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.services import create_club
from data_analyse import rivals
from match.models import Game, Match
from players.models import Player
from team.models import Team

User = get_user_model()


class RivalsBase(TestCase):
    """Club con tres enfrentamientos contra «Norte» (G, G, P), uno contra «Sur» y un amistoso escrito a mano."""

    def setUp(self):
        self.user = User.objects.create_user("cap", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.own = self.club.own_team
        self.norte = Team.objects.create(club=self.club, name="Norte", location="X", in_group=True, division="1000")
        self.sur = Team.objects.create(club=self.club, name="Sur", location="X", in_group=True, division="1000")
        mk = lambda n: Player.objects.create(club=self.club, name=n, last_name=f"{n}son", joined_season="2020-2021")  # noqa: E731
        self.a, self.b = mk("A"), mk("B")
        self.client.login(username="cap", password="pass-12345")

    def match(self, rival, day, own_points, rival_points, own_local=True, games=(), **extra):
        """Enfrentamiento cerrado; ``games`` son (n, pareja_gana)."""
        result = "Victoria Local" if (own_points > rival_points) == own_local else "Victoria Visitante"
        if own_points == rival_points:
            result = "EMPATE"
        local, visiting = (self.own, rival) if own_local else (rival, self.own)
        points = f"{own_points}/{rival_points}" if own_local else f"{rival_points}/{own_points}"
        m = Match.objects.create(club=self.club, local=local, visiting=visiting, start_date=day, draft_mode=False,
                                 result=result, result_points=points, **extra)
        side = "local" if own_local else "visiting"
        for n, won in games:
            winner = ("Local" if own_local else "Visitante") if won else ("Visitante" if own_local else "Local")
            Game.objects.create(match=m, n_game=n, score=3, winner=winner, draft_mode=False,
                                **{f"player_1_{side}": self.a, f"player_2_{side}": self.b})
        return m

    def seed(self):
        self.m1 = self.match(self.norte, datetime.date(2025, 10, 4), 8, 4, games=[(1, True), (2, True)])
        self.m2 = self.match(self.norte, datetime.date(2025, 11, 8), 7, 5, own_local=False, games=[(1, True)])
        self.m3 = self.match(self.norte, datetime.date(2026, 1, 10), 2, 10, games=[(1, False)])
        self.match(self.sur, datetime.date(2026, 2, 7), 6, 6)
        self.friendly = Match.objects.create(
            club=self.club, local=self.own, visiting=None, rival_name="Amigos de Pedro", start_date=datetime.date(2026, 3, 1),
            draft_mode=False, result="Victoria Local", result_points="7/3", match_type=Match.AMISTOSO)


class RivalsTests(RivalsBase):
    """Lógica de data_analyse.rivals."""

    def test_summary_balance_and_sort(self):
        self.seed()
        rows = {r["label"]: r for r in rivals.rival_summary(self.club)}
        norte = rows["Norte"]
        self.assertEqual((norte["played"], norte["won"], norte["drawn"], norte["lost"]), (3, 2, 0, 1))
        self.assertEqual((norte["points_for"], norte["points_against"]), (17, 19))
        self.assertEqual(norte["last"]["outcome"], "D")
        self.assertEqual(norte["streak"], "VVD")
        self.assertEqual(rows["Sur"]["drawn"], 1)
        self.assertTrue(rows["Amigos de Pedro"]["friendly_only"])
        by_balance = [r["label"] for r in rivals.rival_summary(self.club, sort=rivals.SORT_BALANCE)]
        self.assertEqual(by_balance[0], "Norte")  # mismo balance neto que el amistoso, más enfrentamientos
        by_last = [r["label"] for r in rivals.rival_summary(self.club, sort=rivals.SORT_LAST)]
        self.assertEqual(by_last[0], "Amigos de Pedro")

    def test_filters_by_season_and_type(self):
        self.seed()
        labels = lambda **kw: {r["label"] for r in rivals.rival_summary(self.club, **kw)}  # noqa: E731
        self.assertEqual(labels(season="2025-2026"), {"Norte", "Sur", "Amigos de Pedro"})
        self.assertNotIn("Amigos de Pedro", labels(match_type="competitivo"))
        self.assertEqual(labels(match_type="amistoso"), {"Amigos de Pedro"})

    def test_hand_written_names_group_ignoring_case(self):
        for day, name in ((1, "Los Linces"), (8, "los linces ")):
            Match.objects.create(club=self.club, local=self.own, rival_name=name, start_date=datetime.date(2025, 10, day),
                                 draft_mode=False, result="Victoria Local", result_points="7/5", match_type=Match.AMISTOSO)
        rows = rivals.rival_summary(self.club)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["played"], 2)

    def test_open_matches_do_not_count(self):
        Match.objects.create(club=self.club, local=self.own, visiting=self.norte, start_date=datetime.date(2025, 10, 1))
        self.assertEqual(rivals.rival_summary(self.club), [])

    def test_same_name_in_two_divisions_is_two_rivals(self):
        norte500 = Team.objects.create(club=self.club, name="Norte", location="X", in_group=True, division="500")
        self.match(self.norte, datetime.date(2025, 10, 4), 8, 4)
        self.match(norte500, datetime.date(2025, 10, 11), 8, 4)
        self.assertEqual(len(rivals.rival_summary(self.club)), 2)

    def test_detail_best_pairs_and_history(self):
        self.seed()
        players = list(Player.objects.filter(club=self.club))
        detail = rivals.rival_detail(self.club, players, team=self.norte)
        self.assertEqual(detail["played"], 3)
        self.assertEqual([e["date"] for e in detail["history"]][0], datetime.date(2026, 1, 10))
        self.assertEqual(len(detail["best_pairs"]), 1)
        self.assertEqual((detail["best_pairs"][0]["wins"], detail["best_pairs"][0]["played"]), (3, 4))
        self.assertIsNone(rivals.rival_detail(self.club, players, name="Nadie"))

    def test_preview_only_with_history(self):
        self.seed()
        nxt = Match.objects.create(club=self.club, local=self.own, visiting=self.norte, start_date=datetime.date(2026, 5, 1))
        preview = rivals.rival_preview(nxt)
        self.assertEqual((preview["won"], preview["lost"]), (2, 1))
        self.assertEqual(preview["last"]["outcome"], "D")
        self.assertIsNotNone(preview["best_pair"])
        new_rival = Team.objects.create(club=self.club, name="Nuevo", location="X", in_group=True)
        fresh = Match.objects.create(club=self.club, local=self.own, visiting=new_rival, start_date=datetime.date(2026, 5, 8))
        self.assertIsNone(rivals.rival_preview(fresh))

    def test_preview_ignores_later_matches(self):
        self.seed()
        early = Match.objects.create(club=self.club, local=self.own, visiting=self.norte, start_date=datetime.date(2025, 9, 1))
        self.assertIsNone(rivals.rival_preview(early))


class RivalViewsTests(RivalsBase):
    """Vistas: pestaña, ficha, «Previa» en las pantallas del enfrentamiento y aislamiento."""

    def test_list_view_and_tab(self):
        self.seed()
        response = self.client.get(reverse("rival_statistics"))
        self.assertContains(response, "Norte")
        self.assertContains(response, "Amistoso")
        self.assertContains(response, reverse("rival_statistics"))  # pestaña en el menú de estadísticas
        self.assertEqual(self.client.get(reverse("rival_statistics"), {"sort": "balance"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("rival_statistics"), {"sort": "x"}).status_code, 200)

    def test_zero_state(self):
        self.assertContains(self.client.get(reverse("rival_statistics")), "Cierra tu primer enfrentamiento")

    def test_detail_view(self):
        self.seed()
        response = self.client.get(reverse("rival_detail"), {"team": self.norte.public_id})
        self.assertContains(response, "Norte")
        self.assertContains(response, reverse("call_for_match", args=[self.m1.public_id]))
        named = self.client.get(reverse("rival_detail"), {"name": "Amigos de Pedro"})
        self.assertContains(named, "Amigos de Pedro")

    def test_detail_requires_rival_and_club(self):
        self.seed()
        self.assertEqual(self.client.get(reverse("rival_detail")).status_code, 404)
        other = User.objects.create_user("otro", password="pass-12345")
        club_b = create_club("Club B", "Madrid", other)
        foreign = Team.objects.create(club=club_b, name="Ajeno", location="X", in_group=True)
        self.assertEqual(self.client.get(reverse("rival_detail"), {"team": foreign.public_id}).status_code, 404)

    def test_clubs_are_isolated(self):
        self.seed()
        other = User.objects.create_user("otro", password="pass-12345")
        create_club("Club B", "Madrid", other)
        self.client.login(username="otro", password="pass-12345")
        self.assertNotContains(self.client.get(reverse("rival_statistics")), "Norte")

    def test_preview_block_on_match_and_call_pages(self):
        self.seed()
        nxt = Match.objects.create(club=self.club, local=self.own, visiting=self.norte, start_date=datetime.date(2026, 5, 1))
        for url in (reverse("call_for_match", args=[nxt.public_id]), reverse("create_call", args=[nxt.public_id])):
            self.assertContains(self.client.get(url), "Previa", msg_prefix=url)
        fresh = Match.objects.create(club=self.club, local=self.own, visiting=Team.objects.create(
            club=self.club, name="Nuevo", location="X", in_group=True), start_date=datetime.date(2026, 5, 8))
        self.assertNotContains(self.client.get(reverse("call_for_match", args=[fresh.public_id])), "z-preview")

    def test_query_count_does_not_grow_with_rivals(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.seed()

        def queries():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse("rival_statistics"))
            return len(ctx)
        queries()  # la primera petición calienta cachés
        before = queries()
        for i in range(5):
            rival = Team.objects.create(club=self.club, name=f"Extra {i}", location="X", in_group=True)
            self.match(rival, datetime.date(2026, 4, 1 + i), 8, 4)
        self.assertEqual(queries(), before)
