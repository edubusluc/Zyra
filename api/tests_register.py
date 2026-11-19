"""Tests de ``/api/v1/auth/register`` y ``/api/v1/club/create``: cuenta de jugador sin club y alta de su club."""
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Membership


class RegisterAccountTests(TestCase):
    """``POST /api/v1/auth/register``: cuenta sin club (jugador) y alta de club con esa cuenta (``club/create``)."""

    def setUp(self):
        """Limpia cachés."""
        from django.core.cache import cache, caches
        cache.clear()
        caches["ratelimit"].clear()

    def register(self, **changes):
        """POST válido de alta de cuenta con los cambios indicados."""
        import json
        data = {"username": "marta", "email": "marta@example.com", "password": "Clave-Segura-123",
                "device_name": "iPhone", **changes}
        return self.client.post(reverse("api_register"), json.dumps(data), content_type="application/json")

    def test_creates_account_without_club_and_returns_token(self):
        """La cuenta se crea sin club, devuelve token y ``team`` a None, y no hay membresías."""
        response = self.register()
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["token"].startswith("zyra_"))
        self.assertIsNone(data["team"])
        self.assertEqual(data["user"], {"username": "marta", "email": "marta@example.com"})
        self.assertFalse(Membership.objects.filter(user__username="marta").exists())

    def test_validation_errors_come_by_field(self):
        """Usuario repetido, email malo y contraseña floja salen como ``account.<campo>``."""
        self.register()
        taken = self.register(email="otra@example.com")
        self.assertEqual(taken.status_code, 400)
        self.assertIn("account.username", taken.json()["fields"])
        weak = self.register(username="luis", email="no-es-email", password="123")
        fields = weak.json()["fields"]
        self.assertIn("account.email", fields)
        self.assertIn("account.password", fields)

    @override_settings(RATE_LIMITS_ENABLED=True)
    def test_rate_limited(self):
        """Pasado el límite de altas por hora responde 429."""
        from core.views import REGISTER_LIMIT
        for index in range(REGISTER_LIMIT):
            self.register(username=f"u{index}", email=f"u{index}@example.com")
        self.assertEqual(self.register(username="extra", email="extra@example.com").status_code, 429)

    def test_account_without_club_can_create_club_with_its_token(self):
        """Con el token del jugador sin club, ``club/create`` crea su equipo sin pedir cuenta ni emitir otro token."""
        import json
        token = self.register().json()["token"]
        body = {"team": {"name": "Club Norte", "location": "Gijón", "competition": "snp", "gender": "M",
                         "country": "ES", "division": "500"},
                "captain": {"mode": "manual", "name": "Marta", "last_name": "Ruiz"}}
        response = self.client.post(reverse("api_club_create"), json.dumps(body), content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertNotIn("token", data)
        self.assertEqual(data["club"], {"name": "Club Norte", "competition": "snp"})
        membership = Membership.objects.get(user__username="marta")
        self.assertEqual(membership.role, Membership.ADMIN)
        again = self.client.post(reverse("api_club_create"), json.dumps(body), content_type="application/json",
                                 HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual((again.status_code, again.json()["error"]), (409, "space_taken"))

    def test_create_club_requires_token_and_rejects_account(self):
        """Sin token 401; con token, enviar ``account`` es un error."""
        import json
        self.assertEqual(self.client.post(reverse("api_club_create"), "{}", content_type="application/json").status_code, 401)
        token = self.register().json()["token"]
        response = self.client.post(reverse("api_club_create"), json.dumps({"account": {"username": "x"}}),
                                    content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_field"))
