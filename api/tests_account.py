"""Tests de ``/api/v1/account/delete``: mismas reglas que la web, confirmación, freno y revocación de dispositivos."""
import json

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse

from api import tokens
from api.models import DeviceToken, PushDevice
from core.models import Membership
from core.services import create_club
from players.models import Player

User = get_user_model()
PASSWORD = "pass-12345-x"


class AccountDeleteTestCase(TestCase):
    """Base: un club con capitán y un miembro enlazado a un jugador, cada uno con su dispositivo."""

    def setUp(self):
        """Crea el club, los usuarios, la ficha del miembro y los tokens."""
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capitan", "cap@example.com", PASSWORD)
        self.club = create_club("Club Uno", "Sevilla", self.captain, gender="M")
        self.member = User.objects.create_user("miembro", "mie@example.com", PASSWORD)
        Membership.objects.create(user=self.member, club=self.club, role=Membership.MEMBER)
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Ruiz", user=self.member)
        self.device, self.raw = tokens.issue_token(self.member, "iPhone")
        self.captain_device, self.captain_raw = tokens.issue_token(self.captain, "iPad")
        self.url = reverse("api_account_delete")

    def post(self, body, token=None):
        """POST con cuerpo JSON y el token indicado (el del miembro por defecto)."""
        return self.client.post(self.url, json.dumps(body), content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {token or self.raw}")


class DeleteAccountTests(AccountDeleteTestCase):
    """Borrado correcto y sus efectos."""

    def test_requires_token(self):
        """Sin token no hay borrado."""
        response = self.client.post(self.url, json.dumps({"confirm": PASSWORD}), content_type="application/json")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())

    def test_deletes_account_and_keeps_player_sheet(self):
        """Con la contraseña correcta borra la cuenta y la ficha queda en el club sin cuenta."""
        response = self.post({"confirm": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True})
        self.assertFalse(User.objects.filter(pk=self.member.pk).exists())
        self.player.refresh_from_db()
        self.assertIsNone(self.player.user)
        self.assertFalse(self.player.in_team)

    def test_delete_player_option(self):
        """Con ``delete_player`` se elimina también la ficha."""
        self.assertEqual(self.post({"confirm": PASSWORD, "delete_player": True}).status_code, 200)
        self.assertFalse(Player.objects.filter(pk=self.player.pk).exists())

    def test_token_is_dead_afterwards(self):
        """El token usado deja de servir y no queda ningún dispositivo ni registro push de la cuenta."""
        PushDevice.objects.create(device_token=self.device, apns_token="ab" * 32)
        self.post({"confirm": PASSWORD})
        self.assertEqual(self.post({"confirm": PASSWORD}).status_code, 401)
        self.assertFalse(DeviceToken.objects.filter(pk=self.device.pk).exists())
        self.assertEqual(PushDevice.objects.count(), 0)

    def test_other_accounts_untouched(self):
        """Los datos del club y de otras cuentas siguen intactos."""
        self.post({"confirm": PASSWORD})
        self.assertTrue(User.objects.filter(pk=self.captain.pk).exists())
        self.assertTrue(DeviceToken.objects.filter(pk=self.captain_device.pk, revoked_at__isnull=True).exists())
        self.assertTrue(Membership.objects.filter(user=self.captain, club=self.club).exists())

    def test_account_without_password_confirms_with_username(self):
        """Las cuentas sin contraseña (Google/Apple) confirman escribiendo su nombre de usuario."""
        self.member.set_unusable_password()
        self.member.save()
        self.assertEqual(self.post({"confirm": "otro"}).status_code, 403)
        self.assertEqual(self.post({"confirm": " MIEMBRO "}).status_code, 200)


class RefusalTests(AccountDeleteTestCase):
    """Rechazos: no se borra nada."""

    def test_wrong_password(self):
        """Contraseña incorrecta: 403 ``confirmation_failed`` y la cuenta sigue."""
        response = self.post({"confirm": "mala"})
        self.assertEqual((response.status_code, response.json()["error"]), (403, "confirmation_failed"))
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())
        self.assertTrue(DeviceToken.objects.get(pk=self.device.pk).is_active())

    def test_missing_or_invalid_fields(self):
        """Sin ``confirm`` o con ``delete_player`` que no es booleano: 400."""
        self.assertEqual(self.post({}).status_code, 400)
        response = self.post({"confirm": PASSWORD, "delete_player": "yes"})
        self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_field"))
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())

    def test_captain_is_blocked_with_reason(self):
        """Un capitán recibe 409 ``account_blocked`` con el motivo, aunque la contraseña sea correcta."""
        response = self.post({"confirm": PASSWORD}, token=self.captain_raw)
        self.assertEqual((response.status_code, response.json()["error"]), (409, "account_blocked"))
        self.assertIn("Club Uno", response.json()["detail"])
        self.assertTrue(User.objects.filter(pk=self.captain.pk).exists())

    def test_staff_is_blocked(self):
        """El personal de Zyra no puede borrarse desde la API."""
        self.member.is_staff = True
        self.member.save()
        self.assertEqual(self.post({"confirm": PASSWORD}).status_code, 409)

    @override_settings(RATE_LIMITS_ENABLED=True)
    def test_attempts_are_limited(self):
        """Tras 5 intentos por hora, el siguiente recibe 429 aunque la contraseña sea correcta."""
        for _attempt in range(5):
            self.assertEqual(self.post({"confirm": "mala"}).status_code, 403)
        response = self.post({"confirm": PASSWORD})
        self.assertEqual((response.status_code, response.json()["error"]), (429, "rate_limited"))
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())
