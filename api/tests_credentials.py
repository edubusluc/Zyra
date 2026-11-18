"""Tests de la seguridad de los tokens ante cambios de credenciales y cuentas del personal."""
from datetime import timedelta

from allauth.account.signals import password_changed, password_reset, password_set
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from api import tokens
from api.models import DeviceToken

User = get_user_model()


class PasswordChangeTests(TestCase):
    """Cambiar la contraseña cierra la sesión de todas las apps de la cuenta, y solo de ella."""

    def setUp(self):
        """Dos cuentas con dos dispositivos la primera."""
        self.user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        self.other = User.objects.create_user("bea", "bea@example.com", "pass-12345-x")
        self.phone, self.phone_raw = tokens.issue_token(self.user, "iPhone")
        self.tablet, self.tablet_raw = tokens.issue_token(self.user, "iPad")
        self.other_device, self.other_raw = tokens.issue_token(self.other, "iPhone de Bea")

    def test_each_password_signal_revokes_all_tokens(self):
        """Cambio, alta y restablecimiento de contraseña revocan todos los dispositivos de la cuenta."""
        for signal in (password_changed, password_set, password_reset):
            _device, raw = tokens.issue_token(self.user, "nuevo")
            signal.send(sender=User, request=None, user=self.user)
            self.assertIsNone(tokens.resolve_token(raw))
        self.assertIsNone(tokens.resolve_token(self.phone_raw))
        self.assertIsNone(tokens.resolve_token(self.tablet_raw))

    def test_other_accounts_keep_their_tokens(self):
        """Los dispositivos de otras cuentas no se tocan."""
        password_changed.send(sender=User, request=None, user=self.user)
        self.assertIsNotNone(tokens.resolve_token(self.other_raw))

    def test_changing_password_through_the_web_revokes(self):
        """De extremo a extremo: cambiar la contraseña en la web invalida el token de la app."""
        self.client.force_login(self.user)
        response = self.client.post("/accounts/password/change/", {
            "oldpassword": "pass-12345-x", "password1": "otra-clave-9876-Z", "password2": "otra-clave-9876-Z"})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("otra-clave-9876-Z"))
        self.assertIsNone(tokens.resolve_token(self.phone_raw))


class StaffTokenTests(TestCase):
    """Los tokens del personal duran 12 h como su sesión web y no se renuevan."""

    def setUp(self):
        """Una cuenta del personal y una normal."""
        self.now = timezone.now()
        self.staff = User.objects.create_user("jefe", "jefe@example.com", "pass-12345-x", is_staff=True)
        self.normal = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")

    def test_staff_token_expires_in_12_hours(self):
        """Caducidad a las 12 h para el personal y a los días configurados para el resto."""
        staff_device, _raw = tokens.issue_token(self.staff, "iPhone", now=self.now)
        normal_device, _raw = tokens.issue_token(self.normal, "iPhone", now=self.now)
        self.assertEqual(staff_device.expires_at, self.now + timedelta(hours=12))
        self.assertGreater(normal_device.expires_at, self.now + timedelta(days=1))

    @override_settings(API_TOKEN_TOUCH_SECONDS=300)
    def test_staff_token_is_not_renewed_by_use(self):
        """Usarlo no alarga la vida del token del personal, y pasadas las 12 h deja de servir."""
        device, raw = tokens.issue_token(self.staff, "iPhone", now=self.now)
        later = self.now + timedelta(hours=1)
        self.assertIsNotNone(tokens.resolve_token(raw, now=later))
        self.assertEqual(DeviceToken.objects.get(pk=device.pk).expires_at, self.now + timedelta(hours=12))
        self.assertIsNone(tokens.resolve_token(raw, now=self.now + timedelta(hours=12, minutes=1)))
