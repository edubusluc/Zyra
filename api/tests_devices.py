"""Tests del registro push (``/api/v1/devices``): alta idempotente, validación, aislamiento y baja."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from api import push, tokens
from api.models import PushDevice

User = get_user_model()
APNS = "ab" * 32  # 64 caracteres hexadecimales, como los de APNs
OTHER_APNS = "cd" * 32


class DevicesTestCase(TestCase):
    """Base: una cuenta con un dispositivo."""

    def setUp(self):
        """Cuenta «ana» con un token y cachés de límites limpias."""
        caches["ratelimit"].clear()
        self.user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        self.device, self.raw = tokens.issue_token(self.user, "iPhone")
        self.url = reverse("api_devices")

    def post(self, body, token=None):
        """POST con cuerpo JSON y el token indicado."""
        return self.client.post(self.url, json.dumps(body), content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {token or self.raw}")


class RegisterTests(DevicesTestCase):
    """Alta y actualización."""

    def test_first_registration_creates(self):
        """La primera vez crea el registro (201), con entorno de producción por defecto, sin devolver el token."""
        response = self.post({"apns_token": APNS})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"registered": True, "environment": "production"})
        self.assertNotIn(APNS, response.content.decode())
        registered = PushDevice.objects.get()
        self.assertEqual((registered.device_token, registered.apns_token, registered.app_version),
                         (self.device, APNS, ""))

    def test_repeating_is_idempotent(self):
        """Repetir el alta da 200 y no duplica."""
        self.post({"apns_token": APNS})
        self.assertEqual(self.post({"apns_token": APNS}).status_code, 200)
        self.assertEqual(PushDevice.objects.count(), 1)

    def test_new_apns_token_updates_in_place(self):
        """Si APNs cambia el token del mismo dispositivo, se actualiza el mismo registro."""
        self.post({"apns_token": APNS, "environment": "sandbox", "app_version": "1.0.0"})
        response = self.post({"apns_token": OTHER_APNS.upper(), "app_version": "1.1.0"})
        self.assertEqual(response.status_code, 200)
        registered = PushDevice.objects.get()
        self.assertEqual((registered.apns_token, registered.environment, registered.app_version),
                         (OTHER_APNS, "production", "1.1.0"))

    def test_token_is_normalized_to_lowercase(self):
        """El token de APNs se guarda en minúsculas (el mismo con distinta capitalización no se duplica)."""
        self.post({"apns_token": APNS.upper()})
        self.assertEqual(PushDevice.objects.get().apns_token, APNS)

    def test_sandbox_environment(self):
        """Admite el entorno de pruebas."""
        self.assertEqual(self.post({"apns_token": APNS, "environment": "sandbox"}).json()["environment"], "sandbox")

    def test_same_phone_with_another_account_takes_the_token(self):
        """El mismo token de APNs en otra cuenta pasa a esa cuenta: la anterior ya no recibe nada."""
        self.post({"apns_token": APNS})
        luis = User.objects.create_user("luis", "luis@example.com", "pass-12345-y")
        _device, luis_raw = tokens.issue_token(luis, "iPhone de Luis")
        self.assertEqual(self.post({"apns_token": APNS}, token=luis_raw).status_code, 201)
        registered = PushDevice.objects.get()
        self.assertEqual(registered.device_token.user, luis)
        self.assertFalse(PushDevice.objects.filter(device_token=self.device).exists())

    def test_two_devices_of_one_account_are_independent(self):
        """Dos dispositivos de la misma cuenta tienen cada uno el suyo."""
        _other, other_raw = tokens.issue_token(self.user, "iPad")
        self.post({"apns_token": APNS})
        self.post({"apns_token": OTHER_APNS}, token=other_raw)
        self.assertEqual(PushDevice.objects.count(), 2)

    def test_race_on_the_unique_token_is_retried(self):
        """Un choque con la restricción única por un alta simultánea se reintenta una vez."""
        real = PushDevice.objects.update_or_create
        calls = []

        def flaky(*args, **kwargs):
            """Falla la primera vez, como si otra petición hubiera ganado la carrera."""
            calls.append(1)
            if len(calls) == 1:
                raise IntegrityError("duplicado")
            return real(*args, **kwargs)

        with mock.patch.object(type(PushDevice.objects), "update_or_create", side_effect=flaky):
            registered, created = push.register(self.device, APNS)
        self.assertTrue(created)
        self.assertEqual(len(calls), 2)
        self.assertEqual(registered.apns_token, APNS)


class ValidationTests(DevicesTestCase):
    """Entradas no válidas."""

    def test_invalid_bodies_are_rejected(self):
        """Token que no es hexadecimal, demasiado corto o largo, entorno raro o versión rara: 400 y nada guardado."""
        bad = [
            {}, {"apns_token": ""}, {"apns_token": 5}, {"apns_token": "zz" * 32}, {"apns_token": "ab" * 8},
            {"apns_token": "ab" * 101}, {"apns_token": APNS + " "}, {"apns_token": APNS, "environment": "dev"},
            {"apns_token": APNS, "environment": 1}, {"apns_token": APNS, "app_version": "1 0"},
            {"apns_token": APNS, "app_version": "x" * 40}, {"apns_token": APNS, "app_version": 3},
        ]
        for body in bad:
            response = self.post(body)
            self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_field"), body)
        self.assertFalse(PushDevice.objects.exists())

    def test_body_must_be_a_json_object(self):
        """Un cuerpo que no es un objeto JSON da 400."""
        response = self.client.post(self.url, "[1]", content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.json()["error"], "invalid_json")

    def test_needs_a_valid_token(self):
        """Sin token, o con uno revocado, no se registra nada."""
        self.assertEqual(self.client.post(self.url, json.dumps({"apns_token": APNS}),
                                          content_type="application/json").status_code, 401)
        tokens.revoke_token(self.device)
        self.assertEqual(self.post({"apns_token": APNS}).status_code, 401)
        self.assertFalse(PushDevice.objects.exists())

    def test_get_is_not_allowed(self):
        """No hay lectura: GET es 405."""
        self.assertEqual(self.client.get(self.url, HTTP_AUTHORIZATION=f"Bearer {self.raw}").status_code, 405)


class UnregisterTests(DevicesTestCase):
    """Baja del registro."""

    def delete(self, token=None):
        """DELETE con el token indicado."""
        return self.client.delete(self.url, HTTP_AUTHORIZATION=f"Bearer {token or self.raw}")

    def test_delete_unregisters_and_is_idempotent(self):
        """DELETE retira el registro y repetirlo no falla."""
        self.post({"apns_token": APNS})
        self.assertEqual(self.delete().json(), {"registered": False})
        self.assertFalse(PushDevice.objects.exists())
        self.assertEqual(self.delete().status_code, 200)

    def test_delete_only_affects_own_device(self):
        """Darse de baja no toca el registro de otro dispositivo."""
        _other, other_raw = tokens.issue_token(self.user, "iPad")
        self.post({"apns_token": APNS})
        self.post({"apns_token": OTHER_APNS}, token=other_raw)
        self.delete()
        self.assertEqual(PushDevice.objects.get().apns_token, OTHER_APNS)

    def test_logout_removes_the_registration(self):
        """Cerrar sesión en la app (revocar el token) retira el registro push: no se notifica a un dispositivo sin sesión."""
        self.post({"apns_token": APNS})
        self.assertEqual(self.client.post(reverse("api_logout"), HTTP_AUTHORIZATION=f"Bearer {self.raw}").status_code, 200)
        self.assertFalse(PushDevice.objects.exists())

    def test_revoking_one_device_keeps_the_others(self):
        """Revocar un dispositivo no retira el registro de otro de la cuenta."""
        other, other_raw = tokens.issue_token(self.user, "iPad")
        self.post({"apns_token": APNS})
        self.post({"apns_token": OTHER_APNS}, token=other_raw)
        tokens.revoke_token(other)
        self.assertEqual(PushDevice.objects.get().device_token, self.device)

    def test_deleting_the_account_deletes_the_registration(self):
        """Al eliminar la cuenta se borra el registro (dato personal)."""
        self.post({"apns_token": APNS})
        self.user.delete()
        self.assertFalse(PushDevice.objects.exists())
