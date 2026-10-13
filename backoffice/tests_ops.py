"""Tests de las mejoras de operación del back-office: procesos, auditoría, SQL, CRM, métricas y «Entrar como»."""
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Club, Membership
from core.services import create_club
from players.models import Player

from . import alerts, sql
from .audit import audit
from .csvsafe import csv_safe, to_csv_text
from .jobs import JobParam, JobSpec
from .models import (
    AlertState, AuditLog, ClubCrm, ClubNote, DailyActivity, DailyMetric, EmailLog, ErrorEvent, FollowUpTask,
    ImportJob, JobRun, QueryLog, SavedQuery, ScheduledJob,
)
from .scheduler import (
    execute_run, request_manual_run, run_due_jobs, scheduler_status, sync_jobs, touch_scheduler,
)

User = get_user_model()
PASSWORD = "pass-12345"


def patch_jobs(testcase, specs):
    """Sustituye JOBS por ``specs`` durante el test."""
    for target in ("backoffice.scheduler.JOBS", "backoffice.jobs.JOBS"):
        patcher = mock.patch(target, specs)
        patcher.start()
        testcase.addCleanup(patcher.stop)


class StaffTestCase(TestCase):
    """Base: una persona del personal con sesión iniciada y un club con capitán."""

    def setUp(self):
        self.staff = User.objects.create_user("staff", password=PASSWORD, is_staff=True, email="staff@example.com")
        self.captain = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain, player_name="Capi", player_last_name="Tan")
        self.client.login(username="staff", password=PASSWORD)


class QuietJobTests(TestCase):
    def setUp(self):
        patch_jobs(self, [
            JobSpec(name="idle_job", description="x", command="purge_job_runs", args=("--days", "9999"),
                    schedule="* * * * *", idle_output=("Borradas 0 ejecuciones anteriores al",)),
            JobSpec(name="quiet_job", description="x", command="clearsessions", schedule="* * * * *", idle_output=("",)),
            JobSpec(name="noisy_job", description="x", command="purge_job_runs", args=("--days", "9999"), schedule="* * * * *"),
        ])

    def test_idle_scheduled_run_leaves_no_trace_but_updates_the_job(self):
        sync_jobs()
        later = timezone.now() + datetime.timedelta(minutes=2)
        run_due_jobs(now=later)
        quiet = ScheduledJob.objects.get(name="quiet_job")
        self.assertFalse(quiet.runs.exists())
        self.assertIsNotNone(quiet.last_run_at)
        self.assertTrue(ScheduledJob.objects.get(name="noisy_job").runs.exists())

    def test_job_list_shows_last_run_without_loading_every_run(self):
        User.objects.create_user("staff", password=PASSWORD, is_staff=True)
        self.client.login(username="staff", password=PASSWORD)
        job = sync_jobs().get(name="noisy_job")
        JobRun.objects.create(job=job, started_at=timezone.now(), status=JobRun.OK, output="x" * 100)
        newest = JobRun.objects.create(job=job, started_at=timezone.now() + datetime.timedelta(seconds=5), status=JobRun.ERROR)
        from .views import _last_runs
        self.assertEqual(_last_runs([job])[job.pk].pk, newest.pk)
        self.assertEqual(self.client.get(reverse("backoffice:job_list")).status_code, 200)


class FailureNotificationTests(TestCase):
    def setUp(self):
        patch_jobs(self, [JobSpec(name="flaky", description="x", command="flaky_cmd", schedule="* * * * *")])
        User.objects.create_user("staff", password=PASSWORD, is_staff=True, email="staff@example.com")
        self.job = sync_jobs().get()

    def run_once(self, fails):
        from .scheduler import claim_job
        run = claim_job(self.job)
        with mock.patch("backoffice.scheduler.call_command", side_effect=RuntimeError("boom") if fails else None):
            execute_run(run)

    def test_only_the_first_failure_and_the_recovery_are_emailed(self):
        for _ in range(3):
            self.run_once(fails=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(ScheduledJob.objects.get(pk=self.job.pk).consecutive_failures, 3)
        self.run_once(fails=False)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("vuelve a funcionar", mail.outbox[1].subject)
        self.assertEqual(ScheduledJob.objects.get(pk=self.job.pk).consecutive_failures, 0)

    def test_reminder_after_the_interval(self):
        self.run_once(fails=True)
        ScheduledJob.objects.filter(pk=self.job.pk).update(failure_notified_at=timezone.now() - datetime.timedelta(hours=7))
        self.run_once(fails=True)
        self.assertEqual(len(mail.outbox), 2)


class SchedulerStatusTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        patch_jobs(self, [JobSpec(name="a_job", description="x", command="clearsessions", schedule="0 3 * * *")])

    def test_never_ran_then_alive_then_stale(self):
        sync_jobs()
        self.assertTrue(scheduler_status()["late"])
        self.assertIn("no ha pasado nunca", self.client.get(reverse("backoffice:health")).content.decode())
        touch_scheduler()
        self.assertFalse(scheduler_status()["late"])
        future = timezone.now() + datetime.timedelta(minutes=5)
        self.assertTrue(scheduler_status(future)["stale"])

    def test_late_job_is_named(self):
        sync_jobs()
        touch_scheduler()
        ScheduledJob.objects.update(next_run_at=timezone.now() - datetime.timedelta(minutes=30))
        status = scheduler_status()
        self.assertTrue(status["late"])
        self.assertEqual(status["late_jobs"][0]["name"], "a_job")

    @override_settings(BACKOFFICE_RUN_JOBS_INLINE=False)
    def test_run_now_is_queued_for_the_scheduler_when_it_is_alive(self):
        job = sync_jobs().get()
        touch_scheduler()
        run, state = request_manual_run(job, self.staff, ["--x"])
        self.assertEqual((run, state), (None, "queued"))
        job.refresh_from_db()
        self.assertEqual(job.run_requested_args, ["--x"])
        self.assertEqual(request_manual_run(job, self.staff)[1], "busy")
        with mock.patch("backoffice.scheduler.call_command") as command:
            runs = run_due_jobs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].trigger, JobRun.MANUAL)
        self.assertEqual(runs[0].triggered_by, self.staff)
        command.assert_called_once()
        job.refresh_from_db()
        self.assertIsNone(job.run_requested_at)

    @override_settings(BACKOFFICE_RUN_JOBS_INLINE=False)
    def test_run_now_starts_a_thread_without_scheduler(self):
        job = sync_jobs().get()
        with mock.patch("backoffice.scheduler._in_thread") as in_thread:
            run, state = request_manual_run(job, self.staff)
        self.assertEqual(state, "started")
        in_thread.assert_called_once_with(run)

    def test_run_loop_command_does_one_pass_without_loop(self):
        from io import StringIO
        out = StringIO()
        call_command("run_scheduler", stdout=out)
        self.assertIn("Nada que ejecutar", out.getvalue())
        self.assertFalse(scheduler_status()["stale"])


class TeamParamTests(StaffTestCase):
    def test_team_public_id_is_accepted(self):
        import re
        from .jobs import JOBS
        spec = next(j for j in JOBS if j.name == "complete_snp_team")
        team_id = self.club.own_team.public_id
        self.assertTrue(re.fullmatch(spec.params[0].pattern, team_id))
        self.assertTrue(re.fullmatch(spec.params[0].pattern, "123"))
        self.assertFalse(re.fullmatch(spec.params[0].pattern, "TEA; rm -rf"))


class AuditTests(StaffTestCase):
    def test_suspend_and_reactivate_are_audited(self):
        self.client.post(reverse("backoffice:club_toggle_suspended", args=[self.club.public_id]), {"action": "suspend", "reason": "spam"})
        self.client.post(reverse("backoffice:club_toggle_suspended", args=[self.club.public_id]), {"action": "reactivate"})
        logs = list(AuditLog.objects.order_by("id").values_list("action", "username", "object_id"))
        self.assertEqual(logs, [("club.suspend", "staff", self.club.public_id), ("club.reactivate", "staff", self.club.public_id)])
        self.assertEqual(AuditLog.objects.first().object_label, "Club A")

    def test_user_toggle_job_toggle_and_sql_are_audited(self):
        self.client.post(reverse("backoffice:user_toggle_active", args=[self.captain.pk]), {"action": "suspend"})
        sync_jobs()
        self.client.post(reverse("backoffice:job_toggle", args=["purge_job_runs"]))
        actions = set(AuditLog.objects.values_list("action", flat=True))
        self.assertTrue({"user.deactivate", "job.toggle"} <= actions)

    def test_sql_console_runs_are_audited_for_superusers(self):
        User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.client.login(username="root", password=PASSWORD)
        self.client.post(reverse("backoffice:sql_console"), {"action": "run", "sql": "SELECT 1"})
        self.assertTrue(AuditLog.objects.filter(action="sql.run", username="root").exists())

    def test_audit_never_breaks_the_action(self):
        with mock.patch("backoffice.audit.AuditLog.objects.create", side_effect=RuntimeError("db")):
            audit(None, "club.edit", label="x")  # no lanza

    def test_audit_page_filters(self):
        audit(None, "club.edit", label="Club Z")
        audit(None, "job.toggle", label="otro")
        page = self.client.get(reverse("backoffice:audit_list"), {"action": "club.edit"})
        self.assertContains(page, "Club Z")
        self.assertNotContains(page, "otro")

    def test_audit_records_the_impersonator_not_the_viewed_user(self):
        request = mock.Mock(user=self.captain, impersonator=self.staff, META={})
        audit(request, "club.edit", label="x")
        self.assertEqual(AuditLog.objects.get().username, "staff")


class SqlProtectionTests(TestCase):
    def test_encrypted_columns_and_row_functions_are_blocked(self):
        for query in (
            "SELECT password_encrypted AS x FROM players_snpaccount",
            "SELECT username_encrypted FROM players_snpaccount",
            "SELECT row_to_json(u) FROM auth_user u",
            "SELECT to_jsonb(u) FROM auth_user u",
            "SELECT json_object('a', password) FROM auth_user",
        ):
            with self.assertRaises(sql.QueryError, msg=query):
                sql.validate(query)

    def test_normal_queries_still_work(self):
        self.assertEqual(sql.run("SELECT 1 AS one").rows, [(1,)])
        self.assertEqual(sql.validate("SELECT name FROM core_club WHERE name = 'password'"), "SELECT name FROM core_club WHERE name = 'password'")

    def test_encrypted_columns_are_hidden_from_the_schema(self):
        names = {c["name"] for t in sql.schema() for c in t["columns"]}
        self.assertNotIn("password_encrypted", names)
        self.assertNotIn("password", names)

    def test_readonly_role_script_skips_sensitive_columns(self):
        from django.db import connection
        from .management.commands.sql_readonly_role import build_script
        if connection.vendor != "postgresql":
            self.skipTest("Solo PostgreSQL")
        script = "\n".join(build_script("zyra_ro"))
        self.assertNotIn("password_encrypted", script)
        self.assertIn('GRANT SELECT ("', script)


class CsvSafeTests(TestCase):
    def test_formula_prefixes_are_neutralised(self):
        self.assertEqual(csv_safe("=HYPERLINK(\"x\")"), "'=HYPERLINK(\"x\")")
        for text in ("+1", "-1", "@a", "\tx"):
            self.assertTrue(csv_safe(text).startswith("'"))
        self.assertEqual(csv_safe("Juan"), "Juan")
        self.assertEqual(csv_safe(-3), -3)
        self.assertEqual(csv_safe(None), "")

    def test_csv_text_has_bom_and_semicolons(self):
        text = to_csv_text(["a", "=b"], [(1, "=cmd")])
        self.assertTrue(text.startswith("﻿"))
        self.assertIn("a;'=b", text)
        self.assertIn("1;'=cmd", text)

    def test_export_escapes_formulas(self):
        User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.client.login(username="root", password=PASSWORD)
        Club.objects.create(name="=SUM(1+1)")
        response = self.client.post(reverse("backoffice:sql_console"), {"action": "export", "sql": "SELECT name FROM core_club"})
        self.assertIn("'=SUM(1+1)", response.content.decode())


class PurgeTests(TestCase):
    def test_purge_old_data(self):
        user = User.objects.create_user("u", password=PASSWORD)
        club = Club.objects.create(name="C")
        old = timezone.now() - datetime.timedelta(days=800)
        QueryLog.objects.create(user=user, sql="select 1")
        AuditLog.objects.create(action="x", username="u")
        EmailLog.objects.create(to="a@b.c", subject="s", status="sent")
        ErrorEvent.objects.create(path="/x", method="GET", status=500)
        job = ImportJob.objects.create(user=user, club=club, entity="players", mode="create", filename="f.csv", content="a;b",
                                       status=ImportJob.DONE)
        draft = ImportJob.objects.create(user=user, club=club, entity="players", mode="create", filename="d.csv", content="a;b")
        for model in (QueryLog, AuditLog, EmailLog, ErrorEvent, ImportJob):
            model.objects.update(created_at=old)
        call_command("purge_backoffice_data")
        self.assertFalse(QueryLog.objects.exists() or AuditLog.objects.exists() or EmailLog.objects.exists() or ErrorEvent.objects.exists())
        job.refresh_from_db()
        self.assertEqual(job.content, "")  # se vacía, la fila se queda
        self.assertFalse(ImportJob.objects.filter(pk=draft.pk).exists())


class EmailLogTests(TestCase):
    @override_settings(EMAIL_BACKEND="backoffice.email_backend.LoggingEmailBackend",
                       EMAIL_TRANSPORT_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_every_email_is_logged(self):
        from django.core.mail import send_mail
        send_mail("Hola", "texto", "z@example.com", ["a@example.com"])
        log = EmailLog.objects.get()
        self.assertEqual((log.to, log.subject, log.status), ("a@example.com", "Hola", "sent"))
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND="backoffice.email_backend.LoggingEmailBackend",
                       EMAIL_TRANSPORT_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="127.0.0.1", EMAIL_PORT=1)
    def test_failures_are_logged_and_raised(self):
        from django.core.mail import send_mail
        with self.assertRaises(OSError):
            send_mail("Hola", "texto", "z@example.com", ["a@example.com"])
        self.assertEqual(EmailLog.objects.get().status, "failed")
        send_mail("Hola", "texto", "z@example.com", ["a@example.com"], fail_silently=True)
        self.assertEqual(EmailLog.objects.filter(status="failed").count(), 2)

    def test_email_log_page(self):
        User.objects.create_user("staff", password=PASSWORD, is_staff=True)
        self.client.login(username="staff", password=PASSWORD)
        EmailLog.objects.create(to="x@example.com", subject="Bienvenida", status="failed", error="boom")
        page = self.client.get(reverse("backoffice:email_log"), {"status": "failed", "q": "x@"})
        self.assertContains(page, "Bienvenida")
        self.assertNotContains(self.client.get(reverse("backoffice:email_log"), {"status": "sent"}), "Bienvenida")


class ImpersonationTests(StaffTestCase):
    def start(self, reason="Reproducir el problema del capitán"):
        return self.client.post(reverse("backoffice:impersonate_start", args=[self.captain.pk]), {"reason": reason})

    def test_requires_reason_and_rejects_staff(self):
        self.start(reason="x")
        self.assertNotIn("backoffice_impersonation", self.client.session)
        other = User.objects.create_user("other", password=PASSWORD, is_staff=True)
        self.client.post(reverse("backoffice:impersonate_start", args=[other.pk]), {"reason": "motivo suficiente"})
        self.assertNotIn("backoffice_impersonation", self.client.session)
        self.assertFalse(AuditLog.objects.filter(action="impersonate.start").exists())

    def test_sees_the_site_as_the_user_and_audits_start(self):
        self.assertRedirects(self.start(), reverse("home"), fetch_redirect_response=False)
        audit_start = AuditLog.objects.get(action="impersonate.start")
        self.assertEqual((audit_start.username, audit_start.object_label, audit_start.detail["reason"]),
                         ("staff", "capi", "Reproducir el problema del capitán"))
        page = self.client.get(reverse("home"))
        self.assertContains(page, "Editando como")
        self.assertContains(page, "Club A")  # el club del capitán, no el del personal
        self.assertFalse(DailyActivity.objects.filter(user=self.captain).exists())

    def test_writes_are_allowed_and_audited_under_the_staff_member(self):
        self.start()
        response = self.client.post(reverse("create_invitation_link"), {})
        self.assertNotEqual(response.status_code, 403)
        entry = AuditLog.objects.get(action="impersonate.write")
        self.assertEqual((entry.username, entry.object_label, entry.detail["method"]), ("staff", "capi", "POST"))
        self.assertEqual(entry.detail["path"], reverse("create_invitation_link"))
        self.assertFalse(DailyActivity.objects.filter(user=self.captain).exists())
        self.client.get(reverse("home"))
        self.assertEqual(AuditLog.objects.filter(action="impersonate.write").count(), 1)

    def test_sensitive_actions_stay_blocked(self):
        self.start()
        for method, url in (
            ("post", reverse("switch_club")), ("post", reverse("leave_club")), ("post", reverse("delete_account")),
            ("post", reverse("my_profile")), ("post", reverse("snp_account_password")),
            ("get", reverse("delete_account")),
        ):
            self.assertEqual(getattr(self.client, method)(url, {}).status_code, 403, url)
        self.assertEqual(self.client.get(reverse("my_profile")).status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action="impersonate.write").exists())

    def test_stop_audits_and_restores_the_staff_session(self):
        self.start()
        response = self.client.post(reverse("backoffice:impersonate_stop"))
        self.assertRedirects(response, reverse("backoffice:user_detail", args=[self.captain.pk]), fetch_redirect_response=False)
        self.assertTrue(AuditLog.objects.filter(action="impersonate.stop").exists())
        self.assertNotContains(self.client.get(reverse("backoffice:dashboard")), "Editando como")
        self.assertEqual(self.client.get(reverse("backoffice:dashboard")).status_code, 200)

    def test_expires_after_thirty_minutes(self):
        self.start()
        session = self.client.session
        session["backoffice_impersonation"]["started"] = (timezone.now() - datetime.timedelta(minutes=31)).isoformat()
        session.save()
        self.assertEqual(self.client.get(reverse("backoffice:dashboard")).status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="impersonate.stop", detail__expired=True).exists())

    def test_get_with_side_effects_is_blocked(self):
        self.start()
        self.assertEqual(self.client.get("/core/invite/whatever/").status_code, 403)

    def test_non_staff_cannot_use_the_stop_endpoint(self):
        self.client.logout()
        self.client.login(username="capi", password=PASSWORD)
        self.assertRedirects(self.client.post(reverse("backoffice:impersonate_stop")), reverse("home"), fetch_redirect_response=False)


class CrmTests(StaffTestCase):
    def test_crm_card_notes_and_tasks(self):
        url = reverse("backoffice:club_crm_update", args=[self.club.public_id])
        self.client.post(url, {"lifecycle": "at_risk", "contact_name": "Ana", "contact_email": "ana@example.com", "contact_phone": "600"})
        crm = ClubCrm.objects.get(club=self.club)
        self.assertEqual((crm.lifecycle, crm.contact_name), ("at_risk", "Ana"))
        self.client.post(url, {"lifecycle": "active", "contact_email": "mal"})
        crm.refresh_from_db()
        self.assertEqual(crm.lifecycle, "at_risk")  # email inválido: no se guarda
        self.client.post(reverse("backoffice:club_note_add", args=[self.club.public_id]), {"text": "Llamada: contenta"})
        self.assertEqual(ClubNote.objects.get().author_name, "staff")
        self.client.post(reverse("backoffice:task_add"), {"title": "Escribir", "due_date": "2026-10-20", "club": self.club.public_id})
        task = FollowUpTask.objects.get()
        self.assertEqual((task.club, task.assigned_to), (self.club, self.staff))
        self.client.post(reverse("backoffice:task_toggle", args=[task.pk]))
        task.refresh_from_db()
        self.assertIsNotNone(task.done_at)
        detail = self.client.get(reverse("backoffice:club_detail", args=[self.club.public_id]))
        self.assertContains(detail, "Llamada: contenta")
        self.assertContains(detail, "Seguimiento (CRM)")

    def test_task_validation_and_list(self):
        self.client.post(reverse("backoffice:task_add"), {"title": "", "due_date": "no"})
        self.assertFalse(FollowUpTask.objects.exists())
        FollowUpTask.objects.create(title="Vieja", due_date=datetime.date(2020, 1, 1), assigned_to=self.staff)
        page = self.client.get(reverse("backoffice:task_list"))
        self.assertContains(page, "Vieja")
        self.assertContains(page, "Atrasada")

    def test_contact_captain_sends_email_and_leaves_a_trace(self):
        ClubCrm.objects.create(club=self.club, contact_email="ana@example.com")
        self.client.post(reverse("backoffice:club_contact", args=[self.club.public_id]), {"subject": "Hola", "body": "Qué tal <b>va</b>"})
        message = mail.outbox[0]
        self.assertEqual(set(message.to), {"capi@example.com", "ana@example.com"})
        self.assertNotIn("<b>va</b>", message.alternatives[0][0])  # el texto se escapa en el HTML
        self.assertTrue(AuditLog.objects.filter(action="club.contact").exists())
        self.assertIn("Hola", ClubNote.objects.get().text)

    def test_contact_without_content_or_recipients_fails(self):
        url = reverse("backoffice:club_contact", args=[self.club.public_id])
        self.client.post(url, {"subject": "", "body": ""})
        self.assertEqual(len(mail.outbox), 0)
        User.objects.filter(pk=self.captain.pk).update(email="")
        self.client.post(url, {"subject": "a", "body": "b"})
        self.assertEqual(len(mail.outbox), 0)

    def test_club_edit_and_delete(self):
        self.client.post(reverse("backoffice:club_edit", args=[self.club.public_id]), {"name": "Club B"})
        self.club.refresh_from_db()
        self.assertEqual(self.club.name, "Club B")
        delete = reverse("backoffice:club_delete", args=[self.club.public_id])
        self.assertEqual(self.client.post(delete, {"confirm": "Club B"}).status_code, 404)  # solo superusuarios
        User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.client.login(username="root", password=PASSWORD)
        self.client.post(delete, {"confirm": "otro"})
        self.assertTrue(Club.objects.filter(pk=self.club.pk).exists())
        self.client.post(delete, {"confirm": "club b"})
        self.assertFalse(Club.objects.filter(pk=self.club.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="club.delete").exists())

    def test_transfer_captaincy(self):
        member = User.objects.create_user("jugador", password=PASSWORD)
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        Player.objects.create(club=self.club, team=self.club.own_team, name="Ju", last_name="Gador", user=member)
        mbr = Membership.objects.get(user=member, club=self.club)
        self.client.post(reverse("backoffice:club_transfer_captain", args=[self.club.public_id]), {"membership": mbr.public_id})
        mbr.refresh_from_db()
        self.assertEqual(mbr.role, Membership.ADMIN)
        self.assertTrue(AuditLog.objects.filter(action="club.captain_transfer").exists())

    def test_password_reset_email(self):
        self.client.post(reverse("backoffice:user_password_reset", args=[self.captain.pk]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(AuditLog.objects.filter(action="user.reset_link").exists())


class SearchTests(StaffTestCase):
    def test_public_id_redirects_to_the_record(self):
        response = self.client.get(reverse("backoffice:search"), {"q": self.club.public_id})
        self.assertRedirects(response, reverse("backoffice:club_detail", args=[self.club.public_id]), fetch_redirect_response=False)
        team = self.club.own_team
        response = self.client.get(reverse("backoffice:search"), {"q": team.public_id})
        self.assertRedirects(response, reverse("backoffice:club_detail", args=[self.club.public_id]), fetch_redirect_response=False)

    def test_text_search_finds_clubs_users_and_players(self):
        page = self.client.get(reverse("backoffice:search"), {"q": "capi"})
        self.assertContains(page, "capi@example.com")
        self.assertContains(page, "CAPI TAN")
        self.assertContains(self.client.get(reverse("backoffice:search"), {"q": "club a"}), "Club A")
        self.assertContains(self.client.get(reverse("backoffice:search"), {"q": "zzzz"}), "Sin resultados")


class MetricsTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

    def test_daily_activity_is_recorded_once_per_day(self):
        self.client.login(username="capi", password=PASSWORD)
        self.client.get(reverse("home"))
        self.client.get(reverse("home"))
        self.assertEqual(DailyActivity.objects.filter(user=self.captain).count(), 1)

    def test_active_users_use_daily_activity_not_last_login(self):
        from .metrics import active_users
        today = timezone.localdate()
        DailyActivity.objects.create(user=self.captain, date=today)
        DailyActivity.objects.create(user=self.staff, date=today - datetime.timedelta(days=3))
        self.assertEqual(active_users(1), 1)
        self.assertEqual(active_users(7), 2)

    def test_snapshot_command_and_trend(self):
        DailyActivity.objects.create(user=self.captain, date=timezone.localdate())
        call_command("snapshot_daily_metrics")
        call_command("snapshot_daily_metrics")  # idempotente
        metric = DailyMetric.objects.get()
        self.assertEqual((metric.dau, metric.clubs), (1, 1))
        self.assertContains(self.client.get(reverse("backoffice:dashboard")), "Usuarios activos por día")

    def test_errors_are_recorded_with_path_and_exception(self):
        from django.core.cache import cache
        cache.clear()
        self.client.raise_request_exception = False
        with mock.patch("backoffice.views_crm.render", side_effect=RuntimeError("kaboom")):
            self.client.get(reverse("backoffice:search"), {"q": "ab"})
        event = ErrorEvent.objects.get()
        self.assertEqual((event.path, event.status), ("/backoffice/search/", 500))
        self.assertIn("kaboom", event.exception)
        load = self.client.get(reverse("backoffice:load"))
        self.assertContains(load, "/backoffice/search/")

    def test_funnel_counts_steps(self):
        from .metrics import funnel
        steps = {s["label"]: s["n"] for s in funnel()["steps"]}
        self.assertEqual(steps["Club creado"], 1)
        self.assertEqual(steps["Con un enfrentamiento"], 0)
        self.assertContains(self.client.get(reverse("backoffice:usage")), "Embudo")

    def test_attention_inbox_and_menu_counters(self):
        FollowUpTask.objects.create(title="Hoy", due_date=timezone.localdate(), assigned_to=self.staff)
        from django.core.cache import cache
        cache.delete("backoffice:menu_counters")
        page = self.client.get(reverse("backoffice:dashboard"))
        self.assertContains(page, "tareas de seguimiento para hoy")
        self.assertContains(page, "bo-count")

    def test_menu_counters_only_inside_backoffice(self):
        from .context_processors import menu_counters
        request = mock.Mock(path="/", user=self.staff)
        self.assertEqual(menu_counters(request), {})


class AlertTests(StaffTestCase):
    def test_alert_is_sent_once_reminded_and_resolved(self):
        with mock.patch("backoffice.alerts.current_problems", return_value={"reports": "Hay 2 informes fallidos"}):
            self.assertEqual(len(alerts.evaluate()), 1)
            self.assertEqual(alerts.evaluate(), [])  # sigue activa: no se repite
            AlertState.objects.update(notified_at=timezone.now() - datetime.timedelta(hours=25))
            self.assertEqual(len(alerts.evaluate()), 1)  # recordatorio
        with mock.patch("backoffice.alerts.current_problems", return_value={}):
            self.assertEqual(len(alerts.evaluate()), 1)  # resuelta
            self.assertEqual(alerts.evaluate(), [])
        self.assertEqual(len(mail.outbox), 3)

    def test_problems_detects_failing_jobs(self):
        job = ScheduledJob.objects.create(name="roto", consecutive_failures=3)
        self.assertIn("jobs", alerts.current_problems())
        job.delete()
        self.assertNotIn("jobs", alerts.current_problems())

    def test_digest_command(self):
        from io import StringIO
        out = StringIO()
        call_command("send_staff_digest", stdout=out)
        self.assertIn("Clubes nuevos", out.getvalue())
        self.assertEqual(len(mail.outbox), 1)
        call_command("send_staff_digest", "--dry-run", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)


class QueryExportTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.client.login(username="root", password=PASSWORD)

    def save(self, **extra):
        data = {"action": "save", "sql": "SELECT name FROM core_club", "name": "Clubes"}
        return self.client.post(reverse("backoffice:sql_console"), {**data, **extra})

    def test_recipients_must_be_staff(self):
        self.save(export_every="weekly", export_to="fuera@example.com")
        self.assertFalse(SavedQuery.objects.exists())
        self.save(export_every="weekly", export_to="staff@example.com, root@example.com")
        self.assertEqual(SavedQuery.objects.get().export_every, "weekly")

    def test_export_job_sends_csv_when_due(self):
        from .management.commands.send_query_exports import is_due
        self.save(export_every="daily", export_to="staff@example.com")
        query = SavedQuery.objects.get()
        self.assertTrue(is_due(query, timezone.localdate()))
        call_command("send_query_exports")
        message = mail.outbox[0]
        self.assertEqual(message.to, ["staff@example.com"])
        self.assertIn("Club A", message.attachments[0][1])
        call_command("send_query_exports")  # hoy ya se envió
        self.assertEqual(len(mail.outbox), 1)

    def test_weekly_and_monthly_schedule(self):
        from .management.commands.send_query_exports import is_due
        query = SavedQuery(name="q", sql="select 1", export_every="weekly", export_to="a@b.c")
        self.assertTrue(is_due(query, datetime.date(2026, 10, 12)))   # lunes
        self.assertFalse(is_due(query, datetime.date(2026, 10, 13)))
        query.export_every = "monthly"
        self.assertTrue(is_due(query, datetime.date(2026, 11, 1)))
        self.assertFalse(is_due(query, datetime.date(2026, 11, 2)))
