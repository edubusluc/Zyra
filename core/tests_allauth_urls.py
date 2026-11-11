"""Rutas de allauth: solo las aprobadas, sin vía para cambiar el email sin contraseña."""
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from core.allauth_urls import APPROVED_NAMES, REDIRECTED_NAMES
from core.services import create_club

User = get_user_model()


def _accounts_names(resolver=None):
    """Nombres de todas las rutas que cuelgan de ``accounts/``."""
    names = set()

    def walk(patterns, prefix):
        for pattern in patterns:
            text = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, text)
            elif isinstance(pattern, URLPattern) and text.startswith("accounts/"):
                names.add(pattern.name)

    walk((resolver or get_resolver()).url_patterns, "")
    return names


class ApprovedRoutesTests(TestCase):
    def test_only_approved_allauth_routes_exist(self):
        """Si allauth añade una ruta nueva (o alguien la incluye), este test obliga a aprobarla."""
        self.assertEqual(_accounts_names() - APPROVED_NAMES - set(REDIRECTED_NAMES), set())


class EmailChangeBypassTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("capitan", password="pass-12345", email="capitan@example.com")
        create_club("Club A", "Sevilla", self.user)
        EmailAddress.objects.create(user=self.user, email="capitan@example.com", verified=True, primary=True)
        self.client.force_login(self.user)

    def test_account_email_redirects_to_profile(self):
        for url in ("/accounts/email/", "/accounts/3rdparty/"):
            response = self.client.get(url)
            self.assertRedirects(response, reverse("my_profile"), fetch_redirect_response=False)

    def test_cannot_add_email_without_password(self):
        response = self.client.post("/accounts/email/", {"action_add": "", "email": "atacante@evil.test"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(EmailAddress.objects.filter(email="atacante@evil.test").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_social_connections_page_is_closed(self):
        response = self.client.post("/accounts/3rdparty/", {"action": "disconnect"})
        self.assertRedirects(response, reverse("my_profile"), fetch_redirect_response=False)


class PasswordResetTargetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("capitan", password="pass-12345", email="capitan@example.com")

    def test_reset_goes_to_primary_email(self):
        self.client.post(reverse("account_reset_password"), {"email": "capitan@example.com"})
        self.assertEqual([m.to for m in mail.outbox], [["capitan@example.com"]])

    def test_reset_not_sent_to_secondary_unverified_email(self):
        EmailAddress.objects.create(user=self.user, email="atacante@evil.test", verified=False, primary=False)
        response = self.client.post(reverse("account_reset_password"), {"email": "atacante@evil.test"})
        self.assertEqual(response.status_code, 302)
        # allauth avisa de «no hay cuenta» a esa dirección, pero nunca manda el enlace
        self.assertFalse(any("/password/reset/key/" in m.body for m in mail.outbox))


class GoogleNotConfiguredTests(TestCase):
    @override_settings(GOOGLE_LOGIN_ENABLED=False)
    def test_google_login_is_404_not_500(self):
        self.assertEqual(self.client.post(reverse("google_login")).status_code, 404)
        self.assertEqual(self.client.get(reverse("google_login")).status_code, 404)
