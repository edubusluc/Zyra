"""Tests del modelo ``DeviceToken`` y del ciclo de vida de los tokens (``api.tokens``)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from api import tokens
from api.models import DeviceToken

User = get_user_model()


class TokenLifecycleTests(TestCase):
    """Crear, resolver, renovar y revocar tokens."""

    def setUp(self):
        """Una cuenta y un token recién creado."""
        self.user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        self.now = timezone.now()
        self.device, self.raw = tokens.issue_token(self.user, "iPhone de Ana", now=self.now)

    def test_only_the_hash_is_stored(self):
        """En la base de datos no está el token en claro, solo su SHA-256."""
        self.assertNotEqual(self.device.token_hash, self.raw)
        self.assertEqual(self.device.token_hash, tokens.hash_token(self.raw))
        self.assertFalse(DeviceToken.objects.filter(token_hash=self.raw).exists())
        self.assertTrue(self.raw.startswith(tokens.TOKEN_PREFIX))

    def test_gets_public_id_with_own_prefix(self):
        """Tiene identificador público con el prefijo del modelo."""
        self.assertTrue(self.device.public_id.startswith("DVT"))

    def test_tokens_are_unique(self):
        """Dos tokens de la misma cuenta son distintos."""
        _other, raw = tokens.issue_token(self.user, "iPad", now=self.now)
        self.assertNotEqual(raw, self.raw)

    def test_resolve_returns_device_with_user(self):
        """Un token válido devuelve su dispositivo y su cuenta."""
        device = tokens.resolve_token(self.raw, now=self.now)
        self.assertEqual(device.pk, self.device.pk)
        self.assertEqual(device.user, self.user)

    def test_unknown_or_malformed_token_is_rejected(self):
        """Un token inventado o sin el prefijo no resuelve."""
        self.assertIsNone(tokens.resolve_token(tokens.TOKEN_PREFIX + "nada", now=self.now))
        self.assertIsNone(tokens.resolve_token("sin-prefijo", now=self.now))

    @override_settings(API_TOKEN_TTL_DAYS=90)
    def test_expired_token_is_rejected(self):
        """Pasada su caducidad ya no sirve."""
        self.assertIsNone(tokens.resolve_token(self.raw, now=self.now + timedelta(days=91)))

    def test_revoked_token_is_rejected(self):
        """Un token revocado deja de servir al instante."""
        tokens.revoke_token(self.device, now=self.now)
        self.assertIsNone(tokens.resolve_token(self.raw, now=self.now))

    def test_revoke_is_idempotent(self):
        """Revocar dos veces no cambia la fecha de la primera."""
        tokens.revoke_token(self.device, now=self.now)
        tokens.revoke_token(self.device, now=self.now + timedelta(hours=1))
        self.device.refresh_from_db()
        self.assertEqual(self.device.revoked_at, self.now)

    def test_inactive_account_is_rejected(self):
        """Un token de una cuenta desactivada no sirve."""
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(tokens.resolve_token(self.raw, now=self.now))

    def test_deleting_the_account_deletes_tokens(self):
        """Al eliminar la cuenta desaparecen sus tokens."""
        self.user.delete()
        self.assertFalse(DeviceToken.objects.exists())

    def test_device_name_is_trimmed(self):
        """El nombre del dispositivo se limpia y se acota."""
        device, _raw = tokens.issue_token(self.user, "  " + "x" * 300 + "  ", now=self.now)
        self.assertEqual(len(device.device_name), 100)


@override_settings(API_TOKEN_TOUCH_SECONDS=300, API_TOKEN_TTL_DAYS=90)
class TouchTests(TestCase):
    """El uso se anota y la caducidad se renueva sin escribir en cada petición."""

    def setUp(self):
        """Un token creado ahora."""
        user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        self.now = timezone.now()
        self.device, self.raw = tokens.issue_token(user, now=self.now)

    def test_recent_use_does_not_write(self):
        """Un uso dentro de la ventana no toca la base de datos."""
        with self.assertNumQueries(1):  # solo la consulta del token, ningún UPDATE
            tokens.resolve_token(self.raw, now=self.now + timedelta(seconds=60))

    def test_use_after_the_window_renews_expiry(self):
        """Pasada la ventana se anota el uso y se renueva la caducidad (deslizante)."""
        later = self.now + timedelta(days=30)
        tokens.resolve_token(self.raw, now=later)
        self.device.refresh_from_db()
        self.assertEqual(self.device.last_used_at, later)
        self.assertEqual(self.device.expires_at, later + timedelta(days=90))
