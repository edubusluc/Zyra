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


@override_settings(RATE_LIMITS_ENABLED=True)
class AccountLoginThrottleTests(TestCase):
    """El freno de login cuenta también por cuenta: usuario y email suman juntos y da igual la IP (ROADMAP 21)."""

    def setUp(self):
        """Caché limpia y un usuario con email."""
        cache.clear()
        User.objects.create_user("ana", "ana@example.com", "pass-12345-x")

    def attempt(self, typed, ip, password="mala"):
        """Un intento de login con el texto escrito (usuario o email) desde una IP."""
        return self.client.post(reverse("login"), {"username": typed, "password": password}, REMOTE_ADDR=ip)

    def test_many_ips_and_both_spellings_hit_the_account_limit(self):
        """Con 30 fallos repartidos entre IP y entre usuario/email la cuenta se bloquea, incluso con la contraseña buena."""
        from core.views import LOGIN_MAX_FAILURES_PER_ACCOUNT
        for n in range(LOGIN_MAX_FAILURES_PER_ACCOUNT):
            self.assertEqual(self.attempt("ana" if n % 2 else "ANA@example.com", f"9.9.{n}.1").status_code, 200)
        response = self.attempt("ana", "5.5.5.5", password="pass-12345-x")
        self.assertEqual(response.status_code, 429)

    def test_other_accounts_are_not_affected(self):
        """Los fallos contra una cuenta no bloquean a otra."""
        from core.views import LOGIN_MAX_FAILURES_PER_ACCOUNT
        User.objects.create_user("luis", "luis@example.com", "pass-12345-y")
        for n in range(LOGIN_MAX_FAILURES_PER_ACCOUNT):
            self.attempt("ana", f"9.8.{n}.1")
        self.assertEqual(self.attempt("luis", "4.4.4.4", password="pass-12345-y").status_code, 302)


class ContentSecurityPolicyTests(TestCase):
    """CSP en modo informe por defecto, aplicable con CSP_MODE=enforce, y receptor de avisos (ROADMAP 26)."""

    def test_report_only_header_by_default(self):
        """Las páginas HTML llevan la política en modo informe, sin bloquear nada."""
        response = self.client.get(reverse("login"))
        self.assertIn("default-src 'self'", response["Content-Security-Policy-Report-Only"])
        self.assertNotIn("Content-Security-Policy", response)

    @override_settings(CSP_MODE="enforce")
    def test_enforce_and_off_modes(self):
        """«enforce» pone la cabecera que bloquea; «off» no pone ninguna."""
        self.assertIn("Content-Security-Policy", self.client.get(reverse("login")))
        with override_settings(CSP_MODE="off"):
            response = self.client.get(reverse("login"))
            self.assertNotIn("Content-Security-Policy", response)
            self.assertNotIn("Content-Security-Policy-Report-Only", response)

    def test_report_endpoint_logs_and_returns_204(self):
        """El navegador envía el aviso sin CSRF ni sesión: se anota en el log."""
        with self.assertLogs("core.middleware", level="WARNING") as logs:
            response = self.client.post("/csp-report/", '{"csp-report": {"blocked-uri": "https://malo.example"}}',
                                        content_type="application/csp-report")
        self.assertEqual(response.status_code, 204)
        self.assertIn("malo.example", logs.output[0])
        self.assertEqual(self.client.get("/csp-report/").status_code, 404)


class ProductionEmailTests(TestCase):
    """Sin transporte de correo real, la configuración de producción no arranca (ROADMAP 25)."""

    def settings_error(self, **env):
        """Importa settings en un proceso limpio como producción y devuelve su salida de error."""
        import os
        import subprocess
        import sys
        from cryptography.fernet import Fernet
        base = {**os.environ, "DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "x" * 60, "ADMIN_URL": "panel/",
                "FIELD_ENCRYPTION_KEY": Fernet.generate_key().decode(), "DJANGO_ALLOWED_HOSTS": "ejemplo.com"}
        base.pop("EMAIL_HOST_PASSWORD", None)
        base.pop("EMAIL_BACKEND", None)
        base.update(env)
        done = subprocess.run([sys.executable, "-c", "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='zyra.settings'; "
                               "from django.conf import settings; settings.EMAIL_HOST"], env=base, capture_output=True, text=True)
        return done.returncode, done.stderr

    def test_missing_mail_transport_fails_at_startup(self):
        """Sin contraseña de correo y sin backend explícito, producción falla con un mensaje claro."""
        code, err = self.settings_error()
        self.assertNotEqual(code, 0)
        self.assertIn("EMAIL_HOST_PASSWORD", err)

    def test_with_password_it_starts(self):
        """Con la contraseña de correo, arranca."""
        code, err = self.settings_error(EMAIL_HOST_PASSWORD="algo")
        self.assertEqual(code, 0, err)


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
