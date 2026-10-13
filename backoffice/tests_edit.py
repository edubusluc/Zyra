"""Edición del personal desde el back-office: equipo, jugadores y cuenta SNP, siempre auditada."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.services import create_club
from players.models import Player, SnpAccount

from .models import AuditLog

User = get_user_model()


@override_settings(FIELD_ENCRYPTION_KEY="")
class StaffEditTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capitan", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.staff = User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Alvarez", position="Revés")
        self.client.login(username="staff", password="pass-12345")

    def test_non_staff_cannot_edit(self):
        self.client.login(username="capitan", password="pass-12345")
        self.assertEqual(self.client.get(reverse("backoffice:team_edit", args=[self.club.own_team.public_id])).status_code, 404)
        self.assertEqual(self.client.post(reverse("backoffice:player_edit", args=[self.player.public_id])).status_code, 404)

    def test_club_page_lists_edit_links(self):
        page = self.client.get(reverse("backoffice:club_detail", args=[self.club.public_id]))
        self.assertContains(page, reverse("backoffice:team_edit", args=[self.club.own_team.public_id]))
        self.assertContains(page, reverse("backoffice:player_edit", args=[self.player.public_id]))

    def test_team_edit_is_saved_and_audited(self):
        team = self.club.own_team
        url = reverse("backoffice:team_edit", args=[team.public_id])
        self.assertEqual(self.client.get(url).status_code, 200)
        data = {"name": team.name, "gender": "F", "country": "ES", "division": "1000", "location": "Sevilla", "in_group": "on"}
        self.client.post(url, data)
        team.refresh_from_db()
        self.assertEqual((team.gender, team.division), ("F", "1000"))
        entry = AuditLog.objects.get(action="team.edit")
        self.assertEqual(entry.username, "staff")
        self.assertIn("gender", entry.detail["changes"])

    def test_player_edit_is_saved_and_audited(self):
        url = reverse("backoffice:player_edit", args=[self.player.public_id])
        self.client.post(url, {"name": "Ana", "last_name": "Alvarez Ruiz", "position": "Derecha", "skillfull_hand": "NONE",
                               "joined_season": "2026-2027", "in_team": "on"})
        self.player.refresh_from_db()
        self.assertEqual((self.player.last_name, self.player.position), ("Alvarez Ruiz", "Derecha"))
        self.assertEqual(AuditLog.objects.get(action="player.edit").detail["changes"]["last_name"], ["Alvarez", "Alvarez Ruiz"])

    def test_snp_account_edit_never_logs_the_password(self):
        url = reverse("backoffice:snp_account_edit", args=[self.club.public_id])
        self.client.post(url, {"username": "capi", "password": "muy-secreta", "team_id": "4380"})
        account = SnpAccount.objects.get(club=self.club)
        self.assertEqual((account.username, account.password, account.team_id), ("capi", "muy-secreta", "4380"))
        entry = AuditLog.objects.get(action="club.snp_account")
        self.assertNotIn("muy-secreta", str(entry.detail))
        # Contraseña vacía: se mantiene la actual.
        self.client.post(url, {"username": "capi2", "password": "", "team_id": ""})
        account = SnpAccount.objects.get(club=self.club)
        self.assertEqual((account.username, account.password), ("capi2", "muy-secreta"))

    def test_reset_failures_reopens_the_web_option(self):
        self.club.snp_import_failures = 3
        self.club.save()
        self.client.post(reverse("backoffice:snp_import_reset", args=[self.club.public_id]))
        self.club.refresh_from_db()
        self.assertEqual(self.club.snp_import_failures, 0)
        self.assertTrue(AuditLog.objects.filter(action="club.snp_import_reset").exists())
