"""Tests del equipo en la API: miembros, roles, invitaciones, abandonar y textos legales."""
import datetime

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api.tokens import issue_token
from core.models import Invitation, Membership
from core.services import create_club
from players.models import Player

User = get_user_model()
PASSWORD = "Clave-Segura-123"


class MembersApiTests(TestCase):
    """Capitán, un miembro con ficha enlazada y otro sin ficha."""

    def setUp(self):
        """Crea el club, los miembros y los tokens."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", PASSWORD)
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.user = User.objects.create_user("jug", "jug@example.com", PASSWORD)
        self.member = Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        Player.objects.create(club=self.club, name="Luis", last_name="Gil", user=self.user, in_team=True)
        self.other = User.objects.create_user("otro", "otro@example.com", PASSWORD)
        self.other_member = Membership.objects.create(user=self.other, club=self.club, role=Membership.MEMBER)
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.user_token = issue_token(self.user, "iPhone")
        self.team = str(self.club.public_id)

    def call(self, method, name, token, data=None, args=None):
        """Llama al endpoint ``name`` con el token indicado."""
        return getattr(self.client, method)(reverse(name, args=args or [self.team]), data=data, content_type="application/json",
                                            HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_captain_sees_emails_and_actions(self):
        """El capitán ve emails y qué se puede hacer con cada miembro."""
        data = self.call("get", "api_members", self.captain_token).json()
        self.assertTrue(data["is_captain"])
        by_name = {m["username"]: m for m in data["members"]}
        self.assertEqual(by_name["jug"]["email"], "jug@example.com")
        self.assertTrue(by_name["jug"]["can_transfer"])
        self.assertFalse(by_name["otro"]["can_transfer"])
        self.assertFalse(by_name["capi"]["can_remove"])
        self.assertEqual(data["invitations"], [])

    def test_member_sees_only_names_and_roles(self):
        """Un miembro ve usuarios y roles, sin emails ni invitaciones."""
        data = self.call("get", "api_members", self.user_token).json()
        self.assertFalse(data["is_captain"])
        self.assertNotIn("email", data["members"][0])
        self.assertNotIn("invitations", data)

    def test_foreign_account_is_404(self):
        """Una cuenta ajena al equipo: 404."""
        stranger = User.objects.create_user("x", "x@example.com", PASSWORD)
        _, token = issue_token(stranger, "iPhone")
        self.assertEqual(self.call("get", "api_members", token).status_code, 404)

    def test_make_and_remove_manager(self):
        """El capitán nombra gestor y le quita el rol."""
        args = [self.team, str(self.member.public_id)]
        res = self.call("post", "api_member_manager", self.captain_token, {"enable": True}, args)
        self.assertEqual(res.json()["role"], "manager")
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_manager)
        self.call("post", "api_member_manager", self.captain_token, {"enable": False}, args)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_manager)

    def test_member_cannot_manage_roles(self):
        """Un miembro no puede nombrar gestores: 403."""
        args = [self.team, str(self.other_member.public_id)]
        self.assertEqual(self.call("post", "api_member_manager", self.user_token, {"enable": True}, args).status_code, 403)

    def test_third_manager_is_409(self):
        """Con dos gestores ya nombrados, un tercero da 409."""
        third = User.objects.create_user("tercero", "t@example.com", PASSWORD)
        third_member = Membership.objects.create(user=third, club=self.club, role=Membership.MEMBER)
        for member in (self.member, self.other_member):
            self.call("post", "api_member_manager", self.captain_token, {"enable": True}, [self.team, str(member.public_id)])
        res = self.call("post", "api_member_manager", self.captain_token, {"enable": True}, [self.team, str(third_member.public_id)])
        self.assertEqual(res.status_code, 409)

    def test_transfer_captaincy(self):
        """El traspaso deja al anterior capitán como miembro."""
        res = self.call("post", "api_member_transfer", self.captain_token, args=[self.team, str(self.member.public_id)])
        self.assertTrue(res.json()["transferred"])
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_admin)

    def test_transfer_to_unlinked_member_is_409(self):
        """Quien no tiene ficha enlazada no puede recibir la capitanía."""
        res = self.call("post", "api_member_transfer", self.captain_token, args=[self.team, str(self.other_member.public_id)])
        self.assertEqual(res.status_code, 409)

    def test_remove_member(self):
        """Quitar a un miembro lo saca del equipo."""
        self.call("post", "api_member_remove", self.captain_token, args=[self.team, str(self.other_member.public_id)])
        self.assertFalse(Membership.objects.filter(pk=self.other_member.pk).exists())

    def test_captain_cannot_be_removed(self):
        """El capitán no se puede quitar: 409."""
        captain = Membership.objects.get(user=self.captain, club=self.club)
        res = self.call("post", "api_member_remove", self.captain_token, args=[self.team, str(captain.public_id)])
        self.assertEqual(res.status_code, 409)

    def test_invite_by_email_sends_mail(self):
        """Invitar por email crea la invitación y envía el correo."""
        res = self.call("post", "api_invitations", self.captain_token, {"email": "nuevo@example.com"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        listed = self.call("get", "api_members", self.captain_token).json()
        self.assertEqual(listed["invitations"][0]["email"], "nuevo@example.com")

    def test_invite_existing_member_is_400(self):
        """Invitar a un miembro actual da 400 con el campo email."""
        res = self.call("post", "api_invitations", self.captain_token, {"email": "jug@example.com"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("email", res.json()["fields"])

    def test_link_replaces_previous_one(self):
        """Un enlace nuevo invalida el anterior (pasado el margen contra el doble toque)."""
        first = self.call("post", "api_invitation_link", self.captain_token).json()
        Invitation.objects.update(created_at=timezone.now() - datetime.timedelta(minutes=5))
        second = self.call("post", "api_invitation_link", self.captain_token).json()
        self.assertTrue(second["replaced"])
        self.assertEqual(Invitation.objects.pending().filter(reusable=True).count(), 1)

    def test_revoke_invitation(self):
        """Anular una invitación pendiente la borra."""
        sent = self.call("post", "api_invitations", self.captain_token, {"email": "nuevo@example.com"}).json()
        res = self.call("post", "api_invitation_revoke", self.captain_token, args=[self.team, sent["invitation"]["id"]])
        self.assertTrue(res.json()["revoked"])
        self.assertFalse(Invitation.objects.pending().exists())

    def test_member_leaves(self):
        """Un miembro abandona el equipo."""
        res = self.call("post", "api_leave_team", self.user_token)
        self.assertFalse(res.json()["closed"])
        self.assertFalse(Membership.objects.filter(pk=self.member.pk).exists())

    def test_captain_cannot_leave_with_members(self):
        """El capitán con más miembros no puede irse: 409."""
        self.assertEqual(self.call("post", "api_leave_team", self.captain_token).status_code, 409)

    def test_sole_captain_needs_confirm_name_to_close(self):
        """Quien es el único miembro cierra el equipo escribiendo su nombre."""
        self.member.delete()
        self.other_member.delete()
        self.assertEqual(self.call("post", "api_leave_team", self.captain_token, {"confirm_name": "otro"}).status_code, 409)
        res = self.call("post", "api_leave_team", self.captain_token, {"confirm_name": "Club Norte"})
        self.assertTrue(res.json()["closed"])


class LegalApiTests(TestCase):
    """Textos legales en bloques."""

    def setUp(self):
        """Una cuenta con token."""
        cache.clear()
        caches["ratelimit"].clear()
        user = User.objects.create_user("legal", "legal@example.com", PASSWORD)
        _, self.token = issue_token(user, "iPhone")

    def get(self, name, args=None):
        """GET con el token."""
        return self.client.get(reverse(name, args=args or []), HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_list(self):
        """Hay tres documentos."""
        slugs = [d["slug"] for d in self.get("api_legal").json()["documents"]]
        self.assertEqual(slugs, ["privacy", "terms", "cookies"])

    def test_document_blocks(self):
        """La privacidad trae títulos, párrafos y listas, y la fecha."""
        data = self.get("api_legal_document", ["privacy"]).json()
        types = {b["type"] for b in data["blocks"]}
        self.assertEqual(types, {"heading", "paragraph", "list"})
        self.assertTrue(data["updated"])
        self.assertTrue(any("**" in item for b in data["blocks"] if b["type"] == "list" for item in b["items"]))

    def test_unknown_document_is_404(self):
        """Un documento que no existe: 404."""
        self.assertEqual(self.get("api_legal_document", ["nada"]).status_code, 404)
