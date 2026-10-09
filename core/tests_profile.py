"""Pruebas de «Mi perfil» (core.views.my_profile): email, contraseña y jugador enlazado."""
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Membership
from core.services import create_club
from players.models import Player

User = get_user_model()


class MyProfileTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capitan", password="pass-12345", email="capi@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain, gender="M")
        self.user = User.objects.create_user("ana", password="Vieja-clave-123", email="ana@example.com")
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.ana = Player.objects.create(club=self.club, name="Ana", last_name="Ruiz")
        self.client.force_login(self.user)

    def test_menu_links_to_profile(self):
        page = self.client.get(reverse("home"))
        self.assertContains(page, reverse("my_profile"))
        self.assertContains(page, "Mi perfil")

    def test_unlinked_shows_account_and_offers_link(self):
        page = self.client.get(reverse("my_profile"))
        self.assertContains(page, "ana@example.com")
        self.assertContains(page, reverse("account_change_password"))
        self.assertContains(page, "Enlazarme a un jugador")
        self.assertContains(page, reverse("my_player"))

    def test_linked_shows_player_to_edit(self):
        self.ana.user = self.user
        self.ana.save()
        page = self.client.get(reverse("my_profile"))
        self.assertContains(page, "Tu cuenta está enlazada a este jugador")
        self.assertContains(page, self.ana.full_name)
        self.assertNotContains(page, "Enlazarme a un jugador")

    def test_without_club_shows_only_account(self):
        loner = User.objects.create_user("solo", password="pass-12345", email="solo@example.com")
        self.client.force_login(loner)
        page = self.client.get(reverse("my_profile"))
        self.assertContains(page, "solo@example.com")
        self.assertNotContains(page, "Enlazarme a un jugador")

    def test_change_email_requires_current_password(self):
        response = self.client.post(reverse("my_profile"), {"email": "nueva@example.com", "current_password": "mala"})
        self.assertContains(response, "La contraseña no es correcta.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "ana@example.com")

        EmailAddress.objects.create(user=self.user, email="ana@example.com", verified=True, primary=True)
        response = self.client.post(reverse("my_profile"), {"email": "Nueva@Example.com", "current_password": "Vieja-clave-123"})
        self.assertRedirects(response, reverse("my_profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "nueva@example.com")
        # El email anterior deja de contar como verificado para entrar con Google.
        self.assertFalse(EmailAddress.objects.filter(user=self.user, email="ana@example.com").exists())

    def test_change_email_rejects_email_of_other_account(self):
        response = self.client.post(reverse("my_profile"), {"email": "capi@example.com", "current_password": "Vieja-clave-123"})
        self.assertContains(response, "Ese email ya lo usa otra cuenta.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "ana@example.com")

    def test_google_only_account_cannot_change_email(self):
        self.user.set_unusable_password()
        self.user.save()
        SocialAccount.objects.create(user=self.user, provider="google", uid="123")
        self.client.force_login(self.user)  # cambiar la contraseña cierra la sesión
        page = self.client.get(reverse("my_profile") + "?edit=email")
        self.assertContains(page, "Entras con Google")
        self.assertNotContains(page, "Guardar email")
        self.assertNotContains(page, 'href="?edit=email"')
        self.assertNotContains(page, reverse("account_change_password"))
        self.client.post(reverse("my_profile"), {"email": "otra@example.com", "current_password": ""})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "ana@example.com")

    def test_password_change_returns_to_profile(self):
        response = self.client.post(reverse("account_change_password"), {
            "oldpassword": "Vieja-clave-123", "password1": "Nueva-clave-456", "password2": "Nueva-clave-456",
        })
        self.assertRedirects(response, reverse("my_profile"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("my_profile")), "Contraseña actualizada.")
