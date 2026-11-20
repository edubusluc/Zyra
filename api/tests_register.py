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

    def test_username_is_optional_and_generated_from_email(self):
        """Sin usuario (o vacío) se crea uno libre a partir del email; con dos emails iguales antes de la @ no chocan."""
        import json
        first = self.client.post(reverse("api_register"), json.dumps(
            {"email": "marta.ruiz@example.com", "password": "Clave-Segura-123"}), content_type="application/json")
        self.assertEqual(first.status_code, 201)
        first_name = first.json()["user"]["username"]
        self.assertTrue(first_name.startswith("marta"))
        second = self.register(username="", email="marta.ruiz@otro.com")
        self.assertEqual(second.status_code, 201)
        second_name = second.json()["user"]["username"]
        self.assertNotEqual(first_name.lower(), second_name.lower())
        self.assertTrue(second_name.startswith("marta"))
        login = self.client.post(reverse("api_login"), json.dumps(
            {"login": "marta.ruiz@example.com", "password": "Clave-Segura-123"}), content_type="application/json")
        self.assertEqual(login.status_code, 201)

    def test_explicit_username_still_wins(self):
        """Con usuario en el cuerpo se usa tal cual: la web y las apps antiguas no cambian."""
        self.assertEqual(self.register(username="capitana_norte").json()["user"]["username"], "capitana_norte")

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


class PasswordResetApiTests(TestCase):
    """``POST /api/v1/auth/password-reset``: mismo correo y mismos frenos que la web, sin delatar si la cuenta existe."""

    def setUp(self):
        """Limpia cachés y crea una cuenta."""
        from django.core.cache import cache, caches
        from django.contrib.auth import get_user_model
        cache.clear()
        caches["ratelimit"].clear()
        get_user_model().objects.create_user("ana", "ana@example.com", "Clave-Segura-123")

    def ask(self, email):
        """POST con el email indicado."""
        import json
        return self.client.post(reverse("api_password_reset"), json.dumps({"email": email}),
                                content_type="application/json")

    def test_sends_email_for_existing_account(self):
        """Con una cuenta real sale un correo con enlace a la web y la respuesta es ``sent``."""
        from django.core import mail
        response = self.ask("ana@example.com")
        self.assertEqual((response.status_code, response.json()), (200, {"sent": True}))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/password/reset/key/", mail.outbox[0].body)

    def test_same_answer_for_unknown_email(self):
        """Un email sin cuenta da la misma respuesta y no recibe ningún enlace de recuperación (allauth avisa de que no hay cuenta)."""
        from django.core import mail
        response = self.ask("nadie@example.com")
        self.assertEqual((response.status_code, response.json()), (200, {"sent": True}))
        self.assertTrue(all("/accounts/password/reset/key/" not in message.body for message in mail.outbox))

    def test_rejects_text_that_is_not_an_email(self):
        """Lo que no es un email da 400 con el campo."""
        response = self.ask("no-es-email")
        self.assertEqual((response.status_code, response.json()["error"]), (400, "validation_error"))
        self.assertIn("account.email", response.json()["fields"])

    @override_settings(RATE_LIMITS_ENABLED=True)
    def test_email_limit_applies_like_the_web(self):
        """Pasado el límite por email no salen más correos, con la misma respuesta."""
        from django.core import mail
        for _ in range(5):
            self.assertEqual(self.ask("ana@example.com").status_code, 200)
        self.assertEqual(len(mail.outbox), 3)
