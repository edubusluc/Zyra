"""Tests del interruptor de SNP, el aviso por fallos, el límite por club y la comparación de equipos."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from core.models import ServiceSwitch
from core.services import create_club
from core.similarity import is_same_team
from players import snp_import, snp_service

User = get_user_model()


class SnpServiceTests(TestCase):
    """Interruptor y alertas."""

    def setUp(self):
        """Personal con email y un capitán con club."""
        self.staff = User.objects.create_user("staff", "staff@example.com", "pass-12345", is_staff=True)
        self.captain = User.objects.create_user("cap", "cap@example.com", "pass-12345")
        self.club = create_club("Club", "Sevilla", self.captain, gender="M")

    def test_enabled_by_default_and_can_be_switched_off(self):
        """Sin fila el servicio está activo; el personal puede apagarlo."""
        self.assertTrue(snp_service.is_enabled())
        snp_service.set_enabled(False, self.staff, "caído")
        self.assertFalse(snp_service.is_enabled())

    def test_alert_after_three_failures_once(self):
        """Al tercer fallo seguido se avisa al personal, y no se repite enseguida."""
        sent = [snp_service.report_failure("timeout") for _ in range(4)]
        self.assertEqual(sent, [False, False, True, False])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["staff@example.com"])

    def test_success_resets_streak(self):
        """Un éxito pone a cero la racha."""
        snp_service.report_failure("x")
        snp_service.report_success()
        self.assertEqual(ServiceSwitch.objects.get(name=ServiceSwitch.SNP).failure_streak, 0)

    def test_backoffice_toggle_requires_staff(self):
        """Solo el personal apaga el servicio."""
        self.client.force_login(self.captain)
        self.client.post(reverse("backoffice:service_snp_toggle"))
        self.assertTrue(snp_service.is_enabled())
        self.client.force_login(self.staff)
        self.client.post(reverse("backoffice:service_snp_toggle"))
        self.assertFalse(snp_service.is_enabled())

    def test_unlimited_flag_is_per_club(self):
        """El límite de «Completar equipo» depende del campo del club, no de su nombre."""
        self.assertFalse(snp_import.is_unlimited(self.club))
        self.client.force_login(self.staff)
        self.client.post(reverse("backoffice:club_toggle_snp_unlimited", args=[self.club.public_id]), {"action": "enable"})
        self.club.refresh_from_db()
        self.assertTrue(snp_import.is_unlimited(self.club))


class SameTeamTests(TestCase):
    """«X A» y «X B» no son el mismo equipo."""

    def test_letter_distinguishes(self):
        """Una letra distinta separa equipos."""
        self.assertFalse(is_same_team("Padel Club A", "Padel Club B"))
        self.assertTrue(is_same_team("Padel Club A", "padel club a"))
