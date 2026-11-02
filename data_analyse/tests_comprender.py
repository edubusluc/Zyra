"""
Fase 4 de la auditoría de estadísticas («Comprender»): el resumen de Equipo con forma y racha, la media SNP
con su fecha de actualización y el % del equipo en la ficha del jugador.
"""
import datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from data_analyse import records
from data_analyse.tests_extra import ClubDataMixin
from players.models import SnpScoreHistory


class TeamFormTests(ClubDataMixin, TestCase):
    """Club con un empate (10/10) y una victoria (01/11) en 2025-2026."""

    def test_form_and_streak_follow_the_closed_matches(self):
        page = self.client.get(reverse("team_statistics"), {"season": "2025-2026", "match_type": "todos"})
        self.assertEqual(page.context["team_form"], {"form": ["E", "V"], "streak": {"kind": "V", "length": 1}})
        self.assertContains(page, "Racha: 1V")
        self.assertContains(page, 'title="Empate"')

    def test_balance_reads_once(self):
        page = self.client.get(reverse("team_statistics"), {"season": "2025-2026", "match_type": "todos"})
        self.assertContains(page, "de 2 enfrentamientos")
        self.assertContains(page, "st-balance-track-draw")  # hay empates: barra segmentada
        self.assertNotContains(page, "Ganados · 1 de 2")
        self.assertNotContains(page, "Media por jugador")

    def test_player_sheet_shows_the_team_percentage(self):
        page = self.client.get(reverse("player_statistics"), {"player": self.a.public_id, "season": "2025-2026"})
        # El equipo ganó 3 de 4 partidos; A ganó los dos que jugó.
        self.assertEqual(page.context["hero"]["team_pct"], 75)
        self.assertContains(page, "Equipo: 75%")


class SnpUpdateDateTests(ClubDataMixin, TestCase):
    """La fecha de la última actualización del ranking SNP y el aviso cuando pasa de seis días."""

    def _history(self, days_ago):
        date = timezone.localdate() - datetime.timedelta(days=days_ago)
        SnpScoreHistory.objects.create(player=self.a, date=date, score=40, season=self.m1.season)
        return date

    def test_fresh_update_is_not_flagged(self):
        date = self._history(2)
        snp = records.snp_ranking(self.club, self.m1.season)
        self.assertEqual((snp["updated"], snp["stale"]), (date, False))

    def test_old_update_is_flagged_in_ranking_and_sheet(self):
        date = self._history(10)
        self.assertTrue(records.snp_ranking(self.club, self.m1.season)["stale"])
        page = self.client.get(reverse("player_statistics"), {"player": self.a.public_id})
        self.assertEqual(page.context["hero"]["snp_updated"], date)
        self.assertTrue(page.context["hero"]["snp_stale"])
        self.assertContains(page, f"actualizado el {date:%d/%m}")

    def test_no_history_has_no_date(self):
        snp = records.snp_ranking(self.club, self.m1.season)
        self.assertEqual((snp["updated"], snp["stale"]), (None, False))


class SnpStaleRuleTests(SimpleTestCase):
    def test_limit_is_six_days(self):
        today = timezone.localdate()
        self.assertFalse(records.snp_is_stale(today - datetime.timedelta(days=records.SNP_STALE_DAYS)))
        self.assertTrue(records.snp_is_stale(today - datetime.timedelta(days=records.SNP_STALE_DAYS + 1)))
        self.assertFalse(records.snp_is_stale(None))
