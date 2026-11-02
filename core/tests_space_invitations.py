"""
Invitaciones por competición (SNP y LAPI): se comportan igual en las dos, no se invita a quien ya
tiene equipo en esa competición y volver a invitar no borra la invitación de una ficha copiada.
"""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from core.models import Invitation, Membership
from core.services import create_club
from players.models import Player

User = get_user_model()
PASSWORD = "pass-12345-x"


class SpaceInvitationTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.clubs = {code: create_club(f"Club {code}", "Sevilla", self.captain, competition=code)
                      for code in ("snp", "lapi")}
        self.client.login(username="capi", password=PASSWORD)

    def invite(self, code, email):
        self.client.post(reverse("club_members") + f"?en={code}")  # abre el equipo de la competición
        session = self.client.session
        session["club_id"] = self.clubs[code].id
        session.save()
        return self.client.post(reverse("create_invitation"), {"email": email})

    def test_invitation_goes_to_the_active_space_in_both_competitions(self):
        for code in ("snp", "lapi"):
            self.invite(code, f"{code}@example.com")
            invitation = Invitation.objects.get(email=f"{code}@example.com")
            self.assertEqual(invitation.club, self.clubs[code])
            self.assertAlmostEqual((invitation.expires_at - invitation.created_at).total_seconds(), 24 * 3600, delta=60)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["lapi@example.com", "snp@example.com"])

    def test_email_with_a_team_in_that_competition_is_rejected(self):
        other = User.objects.create_user("otra", password=PASSWORD, email="otra@example.com")
        create_club("Otro LAPI", "Huelva", other, competition="lapi")
        self.invite("lapi", "OTRA@example.com")
        self.assertFalse(Invitation.objects.filter(email="otra@example.com").exists())
        self.assertEqual(len(mail.outbox), 0)
        # Pero en la SNP sí puede entrar: allí aún no tiene equipo.
        self.invite("snp", "otra@example.com")
        self.assertTrue(Invitation.objects.filter(club=self.clubs["snp"], email="otra@example.com").exists())

    def test_reinviting_keeps_the_copy_invitation_of_a_sheet(self):
        club = self.clubs["lapi"]
        sheet = Player.objects.create(club=club, team=club.own_team, name="Ana", last_name="Ruiz")
        copy = Invitation.objects.create(club=club, email="ana@example.com", created_by=self.captain, player=sheet)
        self.invite("lapi", "ana@example.com")
        self.assertTrue(Invitation.objects.filter(pk=copy.pk).exists())
        self.assertEqual(Invitation.objects.filter(club=club, email="ana@example.com").count(), 2)

    def test_reinviting_replaces_the_previous_email_invitation(self):
        self.invite("snp", "nuevo@example.com")
        first = Invitation.objects.get(email="nuevo@example.com")
        self.invite("snp", "nuevo@example.com")
        invitation = Invitation.objects.get(email="nuevo@example.com")
        self.assertNotEqual(first.pk, invitation.pk)

    def test_accepting_requires_a_free_space_in_that_competition(self):
        other = User.objects.create_user("otra", password=PASSWORD, email="otra@example.com")
        create_club("Otro LAPI", "Huelva", other, competition="lapi")
        invitation = Invitation.objects.create(club=self.clubs["lapi"], created_by=self.captain, email="otra@example.com")
        self.client.logout()
        self.client.login(username="otra", password=PASSWORD)
        self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertFalse(Membership.objects.filter(user=other, club=self.clubs["lapi"]).exists())
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_at)
        # La misma cuenta sí puede unirse al equipo SNP de otro capitán.
        snp_invitation = Invitation.objects.create(club=self.clubs["snp"], created_by=self.captain)
        self.client.post(reverse("invitation", args=[snp_invitation.token]))
        self.assertTrue(Membership.objects.filter(user=other, club=self.clubs["snp"], role=Membership.MEMBER).exists())
