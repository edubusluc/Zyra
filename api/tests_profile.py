"""Tests de los endpoints de perfil: ``/api/v1/me/profile``, preferencias, email, contraseña, sesiones y traspaso."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache, caches
from django.test import TestCase, override_settings
from django.urls import reverse

from api.tokens import DeviceToken, issue_token
from core.models import Membership
from core.services import create_club
from players.models import Player

User = get_user_model()
PASSWORD = "Clave-Segura-123"


class ProfileApiTests(TestCase):
    """Capitán con club y un miembro con ficha; cada uno con su token."""

    def setUp(self):
        """Crea capitán, miembro y tokens."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", PASSWORD, first_name="Ana")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.user = User.objects.create_user("jug", "jug@example.com", PASSWORD)
        self.member = Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        Player.objects.create(club=self.club, name="Luis", last_name="Gil", user=self.user, in_team=True)
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.user_token = issue_token(self.user, "iPhone")

    def call(self, method, name, token, data=None, args=None):
        """Llama al endpoint ``name`` con el token indicado."""
        return getattr(self.client, method)(reverse(name, args=args or []), data=data, content_type="application/json",
                                            HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_profile")).status_code, 401)

    def test_profile_member(self):
        """El miembro ve su cuenta, su ficha, sin ``report_scope`` y sin capitanías."""
        data = self.call("get", "api_profile", self.user_token).json()
        self.assertEqual(data["account"]["username"], "jug")
        self.assertTrue(data["account"]["has_password"])
        self.assertEqual(data["sheets"][0]["player"]["name"], "Luis Gil")
        self.assertNotIn("report_scope", data["preferences"])
        self.assertEqual(data["captaincies"], [])

    def test_profile_captain_lists_successors(self):
        """El capitán ve ``report_scope`` y a quién puede traspasar."""
        data = self.call("get", "api_profile", self.captain_token).json()
        self.assertIn("report_scope", data["preferences"])
        self.assertEqual(data["captaincies"][0]["successors"][0]["id"], self.member.pk)

    def test_preferences_patch(self):
        """Cambia un booleano y valida tipos y valores."""
        r = self.call("patch", "api_profile_preferences", self.user_token, {"news_email": False, "monthly_scope": "competitivos"})
        self.assertEqual(r.status_code, 200)
        prefs = r.json()["preferences"]
        self.assertFalse(prefs["news_email"])
        self.assertEqual(prefs["monthly_scope"], "competitivos")
        self.assertEqual(self.call("patch", "api_profile_preferences", self.user_token, {"news_email": "si"}).status_code, 400)
        self.assertEqual(self.call("patch", "api_profile_preferences", self.user_token, {"monthly_scope": "x"}).status_code, 400)

    def test_report_scope_ignored_for_member(self):
        """Un miembro no cambia ``report_scope``."""
        r = self.call("patch", "api_profile_preferences", self.user_token, {"report_scope": "competitivos"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("report_scope", r.json()["preferences"])

    def test_email_change(self):
        """Con la contraseña correcta cambia el email y envía confirmación."""
        r = self.call("post", "api_profile_email", self.user_token, {"email": "nuevo@example.com", "current_password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.content)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "nuevo@example.com")
        self.assertFalse(r.json()["email_verified"])
        self.assertTrue(mail.outbox)

    def test_email_change_wrong_password(self):
        """Contraseña errónea: 400 con ``fields``."""
        r = self.call("post", "api_profile_email", self.user_token, {"email": "nuevo@example.com", "current_password": "mal"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("current_password", r.json()["fields"])

    def test_email_change_without_password_account(self):
        """Cuenta sin contraseña: 409 ``no_password``."""
        self.user.set_unusable_password()
        self.user.save()
        r = self.call("post", "api_profile_email", self.user_token, {"email": "n@example.com", "current_password": "x"})
        self.assertEqual(r.status_code, 409)

    def test_password_change_keeps_current_token_and_revokes_others(self):
        """Cambiar la contraseña deja este dispositivo y revoca los demás."""
        _, other = issue_token(self.user, "iPad")
        r = self.call("post", "api_profile_password", self.user_token, {"current_password": PASSWORD, "new_password": "Otra-Clave-456!"})
        self.assertEqual(r.status_code, 200, r.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Otra-Clave-456!"))
        self.assertEqual(self.call("get", "api_profile", self.user_token).status_code, 200)
        self.assertEqual(self.call("get", "api_profile", other).status_code, 401)

    def test_password_change_wrong_current(self):
        """Actual incorrecta: 403."""
        r = self.call("post", "api_profile_password", self.user_token, {"current_password": "mal", "new_password": "Otra-Clave-456!"})
        self.assertEqual(r.status_code, 403)

    def test_password_change_weak(self):
        """Nueva demasiado débil: 400 ``weak_password``."""
        r = self.call("post", "api_profile_password", self.user_token, {"current_password": PASSWORD, "new_password": "123"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"] if "code" in r.json() else "weak_password", "weak_password")

    def test_add_password_for_google_account(self):
        """Sin contraseña previa basta la nueva."""
        self.user.set_unusable_password()
        self.user.save()
        r = self.call("post", "api_profile_password", self.user_token, {"new_password": "Otra-Clave-456!"})
        self.assertEqual(r.status_code, 200, r.content)

    def test_revoke_others(self):
        """Cierra los demás dispositivos y cuenta cuántos."""
        issue_token(self.user, "iPad")
        r = self.call("post", "api_profile_revoke_others", self.user_token)
        self.assertEqual(r.json()["closed"], 1)
        self.assertEqual(DeviceToken.objects.active().filter(user=self.user).count(), 1)

    def test_transfer_captaincy(self):
        """El capitán traspasa y queda como miembro."""
        r = self.call("post", "api_transfer_captaincy", self.captain_token, {"member": self.member.pk}, args=[str(self.club.public_id)])
        self.assertEqual(r.status_code, 200, r.content)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_admin)
        self.assertEqual(Membership.objects.get(user=self.captain, club=self.club).role, Membership.MEMBER)

    def test_transfer_requires_captain(self):
        """Un miembro no puede traspasar: 404."""
        r = self.call("post", "api_transfer_captaincy", self.user_token, {"member": self.member.pk}, args=[str(self.club.public_id)])
        self.assertEqual(r.status_code, 404)

    def test_transfer_invalid_member(self):
        """Miembro inexistente: 409; tipo erróneo: 400."""
        args = [str(self.club.public_id)]
        self.assertEqual(self.call("post", "api_transfer_captaincy", self.captain_token, {"member": 99999}, args=args).status_code, 409)
        self.assertEqual(self.call("post", "api_transfer_captaincy", self.captain_token, {"member": "x"}, args=args).status_code, 400)


class OwnPlayerApiTests(ProfileApiTests):
    """``PATCH /teams/<id>/me/player``: editar la propia ficha."""

    def patch_player(self, token, data, club=None):
        """PATCH de la ficha propia del equipo indicado."""
        return self.call("patch", "api_own_player", token, data, args=[str(club or self.club.public_id)])

    def test_edit_position_and_hand(self):
        """Cambia posición y mano; lo que no se envía se conserva."""
        r = self.patch_player(self.user_token, {"position": "Revés"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["player"]["position"], "Revés")
        r = self.patch_player(self.user_token, {"hand": "Zurdo"})
        self.assertEqual(r.json()["player"]["position"], "Revés")
        self.assertEqual(r.json()["player"]["hand"], "Zurdo")

    def test_invalid_position(self):
        """Posición desconocida: 400 con el campo."""
        r = self.patch_player(self.user_token, {"position": "Portero"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("position", r.json()["fields"])

    def test_invalid_photo(self):
        """Foto que no es base64: 400 en ``photo``."""
        r = self.patch_player(self.user_token, {"photo": "###"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("photo", r.json()["fields"])

    def test_no_linked_player(self):
        """Sin ficha enlazada en ese equipo: 404."""
        other = User.objects.create_user("otro", "otro@example.com", PASSWORD)
        Membership.objects.create(user=other, club=self.club, role=Membership.MEMBER)
        _, token = issue_token(other, "iPhone")
        self.assertEqual(self.patch_player(token, {"position": "Revés"}).status_code, 404)

    def test_remove_photo(self):
        """``remove_photo`` quita la foto."""
        player = Player.objects.get(user=self.user)
        player.photo = "x.jpg"
        player.save()
        r = self.patch_player(self.user_token, {"remove_photo": True})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["player"]["photo"])


class ExportApiTests(ProfileApiTests):
    """``GET /api/v1/me/export``: los datos personales de la cuenta, sin secretos ni datos ajenos."""

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_profile_export")).status_code, 401)

    def test_exports_own_data_only(self):
        """Cuenta, equipos y ficha propios; nada del capitán ni secretos."""
        response = self.call("get", "api_profile_export", self.user_token)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["account"]["username"], "jug")
        self.assertEqual(data["account"]["email"], "jug@example.com")
        self.assertEqual(data["memberships"], [{"club": "Club Norte", "role": "member"}])
        self.assertEqual([s["name"] for s in data["player_sheets"]], ["Luis"])
        self.assertEqual(len(data["app_devices"]), 1)
        text = response.content.decode()
        self.assertNotIn("capi@example.com", text)
        self.assertNotIn("password", text.replace("has_password", ""))
        self.assertNotIn("token", text)

    @override_settings(RATE_LIMITS_ENABLED=True)
    def test_rate_limited(self):
        """A la sexta petición en una hora: 429."""
        for _ in range(5):
            self.assertEqual(self.call("get", "api_profile_export", self.user_token).status_code, 200)
        self.assertEqual(self.call("get", "api_profile_export", self.user_token).status_code, 429)
