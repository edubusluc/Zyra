"""Regresión: añadir la API no cambia el comportamiento de la web (frenos, sesión, CSRF, rutas)."""
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.middleware import FloodProtectionMiddleware

User = get_user_model()


class WebUnchangedTests(TestCase):
    """La web sigue igual con la API montada."""

    def setUp(self):
        """Caché de límites limpia."""
        caches["ratelimit"].clear()
        User.objects.create_user("ana", "ana@example.com", "pass-12345-x")

    @override_settings(RATE_LIMITS_ENABLED=True, FLOOD_LIMIT_GET_PER_MINUTE=3)
    def test_web_is_still_limited_by_ip(self):
        """El freno general por IP sigue frenando la web."""
        codes = [self.client.get(reverse("login"), REMOTE_ADDR="3.3.3.3").status_code for _ in range(5)]
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[3:], [429, 429])

    @override_settings(RATE_LIMITS_ENABLED=True, FLOOD_LIMIT_GET_PER_MINUTE=1)
    def test_api_is_not_limited_by_the_ip_flood_filter(self):
        """La API queda fuera del freno por IP (lo limita el token)."""
        codes = [self.client.get("/api/v1/ping", REMOTE_ADDR="3.3.3.4").status_code for _ in range(4)]
        self.assertNotIn(429, codes)

    def test_only_api_was_added_to_flood_exemptions(self):
        """Las exenciones del freno general son las de siempre más ``/api/``."""
        self.assertEqual(FloodProtectionMiddleware.EXEMPT_PREFIXES, ("/healthz/", "/static/", "/media/", "/api/"))

    def test_web_login_still_uses_session_and_csrf(self):
        """El login web sigue exigiendo CSRF y creando sesión."""
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(reverse("login"), {"username": "ana", "password": "pass-12345-x"}).status_code, 403)
        ok = self.client.post(reverse("login"), {"username": "ana", "password": "pass-12345-x"})
        self.assertEqual(ok.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_web_pages_keep_their_headers(self):
        """Las páginas web siguen sin ``no-store`` de la API y con Vary: Cookie."""
        response = self.client.get(reverse("login"))
        self.assertNotEqual(response.get("Cache-Control"), "no-store")
        self.assertIn("Cookie", response["Vary"])
