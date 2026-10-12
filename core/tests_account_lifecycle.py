"""Tests de la capitanía única, el traspaso de capitanía y la eliminación de la cuenta."""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.models import Membership
from core.services import (CaptaincyError, account_delete_blocker, create_club, delete_account,
                           eligible_successors, transfer_captaincy)
from players.models import Player

User = get_user_model()


class AccountLifecycleTests(TestCase):
    """Club con capitán, un miembro enlazado a un jugador y otro sin enlazar."""

    def setUp(self):
        """Crea el club y los dos miembros."""
        self.captain = User.objects.create_user("capitan", "cap@example.com", "pass-12345")
        self.club = create_club("Club Uno", "Sevilla", self.captain, gender="M")
        self.linked = User.objects.create_user("enlazado", "lin@example.com", "pass-12345")
        self.free = User.objects.create_user("libre", "lib@example.com", "pass-12345")
        self.m_linked = Membership.objects.create(user=self.linked, club=self.club, role=Membership.MEMBER)
        self.m_free = Membership.objects.create(user=self.free, club=self.club, role=Membership.MEMBER)
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Ruiz", user=self.linked)
        self.m_captain = Membership.objects.get(user=self.captain)

    def test_only_one_captain_per_club(self):
        """La base de datos impide un segundo capitán."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.filter(pk=self.m_linked.pk).update(role=Membership.ADMIN)

    def test_successors_are_linked_members(self):
        """Solo los miembros enlazados a un jugador pueden heredar la capitanía."""
        self.assertEqual(list(eligible_successors(self.club)), [self.m_linked])

    def test_transfer_to_unlinked_member_is_refused(self):
        """No se cede la capitanía a quien no está enlazado."""
        with self.assertRaises(CaptaincyError):
            transfer_captaincy(self.club, self.m_captain, self.m_free)

    def test_transfer_swaps_roles(self):
        """El elegido es capitán y el anterior queda como miembro."""
        self.client.force_login(self.captain)
        response = self.client.post(reverse("transfer_captaincy", args=[self.m_linked.public_id]))
        self.assertEqual(response.status_code, 302)
        self.m_captain.refresh_from_db()
        self.m_linked.refresh_from_db()
        self.assertEqual(self.m_linked.role, Membership.ADMIN)
        self.assertEqual(self.m_captain.role, Membership.MEMBER)

    def test_member_cannot_transfer(self):
        """Un miembro corriente no puede traspasar la capitanía."""
        self.client.force_login(self.linked)
        self.client.post(reverse("transfer_captaincy", args=[self.m_linked.public_id]))
        self.m_captain.refresh_from_db()
        self.assertTrue(self.m_captain.is_admin)

    def test_captain_cannot_delete_account(self):
        """Un capitán con más miembros debe ceder antes la capitanía."""
        self.assertIsNotNone(account_delete_blocker(self.captain))
        with self.assertRaises(CaptaincyError):
            delete_account(self.captain)
        self.client.force_login(self.captain)
        self.client.post(reverse("delete_account"), {"confirm": "pass-12345"})
        self.assertTrue(User.objects.filter(pk=self.captain.pk).exists())

    def test_member_deletes_account_keeping_player(self):
        """La ficha del jugador se queda en el club, sin cuenta."""
        self.client.force_login(self.linked)
        response = self.client.post(reverse("delete_account"), {"confirm": "pass-12345"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=self.linked.pk).exists())
        self.player.refresh_from_db()
        self.assertIsNone(self.player.user)

    def test_wrong_password_keeps_account(self):
        """Con contraseña incorrecta no se borra nada."""
        self.client.force_login(self.linked)
        self.client.post(reverse("delete_account"), {"confirm": "mala"})
        self.assertTrue(User.objects.filter(pk=self.linked.pk).exists())

    def test_delete_account_with_player(self):
        """Con la casilla marcada se elimina también la ficha del jugador."""
        self.client.force_login(self.linked)
        self.client.post(reverse("delete_account"), {"confirm": "pass-12345", "delete_player": "on"})
        self.assertFalse(Player.objects.filter(pk=self.player.pk).exists())

    def test_after_transfer_old_captain_can_delete(self):
        """Tras ceder la capitanía, el antiguo capitán ya puede eliminar su cuenta."""
        transfer_captaincy(self.club, self.m_captain, self.m_linked)
        self.assertIsNone(account_delete_blocker(self.captain))
