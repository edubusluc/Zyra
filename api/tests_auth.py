"""Tests de la autenticación por token, los errores y los límites de la API (vía ``GET /api/v1/ping``)."""
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse

from api import tokens

User = get_user_model()


class ApiTestCase(TestCase):
    """Base: una cuenta con un token y caché de límites limpia."""

    def setUp(self):
        """Cuenta, token en claro y caché de límites vacía."""
        caches["ratelimit"].clear()
        self.user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        self.device, self.raw = tokens.issue_token(self.user, "iPhone")
        self.url = reverse("api_ping")

    def get(self, token=None, **extra):
        """GET a ping con el token indicado (por defecto el válido)."""
        header = {"HTTP_AUTHORIZATION": f"Bearer {token or self.raw}"}
        return self.client.get(self.url, **header, **extra)


class AuthenticationTests(ApiTestCase):
    """El token da acceso; sin token o con uno malo, 401 en JSON."""

    def test_valid_token(self):
        """Con token válido responde el dispositivo, sin datos de la cuenta."""
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device"], self.device.public_id)
        self.assertNotIn("ana", response.content.decode())

    def test_missing_header(self):
        """Sin cabecera: 401 con el formato de error estable."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")
        self.assertEqual(response["WWW-Authenticate"], "Bearer")

    def test_wrong_scheme_and_garbage(self):
        """Otro esquema o un token inventado: 401."""
        self.assertEqual(self.client.get(self.url, HTTP_AUTHORIZATION=f"Basic {self.raw}").status_code, 401)
        self.assertEqual(self.get(token="zyra_inventado").status_code, 401)

    def test_revoked_and_expired_look_the_same(self):
        """Revocado y caducado dan el mismo error que uno inexistente (sin pistas)."""
        tokens.revoke_token(self.device)
        revoked = self.get()
        self.assertEqual((revoked.status_code, revoked.json()["error"]), (401, "unauthorized"))

    def test_session_cookie_does_not_authenticate(self):
        """Una sesión web no vale en la API: solo el token."""
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_token_does_not_give_web_access(self):
        """El token no abre páginas de la web."""
        response = self.client.get(reverse("home"), HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_authenticated_user_is_set(self):
        """La vista recibe la cuenta del token en ``request.user``."""
        response = self.get()
        self.assertEqual(response.wsgi_request.user, self.user)
        self.assertEqual(response.wsgi_request.device_token.pk, self.device.pk)


class ResponseShapeTests(ApiTestCase):
    """Formato común de las respuestas."""

    def test_no_session_cookie_and_no_cache(self):
        """No crea sesión ni cookies y las respuestas no se cachean."""
        response = self.get()
        self.assertNotIn("sessionid", response.cookies)
        self.assertNotIn("csrftoken", response.cookies)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_post_without_csrf_is_allowed_to_reach_the_view(self):
        """Sin CSRF: un POST con cliente que sí lo comprueba llega a la vista (que responde 405, no 403)."""
        from django.test import Client
        response = Client(enforce_csrf_checks=True).post(
            self.url, HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "method_not_allowed")
        self.assertIn("GET", response["Allow"])

    def test_unknown_route_is_json_404(self):
        """Una ruta desconocida bajo /api/v1/ responde 404 en JSON, no la página HTML."""
        response = self.client.get("/api/v1/no-existe/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "not_found")

    def test_language_follows_accept_language(self):
        """Los textos de error siguen ``Accept-Language``; el código no cambia."""
        es = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="es").json()
        en = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="en").json()
        self.assertEqual(es["error"], en["error"])
        self.assertNotEqual(es["detail"], en["detail"])


@override_settings(RATE_LIMITS_ENABLED=True, API_RATE_LIMIT_PER_MINUTE=3, API_AUTH_FAILURES_PER_MINUTE=3,
                   API_PUBLIC_LIMIT_PER_MINUTE=2)
class ThrottleTests(ApiTestCase):
    """Límite por token, por IP en lo público y para los tokens inválidos."""

    def test_limit_is_per_token_not_per_ip(self):
        """Dos tokens desde la misma IP no se pisan; uno que se pasa recibe 429 con Retry-After."""
        other, other_raw = tokens.issue_token(self.user, "iPad")
        codes = [self.get(REMOTE_ADDR="5.5.5.5").status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        self.assertEqual(self.get(token=other_raw, REMOTE_ADDR="5.5.5.5").status_code, 200)
        self.assertEqual(self.get(REMOTE_ADDR="5.5.5.5")["Retry-After"], "60")

    def test_same_token_from_many_ips_shares_the_limit(self):
        """El límite sigue al token aunque cambie la IP (redes móviles)."""
        codes = [self.get(REMOTE_ADDR=f"6.6.6.{n}").status_code for n in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])

    def test_invalid_tokens_are_blocked_per_ip(self):
        """Tras varios intentos con token inválido, esa IP recibe 429 sin llegar a la base de datos."""
        for _n in range(3):
            self.assertEqual(self.get(token="zyra_mal", REMOTE_ADDR="7.7.7.7").status_code, 401)
        with self.assertNumQueries(0):
            self.assertEqual(self.get(token="zyra_mal", REMOTE_ADDR="7.7.7.7").status_code, 429)
        self.assertEqual(self.get(REMOTE_ADDR="8.8.8.8").status_code, 200)

    def test_public_routes_limit_by_ip(self):
        """Las rutas públicas (aquí el 404 JSON) se limitan por IP."""
        codes = [self.client.get("/api/v1/x/", REMOTE_ADDR="4.4.4.4").status_code for _ in range(4)]
        self.assertEqual(codes, [404, 404, 429, 429])

    @override_settings(RATE_LIMITS_ENABLED=False)
    def test_disabled_never_limits(self):
        """Con los límites apagados no se limita."""
        self.assertTrue(all(self.get().status_code == 200 for _ in range(6)))
