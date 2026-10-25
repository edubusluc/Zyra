"""Pruebas del calendario mensual de Enfrentamientos y del texto de compartir para WhatsApp."""
import datetime

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Membership
from core.services import create_club
from match import month_view
from match.tests_ux import UxBase
from match.models import Match
from team.models import Team

User = get_user_model()


class MonthViewUnitTests(TestCase):
    """Cálculo de meses y semanas."""

    def test_parse_month_falls_back_to_today(self):
        today = datetime.date(2026, 10, 25)
        self.assertEqual(month_view.parse_month("2026-03", today), datetime.date(2026, 3, 1))
        for bad in ("", None, "2026-13", "2026-00", "abc", "2026-3", "0001-01"):
            self.assertEqual(month_view.parse_month(bad, today), datetime.date(2026, 10, 1))

    def test_shift_month_crosses_years(self):
        self.assertEqual(month_view.shift_month(datetime.date(2026, 1, 1), -1), datetime.date(2025, 12, 1))
        self.assertEqual(month_view.shift_month(datetime.date(2026, 12, 1), 1), datetime.date(2027, 1, 1))

    def test_weeks_start_on_monday_and_cover_the_month(self):
        weeks = month_view.month_weeks(datetime.date(2026, 11, 1))
        self.assertEqual(weeks[0][0].weekday(), 0)
        self.assertTrue(all(len(w) == 7 for w in weeks))
        self.assertIn(datetime.date(2026, 11, 30), [d for w in weeks for d in w])


class CalendarViewTests(UxBase):
    """Vista del calendario: contenido, permisos y que no envíe nada."""

    def test_current_month_lists_matches_with_links(self):
        today = timezone.localdate()
        match = self.match(today.replace(day=15))
        page = self.client.get(reverse("calendar_match"))
        self.assertContains(page, reverse("call_for_match", args=[match.public_id]))
        self.assertContains(page, "Rival")

    def test_month_param_shows_that_month_only(self):
        self.match(datetime.date(2026, 11, 14))
        self.match(datetime.date(2026, 12, 5))
        nov = self.client.get(reverse("calendar_match"), {"month": "2026-11"})
        self.assertContains(nov, "14")
        self.assertEqual(len(nov.context["agenda"]), 1)
        self.assertEqual(nov.context["month_prev"], "2026-10")
        self.assertEqual(nov.context["month_next"], "2026-12")
        self.assertEqual(self.client.get(reverse("calendar_match"), {"month": "basura"}).status_code, 200)

    def test_event_states(self):
        today = timezone.localdate()
        self.match(today)  # próximo: acta abierta y fecha de hoy en adelante
        Match.objects.create(club=self.club, local=self.own, rival_name="Amigos", start_date=today, match_type=Match.AMISTOSO)
        html = self.client.get(reverse("calendar_match")).content.decode()
        self.assertIn("z-cal-event is-upcoming", html)
        self.assertIn("is-friendly", html)
        past = self.match(today - datetime.timedelta(days=40))
        self.assertIn("z-cal-event is-open", self.client.get(
            reverse("calendar_match"), {"month": past.start_date.strftime("%Y-%m")}).content.decode())

    def test_played_match_shows_score(self):
        match = Match.objects.create(club=self.club, local=self.own, visiting=self.rival, start_date=datetime.date(2026, 5, 9),
                                     draft_mode=False, result="Victoria Local", result_points="8/4")
        page = self.client.get(reverse("calendar_match"), {"month": "2026-05"})
        self.assertContains(page, "8-4")
        self.assertContains(page, reverse("call_for_match", args=[match.public_id]))

    def test_other_clubs_matches_are_not_shown(self):
        other = User.objects.create_user("otro", password="pass-12345")
        club_b = create_club("Club B", "Madrid", other)
        rival_b = Team.objects.create(club=club_b, name="Ajeno B", location="X", in_group=True)
        Match.objects.create(club=club_b, local=club_b.own_team, visiting=rival_b, start_date=datetime.date(2026, 5, 9))
        self.assertNotContains(self.client.get(reverse("calendar_match"), {"month": "2026-05"}), "Ajeno B")

    def test_members_can_see_it_and_anonymous_cannot(self):
        member = User.objects.create_user("miembro", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.login(username="miembro", password="pass-12345")
        self.assertEqual(self.client.get(reverse("calendar_match")).status_code, 200)
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("calendar_match")).status_code, 200)

    def test_post_is_not_allowed_and_nothing_is_sent(self):
        self.assertEqual(self.client.post(reverse("calendar_match")).status_code, 405)
        self.client.get(reverse("calendar_match"))
        self.assertEqual(len(mail.outbox), 0)

    def test_tabs_link_list_and_calendar(self):
        self.assertContains(self.client.get(reverse("list_match")), reverse("calendar_match"))
        self.assertContains(self.client.get(reverse("calendar_match")), reverse("list_match"))


class ShareTextTests(UxBase):
    """Texto de «Compartir resultado» pensado para WhatsApp."""

    def closed_match(self):
        match = self.match()
        self.closed_call(match)
        games = self.lineup(match)
        self.client.post(reverse("enter_results", args=[match.public_id]), self.results_post(games))
        self.client.post(reverse("close_match", args=[match.public_id]))
        return match

    def share(self, match):
        return self.client.get(reverse("call_for_match", args=[match.public_id])).context["share_text"]

    def test_text_has_bold_headline_games_and_footer(self):
        text = self.share(self.closed_match())
        lines = text.split("\n")
        self.assertEqual(lines[0], "✅ *Victoria 12-0* contra Rival")
        self.assertIn("Rival", lines[1])
        self.assertIn("10/10/2026", lines[1])
        self.assertIn("✅ *Partido 1* ·", text)
        self.assertIn("6-2 6-3", text)
        self.assertEqual(lines[-1], "Hecho con Zyra")
        self.assertNotIn("Amistoso", text)

    def test_friendly_is_marked(self):
        match = self.closed_match()
        Match.objects.filter(pk=match.pk).update(match_type=Match.AMISTOSO)
        match.refresh_from_db()
        self.assertIn("Amistoso", self.share(match).split("\n")[1])
