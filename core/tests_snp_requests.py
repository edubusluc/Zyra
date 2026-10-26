"""Pruebas de «Pedir actualización a Zyra»: petición del capitán, paso de la tarjeta, back-office y aviso al personal."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from backoffice import alerts
from backoffice.models import ScheduledJob
from core import season_prep
from core.services import create_club
from core.tests_season_prep import OCT, SeasonPrepBase, at
from core.tests_security import PASSWORD
from players import snp_requests
from players.models import SnpAccount, SnpUpdateRequest

User = get_user_model()


class RequestFlowTests(SeasonPrepBase):
    """Crear la petición, quién puede y cómo cuenta para la tarjeta."""

    def setUp(self):
        super().setUp()
        SnpAccount.objects.create(club=self.club, username="u", password="p")

    def post(self, user, **data):
        self.client.login(username=user, password=PASSWORD)
        return self.client.post(reverse("snp_update_request"), data)

    def test_captain_creates_one_open_request_with_note(self):
        response = self.post("captain", note="Dos fichajes nuevos", **{"from": "home"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        request = snp_requests.open_request(self.club)
        self.assertEqual(request.note, "Dos fichajes nuevos")
        self.assertEqual(request.requested_by, self.captain)
        self.post("captain", note="otra")
        self.assertEqual(SnpUpdateRequest.objects.filter(club=self.club).count(), 1)
        self.assertEqual(snp_requests.open_request(self.club).note, "Dos fichajes nuevos")

    def test_only_the_captain_can_ask(self):
        self.assertEqual(self.post("manager").status_code, 403)
        self.assertEqual(self.post("member").status_code, 403)
        self.assertFalse(SnpUpdateRequest.objects.exists())

    def test_get_is_not_allowed(self):
        self.client.login(username="captain", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("snp_update_request")).status_code, 405)

    def test_card_offers_the_request_and_then_shows_its_state(self):
        self.client.login(username="captain", password=PASSWORD)
        with at(OCT):
            page = self.client.get(reverse("home"))
        self.assertContains(page, "Pedir actualización a Zyra")
        self.post("captain")
        with at(OCT):
            page = self.client.get(reverse("home"))
        self.assertContains(page, "Zyra la está revisando")
        self.assertNotContains(page, "Pedir actualización a Zyra")

    def test_players_page_offers_it_to_the_captain_only(self):
        self.client.login(username="captain", password=PASSWORD)
        self.assertContains(self.client.get(reverse("list_players")), "Pedir actualización a Zyra")
        self.client.login(username="manager", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("list_players")), "Pedir actualización a Zyra")

    def test_done_request_completes_the_snp_step_for_the_season(self):
        request, _created = snp_requests.create_request(self.club, self.captain)
        steps = {s["key"]: s for s in self.prep(self.captain_membership)["steps"]}
        self.assertFalse(steps["snp"]["done"])
        self.assertEqual(steps["snp"]["request"], request)
        self.assertTrue(snp_requests.finish(request, self.captain))
        self.assertFalse(snp_requests.finish(request, self.captain))
        with at(OCT):
            steps = {s["key"]: s for s in season_prep.season_prep_for(self.captain_membership, OCT)["steps"]}
        self.assertTrue(steps["snp"]["done"])

    def test_a_new_request_is_possible_after_the_previous_one_is_done(self):
        first, _created = snp_requests.create_request(self.club, self.captain)
        snp_requests.finish(first, self.captain)
        second, created = snp_requests.create_request(self.club, self.captain, "x" * 300)
        self.assertTrue(created)
        self.assertEqual(len(second.note), 200)


class BackofficeTests(SeasonPrepBase):
    """Lista del personal, «Completar equipo» y «Marcar hecha»."""

    def setUp(self):
        super().setUp()
        SnpAccount.objects.create(club=self.club, username="u", password="p")
        self.staff = User.objects.create_user("staff", "staff@example.com", PASSWORD, is_staff=True)
        self.request, _created = snp_requests.create_request(self.club, self.captain, "nuevos")

    def test_list_is_for_staff_only(self):
        url = reverse("backoffice:snp_request_list")
        self.client.login(username="captain", password=PASSWORD)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.login(username="staff", password=PASSWORD)
        page = self.client.get(url)
        self.assertContains(page, self.club.name)
        self.assertContains(page, "nuevos")

    def test_mark_done(self):
        self.client.login(username="staff", password=PASSWORD)
        response = self.client.post(reverse("backoffice:snp_request_done", args=[self.request.public_id]))
        self.assertRedirects(response, reverse("backoffice:snp_request_list"))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, SnpUpdateRequest.DONE)
        self.assertEqual(self.request.done_by, self.staff)

    def test_run_launches_complete_snp_team_for_the_own_team(self):
        job = ScheduledJob.objects.create(name="complete_snp_team")
        self.client.login(username="staff", password=PASSWORD)
        with mock.patch("backoffice.views.request_manual_run", return_value=(None, "queued")) as run:
            response = self.client.post(reverse("backoffice:snp_request_run", args=[self.request.public_id]))
        run.assert_called_once_with(job, self.staff, [self.club.own_team.public_id])
        self.assertRedirects(response, reverse("backoffice:job_detail", args=["complete_snp_team"]), fetch_redirect_response=False)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, SnpUpdateRequest.OPEN)

    def test_run_needs_an_snp_account(self):
        ScheduledJob.objects.create(name="complete_snp_team")
        SnpAccount.objects.filter(club=self.club).delete()
        self.client.login(username="staff", password=PASSWORD)
        with mock.patch("backoffice.views.request_manual_run") as run:
            self.client.post(reverse("backoffice:snp_request_run", args=[self.request.public_id]))
        run.assert_not_called()

    def test_non_staff_cannot_use_the_actions(self):
        self.client.login(username="captain", password=PASSWORD)
        for name in ("snp_request_done", "snp_request_run"):
            self.assertEqual(self.client.post(reverse(f"backoffice:{name}", args=[self.request.public_id])).status_code, 404)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, SnpUpdateRequest.OPEN)


class StaffAlertTests(SeasonPrepBase):
    """Aviso por correo al personal con más de cinco peticiones abiertas."""

    def setUp(self):
        super().setUp()
        User.objects.create_user("staff", "staff@example.com", PASSWORD, is_staff=True)
        patcher = mock.patch("backoffice.metrics.scheduler_status", return_value={"late": False})
        patcher.start()
        self.addCleanup(patcher.stop)

    def open_requests(self, n):
        for i in range(n):
            owner = User.objects.create_user(f"cap{i}", f"cap{i}@example.com", PASSWORD)
            club = create_club(f"Club {i}", "Sevilla", owner, gender="M")
            snp_requests.create_request(club, owner)

    def test_five_open_requests_do_not_alert(self):
        self.open_requests(5)
        self.assertNotIn("snp_requests", alerts.current_problems())
        self.assertEqual(alerts.evaluate(), [])

    def test_six_open_requests_alert_once(self):
        self.open_requests(6)
        self.assertIn("snp_requests", alerts.current_problems())
        mail.outbox.clear()
        self.assertEqual(len(alerts.evaluate()), 1)
        self.assertEqual(mail.outbox[0].to, ["staff@example.com"])
        self.assertEqual(alerts.evaluate(), [])
