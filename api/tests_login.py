"""Tests de ``POST /api/v1/auth/login`` y ``/auth/logout``, y de que comparten el freno de login con la web."""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from api import tokens
from api.models import DeviceToken
from core.login_throttle import LOGIN_MAX_FAILURES, LOGIN_MAX_FAILURES_PER_ACCOUNT

User = get_user_model()
PASSWORD = "pass-12345-x"


class LoginTestCase(TestCase):
    """Base: una cuenta y cachés limpias."""

    def setUp(self):
        """Cuenta «ana» y cachés de límites vacías."""
        cache.clear()
        caches["ratelimit"].clear()
        self.user = User.objects.create_user("ana", "ana@example.com", PASSWORD)
        self.login_url = reverse("api_login")

    def login(self, login="ana", password=PASSWORD, ip="1.1.1.1", client=None, **extra):
        """POST de login con cuerpo JSON."""
        body = {"login": login, "password": password, **extra}
        return (client or self.client).post(self.login_url, json.dumps(body), content_type="application/json",
                                            REMOTE_ADDR=ip)

    def web_login(self, username, password, ip="1.1.1.1"):
        """Intento de login en la web."""
        return self.client.post(reverse("login"), {"username": username, "password": password}, REMOTE_ADDR=ip)


class LoginTests(LoginTestCase):
    """Credenciales, token devuelto y formato."""

    def test_login_returns_a_working_token(self):
        """Con credenciales buenas devuelve un token que sirve en la API."""
        response = self.login(device_name="iPhone de Ana")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["user"], {"username": "ana", "email": "ana@example.com"})
        self.assertEqual(DeviceToken.objects.get(public_id=data["device"]).device_name, "iPhone de Ana")
        ping = self.client.get(reverse("api_ping"), HTTP_AUTHORIZATION=f"Bearer {data['token']}")
        self.assertEqual(ping.status_code, 200)

    def test_login_with_email(self):
        """Como en la web, vale el email en lugar del usuario."""
        self.assertEqual(self.login(login="ana@example.com").status_code, 201)

    def test_does_not_create_a_web_session(self):
        """No hay sesión ni cookies: el token no abre la web."""
        response = self.login()
        self.assertNotIn("sessionid", response.cookies)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_no_csrf_needed(self):
        """Un cliente que comprueba CSRF puede iniciar sesión (no hay cookie de la que depender)."""
        self.assertEqual(self.login(client=Client(enforce_csrf_checks=True)).status_code, 201)

    def test_bad_credentials_look_the_same(self):
        """Contraseña mala, usuario inexistente y cuenta desactivada dan el mismo 401 (no revela qué existe)."""
        User.objects.create_user("inactivo", "i@example.com", PASSWORD, is_active=False)
        bodies = {self.login(password="mala").content, self.login(login="nadie").content,
                  self.login(login="inactivo").content}
        self.assertEqual(len(bodies), 1)
        self.assertEqual(self.login(password="mala").status_code, 401)
        self.assertEqual(self.login(password="mala").json()["error"], "invalid_credentials")
        self.assertFalse(DeviceToken.objects.exists())

    def test_invalid_bodies(self):
        """Cuerpo que no es JSON, no es un objeto o con campos mal tipados: 400 con código estable."""
        post = lambda data: self.client.post(self.login_url, data, content_type="application/json")  # noqa: E731
        self.assertEqual(post("no es json").json()["error"], "invalid_json")
        self.assertEqual(post("[1, 2]").json()["error"], "invalid_json")
        self.assertEqual(post("{}").json()["error"], "invalid_field")
        self.assertEqual(post(json.dumps({"login": "ana", "password": 123})).json()["error"], "invalid_field")
        self.assertEqual(post(json.dumps({"login": " ", "password": "x"})).json()["error"], "invalid_field")
        self.assertEqual(post(json.dumps({"login": "ana", "password": "x" * 2000})).status_code, 400)
        self.assertEqual(post(json.dumps({"login": "ana", "password": "x", "device_name": 5})).status_code, 400)

    def test_get_is_not_allowed(self):
        """Solo POST."""
        self.assertEqual(self.client.get(self.login_url).status_code, 405)


@override_settings(RATE_LIMITS_ENABLED=True, API_PUBLIC_LIMIT_PER_MINUTE=1000)
class LoginThrottleTests(LoginTestCase):
    """Mismo freno que la web, compartido en los dos sentidos."""

    def test_locks_after_max_failures_even_with_the_right_password(self):
        """Tras los fallos permitidos, 429 con Retry-After, también con la contraseña buena."""
        for _n in range(LOGIN_MAX_FAILURES):
            self.assertEqual(self.login(password="mala").status_code, 401)
        response = self.login()
        self.assertEqual((response.status_code, response.json()["error"]), (429, "login_locked"))
        self.assertEqual(response["Retry-After"], "900")
        self.assertFalse(DeviceToken.objects.exists())

    def test_other_ip_or_account_is_not_locked(self):
        """El bloqueo por IP y usuario no afecta a otra IP ni a otra cuenta."""
        User.objects.create_user("luis", "luis@example.com", PASSWORD)
        for _n in range(LOGIN_MAX_FAILURES):
            self.login(password="mala")
        self.assertEqual(self.login(ip="2.2.2.2").status_code, 201)
        self.assertEqual(self.login(login="luis").status_code, 201)

    def test_success_resets_the_counter(self):
        """Un acierto pone a cero los fallos."""
        for _n in range(LOGIN_MAX_FAILURES - 1):
            self.login(password="mala")
        self.assertEqual(self.login().status_code, 201)
        for _n in range(LOGIN_MAX_FAILURES - 1):
            self.assertEqual(self.login(password="mala").status_code, 401)
        self.assertEqual(self.login().status_code, 201)

    def test_account_limit_across_ips_and_spellings(self):
        """El freno por cuenta cuenta desde cualquier IP y escribiendo usuario o email."""
        for n in range(LOGIN_MAX_FAILURES_PER_ACCOUNT):
            self.login(login="ana" if n % 2 else "ANA@example.com", password="mala", ip=f"9.9.{n}.1")
        self.assertEqual(self.login(ip="5.5.5.5").status_code, 429)

    def test_web_failures_lock_the_api(self):
        """Los fallos en la web bloquean la API: es el mismo contador."""
        for _n in range(LOGIN_MAX_FAILURES):
            self.web_login("ana", "mala")
        self.assertEqual(self.login().status_code, 429)

    def test_api_failures_lock_the_web(self):
        """Y al revés: los fallos en la API bloquean el login web."""
        for _n in range(LOGIN_MAX_FAILURES):
            self.login(password="mala")
        self.assertEqual(self.web_login("ana", PASSWORD).status_code, 429)

    @override_settings(API_PUBLIC_LIMIT_PER_MINUTE=2)
    def test_public_ip_limit_applies(self):
        """Además, el límite por IP de las rutas públicas de la API."""
        codes = [self.login(password="mala", ip="3.3.3.3").status_code for _n in range(4)]
        self.assertEqual(codes, [401, 401, 429, 429])


class LogoutTests(LoginTestCase):
    """Cerrar sesión revoca el token del dispositivo."""

    def setUp(self):
        """Dos dispositivos de la misma cuenta."""
        super().setUp()
        _device, self.raw = tokens.issue_token(self.user, "iPhone")
        _other, self.other_raw = tokens.issue_token(self.user, "iPad")
        self.url = reverse("api_logout")

    def logout(self, token=None):
        """POST de logout con el token indicado."""
        return self.client.post(self.url, HTTP_AUTHORIZATION=f"Bearer {token or self.raw}")

    def test_logout_revokes_only_this_token(self):
        """El token usado deja de servir; el de otro dispositivo sigue valiendo."""
        self.assertEqual(self.logout().json(), {"revoked": True})
        self.assertEqual(self.client.get(reverse("api_ping"), HTTP_AUTHORIZATION=f"Bearer {self.raw}").status_code, 401)
        self.assertEqual(self.client.get(reverse("api_ping"), HTTP_AUTHORIZATION=f"Bearer {self.other_raw}").status_code, 200)

    def test_logout_twice_is_unauthorized(self):
        """Repetirlo con el mismo token ya es 401."""
        self.logout()
        self.assertEqual(self.logout().status_code, 401)

    def test_logout_needs_a_token(self):
        """Sin token, 401."""
        self.assertEqual(self.client.post(self.url).status_code, 401)

    def test_login_logout_roundtrip(self):
        """Iniciar y cerrar sesión de extremo a extremo."""
        token = self.login().json()["token"]
        self.assertEqual(self.logout(token).status_code, 200)
        self.assertEqual(self.client.get(reverse("api_ping"), HTTP_AUTHORIZATION=f"Bearer {token}").status_code, 401)
