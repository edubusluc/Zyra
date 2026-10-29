"""Pruebas del informe mensual por email (data, PDF, comando, preferencias y baja)."""
import datetime
import re
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import MonthlyReportDelivery, UserPreference
from core.services import create_club
from core.unsubscribe import unsubscribe_path, unsubscribe_token, user_from_token
from match.models import Game, Match, Result
from match.monthly_pdf import render_monthly_report
from match.monthly_report import build_monthly_report, previous_month
from call.models import Call
from players.models import Player, SnpScoreHistory
from team.models import Team

User = get_user_model()
MONTH = datetime.date(2026, 9, 1)


def make_game(match, n, a, b, winner="Local", sets=((6, 4), (6, 3))):
    """Partido cerrado de la pareja (a, b) como local con su resultado."""
    game = Game.objects.create(match=match, n_game=n, player_1_local=a, player_2_local=b, winner=winner,
                               score=3 if n < 3 else 2, draft_mode=False)
    Result.objects.create(game=game, set1_local=sets[0][0], set1_visiting=sets[0][1],
                          set2_local=sets[1][0], set2_visiting=sets[1][1], draft_mode=False)
    return game


class MonthlyBase(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capi", password="pass-12345", email="capi@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.user = User.objects.create_user("ana", password="pass-12345", email="ana@example.com")
        self.ana = Player.objects.create(club=self.club, name="Ana", last_name="López", user=self.user)
        self.bea = Player.objects.create(club=self.club, name="Bea", last_name="Ruiz")
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        own = self.club.own_team
        self.match = Match.objects.create(club=self.club, local=own, visiting=self.rival, start_date=MONTH.replace(day=10),
                                          match_type=Match.ENFRENTAMIENTO, draft_mode=False)
        self.friendly = Match.objects.create(club=self.club, local=own, visiting=self.rival, start_date=MONTH.replace(day=20),
                                             match_type=Match.AMISTOSO, draft_mode=False)
        make_game(self.match, 1, self.ana, self.bea)
        make_game(self.match, 2, self.bea, self.ana, winner="Visitante", sets=((3, 6), (4, 6)))
        make_game(self.friendly, 1, self.ana, self.bea)
        # Fuera de mes: no cuenta
        other = Match.objects.create(club=self.club, local=own, visiting=self.rival, start_date=datetime.date(2026, 8, 30),
                                     match_type=Match.ENFRENTAMIENTO, draft_mode=False)
        make_game(other, 1, self.ana, self.bea)


class ReportDataTests(MonthlyBase):
    def test_previous_month(self):
        self.assertEqual(previous_month(datetime.date(2026, 10, 1)), MONTH)
        self.assertEqual(previous_month(datetime.date(2027, 1, 15)), datetime.date(2026, 12, 1))

    def test_all_matches(self):
        report = build_monthly_report(self.ana, MONTH)
        self.assertEqual((report["played"], report["wins"], report["losses"]), (3, 2, 1))
        self.assertEqual(report["pct"], 67)
        self.assertEqual(report["points"], 6)
        self.assertEqual(report["partners"][0]["name"], "BEA RUIZ")
        self.assertEqual(report["matches"], 2)
        self.assertEqual(report["streak"], ("V", 1))

    def test_competitive_scope_excludes_friendlies(self):
        report = build_monthly_report(self.ana, MONTH, "competitivos")
        self.assertEqual((report["played"], report["wins"]), (2, 1))

    def test_visiting_side_and_removed_partner(self):
        Game.objects.create(match=self.match, n_game=3, player_1_visiting=self.ana, player_2_visiting=self.bea,
                            winner="Visitante", score=2, draft_mode=False)
        self.bea.delete()
        report = build_monthly_report(self.ana, MONTH)
        self.assertEqual(report["played"], 4)
        self.assertEqual({g["partner"] for g in report["games"]}, {"BEA RUIZ"})
        self.assertEqual(report["partners"][0]["played"], 4)

    def test_no_games(self):
        self.assertEqual(build_monthly_report(self.bea, datetime.date(2026, 7, 1))["played"], 0)

    def test_pdf_renders(self):
        pdf = render_monthly_report(build_monthly_report(self.ana, MONTH))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertLessEqual(pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page "), 2)

    def test_calls_statuses_and_scope(self):
        # Apuntada y alineada, apuntada sin jugar y sin apuntarse (amistoso); la abierta no cuenta
        played = Call.objects.create(match=self.match, draft_mode=False)
        played.players.add(self.ana)
        benched_match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                             start_date=MONTH.replace(day=15), match_type=Match.ENFRENTAMIENTO,
                                             draft_mode=False)
        Call.objects.create(match=benched_match, draft_mode=False).players.add(self.ana)
        Call.objects.create(match=self.friendly, draft_mode=False)
        open_match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=MONTH.replace(day=25), match_type=Match.ENFRENTAMIENTO)
        Call.objects.create(match=open_match, draft_mode=True).players.add(self.ana)
        report = build_monthly_report(self.ana, MONTH)
        self.assertEqual([c["status"] for c in report["calls"]], ["played", "benched", "absent"])
        self.assertEqual(report["call_counts"], {"played": 1, "benched": 1, "absent": 1})
        competitive = build_monthly_report(self.ana, MONTH, "competitivos")
        self.assertEqual([c["status"] for c in competitive["calls"]], ["played", "benched"])
        self.assertTrue(render_monthly_report(report).startswith(b"%PDF"))

    def test_snp_history_of_the_month(self):
        for day, score in ((datetime.date(2026, 8, 31), 100), (datetime.date(2026, 9, 7), 120),
                           (datetime.date(2026, 9, 21), 150.5), (datetime.date(2026, 10, 1), 200)):
            SnpScoreHistory.objects.create(player=self.ana, date=day, score=score)
        report = build_monthly_report(self.ana, MONTH)
        self.assertEqual(report["snp"], [(datetime.date(2026, 9, 7), 120), (datetime.date(2026, 9, 21), 150.5)])
        self.assertTrue(render_monthly_report(report).startswith(b"%PDF"))
        # Con un solo punto o ninguno también se genera
        SnpScoreHistory.objects.filter(date=datetime.date(2026, 9, 21)).delete()
        self.assertTrue(render_monthly_report(build_monthly_report(self.ana, MONTH)).startswith(b"%PDF"))
        SnpScoreHistory.objects.all().delete()
        self.assertEqual(build_monthly_report(self.ana, MONTH)["snp"], [])

    def test_pdf_with_many_games(self):
        for i in range(30):
            m = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                     start_date=MONTH.replace(day=1 + i % 28), match_type=Match.RETO, draft_mode=False)
            make_game(m, 1, self.ana, self.bea)
        self.assertTrue(render_monthly_report(build_monthly_report(self.ana, MONTH)).startswith(b"%PDF"))


@override_settings(SITE_URL="https://zyra.example")
class CommandTests(MonthlyBase):
    def run_command(self, *args):
        out = StringIO()
        call_command("send_monthly_reports", *args, stdout=out)
        return out.getvalue()

    def test_sends_once_with_pdf_and_unsubscribe(self):
        self.run_command("--month", "2026-09")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["ana@example.com"])
        self.assertEqual(message.attachments[0][0], "informe-mensual-2026-09.pdf")
        self.assertEqual(message.attachments[0][2], "application/pdf")
        # El token lleva marca de tiempo: se valida el enlace, no se compara el texto exacto.
        link = re.search(r"https://zyra\.example(/core/monthly-report/unsubscribe/[^/\s]+/)", message.body)
        self.assertIsNotNone(link)
        token = link.group(1).rstrip("/").rsplit("/", 1)[1]
        self.assertEqual(user_from_token(token), self.user)
        self.assertIn("List-Unsubscribe", message.extra_headers)
        self.assertEqual(MonthlyReportDelivery.objects.get().sent_at is not None, True)
        # Segunda pasada: no repite
        self.run_command("--month", "2026-09")
        self.assertEqual(len(mail.outbox), 1)

    def test_one_email_with_a_pdf_per_team(self):
        lapi = create_club("Club A LAPI", "Sevilla", self.captain, competition="lapi")
        ana_lapi = Player.objects.create(club=lapi, name="Ana", last_name="López", user=self.user)
        bea_lapi = Player.objects.create(club=lapi, name="Bea", last_name="Ruiz")
        rival = Team.objects.create(club=lapi, name="Norte", location="X", in_group=True)
        match = Match.objects.create(club=lapi, local=lapi.own_team, visiting=rival, start_date=MONTH.replace(day=12),
                                     match_type="liga", draft_mode=False)
        make_game(match, 1, ana_lapi, bea_lapi)
        self.run_command("--month", "2026-09")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual([a[0] for a in message.attachments],
                         ["informe-mensual-2026-09-snp.pdf", "informe-mensual-2026-09-lapi.pdf"])
        self.assertIn("Club A (SNP)", message.body)
        self.assertIn("Club A LAPI (LAPI)", message.body)
        # Un equipo sin partidos ese mes no lleva PDF.
        mail.outbox.clear()
        MonthlyReportDelivery.objects.all().delete()
        match.delete()
        self.run_command("--month", "2026-09")
        self.assertEqual([a[0] for a in mail.outbox[0].attachments], ["informe-mensual-2026-09.pdf"])

    def test_skips_disabled_no_games_and_unlinked(self):
        UserPreference.objects.create(user=self.user, monthly_report=False)
        self.assertIn("lo desactivó", self.run_command("--month", "2026-09"))
        self.assertEqual(len(mail.outbox), 0)
        UserPreference.objects.filter(user=self.user).update(monthly_report=True)
        self.assertIn("sin partidos", self.run_command("--month", "2026-07"))
        self.assertEqual(len(mail.outbox), 0)

    def test_scope_preference_applies(self):
        UserPreference.objects.create(user=self.user, monthly_scope="competitivos")
        self.run_command("--month", "2026-09")
        self.assertIn("2 partidos", mail.outbox[0].body)

    def test_failure_is_retried(self):
        from unittest import mock
        with mock.patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=OSError("smtp")):
            with self.assertRaises(CommandError):
                self.run_command("--month", "2026-09")
        self.assertFalse(MonthlyReportDelivery.objects.exists())
        self.run_command("--month", "2026-09")
        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_sends_nothing(self):
        self.assertIn("ana@example.com", self.run_command("--month", "2026-09", "--dry-run"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(MonthlyReportDelivery.objects.exists())

    def test_manual_send_skips_idempotency_and_leaves_a_record(self):
        self.run_command("--month", "2026-09")
        out = self.run_command("--month", "2026-09", "--user", "ANA@example.com")
        self.assertIn("Enviado a mano", out)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].to, ["ana@example.com"])
        delivery = MonthlyReportDelivery.objects.get()
        self.assertEqual(delivery.manual_sends, 1)
        self.assertIsNotNone(delivery.last_manual_at)

    def test_manual_send_without_previous_delivery_or_with_opt_out(self):
        UserPreference.objects.create(user=self.user, monthly_report=False)
        self.run_command("--month", "2026-09", "--user", "ana@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(MonthlyReportDelivery.objects.get().manual_sends, 1)

    def test_manual_send_errors_and_dry_run(self):
        with self.assertRaises(CommandError):
            self.run_command("--month", "2026-09", "--user", "nadie@example.com")
        with self.assertRaises(CommandError):
            self.run_command("--month", "2026-07", "--user", "ana@example.com")
        self.assertIn("ana@example.com", self.run_command("--month", "2026-09", "--user", "ana@example.com", "--dry-run"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(MonthlyReportDelivery.objects.exists())

    def test_suspended_club_and_bad_month(self):
        self.club.suspended_at = datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc)
        self.club.save()
        self.run_command("--month", "2026-09")
        self.assertEqual(len(mail.outbox), 0)
        with self.assertRaises(CommandError):
            self.run_command("--month", "septiembre")

    @override_settings(SITE_URL="")
    def test_requires_site_url(self):
        with self.assertRaises(CommandError):
            self.run_command()


class PreferencesAndUnsubscribeTests(MonthlyBase):
    def test_profile_saves_monthly_preferences(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("my_profile"))
        self.assertTrue(page.context["monthly_report"])
        self.client.post(reverse("my_profile"), {"report_scope": "todos", "monthly_form": "1",
                                                 "monthly_scope": "competitivos"})
        self.assertEqual(UserPreference.monthly_for(self.user), (False, "competitivos"))
        self.client.post(reverse("my_profile"), {"report_scope": "todos", "monthly_form": "1",
                                                 "monthly_report": "on", "monthly_scope": "todos"})
        self.assertEqual(UserPreference.monthly_for(self.user), (True, "todos"))

    def test_unsubscribe_needs_confirmation_and_works_without_login(self):
        url = unsubscribe_path(self.user)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(UserPreference.monthly_for(self.user)[0])  # el GET no cambia nada
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserPreference.monthly_for(self.user)[0])

    def test_unsubscribe_post_requires_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.post(unsubscribe_path(self.user))
        self.assertTrue(UserPreference.monthly_for(self.user)[0])

    def test_bad_token(self):
        response = self.client.post(reverse("monthly_unsubscribe", args=[unsubscribe_token(self.user) + "x"]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(UserPreference.monthly_for(self.user)[0])
