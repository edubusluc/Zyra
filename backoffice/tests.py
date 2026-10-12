import datetime

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Club, Invitation, Membership
from core.services import create_club
from match.models import Match
from players.models import Player
from team.models import Team

from .metrics import dashboard_kpis, load_metrics, online_users, signups_by_week
from .middleware import flush_metrics
from .models import JobRun, RequestMetric, ScheduledJob, UserActivity

User = get_user_model()

PAGES = [
    ("backoffice:dashboard", []),
    ("backoffice:club_list", []),
    ("backoffice:user_list", []),
    ("backoffice:load", []),
    ("backoffice:job_list", []),
    ("backoffice:run_list", []),
    ("backoffice:usage", []),
    ("backoffice:health", []),
]


class BackofficeAccessTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user("member", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.member)

    def test_anonymous_is_sent_to_login(self):
        for name, args in PAGES:
            response = self.client.get(reverse(name, args=args))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name, args=args)}", fetch_redirect_response=False)

    def test_club_admin_without_staff_gets_404(self):
        self.client.login(username="member", password="pass-12345")
        for name, args in PAGES + [("backoffice:club_detail", [self.club.public_id]), ("backoffice:user_detail", [self.member.id])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 404, name)

    def test_staff_sees_every_page(self):
        User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.client.login(username="staff", password="pass-12345")
        for name, args in PAGES + [("backoffice:club_detail", [self.club.public_id]), ("backoffice:user_detail", [self.member.id])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)

    def test_menu_link_only_for_staff(self):
        self.client.login(username="member", password="pass-12345")
        self.assertNotContains(self.client.get(reverse("home")), reverse("backoffice:dashboard"))
        self.member.is_staff = True
        self.member.save()
        self.assertContains(self.client.get(reverse("home")), reverse("backoffice:dashboard"))

    def test_django_admin_is_superuser_only(self):
        User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.client.login(username="staff", password="pass-12345")
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)
        User.objects.create_superuser("root", password="pass-12345")
        self.client.login(username="root", password="pass-12345")
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)


class BackofficeDataTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.admin_a = User.objects.create_user("ana", email="ana@example.com", password="pass-12345")
        self.admin_b = User.objects.create_user("bea", password="pass-12345")
        self.club_a = create_club("Club Alfa", "Sevilla", self.admin_a)
        self.club_b = create_club("Club Beta", "Madrid", self.admin_b)
        Player.objects.create(club=self.club_a, name="Pepe", last_name="Uno")
        Player.objects.create(club=self.club_a, name="Luis", last_name="Dos", in_team=False)
        rival = Team.objects.create(club=self.club_a, name="Rival", location="X")
        today = timezone.localdate()
        Match.objects.create(club=self.club_a, local=self.club_a.own_team, visiting=rival, start_date=today - datetime.timedelta(days=3))
        Match.objects.create(club=self.club_a, local=self.club_a.own_team, visiting=rival, start_date=today + datetime.timedelta(days=5))
        SocialAccount.objects.create(user=self.admin_b, provider="google", uid="123")
        self.client.login(username="staff", password="pass-12345")

    def test_dashboard_counts_across_all_clubs(self):
        kpis = dashboard_kpis()
        self.assertEqual(kpis["clubs"]["total"], 2)
        self.assertEqual(kpis["clubs"]["active"], 1)
        self.assertEqual(kpis["users"]["total"], 3)
        self.assertEqual(kpis["users"]["google"], 1)
        self.assertEqual(kpis["users"]["without_club"], 1)
        self.assertEqual(kpis["activity"]["players"], 1)
        self.assertEqual(kpis["activity"]["matches_30"], 1)
        self.assertEqual(kpis["activity"]["matches_upcoming"], 1)

    def test_invitation_conversion(self):
        Invitation.objects.create(club=self.club_a, created_by=self.admin_a)
        Invitation.objects.create(club=self.club_a, created_by=self.admin_a, used_by=self.admin_b, used_at=timezone.now())
        inv = dashboard_kpis()["invitations"]
        self.assertEqual((inv["created_30"], inv["used_30"], inv["conversion_30"], inv["pending"]), (2, 1, 50, 1))

    def test_signups_by_week_has_every_week(self):
        weeks = signups_by_week(weeks=8)
        self.assertEqual(len(weeks), 8)
        self.assertEqual(weeks[-1]["n"], 3)
        self.assertEqual(weeks[-1]["pct"], 100)

    def test_club_list_search_filters_and_counts(self):
        page = self.client.get(reverse("backoffice:club_list"), {"q": "alfa"}).context["page"]
        [club] = page.object_list
        self.assertEqual((club.name, club.n_members, club.n_players, club.n_matches), ("Club Alfa", 1, 1, 2))
        self.assertEqual(club.last_match, timezone.localdate() - datetime.timedelta(days=3))

        inactive = self.client.get(reverse("backoffice:club_list"), {"activity": "inactive"}).context["page"]
        self.assertEqual([c.name for c in inactive], ["Club Beta"])

    def test_club_list_orderings(self):
        for order in ["recent", "name", "members", "activity", "bogus"]:
            response = self.client.get(reverse("backoffice:club_list"), {"order": order})
            self.assertEqual(len(response.context["page"].object_list), 2, order)

    def test_user_list_filters(self):
        url = reverse("backoffice:user_list")
        names = lambda **p: [u.username for u in self.client.get(url, p).context["page"]]
        self.assertEqual(names(q="ana@"), ["ana"])
        self.assertEqual(names(kind="google"), ["bea"])
        self.assertEqual(names(kind="no_club"), ["staff"])
        self.assertEqual(names(kind="staff"), ["staff"])

    def test_detail_pages_show_club_data(self):
        response = self.client.get(reverse("backoffice:club_detail", args=[self.club_a.public_id]))
        self.assertContains(response, "ana@example.com")
        self.assertEqual(response.context["players_total"], 2)
        self.assertEqual(response.context["players_active"], 1)

        response = self.client.get(reverse("backoffice:user_detail", args=[self.admin_b.id]))
        self.assertContains(response, "Club Beta")
        self.assertContains(response, "Google")
        self.assertFalse(Membership.objects.filter(user=self.staff).exists())


class ActivityAndLoadTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        flush_metrics()
        RequestMetric.objects.all().delete()
        self.staff = User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.member = User.objects.create_user("member", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.member)

    def test_requests_mark_user_online_with_club_and_path(self):
        self.client.login(username="member", password="pass-12345")
        self.client.get(reverse("list_players"))
        activity = UserActivity.objects.get(user=self.member)
        self.assertEqual(activity.club, self.club)
        self.assertEqual(activity.last_path, reverse("list_players"))
        self.assertEqual([a.user for a in online_users()], [self.member])

    def test_activity_is_written_at_most_once_a_minute(self):
        self.client.login(username="member", password="pass-12345")
        self.client.get(reverse("home"))
        self.client.get(reverse("list_players"))
        self.assertEqual(UserActivity.objects.get(user=self.member).last_path, reverse("home"))

    def test_old_activity_is_not_online(self):
        UserActivity.objects.create(user=self.member, last_seen=timezone.now() - datetime.timedelta(minutes=10))
        self.assertEqual(online_users().count(), 0)

    def test_logout_removes_user_from_online(self):
        self.client.login(username="member", password="pass-12345")
        self.client.get(reverse("home"))
        self.client.post(reverse("logout"))
        self.assertFalse(UserActivity.objects.filter(user=self.member).exists())

    def test_requests_are_counted_per_minute(self):
        self.client.get(reverse("login"))
        self.client.get(reverse("login"))
        self.client.get("/static/style.css")  # los estáticos no cuentan
        flush_metrics()
        metric = RequestMetric.objects.get()
        self.assertEqual(metric.requests, 2)
        self.assertEqual(metric.errors, 0)

        self.client.get(reverse("login"))
        flush_metrics()
        self.assertEqual(RequestMetric.objects.get().requests, 3)

    def test_load_page_and_series(self):
        now = timezone.now().replace(second=0, microsecond=0)
        RequestMetric.objects.create(minute=now - datetime.timedelta(minutes=2), requests=10, errors=1, total_ms=1000, max_ms=400)
        RequestMetric.objects.create(minute=now - datetime.timedelta(hours=3), requests=5, total_ms=500, max_ms=100)
        data = load_metrics()
        self.assertEqual(len(data["minutes"]), 60)
        self.assertEqual(len(data["hours"]), 24)
        self.assertEqual(data["last_hour"]["requests"], 10)
        self.assertEqual(data["last_hour"]["avg_ms"], 100)
        self.assertEqual(data["last_hour"]["errors"], 1)
        self.assertEqual(data["last_day"]["requests"], 15)
        self.assertEqual(data["peak_minute"]["requests"], 10)
        self.assertEqual(sum(h["requests"] for h in data["hours"]), 15)

        self.client.login(username="staff", password="pass-12345")
        response = self.client.get(reverse("backoffice:load"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "staff")  # el propio staff aparece conectado

    def test_purge_command(self):
        from django.core.management import call_command
        RequestMetric.objects.create(minute=timezone.now() - datetime.timedelta(days=40), requests=1)
        RequestMetric.objects.create(minute=timezone.now().replace(second=0, microsecond=0), requests=1)
        call_command("purge_request_metrics", stdout=open("/dev/null", "w"))
        self.assertEqual(RequestMetric.objects.count(), 1)


class AgoFilterTests(TestCase):
    def test_ago(self):
        from .templatetags.backoffice_tags import ago
        now = timezone.now()
        self.assertEqual(ago(None), "nunca")
        self.assertEqual(ago(now), "ahora mismo")
        self.assertTrue(ago(now - datetime.timedelta(minutes=5)).startswith("hace 5"))
        self.assertEqual(ago(timezone.localdate()), "hoy")
        self.assertTrue(ago(timezone.localdate() - datetime.timedelta(days=3)).startswith("hace 3"))


class CronTests(TestCase):
    def at(self, *args):
        from zoneinfo import ZoneInfo
        return datetime.datetime(*args, tzinfo=ZoneInfo("Europe/Madrid"))

    def test_next_after(self):
        from .cron import Cron
        self.assertEqual(Cron("0 3 * * *").next_after(self.at(2026, 9, 30, 2, 59)), self.at(2026, 9, 30, 3, 0))
        self.assertEqual(Cron("0 3 * * *").next_after(self.at(2026, 9, 30, 3, 0)), self.at(2026, 10, 1, 3, 0))
        self.assertEqual(Cron("*/15 * * * *").next_after(self.at(2026, 9, 30, 10, 7)), self.at(2026, 9, 30, 10, 15))
        # Lunes (1) a las 8:30; el 30/9/2026 es miércoles.
        self.assertEqual(Cron("30 8 * * 1").next_after(self.at(2026, 9, 30, 12, 0)), self.at(2026, 10, 5, 8, 30))
        self.assertEqual(Cron("0 0 1 * *").next_after(self.at(2026, 9, 30, 12, 0)), self.at(2026, 10, 1, 0, 0))
        self.assertEqual(Cron("0 9 * * 0,6").next_after(self.at(2026, 9, 30, 12, 0)), self.at(2026, 10, 3, 9, 0))

    def test_invalid_expressions(self):
        from .cron import Cron, CronError
        for bad in ["", "* * * *", "61 * * * *", "a * * * *", "*/0 * * * *", "0 3 31 2 *"]:
            with self.assertRaises(CronError, msg=bad):
                Cron(bad).next_after(self.at(2026, 1, 1, 0, 0))

    def test_describe(self):
        from .cron import Cron
        self.assertEqual(Cron("0 3 * * *").describe(), "Cada día a las 03:00")
        self.assertEqual(Cron("*/5 * * * *").describe(), "Cada 5 minutos")
        self.assertEqual(Cron("30 8 * * 1").describe(), "Cada lunes a las 08:30")

    def test_registered_jobs_are_valid(self):
        from django.core.management import get_commands
        from .cron import Cron
        from .jobs import JOBS
        self.assertEqual(len({j.name for j in JOBS}), len(JOBS))
        for spec in JOBS:
            if spec.schedule:  # sin horario: solo a mano
                Cron(spec.schedule)
            self.assertIn(spec.command, get_commands(), spec.name)


class ManualJobWithParamsTests(TestCase):
    """Procesos sin horario que piden datos al lanzarlos (p. ej. complete_snp_team con el id del equipo)."""

    def setUp(self):
        from unittest import mock
        from .jobs import JobParam, JobSpec
        specs = [JobSpec(name="param_job", description="Con datos", command="purge_job_runs", args=("--days",),
                         params=(JobParam("days", "Días"),))]
        for target in ("backoffice.scheduler.JOBS", "backoffice.jobs.JOBS"):
            patcher = mock.patch(target, specs)
            patcher.start()
            self.addCleanup(patcher.stop)
        User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.client.login(username="staff", password="pass-12345")

    def test_manual_only_job_is_never_scheduled(self):
        from .scheduler import run_due_jobs, scheduler_is_late, sync_jobs
        job = sync_jobs().get()
        self.assertIsNone(job.next_run_at)
        self.assertEqual(run_due_jobs(), [])
        self.assertFalse(scheduler_is_late())
        page = self.client.get(reverse("backoffice:job_detail", args=["param_job"]))
        self.assertContains(page, "Solo a mano")
        self.assertContains(page, 'name="days"')

    @override_settings(BACKOFFICE_RUN_JOBS_INLINE=True)
    def test_run_now_passes_the_params_to_the_command(self):
        from .scheduler import sync_jobs
        sync_jobs()
        url = reverse("backoffice:job_run_now", args=["param_job"])
        response = self.client.post(url, {"days": "abc"})
        self.assertRedirects(response, reverse("backoffice:job_detail", args=["param_job"]))
        self.assertFalse(JobRun.objects.exists())

        self.client.post(url, {"days": " 30 "})
        run = JobRun.objects.get()
        self.assertEqual((run.args, run.status), (["30"], JobRun.OK))
        self.assertIn("Inicio: python manage.py purge_job_runs --days 30", run.output)


class SchedulerTests(TestCase):
    def setUp(self):
        from unittest import mock
        from .jobs import JobSpec
        self.specs = [
            JobSpec(name="ok_job", description="Va bien", command="purge_request_metrics", schedule="0 3 * * *"),
            JobSpec(name="bad_job", description="Falla", command="no_existe", schedule="0 4 * * *"),
        ]
        patcher = mock.patch("backoffice.scheduler.JOBS", self.specs)
        patcher.start()
        self.addCleanup(patcher.stop)
        spec_patch = mock.patch("backoffice.jobs.JOBS", self.specs)
        spec_patch.start()
        self.addCleanup(spec_patch.stop)
        self.staff = User.objects.create_user("staff", email="staff@example.com", password="pass-12345", is_staff=True)

    def test_sync_creates_jobs_with_next_run(self):
        from .scheduler import sync_jobs
        jobs = {j.name: j for j in sync_jobs()}
        self.assertEqual(set(jobs), {"ok_job", "bad_job"})
        self.assertTrue(all(j.next_run_at > timezone.now() for j in jobs.values()))

    def test_due_jobs_run_and_are_logged(self):
        from django.core import mail
        from .scheduler import run_due_jobs, sync_jobs
        sync_jobs()
        ScheduledJob.objects.update(next_run_at=timezone.now() - datetime.timedelta(minutes=1))
        runs = {r.job.name: r for r in run_due_jobs()}

        self.assertEqual(runs["ok_job"].status, JobRun.OK)
        self.assertIn("Borradas", runs["ok_job"].output)
        self.assertEqual(runs["bad_job"].status, JobRun.ERROR)
        self.assertIn("no_existe", runs["bad_job"].error)

        # Se reprograman para su siguiente hora y se libera la marca de "en curso".
        for job in ScheduledJob.objects.all():
            self.assertIsNone(job.running_since)
            self.assertGreater(job.next_run_at, timezone.now())
        # Aviso por email del fallo al personal de Zyra.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("bad_job", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["staff@example.com"])

        self.assertEqual(run_due_jobs(), [])  # nada más que hacer

    def test_paused_job_does_not_run_but_manual_request_does(self):
        from .scheduler import run_due_jobs, sync_jobs
        sync_jobs()
        ScheduledJob.objects.update(next_run_at=timezone.now() - datetime.timedelta(minutes=1), enabled=False)
        self.assertEqual(run_due_jobs(), [])

        ScheduledJob.objects.filter(name="ok_job").update(run_requested_at=timezone.now(), run_requested_by=self.staff)
        [run] = run_due_jobs()
        self.assertEqual((run.job.name, run.trigger, run.triggered_by), ("ok_job", JobRun.MANUAL, self.staff))
        self.assertIsNone(ScheduledJob.objects.get(name="ok_job").run_requested_at)

    def test_running_job_is_not_started_twice_and_dead_run_is_released(self):
        from .scheduler import run_due_jobs, run_job, sync_jobs
        sync_jobs()
        job = ScheduledJob.objects.get(name="ok_job")
        ScheduledJob.objects.filter(pk=job.pk).update(running_since=timezone.now())
        self.assertIsNone(run_job(job))

        # El proceso murió hace rato: sin señales de vida desde hace 2 horas.
        long_ago = timezone.now() - datetime.timedelta(hours=2)
        stuck = JobRun.objects.create(job=job, started_at=long_ago)
        ScheduledJob.objects.filter(pk=job.pk).update(running_since=long_ago, heartbeat_at=long_ago, next_run_at=timezone.now())
        runs = run_due_jobs()
        stuck.refresh_from_db()
        self.assertEqual(stuck.status, JobRun.ERROR)
        self.assertIn("Interrumpida", stuck.error)
        self.assertEqual([r.status for r in runs], [JobRun.OK])

    def test_long_running_job_with_heartbeat_is_never_launched_again(self):
        """Un proceso que sigue vivo (p. ej. update_snp_scores con miles de clubes) no se duplica."""
        from .scheduler import claim_job, run_due_jobs, sync_jobs
        start = timezone.now() - datetime.timedelta(hours=5)
        sync_jobs(start)
        ScheduledJob.objects.update(enabled=False)
        ScheduledJob.objects.filter(name="ok_job").update(enabled=True, next_run_at=start)
        job = ScheduledJob.objects.get(name="ok_job")
        run = claim_job(job, now=start)
        # Lleva 5 horas en marcha pero dio señales de vida hace un minuto.
        ScheduledJob.objects.filter(pk=job.pk).update(heartbeat_at=timezone.now() - datetime.timedelta(minutes=1))
        self.assertEqual(run_due_jobs(), [])
        run.refresh_from_db()
        self.assertEqual(run.status, JobRun.RUNNING)
        self.assertIsNotNone(ScheduledJob.objects.get(pk=job.pk).running_since)

    def test_claim_moves_next_run_so_an_interrupted_run_is_not_relaunched_at_once(self):
        from .scheduler import claim_job, run_due_jobs, sync_jobs
        now = timezone.now()
        sync_jobs(now)
        ScheduledJob.objects.update(enabled=False)
        ScheduledJob.objects.filter(name="ok_job").update(enabled=True, next_run_at=now - datetime.timedelta(minutes=1))
        job = ScheduledJob.objects.get(name="ok_job")
        claim_job(job, now=now)
        self.assertGreater(ScheduledJob.objects.get(pk=job.pk).next_run_at, now)

        # El proceso muere: tras liberarse la marca, no se relanza hasta su siguiente hora.
        later = now + datetime.timedelta(minutes=30)
        self.assertEqual(run_due_jobs(now=later), [])
        job.refresh_from_db()
        self.assertIsNone(job.running_since)
        self.assertEqual(job.runs.get().status, JobRun.ERROR)

    def test_heartbeat_marks_the_running_job_as_alive(self):
        from unittest import mock
        from .scheduler import Heartbeat, sync_jobs
        sync_jobs()
        job = ScheduledJob.objects.get(name="ok_job")
        started = timezone.now() - datetime.timedelta(hours=3)
        ScheduledJob.objects.filter(pk=job.pk).update(running_since=started, heartbeat_at=started)
        heartbeat = Heartbeat(job)
        # Un latido y se para; se ejecuta en este hilo para usar la base de datos del test.
        heartbeat.stopped = mock.Mock(wait=mock.Mock(side_effect=[False, True]))
        with mock.patch("backoffice.scheduler.db_connections"):
            heartbeat._beat()
        self.assertGreater(ScheduledJob.objects.get(pk=job.pk).heartbeat_at, started)

    def test_scheduler_is_late(self):
        from .scheduler import scheduler_is_late, sync_jobs
        sync_jobs()
        self.assertFalse(scheduler_is_late())
        ScheduledJob.objects.filter(name="ok_job").update(next_run_at=timezone.now() - datetime.timedelta(minutes=30))
        self.assertTrue(scheduler_is_late())

    @override_settings(BACKOFFICE_RUN_JOBS_INLINE=True)
    def test_pages_and_actions(self):
        from .scheduler import sync_jobs
        sync_jobs()
        self.client.login(username="staff", password="pass-12345")
        self.assertContains(self.client.get(reverse("backoffice:job_list")), "ok_job")

        # "Ejecutar ahora" arranca al momento y lleva a la traza de la ejecución.
        response = self.client.post(reverse("backoffice:job_run_now", args=["ok_job"]))
        run = JobRun.objects.get()
        self.assertRedirects(response, reverse("backoffice:run_detail", args=[run.public_id]))
        self.assertEqual((run.trigger, run.triggered_by, run.status), (JobRun.MANUAL, self.staff, JobRun.OK))
        self.assertIn("Inicio: python manage.py purge_request_metrics", run.output)
        self.assertIn("Fin: correcto", run.output)
        self.assertIsNone(ScheduledJob.objects.get(name="ok_job").running_since)

        detail = reverse("backoffice:job_detail", args=["ok_job"])
        self.client.post(reverse("backoffice:job_toggle", args=["ok_job"]), {"next": detail})
        self.assertFalse(ScheduledJob.objects.get(name="ok_job").enabled)
        # "next" solo acepta rutas de este sitio.
        response = self.client.post(reverse("backoffice:job_toggle", args=["ok_job"]), {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("backoffice:job_list"))

        self.assertContains(self.client.get(detail), "Correcta")
        self.assertContains(self.client.get(reverse("backoffice:run_detail", args=[run.public_id])), "Borradas")
        log = self.client.get(reverse("backoffice:run_list"), {"status": "ok", "job": "ok_job"})
        self.assertEqual([r.id for r in log.context["page"]], [run.id])

    def test_run_now_while_running_is_refused(self):
        from .scheduler import sync_jobs
        sync_jobs()
        ScheduledJob.objects.filter(name="ok_job").update(running_since=timezone.now())
        self.client.login(username="staff", password="pass-12345")
        response = self.client.post(reverse("backoffice:job_run_now", args=["ok_job"]))
        self.assertRedirects(response, reverse("backoffice:job_list"))
        self.assertFalse(JobRun.objects.exists())

    def test_live_output_endpoint(self):
        from .scheduler import sync_jobs
        sync_jobs()
        job = ScheduledJob.objects.get(name="ok_job")
        run = JobRun.objects.create(job=job, started_at=timezone.now(), output="línea 1\nlínea 2\n")
        self.client.login(username="staff", password="pass-12345")
        url = reverse("backoffice:run_live", args=[run.public_id])
        data = self.client.get(url).json()
        self.assertEqual((data["finished"], data["output"], data["offset"]), (False, "línea 1\nlínea 2\n", 16))
        self.assertContains(self.client.get(reverse("backoffice:run_detail", args=[run.public_id])), "En directo")

        JobRun.objects.filter(pk=run.pk).update(output=run.output + "línea 3\n", status=JobRun.ERROR,
                                                 finished_at=timezone.now(), error="Boom")
        data = self.client.get(url, {"offset": 16}).json()
        self.assertEqual((data["finished"], data["output"], data["error"]), (True, "línea 3\n", "Boom"))

    def test_live_output_is_saved_while_running(self):
        from .scheduler import LiveOutput, sync_jobs
        sync_jobs()
        run = JobRun.objects.create(job=ScheduledJob.objects.get(name="ok_job"), started_at=timezone.now())
        out = LiveOutput(run, every=0)
        out.write("paso 1\n")
        run.refresh_from_db()
        self.assertEqual(run.output, "paso 1\n")

    def test_actions_need_post_and_staff(self):
        self.client.login(username="staff", password="pass-12345")
        self.assertEqual(self.client.get(reverse("backoffice:job_run_now", args=["ok_job"])).status_code, 405)
        User.objects.create_user("member", password="pass-12345")
        self.client.login(username="member", password="pass-12345")
        self.assertEqual(self.client.post(reverse("backoffice:job_run_now", args=["ok_job"])).status_code, 404)

    def test_purge_job_runs(self):
        from django.core.management import call_command
        from .scheduler import sync_jobs
        sync_jobs()
        job = ScheduledJob.objects.first()
        JobRun.objects.create(job=job, status=JobRun.OK, started_at=timezone.now() - datetime.timedelta(days=100))
        JobRun.objects.create(job=job, status=JobRun.OK, started_at=timezone.now())
        call_command("purge_job_runs", stdout=open("/dev/null", "w"))
        self.assertEqual(JobRun.objects.count(), 1)


class LiveOutputAsyncTests(TransactionTestCase):
    """Procesos que escriben su salida con un event loop en marcha (Playwright en update_snp_scores)."""

    def test_live_output_is_saved_from_async_context(self):
        import asyncio
        from .scheduler import LiveOutput, sync_jobs
        sync_jobs()
        run = JobRun.objects.create(job=ScheduledJob.objects.first(), started_at=timezone.now())
        out = LiveOutput(run, every=0)

        async def write_from_loop():
            out.write("Iniciando sesión en SNP…\n")

        asyncio.run(write_from_loop())  # antes: SynchronousOnlyOperation
        run.refresh_from_db()
        self.assertEqual(run.output, "Iniciando sesión en SNP…\n")


class SqlConsoleTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", email="root@example.com", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.root)
        self.client.login(username="root", password="pass-12345")
        self.url = reverse("backoffice:sql_console")

    def test_select_runs_and_is_logged(self):
        from .models import QueryLog
        response = self.client.post(self.url, {"sql": "SELECT name FROM core_club", "action": "run"})
        self.assertEqual(response.context["result"].rows, [("Club A",)])
        log = QueryLog.objects.get()
        self.assertEqual((log.user, log.row_count, log.exported, log.error), (self.root, 1, False, ""))

    def test_page_ships_schema_for_autocomplete(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="sql-schema"')
        self.assertContains(response, "js/backoffice-sql.js")
        self.assertContains(response, '"target": "team_team"')
        self.assertNotContains(response, "django_session")

    def test_writes_are_rejected(self):
        from . import sql
        for query in [
            "DELETE FROM core_club",
            "UPDATE core_club SET name = 'x'",
            "SELECT 1; DELETE FROM core_club",
            "WITH x AS (SELECT 1) DELETE FROM core_club",
            "PRAGMA query_only = OFF",
            "ATTACH DATABASE 'x.db' AS x",
        ]:
            with self.assertRaises(sql.QueryError, msg=query):
                sql.run(query)
        self.assertTrue(Club.objects.filter(name="Club A").exists())
        # La conexión vuelve a admitir escrituras después de una consulta.
        Club.objects.create(name="Club B")

    def test_sensitive_data_is_hidden(self):
        from . import sql
        with self.assertRaises(sql.QueryError):
            sql.run("SELECT password FROM auth_user")
        with self.assertRaises(sql.QueryError):
            sql.run("SELECT * FROM django_session")
        result = sql.run("SELECT * FROM auth_user")
        index = result.columns.index("password")
        self.assertEqual(result.rows[0][index], sql.MASK)
        self.assertEqual(result.masked, ["password"])
        tables = [t["name"] for t in sql.schema()]
        self.assertIn("core_club", tables)
        self.assertNotIn("django_session", tables)
        self.assertNotIn("password", next(t for t in sql.schema() if t["name"] == "auth_user")["columns"])

    def test_row_limit_and_timeout(self):
        from . import sql
        result = sql.run("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 50) SELECT x FROM c", limit=10)
        self.assertEqual((result.row_count, result.truncated), (10, True))
        with self.assertRaisesMessage(sql.QueryError, "tardó más de"):
            sql.run("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c", timeout=0.5)

    def test_export_csv(self):
        response = self.client.post(self.url, {"sql": "SELECT name, slug FROM core_club", "action": "export"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        body = response.content.decode("utf-8-sig")
        self.assertEqual(body.splitlines(), ["name;slug", "Club A;club-a"])

    def test_save_and_delete_query(self):
        from .models import SavedQuery
        response = self.client.post(self.url, {"sql": "SELECT name FROM core_club;", "action": "save", "name": "Clubes"})
        saved = SavedQuery.objects.get()
        self.assertRedirects(response, f"{self.url}?saved={saved.public_id}")
        self.assertEqual(saved.sql, "SELECT name FROM core_club")
        self.assertContains(self.client.get(self.url, {"saved": saved.public_id}), "SELECT name FROM core_club")
        # No se guarda una consulta que no se podría ejecutar.
        self.client.post(self.url, {"sql": "DELETE FROM core_club", "action": "save", "name": "Mal"})
        self.assertEqual(SavedQuery.objects.count(), 1)
        self.client.post(reverse("backoffice:sql_delete_saved", args=[saved.public_id]))
        self.assertFalse(SavedQuery.objects.exists())

    def test_only_superusers(self):
        User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.client.login(username="staff", password="pass-12345")
        for name in ["backoffice:sql_console", "backoffice:sql_log", "backoffice:import_list"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 404, name)
        self.assertNotContains(self.client.get(reverse("backoffice:dashboard")), reverse("backoffice:sql_console"))


class ImportTests(TestCase):
    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.upload = SimpleUploadedFile
        self.root = User.objects.create_superuser("root", password="pass-12345")
        self.club = create_club("Los Gladiadores", "Sevilla", self.root)
        self.other = create_club("Otro", "Madrid", self.root)
        self.client.login(username="root", password="pass-12345")

    def start(self, content, entity="players", mode="upsert", club=None):
        from .models import ImportJob
        f = self.upload("datos.csv", content.encode("utf-8-sig"), content_type="text/csv")
        response = self.client.post(reverse("backoffice:import_list"), {
            "entity": entity, "mode": mode, "club": (club or self.club).pk, "file": f,
        })
        job = ImportJob.objects.latest("created_at")
        self.assertRedirects(response, reverse("backoffice:import_map", args=[job.public_id]))
        return job

    def test_non_numeric_club_shows_error_instead_of_500(self):
        f = self.upload("datos.csv", "Nombre\nAna\n".encode("utf-8-sig"), content_type="text/csv")
        response = self.client.post(reverse("backoffice:import_list"),
                                    {"entity": "players", "mode": "create", "club": "abc", "file": f})
        self.assertEqual(response.status_code, 302)  # vuelve a la lista con el mensaje de error
        from .models import ImportJob
        self.assertFalse(ImportJob.objects.exists())

    def test_players_full_flow_with_auto_mapping_and_undo(self):
        existing = Player.objects.create(club=self.club, name="Ana", last_name="García", position="Derecha")
        Player.objects.create(club=self.other, name="Luis", last_name="Pérez")
        job = self.start("Nombre;Apellidos;Posición;En plantilla\nAna;García;Revés;sí\nLuis;Pérez;Derecha;no\n")
        self.assertEqual(set(job.mapping), {"name", "last_name", "position", "in_team"})

        preview = self.client.get(reverse("backoffice:import_preview", args=[job.public_id]))
        self.assertEqual((preview.context["creates"], preview.context["updates"], preview.context["errors"]), (1, 1, 0))

        self.client.post(reverse("backoffice:import_confirm", args=[job.public_id]))
        job.refresh_from_db()
        self.assertEqual((job.status, job.created_count, job.updated_count), ("done", 1, 1))
        existing.refresh_from_db()
        self.assertEqual(existing.position, "Revés")
        luis = Player.objects.get(club=self.club, name="Luis")
        self.assertEqual((luis.in_team, luis.team), (False, self.club.own_team))
        # El jugador del otro club no se ha tocado.
        self.assertEqual(Player.objects.filter(club=self.other).count(), 1)

        self.client.post(reverse("backoffice:import_undo", args=[job.public_id]))
        existing.refresh_from_db()
        self.assertEqual(existing.position, "Derecha")
        self.assertFalse(Player.objects.filter(club=self.club, name="Luis").exists())

    def test_errors_block_the_whole_import(self):
        job = self.start("name,last_name,position\nAna,García,Derecha\n,Sin nombre,Revés\nEva,López,Portero\nAna,García,Revés\n")
        preview = self.client.get(reverse("backoffice:import_preview", args=[job.public_id]))
        self.assertEqual(preview.context["errors"], 3)
        errors = self.client.get(reverse("backoffice:import_preview", args=[job.public_id]), {"errors": "csv"}).content.decode("utf-8-sig")
        self.assertIn("Nombre: obligatorio", errors)
        self.assertIn("Portero", errors)
        self.assertIn("Repetido en el fichero", errors)

        self.client.post(reverse("backoffice:import_confirm", args=[job.public_id]))
        self.assertFalse(Player.objects.exists())
        job.refresh_from_db()
        self.assertEqual(job.status, "draft")

    def test_modes(self):
        Player.objects.create(club=self.club, name="Ana", last_name="García")
        job = self.start("name;last_name\nAna;García\nEva;López\n", mode="create")
        self.assertEqual(self.client.get(reverse("backoffice:import_preview", args=[job.public_id])).context["errors"], 1)
        job = self.start("name;last_name\nAna;García\nEva;López\n", mode="update")
        self.assertEqual(self.client.get(reverse("backoffice:import_preview", args=[job.public_id])).context["errors"], 1)

    def test_update_by_id_only_inside_the_club(self):
        mine = Player.objects.create(club=self.club, name="Ana", last_name="García")
        theirs = Player.objects.create(club=self.other, name="Eva", last_name="López")
        job = self.start(f"id;name\n{mine.pk};Anabel\n{theirs.pk};Hack\n", mode="update")
        preview = self.client.get(reverse("backoffice:import_preview", args=[job.public_id]))
        self.assertEqual((preview.context["updates"], preview.context["errors"]), (1, 1))

    def test_manual_mapping(self):
        job = self.start("Col A;Col B\nPádel Norte;Sevilla\n", entity="teams", mode="create")
        self.assertEqual(job.mapping, {})
        self.client.post(reverse("backoffice:import_map", args=[job.public_id]), {"map_name": "0", "map_location": "1"})
        self.client.post(reverse("backoffice:import_confirm", args=[job.public_id]))
        team = Team.objects.get(club=self.club, name="Pádel Norte")
        self.assertEqual((team.location, team.is_own), ("Sevilla", False))

    def test_matches_need_existing_teams(self):
        Team.objects.create(club=self.club, name="Rival", location="X")
        job = self.start("Fecha;Local;Visitante\n25/10/2026;Los Gladiadores;Rival\n2026-11-01;Rival;Nadie\n", entity="matches", mode="create")
        preview = self.client.get(reverse("backoffice:import_preview", args=[job.public_id]))
        self.assertEqual((preview.context["creates"], preview.context["errors"]), (1, 1))

    def test_bad_files(self):
        from .models import ImportJob
        for content in ["", "name;last_name\n"]:
            f = self.upload("x.csv", content.encode(), content_type="text/csv")
            self.client.post(reverse("backoffice:import_list"), {"entity": "players", "mode": "create", "club": self.club.pk, "file": f})
        from .models import ImportJob
        self.assertFalse(ImportJob.objects.exists())

    def test_template(self):
        body = self.client.get(reverse("backoffice:import_template", args=["players"])).content.decode("utf-8-sig")
        self.assertTrue(body.startswith("ID;Nombre;Apellidos"))
        self.assertEqual(self.client.get(reverse("backoffice:import_template", args=["nope"])).status_code, 404)


class SqlRelationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", password="pass-12345")
        self.club = create_club("Los Gladiadores", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Pádel Norte", location="X")
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date(2026, 10, 25))
        Player.objects.create(club=self.club, name="Pepe", last_name="Uno")

    def test_follow_foreign_keys_like_soql(self):
        from . import sql
        result = sql.run("SELECT local_id, visiting_id, local_id.name, visiting.name AS rival FROM match_match")
        self.assertEqual(result.columns, ["local_id", "visiting_id", "local_id.name", "rival"])
        self.assertEqual(result.rows, [(self.club.own_team.id, self.rival.id, "Los Gladiadores", "Pádel Norte")])
        self.assertIn("LEFT JOIN team_team", result.expanded_sql)

    def test_several_hops_alias_and_where(self):
        from . import sql
        result = sql.run("SELECT m.id, m.local_id.club_id.name FROM match_match m WHERE m.visiting_id.name = 'Pádel Norte'")
        self.assertEqual(result.columns, ["id", "local_id.club_id.name"])
        self.assertEqual(result.rows, [(self.match.id, "Los Gladiadores")])

    def test_bare_columns_are_not_ambiguous(self):
        from . import sql
        result = sql.run("SELECT name, club.name AS club FROM players_player ORDER BY name")
        self.assertEqual(result.rows, [("Pepe", "Los Gladiadores")])

    def test_queries_without_paths_are_unchanged(self):
        from . import sql
        query = "SELECT c.name FROM core_club c WHERE c.name = 'a.b'"
        self.assertEqual(sql.expand_relations(query), query)
        self.assertEqual(sql.run(query).expanded_sql, "")

    def test_errors(self):
        from . import sql
        with self.assertRaisesMessage(sql.QueryError, "no tiene la columna nope"):
            sql.run("SELECT local_id.nope FROM match_match")
        with self.assertRaisesMessage(sql.QueryError, "no es una relación"):
            sql.run("SELECT local_id.location.name FROM match_match")
        with self.assertRaises(sql.QueryError):
            sql.run("SELECT user_id.password FROM core_membership")
        with self.assertRaisesMessage(sql.QueryError, "subconsultas"):
            sql.run("SELECT local_id.name FROM match_match WHERE id IN (SELECT id FROM match_match)")

    def test_schema_shows_foreign_keys(self):
        from . import sql
        match = next(t for t in sql.schema() if t["name"] == "match_match")
        local = next(c for c in match["columns"] if c["name"] == "local_id")
        self.assertEqual(local["target"], "team_team")


class UsageAndHealthTests(TestCase):
    """Páginas de uso de la plataforma y salud de los servicios con datos."""

    def setUp(self):
        from call.models import Call, ReportDelivery
        from players.models import SnpAccount

        self.member = User.objects.create_user("member", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.member)
        today = timezone.localdate()
        match = Match.objects.create(club=self.club, local=self.club.own_team, start_date=today, rival_name="Rival",
                                     draft_mode=False)
        call = Call.objects.create(match=match, draft_mode=False)
        ReportDelivery.objects.create(call=call, email="a@example.com", status=ReportDelivery.SENT, attempts=2)
        ReportDelivery.objects.create(call=call, email="b@example.com", status=ReportDelivery.FAILED, attempts=5,
                                      last_error="SMTP caído")
        account = SnpAccount(club=self.club, last_sync_ok=False, last_sync_message="Contraseña rechazada")
        account.username = "user"
        account.password = "secret"
        account.save()
        User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.client.login(username="staff", password="pass-12345")

    def test_usage(self):
        response = self.client.get(reverse("backoffice:usage"))
        usage = response.context["usage"]
        self.assertEqual(usage["totals"]["matches"], 1)
        self.assertEqual(usage["totals"]["calls"], 1)
        features = {f["label"]: f for f in usage["features"]}
        self.assertEqual(features["Han cerrado una convocatoria"]["pct"], 100)
        self.assertEqual(features["Tienen cuenta SNP"]["n"], 1)
        self.assertEqual(features["Han hecho una alineación"]["n"], 0)
        self.assertContains(response, "Club A")

    def test_health(self):
        response = self.client.get(reverse("backoffice:health"))
        health = response.context["health"]
        self.assertEqual((health["reports"]["sent"], health["reports"]["failed"], health["reports"]["retried"]), (1, 1, 1))
        self.assertEqual(health["reports"]["ok_pct"], 50)
        self.assertEqual(health["snp"]["failed"], 1)
        self.assertContains(response, "SMTP caído")
        self.assertContains(response, "Contraseña rechazada")
