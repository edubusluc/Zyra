from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.services import create_club

User = get_user_model()


class LanguageTests(TestCase):
    """La web sale en español salvo que el usuario elija inglés en el selector."""

    def setUp(self):
        user = User.objects.create_user("admin", password="pass-12345")
        create_club("Club A", "Sevilla", user)
        self.client.login(username="admin", password="pass-12345")

    def test_spanish_by_default_even_if_browser_prefers_english(self):
        response = self.client.get(reverse("home"), HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
        self.assertContains(response, '<html lang="es"')
        self.assertContains(response, "Plantilla")
        self.assertContains(response, "English")
        self.assertEqual(response["Content-Language"], "es")

    def test_selector_switches_to_english_and_back(self):
        response = self.client.post(reverse("set_language"), {"language": "en", "next": reverse("list_players")})
        self.assertRedirects(response, reverse("list_players"), fetch_redirect_response=False)

        response = self.client.get(reverse("home"))
        self.assertContains(response, '<html lang="en"')
        self.assertContains(response, "Squad")
        self.assertContains(response, "Log out")
        self.assertNotContains(response, "Cerrar sesión")

        self.client.post(reverse("set_language"), {"language": "es", "next": "/"})
        self.assertContains(self.client.get(reverse("home")), "Cerrar sesión")

    def test_unknown_language_cookie_falls_back_to_spanish(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "fr"
        self.assertContains(self.client.get(reverse("home")), '<html lang="es"')

    def test_messages_and_form_errors_are_translated(self):
        self.client.logout()
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = self.client.post(reverse("login"), {"username": "admin", "password": "wrong"})
        self.assertNotContains(response, "Iniciar sesión")
        self.assertContains(response, "Log in")
        self.assertContains(response, "Please enter a correct username and password")

    def test_javascript_catalog_has_english_strings(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = self.client.get(reverse("javascript-catalog"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Won")
