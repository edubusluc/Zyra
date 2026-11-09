"""Tests de los frenos de abuso, la verificación de email, el aviso de Google y ADMIN_URL."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core import ratelimit
from core.services import create_club

User = get_user_model()


@override_settings(RATE_LIMITS_ENABLED=True, TRUSTED_PROXY_COUNT=1)
class RateLimitTests(TestCase):
    """El contador compartido y la IP real."""

    def setUp(self):
        """Caché limpia entre tests."""
        cache.clear()

    def test_client_ip_uses_rightmost_trusted_hop(self):
        """Con un proxy de confianza se toma la última IP de X-Forwarded-For, no la que envía el cliente."""
        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 1.2.3.4", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(ratelimit.client_ip(request), "1.2.3.4")

    def test_too_many_blocks_after_limit(self):
        """A partir del límite se bloquea."""
        request = RequestFactory().get("/", REMOTE_ADDR="9.9.9.9")
        results = [ratelimit.too_many(request, "t", 3, 60) for _ in range(5)]
        self.assertEqual(results, [False, False, False, True, True])

    @override_settings(RATE_LIMITS_ENABLED=False)
    def test_disabled_never_blocks(self):
        """Con los límites apagados nunca se bloquea."""
        request = RequestFactory().get("/", REMOTE_ADDR="9.9.9.9")
        self.assertFalse(any(ratelimit.too_many(request, "t", 1, 60) for _ in range(5)))

    def test_password_check_returns_429(self):
        """La comprobación de contraseña devuelve 429 al pasarse."""
        url = reverse("password_check")
        codes = [self.client.post(url, {"password": "x"}, REMOTE_ADDR="8.8.8.8").status_code for _ in range(62)]
        self.assertIn(429, codes)


@override_settings(RATE_LIMITS_ENABLED=True)
class PasswordResetLimitTests(TestCase):
    """«¿Has olvidado tu contraseña?» no manda más correos de la cuenta por hora, y no delata si existe."""

    def setUp(self):
        """Caché limpia entre tests."""
        cache.clear()

    def ask(self, email, ip="7.7.7.7"):
        """Pide el cambio de contraseña y comprueba que la respuesta es siempre la misma."""
        response = self.client.post(reverse("account_reset_password"), {"email": email}, REMOTE_ADDR=ip)
        self.assertRedirects(response, reverse("account_reset_password_done"), fetch_redirect_response=False)

    def test_email_limit_stops_sending_with_same_response(self):
        """Al cuarto intento para el mismo email no sale correo, con la misma pantalla."""
        for n in range(5):
            self.ask("nadie@example.com", ip=f"7.7.7.{n}")
        self.assertEqual(len(mail.outbox), 3)

    def test_ip_limit_stops_sending(self):
        """Una IP que pide para muchos emails distintos se corta a los cinco."""
        for n in range(7):
            self.ask(f"u{n}@example.com")
        self.assertEqual(len(mail.outbox), 5)


class EmailVerificationTests(TestCase):
    """Verificación de email al registrar el club y reenvío."""

    def test_resend_sends_confirmation(self):
        """«Mi perfil» permite reenviar el enlace de confirmación."""
        user = User.objects.create_user("ana", "ana@example.com", "pass-12345")
        create_club("Club", "Sevilla", user, gender="M")
        self.client.force_login(user)
        response = self.client.post(reverse("resend_verification"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ana@example.com", mail.outbox[0].to)


class AdminUrlTests(TestCase):
    """La ruta del admin sale de ADMIN_URL."""

    def test_default_admin_url_in_debug(self):
        """En desarrollo el admin sigue en /admin/."""
        from django.conf import settings
        self.assertEqual(settings.ADMIN_URL, "admin/")
