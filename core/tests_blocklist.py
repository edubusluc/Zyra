from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.blocklist import block, is_blocked, normalize_email
from core.models import BlockedEmail, Club, Invitation, Membership
from core.services import create_club

User = get_user_model()

CLUB = {"name": "Club Nuevo", "location": "Cádiz", "gender": "F", "country": "ES", "division": "500",
        "player-name": "Ana", "player-last_name": "Ruiz"}
SIGNUP = {"username": "nuevo", "password1": "Clave-Segura-123", "password2": "Clave-Segura-123"}


class NormalizeTests(TestCase):
    def test_variants_of_the_same_mailbox(self):
        self.assertEqual(normalize_email(" J.Perez+club@GoogleMail.com "), "jperez@gmail.com")
        self.assertEqual(normalize_email("ana+x@empresa.es"), "ana@empresa.es")
        # Fuera de Gmail los puntos sí cuentan.
        self.assertEqual(normalize_email("a.b@empresa.es"), "a.b@empresa.es")

    def test_check_is_one_indexed_query(self):
        block("malo@gmail.com")
        BlockedEmail.objects.bulk_create(
            BlockedEmail(public_id=f"BLE{i:012d}", email=f"user{i}@x.com", original_email=f"user{i}@x.com") for i in range(2000)
        )
        with CaptureQueriesContext(connection) as ctx:
            self.assertTrue(is_blocked("M.A.L.O+otra@gmail.com"))
        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertIn('"email" =', ctx.captured_queries[0]["sql"])
        self.assertTrue(BlockedEmail._meta.get_field("email").unique)


class BlockedEmailTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capitan", password="pass-12345", email="capitan@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        block("malo@example.com")

    def test_blocked_email_cannot_register_a_club(self):
        response = self.client.post(reverse("register_club"), {**CLUB, **SIGNUP, "email": "Malo+2@Example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no puede registrarse")
        self.assertFalse(Club.objects.filter(name="Club Nuevo").exists())
        self.assertFalse(User.objects.filter(username="nuevo").exists())

    def test_logged_in_blocked_user_cannot_create_another_club(self):
        user = User.objects.create_user("malo", password="pass-12345", email="malo@example.com")
        self.client.force_login(user)
        response = self.client.post(reverse("register_club"), CLUB)
        self.assertContains(response, "no puede crear clubes")
        self.assertFalse(Club.objects.filter(name="Club Nuevo").exists())

    def test_captain_cannot_invite_blocked_email(self):
        self.client.force_login(self.captain)
        response = self.client.post(reverse("create_invitation"), {"email": "malo@example.com"})
        self.assertContains(response, "No se puede invitar a este email")
        self.assertFalse(Invitation.objects.exists())

    def test_blocked_email_cannot_sign_up_from_invitation_link(self):
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain)
        response = self.client.post(reverse("invitation", args=[invitation.token]), {**SIGNUP, "email": "malo@example.com"})
        self.assertContains(response, "no puede registrarse")
        self.assertFalse(User.objects.filter(username="nuevo").exists())

    def test_existing_blocked_user_cannot_join_with_link(self):
        user = User.objects.create_user("malo", password="pass-12345", email="malo@example.com")
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain)
        self.client.force_login(user)
        self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertFalse(Membership.objects.filter(user=user).exists())

    def test_unblocked_email_still_works(self):
        response = self.client.post(reverse("register_club"), {**CLUB, **SIGNUP, "email": "bueno@example.com"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)


class SuspendClubBlocksEmailsTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capitan", password="pass-12345", email="Capitan@Example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.member = User.objects.create_user("jugador", password="pass-12345", email="jugador@example.com")
        Membership.objects.create(user=self.member, club=self.club, role=Membership.MEMBER)
        self.staff = User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.client.force_login(self.staff)
        self.url = reverse("backoffice:club_toggle_suspended", args=[self.club.public_id])

    def test_captains_are_preselected_to_block(self):
        page = self.client.get(reverse("backoffice:club_detail", args=[self.club.public_id]))
        self.assertContains(page, f'value="{self.captain.pk}" id="block-{self.captain.pk}" checked')
        self.assertNotContains(page, f'value="{self.member.pk}" id="block-{self.member.pk}" checked')

    def test_suspending_blocks_marked_emails_and_reactivating_unblocks(self):
        self.client.post(self.url, {"action": "suspend", "reason": "Fotos", "block": [str(self.captain.pk)]})
        self.assertTrue(is_blocked("capitan@example.com"))
        self.assertFalse(is_blocked("jugador@example.com"))
        self.assertEqual(BlockedEmail.objects.get().club, self.club)

        # El capitán ya no puede crear un club nuevo.
        self.client.force_login(self.captain)
        self.client.post(reverse("register_club"), CLUB)
        self.assertFalse(Club.objects.filter(name="Club Nuevo").exists())

        self.client.force_login(self.staff)
        self.client.post(self.url, {"action": "reactivate"})
        self.assertFalse(is_blocked("capitan@example.com"))

    def test_changing_email_does_not_escape_the_block(self):
        self.client.post(self.url, {"action": "suspend", "block": [str(self.captain.pk)]})
        self.captain.email = "otro-email@example.com"
        self.captain.save()
        self.client.force_login(self.captain)
        self.client.post(reverse("register_club"), CLUB)
        self.assertFalse(Club.objects.filter(name="Club Nuevo").exists())

    def test_blocked_email_cannot_be_added_to_an_account(self):
        from django import forms

        from core.adapters import AccountAdapter

        block("malo@example.com")
        with self.assertRaises(forms.ValidationError):
            AccountAdapter().clean_email("Malo@example.com")

    def test_reactivating_keeps_block_of_captain_of_another_suspended_club(self):
        other = create_club("Club B", "Huelva", self.captain)
        other_url = reverse("backoffice:club_toggle_suspended", args=[other.public_id])
        self.client.post(self.url, {"action": "suspend", "block": [str(self.captain.pk)]})
        self.client.post(other_url, {"action": "suspend", "block": [str(self.captain.pk)]})
        self.client.post(self.url, {"action": "reactivate"})
        self.assertTrue(is_blocked("capitan@example.com"))
        self.assertEqual(BlockedEmail.objects.get().club, other)
        self.client.post(other_url, {"action": "reactivate"})
        self.assertFalse(is_blocked("capitan@example.com"))

    def test_staff_blocklist_page(self):
        self.client.post(reverse("backoffice:blocked_email_add"), {"email": "Otro@Gmail.com", "reason": "spam"})
        self.assertTrue(is_blocked("o.t.r.o@gmail.com"))
        page = self.client.get(reverse("backoffice:blocked_email_list"), {"q": "otro"})
        self.assertContains(page, "Otro@Gmail.com")
        blocked = BlockedEmail.objects.get()
        self.client.post(reverse("backoffice:blocked_email_delete", args=[blocked.public_id]))
        self.assertFalse(BlockedEmail.objects.exists())

    def test_only_staff(self):
        self.client.force_login(self.captain)
        self.assertEqual(self.client.get(reverse("backoffice:blocked_email_list")).status_code, 404)


class GoogleSignupTests(TestCase):
    def test_google_signup_closed_for_blocked_email(self):
        from types import SimpleNamespace

        from core.adapters import SocialAccountAdapter

        block("malo@gmail.com")
        adapter = SocialAccountAdapter()
        blocked = SimpleNamespace(email_addresses=[SimpleNamespace(email="Malo@gmail.com")], user=None)
        allowed = SimpleNamespace(email_addresses=[SimpleNamespace(email="bueno@gmail.com")], user=None)
        self.assertFalse(adapter.is_open_for_signup(None, blocked))
        self.assertTrue(adapter.is_open_for_signup(None, allowed))
