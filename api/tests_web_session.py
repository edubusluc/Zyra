"""Tests del puente app → web: caducidad, reutilización y robo del ticket de un solo uso."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api import tokens, web_session
from api.models import WebLoginTicket

User = get_user_model()
APP_UA = "ZyraApp/1.0 (iPhone; iOS 18.1)"
BROWSER_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) Safari/604.1"


class WebSessionTestCase(TestCase):
    """Base: una cuenta con un dispositivo y utilidades para pedir y canjear tickets."""

    def setUp(self):
        """Cuenta «ana» con un token y cachés de límites limpias."""
        caches["ratelimit"].clear()
        self.user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        self.device, self.raw = tokens.issue_token(self.user, "iPhone")

    def ask(self, token=None, body=None, client=None):
        """POST a /auth/web-session con el token indicado."""
        return (client or self.client).post(
            reverse("api_web_session"), json.dumps(body or {}), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.raw}")

    def ticket_path(self, **body):
        """Ruta (sin dominio) de una URL de un solo uso recién pedida."""
        response = self.ask(body=body)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["url"].split("://", 1)[1].split("/", 1)[1].join(["/", ""])

    def open(self, path, user_agent=APP_UA, client=None):
        """GET a la URL de canje con el User-Agent indicado (por defecto el de la app)."""
        return (client or Client()).get(path, HTTP_USER_AGENT=user_agent)


class IssueTicketTests(WebSessionTestCase):
    """Pedir la URL de un solo uso."""

    def test_returns_a_url_that_expires_in_60_seconds(self):
        """Devuelve la URL absoluta y su caducidad a 60 s; en la base de datos solo está el hash."""
        before = timezone.now()
        response = self.ask()
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["url"].startswith("http://testserver/app/session/"))
        ticket = WebLoginTicket.objects.get()
        self.assertAlmostEqual((ticket.expires_at - before).total_seconds(), 60, delta=5)
        raw = data["url"].rstrip("/").rsplit("/", 1)[1]
        self.assertNotEqual(ticket.ticket_hash, raw)
        self.assertFalse(WebLoginTicket.objects.filter(ticket_hash=raw).exists())
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_needs_a_token(self):
        """Sin token o con uno revocado no se emite nada."""
        self.assertEqual(self.client.post(reverse("api_web_session")).status_code, 401)
        tokens.revoke_token(self.device)
        self.assertEqual(self.ask().status_code, 401)
        self.assertFalse(WebLoginTicket.objects.exists())

    def test_every_ticket_is_different(self):
        """Cada petición da un ticket nuevo."""
        self.assertNotEqual(self.ticket_path(), self.ticket_path())

    def test_next_must_be_a_local_path(self):
        """Destinos con otro dominio, ``//``, barras invertidas, esquemas raros o la API se rechazan al pedirlo."""
        for bad in ("https://evil.example/", "//evil.example", "/\\evil.example", "javascript:alert(1)", "evil",
                    "/api/v1/ping", "/a\nb", "/" + "x" * 600, 5, ["/"]):
            response = self.ask(body={"next": bad})
            self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_next"), bad)
        self.assertFalse(WebLoginTicket.objects.exists())

    def test_get_is_not_allowed(self):
        """Solo POST."""
        self.assertEqual(self.client.get(reverse("api_web_session"),
                                         HTTP_AUTHORIZATION=f"Bearer {self.raw}").status_code, 405)

    @override_settings(RATE_LIMITS_ENABLED=True, API_WEB_SESSION_LIMIT_PER_MINUTE=2, API_RATE_LIMIT_PER_MINUTE=100)
    def test_limited_per_token(self):
        """Un token no puede pedir tickets sin freno."""
        codes = [self.ask().status_code for _n in range(4)]
        self.assertEqual(codes, [201, 201, 429, 429])


class RedeemTicketTests(WebSessionTestCase):
    """Canjear el ticket abre la sesión web normal."""

    def test_redeem_logs_in_and_redirects(self):
        """Con el ticket y el User-Agent de la app se inicia la sesión y se llega al destino pedido."""
        path = self.ticket_path(next="/match/list/?x=1")
        client = Client()
        response = self.open(path, client=client)
        self.assertRedirects(response, "/match/list/?x=1", fetch_redirect_response=False)
        self.assertEqual(client.session["_auth_user_id"], str(self.user.pk))
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("/app/session/", response["Location"])

    def test_default_destination_is_home(self):
        """Sin ``next`` va a la portada."""
        response = self.open(self.ticket_path())
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_session_is_the_normal_long_one(self):
        """La sesión dura como «Mantener la sesión iniciada» (no hasta cerrar el navegador)."""
        client = Client()
        self.open(self.ticket_path(), client=client)
        self.assertGreater(client.session.get_expiry_age(), 60 * 60 * 24 * 300)

    def test_staff_session_keeps_its_12_hour_limit(self):
        """Las cuentas del personal conservan el límite de 12 h de la web."""
        self.user.is_staff = True
        self.user.save()
        client = Client()
        self.open(self.ticket_path(), client=client)
        self.assertLessEqual(client.session.get_expiry_age(), 12 * 3600)

    def test_ticket_is_stored_with_its_session(self):
        """Se anota la sesión creada y la fecha de uso."""
        client = Client()
        self.open(self.ticket_path(), client=client)
        ticket = WebLoginTicket.objects.get()
        self.assertEqual(ticket.session_key, client.session.session_key)
        self.assertIsNotNone(ticket.used_at)


class TicketSecurityTests(WebSessionTestCase):
    """Caducidad, reutilización y robo."""

    def assert_rejected(self, response, client=None):
        """El canje falla: a la pantalla de acceso y sin sesión."""
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        if client is not None:
            self.assertNotIn("_auth_user_id", client.session)

    def test_expired_ticket_fails(self):
        """A los 61 s ya no sirve (y no inicia sesión)."""
        path = self.ticket_path()
        WebLoginTicket.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        client = Client()
        self.assert_rejected(self.open(path, client=client), client)

    def test_expiry_boundary_with_explicit_clock(self):
        """Justo antes de los 60 s sirve; justo después no."""
        device = self.device
        now = timezone.now()
        _t, early = web_session.issue_ticket(device, "/", now=now)
        _t, late = web_session.issue_ticket(device, "/", now=now)
        self.assertIsNotNone(web_session.consume_ticket(early, now=now + timedelta(seconds=59)))
        self.assertIsNone(web_session.consume_ticket(late, now=now + timedelta(seconds=61)))

    def test_ticket_cannot_be_reused(self):
        """El segundo canje falla, aunque sea inmediato y con el User-Agent de la app."""
        path = self.ticket_path()
        first = Client()
        self.assertEqual(self.open(path, client=first).status_code, 302)
        second = Client()
        self.assert_rejected(self.open(path, client=second), second)
        self.assertEqual(first.session["_auth_user_id"], str(self.user.pk))  # la primera sesión sigue valiendo

    def test_consume_is_single_winner(self):
        """Dos canjes seguidos de la misma lógica: solo uno obtiene el ticket."""
        _t, raw = web_session.issue_ticket(self.device, "/")
        results = [web_session.consume_ticket(raw), web_session.consume_ticket(raw)]
        self.assertEqual([r is not None for r in results], [True, False])

    def test_stolen_ticket_from_a_browser_does_not_work_nor_burn(self):
        """Un navegador (o una vista previa de enlaces) no canjea el ticket ni lo gasta: la app sigue pudiendo."""
        path = self.ticket_path()
        client = Client()
        self.assert_rejected(self.open(path, user_agent=BROWSER_UA, client=client), client)
        self.assert_rejected(self.client.get(path), client)  # sin User-Agent
        self.assertIsNone(WebLoginTicket.objects.get().used_at)
        self.assertEqual(self.open(path).status_code, 302)

    def test_forged_and_unknown_tickets_fail(self):
        """Tickets inventados, con el hash en lugar del ticket o con caracteres raros fallan."""
        path = self.ticket_path()
        known_hash = WebLoginTicket.objects.get().ticket_hash
        for bad in ("a" * 43, known_hash, "x"):
            self.assert_rejected(self.open(f"/app/session/{bad}/"))
        self.assertEqual(self.open("/app/session/ab$d/").status_code, 404)
        self.assertEqual(self.open(path).status_code, 302)

    def test_ticket_always_logs_in_its_own_account(self):
        """Un ticket de ana nunca inicia la sesión de otra cuenta, ni siquiera con el navegador de otra."""
        luis = User.objects.create_user("luis", "luis@example.com", "pass-12345-y")
        client = Client()
        client.force_login(luis)
        self.open(self.ticket_path(), client=client)
        self.assertEqual(client.session["_auth_user_id"], str(self.user.pk))
        self.assertEqual(WebLoginTicket.objects.get().session_key, client.session.session_key)

    def test_revoked_token_between_issue_and_redeem_fails(self):
        """Si se revoca el dispositivo antes de canjear, el ticket no vale."""
        path = self.ticket_path()
        tokens.revoke_token(self.device)
        client = Client()
        self.assert_rejected(self.open(path, client=client), client)

    def test_expired_token_between_issue_and_redeem_fails(self):
        """Si el token caduca antes de canjear, tampoco."""
        path = self.ticket_path()
        type(self.device).objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assert_rejected(self.open(path))

    def test_deactivated_account_fails(self):
        """Una cuenta desactivada no entra."""
        path = self.ticket_path()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assert_rejected(self.open(path))

    def test_ticket_of_another_device_is_independent(self):
        """Revocar un dispositivo no invalida los tickets ni las sesiones de otro."""
        other, other_raw = tokens.issue_token(self.user, "iPad")
        path = self.ticket_path()
        tokens.revoke_token(other)
        self.assertEqual(self.open(path).status_code, 302)

    def test_post_is_not_allowed_on_redeem(self):
        """El canje es solo GET: un POST no lo gasta."""
        path = self.ticket_path()
        self.assertEqual(Client().post(path, HTTP_USER_AGENT=APP_UA).status_code, 405)
        self.assertIsNone(WebLoginTicket.objects.get().used_at)


class LogoutEndsWebSessionTests(WebSessionTestCase):
    """Cerrar sesión o revocar el dispositivo corta también la web que la app abrió."""

    def test_logout_ends_the_web_session(self):
        """Tras /auth/logout la sesión web creada con el ticket deja de valer."""
        client = Client()
        self.open(self.ticket_path(), client=client)
        self.assertEqual(client.get(reverse("my_profile")).status_code, 200)
        self.assertEqual(self.client.post(reverse("api_logout"), HTTP_AUTHORIZATION=f"Bearer {self.raw}").status_code, 200)
        self.assertEqual(client.get(reverse("my_profile")).status_code, 302)

    def test_other_web_sessions_survive(self):
        """Las sesiones web normales de la cuenta (navegador) no se tocan."""
        browser = Client()
        browser.force_login(self.user)
        tokens.revoke_token(self.device)
        self.assertEqual(browser.get(reverse("my_profile")).status_code, 200)


class PurgeTests(WebSessionTestCase):
    """Limpieza oportunista de tickets viejos."""

    def test_old_unused_tickets_are_deleted_but_used_ones_kept(self):
        """Se borran los caducados sin canjear de hace más de un día; los canjeados se conservan mientras pueda vivir su sesión."""
        now = timezone.now()
        old, _raw = web_session.issue_ticket(self.device, "/", now=now - timedelta(days=3))
        used, raw = web_session.issue_ticket(self.device, "/", now=now - timedelta(days=3))
        WebLoginTicket.objects.filter(pk=used.pk).update(used_at=now - timedelta(days=3))
        web_session.issue_ticket(self.device, "/", now=now)
        self.assertFalse(WebLoginTicket.objects.filter(pk=old.pk).exists())
        self.assertTrue(WebLoginTicket.objects.filter(pk=used.pk).exists())


class SecondTabKeepsCsrfTests(WebSessionTestCase):
    """Las pestañas canjean un ticket cada una con las mismas cookies: la segunda no rompe los formularios de la primera."""

    def test_second_ticket_keeps_session_and_csrf(self):
        """Con la sesión ya iniciada, canjear otro ticket no cambia la sesión ni rota el token CSRF."""
        client = Client()
        first = self.open(self.ticket_path(), client=client)
        self.assertEqual(first.status_code, 302)
        session_key = client.cookies["sessionid"].value
        csrf = client.cookies.get("csrftoken")
        second = self.open(self.ticket_path(), client=client)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(client.cookies["sessionid"].value, session_key)
        self.assertEqual(client.cookies.get("csrftoken").value if csrf else None,
                         csrf.value if csrf else None)
        self.assertEqual(int(client.session["_auth_user_id"]), self.user.pk)
