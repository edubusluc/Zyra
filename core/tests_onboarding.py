"""Tests del registro: foco del formulario, primeros pasos, un solo club por cuenta y enlaces compartidos."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Club, Invitation, Membership
from core.services import create_club
from match.models import Match
from players.models import Player, SnpAccount
from team.models import Team

User = get_user_model()

CLUB = {"name": "Club Nuevo", "location": "Sevilla", "gender": "M", "country": "ES", "division": "500",
        "player-name": "Ana", "player-last_name": "Ruiz"}
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

    def test_new_club_sees_the_steps(self):
        self.register()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Primeros pasos")
        for url in (reverse("create_team"), reverse("club_members") + "#invitaciones",
                    reverse("create_player"), reverse("create_match"), reverse("snp_account")):
            self.assertContains(response, f'href="{url}"')

    def test_steps_are_ticked_with_club_data(self):
        club = self.register()
        Team.objects.create(club=club, name="Rival", in_group=True)
        Player.objects.create(club=club, name="Eva", last_name="Sanz")
        steps = {s["key"]: s["done"] for s in self.client.get(reverse("home")).context["onboarding"]}
        self.assertEqual(steps, {"team": True, "invite": False, "player": True, "match": False, "snp": False})

    def test_hidden_when_all_steps_are_done(self):
        club = self.register()
        rival = Team.objects.create(club=club, name="Rival", in_group=True)
        Player.objects.create(club=club, name="Eva", last_name="Sanz")
        Invitation.objects.create(club=club, reusable=True)
        Match.objects.create(club=club, local=club.own_team, visiting=rival, start_date=datetime.date.today())
        account = SnpAccount(club=club)
        account.username, account.password = "cap", "secreto"
        account.save()
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


class CaptainPlayerTests(TestCase):
    """Al registrar el club se crea el jugador del capitán, enlazado a su cuenta."""

    def test_register_creates_captain_player_linked_to_account(self):
        self.client.post(reverse("register_club"), {**CLUB, **SIGNUP})
        club = Club.objects.get(name="Club Nuevo")
        user = User.objects.get(username="nuevo")
        player = Player.objects.get(club=club)
        self.assertEqual((player.name, player.last_name, player.user), ("Ana", "Ruiz", user))
        self.assertEqual(player.team, club.own_team)
        self.assertEqual((user.first_name, user.last_name), ("Ana", "Ruiz"))

    def test_name_and_last_name_are_required(self):
        data = {**CLUB, **SIGNUP, "player-name": "", "player-last_name": ""}
        response = self.client.post(reverse("register_club"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Club.objects.exists())
        self.assertFalse(User.objects.filter(username="nuevo").exists())

    def test_form_warns_that_names_must_match_snp(self):
        response = self.client.get(reverse("register_club"))
        self.assertContains(response, "Tu jugador")
        self.assertContains(response, "deben coincidir exactamente con los que tienes registrados en SNP")
        self.assertContains(response, 'name="player-last_name"')

    def test_captain_player_does_not_tick_create_player_step(self):
        self.client.post(reverse("register_club"), {**CLUB, **SIGNUP})
        steps = {s["key"]: s["done"] for s in self.client.get(reverse("home")).context["onboarding"]}
        self.assertFalse(steps["player"])

    def google_user(self, first_name="", last_name=""):
        from allauth.socialaccount.models import SocialAccount

        user = User.objects.create_user("g", email="g@example.com", first_name=first_name, last_name=last_name)
        SocialAccount.objects.create(user=user, provider="google", uid="123")
        self.client.force_login(user)
        return user

    def test_google_name_is_prefilled(self):
        self.google_user("Lucía", "Martín")
        response = self.client.get(reverse("register_club"))
        self.assertContains(response, 'value="Lucía"')
        self.assertContains(response, 'value="Martín"')
        self.assertNotContains(response, "No ha sido posible obtener tu nombre y apellidos")

    def test_google_without_name_asks_for_it(self):
        self.google_user("Lucía", "")
        response = self.client.get(reverse("register_club"))
        self.assertContains(response, "No ha sido posible obtener tu nombre y apellidos de tu cuenta de Google")

    def test_google_user_registers_club_with_player(self):
        user = self.google_user()
        self.client.post(reverse("register_club"), CLUB)
        player = Player.objects.get(user=user)
        self.assertEqual((player.name, player.last_name), ("Ana", "Ruiz"))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Ana")


class CaptaincyTransferSnpTests(TestCase):
    """Al traspasar la capitanía se borran las credenciales SNP y el nuevo capitán las vuelve a pedir."""

    def setUp(self):
        self.old = User.objects.create_user("viejo", "viejo@example.com", "pass-12345")
        self.club = create_club("Club Dos", "Sevilla", self.old, gender="M")
        self.new = User.objects.create_user("nuevo2", "nuevo2@example.com", "pass-12345")
        self.target = Membership.objects.create(user=self.new, club=self.club, role=Membership.MEMBER)
        Player.objects.create(club=self.club, name="Eva", last_name="Sanz", user=self.new)
        account = SnpAccount(club=self.club)
        account.username, account.password = "cap", "secreto"
        account.save()
        self.club.onboarding_dismissed_at = timezone.now()
        self.club.save()

    def test_transfer_deletes_snp_account_and_reopens_first_steps(self):
        from core.services import transfer_captaincy
        transfer_captaincy(self.club, Membership.objects.get(user=self.old), self.target)
        self.assertFalse(SnpAccount.objects.filter(club=self.club).exists())
        self.client.force_login(self.new)
        response = self.client.get(reverse("home"))
        steps = {s["key"]: s["done"] for s in response.context["onboarding"]}
        self.assertFalse(steps["snp"])
        self.assertContains(response, "Primeros pasos")


class ConfirmModalTests(TestCase):
    """Las confirmaciones usan el popup de Zyra, no ``confirm()`` del navegador."""

    def test_transfer_form_uses_custom_confirm(self):
        old = User.objects.create_user("cap3", "cap3@example.com", "pass-12345")
        club = create_club("Club Tres", "Sevilla", old, gender="M")
        member = User.objects.create_user("miembro3", "m3@example.com", "pass-12345")
        Membership.objects.create(user=member, club=club, role=Membership.MEMBER)
        Player.objects.create(club=club, name="Eva", last_name="Sanz", user=member)
        self.client.force_login(old)
        response = self.client.get(reverse("club_members"))
        self.assertContains(response, "data-confirm=")
        self.assertContains(response, "confirm-modal.js")
        self.assertNotContains(response, "return confirm(")


class NoNativeDialogsTests(TestCase):
    """Ninguna plantilla ni JS propio usa los diálogos del navegador (confirm, alert, prompt)."""

    def test_no_native_dialogs(self):
        import pathlib, re
        root = pathlib.Path(__file__).resolve().parent.parent
        pattern = re.compile(r"(?<![\w.])(confirm|alert|prompt)\s*\(")
        found = [str(p.relative_to(root)) for p in list(root.glob("**/templates/**/*.html")) + list(root.glob("static/js/*.js"))
                 if pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(found, [])
