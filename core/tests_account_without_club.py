"""Cuentas sin club: alta sin registrar club, página de espera y unión posterior por invitación."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Invitation, Membership
from .services import create_club

User = get_user_model()
PASSWORD = "pass-12345-xyz"
SIGNUP = {"username": "espera", "email": "espera@example.com", "password1": PASSWORD, "password2": PASSWORD}


class RegisterAccountTests(TestCase):
    def test_chooser_offers_player_and_captain(self):
        response = self.client.get(reverse("register"))
        self.assertContains(response, "Registrarme como jugador")
        self.assertContains(response, "Registrarme como capitán")
        self.assertContains(response, f'href="{reverse("register_account")}"')
        self.assertContains(response, f'href="{reverse("register_club")}"')

    def test_captain_responsibilities_and_handover_are_explained(self):
        """El capitán lee sus tareas y que puede traspasar la capitanía antes de crear el club."""
        for url_name in ("register", "register_club"):
            response = self.client.get(reverse(url_name))
            self.assertContains(response, "apuntas los resultados")
            self.assertContains(response, "traspasar la capitanía")

    def test_chooser_redirects_logged_in_users(self):
        self.client.post(reverse("register_account"), SIGNUP)
        self.assertRedirects(self.client.get(reverse("register")), reverse("home"), fetch_redirect_response=False)

    def test_landing_and_forms_link_to_chooser(self):
        self.assertContains(self.client.get(reverse("home")), f'href="{reverse("register")}"')
        self.assertContains(self.client.get(reverse("register_account")), f'href="{reverse("register")}"')
        self.assertContains(self.client.get(reverse("register_club")), f'href="{reverse("register")}"')

    def test_account_page_has_form(self):
        self.assertContains(self.client.get(reverse("register_account")), "Solo quiero unirme a un club por invitación")

    def test_signup_creates_account_without_club_and_logs_in(self):
        response = self.client.post(reverse("register_account"), SIGNUP)
        self.assertRedirects(response, reverse("no_club"))
        user = User.objects.get(username="espera")
        self.assertFalse(Membership.objects.filter(user=user).exists())
        self.assertEqual(self.client.get(reverse("home")).status_code, 302)
        self.assertContains(self.client.get(reverse("no_club")), "todavía no perteneces a ningún club")

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user("otro", email="espera@example.com", password=PASSWORD)
        response = self.client.post(reverse("register_account"), SIGNUP)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="espera").exists())

    def test_logged_in_user_is_redirected(self):
        self.client.post(reverse("register_account"), SIGNUP)
        self.assertRedirects(self.client.get(reverse("register_account")), reverse("home"), fetch_redirect_response=False)

    def test_clubless_account_can_join_by_invitation_and_register_club(self):
        captain = User.objects.create_user("capi", password=PASSWORD)
        club = create_club("Club A", "Sevilla", captain, player_name="Capi", player_last_name="Tan")
        self.client.post(reverse("register_account"), SIGNUP)
        self.assertEqual(self.client.get(reverse("register_club")).status_code, 200)
        invitation = Invitation.objects.create(club=club, created_by=captain, token="tok-espera")
        response = self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Membership.objects.filter(user__username="espera", club=club).exists())
