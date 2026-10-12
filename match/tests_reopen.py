"""Tests de los resultados estándar y de la reapertura del acta."""
import datetime

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.services import create_club
from match import outcomes
from match.models import Match
from players.models import SEASON_START_MONTH
from team.models import Team

User = get_user_model()


class OutcomesTests(SimpleTestCase):
    """Valores canónicos de resultado."""

    def test_from_points(self):
        """Los puntos deciden el resultado."""
        self.assertEqual(outcomes.from_points(3, 2), outcomes.LOCAL_WIN)
        self.assertEqual(outcomes.from_points(2, 3), outcomes.VISITING_WIN)
        self.assertEqual(outcomes.from_points(2, 2), outcomes.DRAW)

    def test_season_starts_in_august(self):
        """La temporada empieza el 1 de agosto."""
        self.assertEqual(SEASON_START_MONTH, 8)


class ReopenMatchTests(TestCase):
    """Reabrir un acta cerrada."""

    def setUp(self):
        """Club con un enfrentamiento cerrado."""
        self.captain = User.objects.create_user("capitan", "c@example.com", "pass-12345")
        self.club = create_club("Club", "Sevilla", self.captain, gender="M")
        rival = Team.objects.create(club=self.club, name="Rival", location="Huelva")
        self.match = Match.objects.create(
            club=self.club, local=self.club.own_team, visiting=rival, start_date=datetime.date(2026, 10, 1),
            draft_mode=False, result=outcomes.LOCAL_WIN, result_points="4-2",
        )

    def test_reopen_sets_draft_and_records_who(self):
        """El acta vuelve a borrador y queda anotado quién la reabrió."""
        self.client.force_login(self.captain)
        response = self.client.post(reverse("reopen_match", args=[self.match.public_id]))
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        self.assertTrue(self.match.draft_mode)
        self.assertEqual(self.match.result, outcomes.NONE)
        self.assertEqual(self.match.reopened_by, self.captain)
        self.assertIsNotNone(self.match.reopened_at)

    def test_reopen_requires_post(self):
        """Un GET no reabre nada."""
        self.client.force_login(self.captain)
        self.client.get(reverse("reopen_match", args=[self.match.public_id]))
        self.match.refresh_from_db()
        self.assertFalse(self.match.draft_mode)
