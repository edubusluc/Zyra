"""Pruebas del rol de gestor: qué puede hacer frente al capitán y al miembro, y cómo se nombra."""
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import Invitation, Membership
from core.services import ManagerError, create_club, set_manager, transfer_captaincy
from core.tests_security import PASSWORD, SecurityBase
from match.notifications import admin_emails
from players.models import Player, SnpTeamImport

User = get_user_model()


class ManagerBase(SecurityBase):
    """Club con capitán, miembro y un gestor (``manager``)."""

    def setUp(self):
        super().setUp()
        self.manager = User.objects.create_user("manager", password=PASSWORD, email="manager@example.com")
        self.manager_membership = Membership.objects.create(user=self.manager, club=self.club, role=Membership.MANAGER)

    def manager_urls(self):
        m, c, g = self.match.public_id, self.call.public_id, self.game.public_id
        return [
            reverse("create_match"), reverse("create_call", args=[m]), reverse("close_call", args=[m]),
            reverse("resend_call_report", args=[m]), reverse("call_report", args=[m]), reverse("edit_call", args=[c]),
            reverse("closed_call", args=[c]), reverse("existing_call", args=[m]), reverse("create_game", args=[m]),
            reverse("create_result", args=[g]), reverse("edit_result", args=[g]), reverse("close_match", args=[m]),
            reverse("edit_games_match", args=[m]), reverse("create_penalty", args=[c]), reverse("delete_penalty"),
            reverse("create_player"), reverse("edit_player", args=[self.player.public_id]),
            reverse("delete_player", args=[self.player.public_id]), reverse("manage_roster"),
            reverse("create_team"), reverse("edit_team", args=[self.rival.public_id]), reverse("manage_teams"),
            reverse("warnings_statistics"),
        ]

    def captain_only_urls(self):
        m = self.match.public_id
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain)
        team_import = SnpTeamImport.objects.create(club=self.club, started_by=self.captain)
        return [
            reverse("delete_match", args=[m]), reverse("reopen_match", args=[m]), reverse("delete_call", args=[m]),
            reverse("unlink_player", args=[self.player.public_id]),
            reverse("snp_account"), reverse("snp_account_delete"), reverse("complete_team_start"),
            reverse("complete_team_status", args=[team_import.public_id]),
            reverse("complete_team_confirm", args=[team_import.public_id]),
            reverse("complete_team_cancel", args=[team_import.public_id]),
            reverse("club_members"), reverse("create_invitation"), reverse("create_invitation_link"),
            reverse("revoke_invitation", args=[invitation.public_id]),
            reverse("update_member", args=[self.membership.public_id]),
            reverse("remove_member", args=[self.membership.public_id]),
            reverse("transfer_captaincy", args=[self.membership.public_id]),
            reverse("set_manager", args=[self.membership.public_id]),
        ]


class PermissionMatrixTests(ManagerBase):
    """Cada vista protegida, por rol: el gestor entra en las deportivas y no en las del capitán."""

    def test_manager_reaches_every_sporting_url(self):
        self.client.login(username="manager", password=PASSWORD)
        for url in self.manager_urls():
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    self.assertNotEqual(getattr(self.client, method)(url).status_code, 403)

    def test_manager_gets_forbidden_page_on_captain_only_urls(self):
        self.client.login(username="manager", password=PASSWORD)
        for url in self.captain_only_urls():
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertTemplateUsed(response, "403.html")
        self.assertTrue(Membership.objects.filter(pk=self.membership.pk, role=Membership.MEMBER).exists())

    def test_member_gets_forbidden_on_sporting_urls(self):
        self.client.login(username="member", password=PASSWORD)
        for url in self.manager_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_captain_reaches_everything(self):
        self.client.login(username="captain", password=PASSWORD)
        for url in self.manager_urls():
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 403)

    def test_manager_of_another_club_cannot_touch_this_club(self):
        other_user = User.objects.create_user("other", password=PASSWORD, email="other@example.com")
        other = create_club("Club B", "Madrid", other_user)
        stranger = User.objects.create_user("stranger", password=PASSWORD, email="stranger@example.com")
        Membership.objects.create(user=stranger, club=other, role=Membership.MANAGER)
        self.client.login(username="stranger", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("edit_player", args=[self.player.public_id])).status_code, 404)
        self.assertEqual(self.client.get(reverse("create_call", args=[self.match.public_id])).status_code, 404)


class ManagerScreensTests(ManagerBase):
    """Lo que ve el gestor en las pantallas."""

    def test_manager_sees_sporting_buttons_but_not_captain_ones(self):
        self.client.login(username="manager", password=PASSWORD)
        page = self.client.get(reverse("call_for_match", args=[self.match.public_id]))
        self.assertContains(page, reverse("edit_match_date", args=[self.match.public_id]))
        self.assertNotContains(page, reverse("reopen_match", args=[self.match.public_id]))
        listing = self.client.get(reverse("list_match"))
        self.assertContains(listing, reverse("create_match"))
        self.assertNotContains(listing, reverse("delete_match", args=[self.match.public_id]))

    def test_manager_club_page_has_no_members_or_snp(self):
        self.client.login(username="manager", password=PASSWORD)
        page = self.client.get(reverse("club_home"))
        self.assertContains(page, reverse("create_player"))
        self.assertNotContains(page, f'href="{reverse("club_members")}"')
        self.assertNotContains(page, f'href="{reverse("snp_account")}"')

    def test_report_emails_include_managers(self):
        self.assertEqual(admin_emails(self.club), ["captain@example.com", "manager@example.com"])


class SetManagerTests(ManagerBase):
    """Nombrar y quitar gestores."""

    def post(self, membership, enable):
        return self.client.post(reverse("set_manager", args=[membership.public_id]), {"enable": enable})

    def test_captain_makes_and_removes_a_manager(self):
        self.client.login(username="captain", password=PASSWORD)
        self.post(self.membership, "1")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, Membership.MANAGER)
        self.post(self.membership, "0")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, Membership.MEMBER)

    def test_at_most_two_managers(self):
        extra = Membership.objects.create(user=User.objects.create_user("x2", password=PASSWORD, email="x2@example.com"),
                                          club=self.club, role=Membership.MANAGER)
        self.client.login(username="captain", password=PASSWORD)
        response = self.post(self.membership, "1")
        self.assertEqual(response.status_code, 302)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, Membership.MEMBER)
        page = self.client.get(reverse("club_members"))
        self.assertContains(page, "como máximo dos gestores")
        self.assertEqual(extra.club.memberships.filter(role=Membership.MANAGER).count(), 2)

    def test_captain_cannot_be_changed_and_foreign_membership_is_404(self):
        with self.assertRaises(ManagerError):
            set_manager(self.club, self.captain_membership, self.captain_membership, True)
        other_user = User.objects.create_user("o", password=PASSWORD, email="o@example.com")
        other = create_club("Club B", "Madrid", other_user)
        foreign = Membership.objects.get(user=other_user, club=other)
        self.client.login(username="captain", password=PASSWORD)
        self.assertEqual(self.post(foreign, "1").status_code, 404)

    def test_manager_and_member_cannot_name_managers(self):
        for user in ("manager", "member"):
            self.client.login(username=user, password=PASSWORD)
            self.assertEqual(self.post(self.membership, "1").status_code, 403)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, Membership.MEMBER)

    def test_service_rejects_non_captain(self):
        with self.assertRaises(ManagerError):
            set_manager(self.club, self.manager_membership, self.membership, True)

    def test_transfer_to_manager_keeps_other_managers(self):
        Player.objects.create(club=self.club, name="Mgr", last_name="X", user=self.manager)
        transfer_captaincy(self.club, self.captain_membership, self.manager_membership)
        self.manager_membership.refresh_from_db()
        self.captain_membership.refresh_from_db()
        self.assertEqual(self.manager_membership.role, Membership.ADMIN)
        self.assertEqual(self.captain_membership.role, Membership.MEMBER)
