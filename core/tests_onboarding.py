"""Tests del registro: foco del formulario, primeros pasos, un solo club por cuenta y enlaces compartidos."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Club, Invitation, Membership
from core.services import create_club
from match.models import Match
from players.models import Player
from team.models import Team

User = get_user_model()

CLUB = {"name": "Club Nuevo", "location": "Sevilla", "gender": "M", "country": "ES", "division": "500"}
SIGNUP = {
    "username": "nuevo", "email": "nuevo@example.com",
    "password1": "Clave-Segura-123", "password2": "Clave-Segura-123",
}


class RegisterFormFocusTests(TestCase):
    def test_register_page_does_not_jump_to_username(self):
        response = self.client.get(reverse("register_club"))
        self.assertNotContains(response, "autofocus")


class OnboardingTests(TestCase):
    def register(self):
        self.client.post(reverse("register_club"), {**CLUB, **SIGNUP})
        return Club.objects.get(name="Club Nuevo")

    def test_new_club_sees_the_four_steps(self):
        self.register()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Primeros pasos")
        for url in (reverse("create_team"), reverse("club_members") + "#invitaciones",
                    reverse("create_player"), reverse("create_match")):
            self.assertContains(response, f'href="{url}"')

    def test_steps_are_ticked_with_club_data(self):
        club = self.register()
        Team.objects.create(club=club, name="Rival", in_group=True)
        Player.objects.create(club=club, name="Eva", last_name="Sanz")
        steps = {s["key"]: s["done"] for s in self.client.get(reverse("home")).context["onboarding"]}
        self.assertEqual(steps, {"team": True, "invite": False, "player": True, "match": False})

    def test_hidden_when_all_steps_are_done(self):
        club = self.register()
        rival = Team.objects.create(club=club, name="Rival", in_group=True)
        Player.objects.create(club=club, name="Eva", last_name="Sanz")
        Invitation.objects.create(club=club, reusable=True)
        Match.objects.create(club=club, local=club.own_team, visiting=rival, start_date=datetime.date.today())
        self.assertNotContains(self.client.get(reverse("home")), "Primeros pasos")

    def test_captain_can_dismiss_it(self):
        club = self.register()
        self.client.post(reverse("dismiss_onboarding"))
        club.refresh_from_db()
        self.assertIsNotNone(club.onboarding_dismissed_at)
        self.assertNotContains(self.client.get(reverse("home")), "Primeros pasos")

    def test_members_do_not_see_it(self):
        club = self.register()
        member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=member, club=club, role=Membership.MEMBER)
        self.client.force_login(member)
        self.assertNotContains(self.client.get(reverse("home")), "Primeros pasos")
        self.assertEqual(self.client.post(reverse("dismiss_onboarding")).status_code, 403)


class SingleClubTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capitan", password="pass-12345", email="capitan@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.other_captain = User.objects.create_user("otro", password="pass-12345", email="otro@example.com")
        self.other = create_club("Club B", "Huelva", self.other_captain)

    def test_captain_cannot_register_another_club(self):
        self.client.force_login(self.captain)
        response = self.client.post(reverse("register_club"), CLUB)
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertFalse(Club.objects.filter(name="Club Nuevo").exists())
        self.assertRedirects(self.client.get(reverse("register_club")), reverse("home"), fetch_redirect_response=False)

    def test_member_cannot_register_a_club(self):
        member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)
        self.client.post(reverse("register_club"), CLUB)
        self.assertFalse(Club.objects.filter(name="Club Nuevo").exists())

    def test_menu_has_no_register_option_with_a_club(self):
        self.client.force_login(self.captain)
        self.assertNotContains(self.client.get(reverse("home")), f'href="{reverse("register_club")}"')

    def test_user_without_club_can_register(self):
        user = User.objects.create_user("libre", password="pass-12345", email="libre@example.com")
        self.client.force_login(user)
        self.client.post(reverse("register_club"), CLUB)
        self.assertTrue(Membership.objects.filter(user=user, club__name="Club Nuevo", role=Membership.ADMIN).exists())

    def test_member_of_a_suspended_club_can_register(self):
        self.other.suspended_at = timezone.now()
        self.other.save()
        self.client.force_login(self.other_captain)
        self.client.post(reverse("register_club"), CLUB)
        self.assertTrue(Club.objects.filter(name="Club Nuevo").exists())

    def test_captain_cannot_join_another_club(self):
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain, reusable=True)
        self.client.force_login(self.other_captain)
        response = self.client.get(reverse("invitation", args=[invitation.token]))
        self.assertContains(response, "solo se puede pertenecer a un club")
        self.assertNotContains(response, "Unirme como")
        self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertFalse(Membership.objects.filter(user=self.other_captain, club=self.club).exists())

    def test_user_can_join_after_leaving_their_club(self):
        member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=member, club=self.other, role=Membership.MEMBER)
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain, reusable=True)
        self.client.force_login(member)
        self.client.post(reverse("leave_club"))
        self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertTrue(Membership.objects.filter(user=member, club=self.club).exists())


class SharedLinkTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capitan", password="pass-12345", email="capitan@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.client.force_login(self.captain)

    def test_new_link_invalidates_the_previous_one(self):
        self.client.post(reverse("create_invitation_link"))
        first = Invitation.objects.get()
        self.client.post(reverse("create_invitation_link"))
        first.refresh_from_db()
        self.assertFalse(first.is_valid)
        pending = list(self.club.invitations.pending())
        self.assertEqual(len(pending), 1)
        self.assertNotEqual(pending[0], first)
        response = self.client.get(reverse("invitation", args=[first.token]))
        self.assertEqual(response.status_code, 410)

    def test_new_link_keeps_email_invitations(self):
        email_inv = Invitation.objects.create(club=self.club, created_by=self.captain, email="eva@example.com")
        self.client.post(reverse("create_invitation_link"))
        self.assertTrue(self.club.invitations.pending().filter(pk=email_inv.pk).exists())
        self.assertEqual(self.client.get(reverse("club_members")).content.decode().count("Enlace compartido"), 1)
