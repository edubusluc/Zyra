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
        self.assertContains(page, "Nombre de perfil")
        self.assertContains(page, "ana</span>")
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
        self.assertContains(page, reverse("account_set_password"))
        self.client.post(reverse("my_profile"), {"email": "otra@example.com", "current_password": ""})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "ana@example.com")

    def test_password_change_returns_to_profile(self):
        response = self.client.post(reverse("account_change_password"), {
            "oldpassword": "Vieja-clave-123", "password1": "Nueva-clave-456", "password2": "Nueva-clave-456",
        })
        self.assertRedirects(response, reverse("my_profile"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("my_profile")), "Contraseña actualizada.")

    def test_google_only_account_can_add_password_without_current_one(self):
        self.user.set_unusable_password()
        self.user.save()
        SocialAccount.objects.create(user=self.user, provider="google", uid="123")
        self.client.force_login(self.user)  # quitar la contraseña invalida la sesión
        page = self.client.get(reverse("account_set_password"))
        self.assertNotContains(page, "Contraseña actual")
        self.assertContains(page, "data-password-rules")
        response = self.client.post(reverse("account_set_password"), {
            "password1": "Nueva-clave-456", "password2": "Nueva-clave-456",
        })
        self.assertRedirects(response, reverse("my_profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Nueva-clave-456"))
        self.assertTrue(SocialAccount.objects.filter(user=self.user, provider="google").exists())
        page = self.client.get(reverse("my_profile"))
        self.assertContains(page, reverse("account_change_password"))
        self.assertContains(page, "También puedes entrar con Google.")

    def test_account_with_password_is_sent_to_change_form(self):
        response = self.client.get(reverse("account_set_password"))
        self.assertRedirects(response, reverse("account_change_password"), fetch_redirect_response=False)


class ReportPreferenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", password="Vieja-clave-123", email="ana@example.com")
        self.club = create_club("Club A", "Sevilla", self.user, gender="M")
        self.client.force_login(self.user)

    def test_member_does_not_see_or_change_the_call_up_report_scope(self):
        """El informe de la convocatoria es del capitán (H-24): un miembro no lo ve ni lo cambia."""
        member = User.objects.create_user("socio", password="Vieja-clave-123", email="socio@example.com")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)
        page = self.client.get(reverse("my_profile"))
        self.assertNotContains(page, "Datos del informe PDF al crear un partido")
        self.assertContains(page, "Informe mensual por email")
        self.client.post(reverse("my_profile"), {"report_scope": "competitivos", "monthly_form": "1"})
        self.assertEqual(self.client.get(reverse("my_profile")).context["report_scope"], "todos")

    def test_default_is_all_data_and_it_is_saved(self):
        page = self.client.get(reverse("my_profile"))
        self.assertContains(page, "Solo enfrentamientos competitivos")
        self.assertEqual(page.context["report_scope"], "todos")
        response = self.client.post(reverse("my_profile"), {"report_scope": "competitivos"})
        self.assertRedirects(response, reverse("my_profile"))
        self.assertEqual(self.client.get(reverse("my_profile")).context["report_scope"], "competitivos")
        self.client.post(reverse("my_profile"), {"report_scope": "todos"})
        self.assertEqual(self.client.get(reverse("my_profile")).context["report_scope"], "todos")

    def test_invalid_value_is_ignored(self):
        self.client.post(reverse("my_profile"), {"report_scope": "otra"})
        self.assertEqual(self.client.get(reverse("my_profile")).context["report_scope"], "todos")
