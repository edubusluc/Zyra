"""Tests de ``/api/v1/auth/apple``: verificación del token (con claves generadas aquí, sin red) y reglas de cuentas."""
import hashlib
import json
import time
from unittest import mock

import jwt
from allauth.account.models import EmailAddress
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase, override_settings
from django.urls import reverse

from api import apple
from api.models import AppleIdentity, DeviceToken
from core.models import BlockedEmail

User = get_user_model()
CLIENT_ID = "es.zyra.app"
NONCE = "nonce-en-claro-123"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks(key=KEY, kid="kid1"):
    """Claves públicas como las publica Apple."""
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return [{**data, "kid": kid, "alg": "RS256", "use": "sig"}]


def make_token(sub="apple-sub-1", email="ana@example.com", key=KEY, kid="kid1", **overrides):
    """``identity_token`` firmado, con los datos válidos salvo lo que se cambie en ``overrides``."""
    now = int(time.time())
    claims = {"iss": apple.ISSUER, "aud": CLIENT_ID, "iat": now, "exp": now + 600, "sub": sub, "email": email,
              "email_verified": "true", "nonce": hashlib.sha256(NONCE.encode()).hexdigest()}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


@override_settings(APPLE_CLIENT_IDS=CLIENT_ID)
class AppleTestCase(TestCase):
    """Base: Apple configurado, caché limpia y las claves de Apple simuladas."""

    def setUp(self):
        """Limpia cachés y sustituye la descarga de claves."""
        cache.clear()
        caches["ratelimit"].clear()
        patcher = mock.patch("api.apple.fetch_jwks", return_value=jwks())
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse("api_apple")

    def post(self, token=None, nonce=NONCE, **extra):
        """POST con cuerpo JSON (token válido por defecto)."""
        body = {"identity_token": token or make_token(), "nonce": nonce, **extra}
        return self.client.post(self.url, json.dumps(body), content_type="application/json")


class TokenVerificationTests(AppleTestCase):
    """Se acepta solo un token firmado por Apple, para nuestra app, vigente, con su nonce y no usado antes."""

    def test_valid_token(self):
        """Un token correcto devuelve sus datos."""
        claims = apple.verify_identity_token(make_token(), NONCE)
        self.assertEqual(claims, {"sub": "apple-sub-1", "email": "ana@example.com", "email_verified": True})

    def test_email_verified_as_boolean(self):
        """Apple a veces manda ``email_verified`` como booleano."""
        claims = apple.verify_identity_token(make_token(email_verified=True), NONCE)
        self.assertTrue(claims["email_verified"])

    def test_rejected_tokens(self):
        """Firma ajena, caducado, otro emisor, otra app, nonce incorrecto, sin nonce y alg ``none``."""
        bad = {
            "signed by another key": make_token(key=OTHER_KEY),
            "expired": make_token(exp=int(time.time()) - 10),
            "other issuer": make_token(iss="https://evil.example.com"),
            "other audience": make_token(aud="com.otra.app"),
            "no subject": make_token(sub=None),
            "wrong nonce": make_token(nonce=hashlib.sha256(b"otro").hexdigest()),
            "no nonce": make_token(nonce=None),
            "unknown kid": make_token(kid="desconocido"),
            "garbage": "no.es.un.jwt",
            "alg none": jwt.encode({"iss": apple.ISSUER, "aud": CLIENT_ID, "sub": "x"}, None, algorithm="none"),
        }
        for name, token in bad.items():
            with self.subTest(name), self.assertRaises(apple.AppleTokenError):
                apple.verify_identity_token(token, NONCE)

    def test_token_can_be_used_only_once(self):
        """Repetir el mismo token falla (no se puede reutilizar uno interceptado)."""
        token = make_token()
        apple.verify_identity_token(token, NONCE)
        with self.assertRaises(apple.AppleTokenError):
            apple.verify_identity_token(token, NONCE)

    def test_keys_are_cached(self):
        """Las claves se descargan una vez y se reutilizan."""
        apple.verify_identity_token(make_token(), NONCE)
        apple.verify_identity_token(make_token(sub="otro"), NONCE)
        self.assertEqual(self.fetch.call_count, 1)

    def test_unknown_kid_does_not_hammer_apple(self):
        """Tokens con claves inventadas no provocan una descarga cada vez: solo una cada pocos minutos."""
        for _attempt in range(5):
            with self.assertRaises(apple.AppleTokenError):
                apple.verify_identity_token(make_token(kid="inventado"), NONCE)
        self.assertLessEqual(self.fetch.call_count, 2)

    def test_apple_down(self):
        """Sin claves en caché y sin respuesta de Apple, error distinto al de token inválido."""
        self.fetch.side_effect = apple.AppleUnavailable("sin red")
        with self.assertRaises(apple.AppleUnavailable):
            apple.verify_identity_token(make_token(), NONCE)


class AppleEndpointTests(AppleTestCase):
    """El endpoint: desactivado, cuentas nuevas, enlace por email y rechazos."""

    @override_settings(APPLE_CLIENT_IDS="")
    def test_disabled_without_configuration(self):
        """Sin ``APPLE_CLIENT_IDS`` responde 404 y no llama a Apple."""
        response = self.post()
        self.assertEqual((response.status_code, response.json()["error"]), (404, "not_found"))
        self.fetch.assert_not_called()

    def test_creates_new_account_without_password(self):
        """Usuario nuevo: cuenta sin contraseña, email verificado y token de dispositivo."""
        response = self.post(first_name="Ana", last_name="Ruiz", device_name="iPhone")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="ana@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertEqual((user.first_name, user.last_name), ("Ana", "Ruiz"))
        self.assertTrue(EmailAddress.objects.filter(user=user, email="ana@example.com", verified=True).exists())
        self.assertEqual(AppleIdentity.objects.get().user, user)
        self.assertEqual(response.json()["user"]["email"], "ana@example.com")
        self.assertTrue(DeviceToken.objects.filter(user=user, device_name="iPhone").exists())

    def test_second_login_uses_the_linked_account(self):
        """Volver a entrar (otro token) usa la misma cuenta, aunque Apple ya no dé el email."""
        self.post()
        response = self.post(make_token(email=None))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.count(), 1)

    def test_links_existing_verified_account(self):
        """Una cuenta con ese email verificado se enlaza y conserva su contraseña."""
        user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        EmailAddress.objects.create(user=user, email="ana@example.com", verified=True, primary=True)
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(AppleIdentity.objects.get().user, user)
        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        self.assertEqual(User.objects.count(), 1)

    def test_unconfirmed_existing_account_is_not_linked(self):
        """Si el email existe sin confirmar, no se enlaza ni se crea nada (409)."""
        User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        response = self.post()
        self.assertEqual((response.status_code, response.json()["error"]), (409, "apple_account_unconfirmed"))
        self.assertEqual((AppleIdentity.objects.count(), User.objects.count()), (0, 1))

    def test_unverified_apple_email_is_refused(self):
        """Si Apple no verificó el email, no se crea ni se enlaza."""
        response = self.post(make_token(email_verified="false"))
        self.assertEqual((response.status_code, response.json()["error"]), (403, "apple_email_unverified"))
        self.assertEqual(User.objects.count(), 0)

    def test_blocked_email_is_refused(self):
        """Un email bloqueado por el personal no entra."""
        BlockedEmail.objects.create(email="ana@example.com")
        response = self.post()
        self.assertEqual((response.status_code, response.json()["error"]), (403, "email_blocked"))
        self.assertEqual(User.objects.count(), 0)

    def test_inactive_account_is_refused(self):
        """Una cuenta desactivada no entra por Apple, ni ya enlazada ni por email."""
        user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x", is_active=False)
        EmailAddress.objects.create(user=user, email="ana@example.com", verified=True, primary=True)
        self.assertEqual(self.post().status_code, 401)
        AppleIdentity.objects.create(user=user, subject="apple-sub-2")
        self.assertEqual(self.post(make_token(sub="apple-sub-2")).status_code, 401)

    def test_invalid_and_replayed_token(self):
        """Token falso o repetido: 401 ``invalid_apple_token``."""
        self.assertEqual(self.post(make_token(key=OTHER_KEY)).json()["error"], "invalid_apple_token")
        token = make_token()
        self.assertEqual(self.post(token).status_code, 201)
        self.assertEqual(self.post(token).status_code, 401)

    def test_apple_unavailable(self):
        """Sin claves de Apple: 503 con código propio."""
        self.fetch.side_effect = apple.AppleUnavailable("sin red")
        response = self.post()
        self.assertEqual((response.status_code, response.json()["error"]), (503, "apple_unavailable"))

    def test_missing_fields(self):
        """Sin ``identity_token`` o sin ``nonce``: 400."""
        for body in ({"nonce": NONCE}, {"identity_token": make_token()}):
            response = self.client.post(self.url, json.dumps(body), content_type="application/json")
            self.assertEqual(response.status_code, 400)

    def test_deleting_the_account_removes_the_link(self):
        """Al borrar la cuenta desaparece el enlace con Apple."""
        self.post()
        User.objects.get().delete()
        self.assertEqual(AppleIdentity.objects.count(), 0)
