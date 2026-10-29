"""
Fase 2 de las competiciones: «Copiar jugadores» entre el equipo SNP y el LAPI de una misma cuenta
(players.copy), la invitación de la ficha copiada, la sincronización de nombre y foto entre fichas
de la misma cuenta, el aviso de plantilla LAPI y «¿Es el mismo jugador?» en Completar equipo.
"""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.middleware import SESSION_KEY
from core.models import Invitation, Membership
from core.services import create_club
from players import copy as player_copy, snp_import
from players.models import Player, SnpTeamImport

User = get_user_model()
PASSWORD = "pass-12345-x"


class CopyPlayersTests(TestCase):
    """Edu es capitán en SNP y en LAPI; Ana tiene cuenta en SNP; Luis no tiene cuenta."""

    def setUp(self):
        self.edu = User.objects.create_user("edu", password=PASSWORD, email="edu@example.com")
        self.snp = create_club("Gladiadores", "Sevilla", self.edu, division="500",
                               player_name="Edu", player_last_name="Bus")
        self.lapi = create_club("Gladiadores LAPI", "Sevilla", self.edu, competition="lapi")
        self.ana_user = User.objects.create_user("ana", password=PASSWORD, email="ana@example.com")
        Membership.objects.create(user=self.ana_user, club=self.snp, role=Membership.MEMBER)
        self.ana = Player.objects.create(club=self.snp, team=self.snp.own_team, name="Ana", last_name="Ruiz",
                                         user=self.ana_user, position="drive", snp_score=120)
        self.luis = Player.objects.create(club=self.snp, team=self.snp.own_team, name="Luis", last_name="Gil")
        self.client.login(username="edu", password=PASSWORD)
        self._activate(self.lapi)

    def _activate(self, club):
        session = self.client.session
        session[SESSION_KEY] = club.id
        session.save()

    def _status(self, player):
        rows = player_copy.candidates(self.snp, self.lapi)
        return next(r["status"] for r in rows if r["player"] == player)

    def test_candidates_status(self):
        edu = Player.objects.get(club=self.snp, user=self.edu)
        self.assertEqual(self._status(self.ana), player_copy.INVITE)
        self.assertEqual(self._status(self.luis), player_copy.COPY)
        # Edu ya es capitán en LAPI sin ficha: la copia se enlaza a su cuenta sin invitación.
        self.assertEqual(self._status(edu), player_copy.MEMBER)
        player_copy.copy_players(self.snp, self.lapi, [edu.pk], self.edu)
        self.assertEqual(Player.objects.get(club=self.lapi, name="Edu").user, self.edu)
        self.assertFalse(Invitation.objects.filter(player__club=self.lapi).exists())
        self.assertEqual(self._status(edu), player_copy.ALREADY)
        Player.objects.filter(club=self.lapi).delete()
        Player.objects.create(club=self.lapi, team=self.lapi.own_team, name="Edu", last_name="Bus", user=self.edu)
        self.assertEqual(self._status(edu), player_copy.ALREADY)
        # Ana ya juega en otro equipo LAPI.
        other = create_club("Otro LAPI", "Cádiz", User.objects.create_user("x", password=PASSWORD), competition="lapi")
        Membership.objects.create(user=self.ana_user, club=other, role=Membership.MEMBER)
        self.assertEqual(self._status(self.ana), player_copy.OTHER_TEAM)

    def test_copy_creates_sheets_and_invites(self):
        page = self.client.get(reverse("copy_players"))
        self.assertContains(page, "ANA RUIZ")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("copy_players"), {"players": [self.ana.pk, self.luis.pk]}, follow=True)
        self.assertContains(response, "2 jugadores copiados.")
        ana_copy = Player.objects.get(club=self.lapi, name="Ana")
        self.assertEqual((ana_copy.copied_from, ana_copy.user, ana_copy.position, ana_copy.snp_score),
                         (self.ana, None, "drive", None))
        self.assertTrue(Player.objects.filter(club=self.lapi, name="Luis", copied_from=self.luis).exists())
        invitation = Invitation.objects.get(player=ana_copy)
        self.assertEqual(invitation.email, "ana@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(invitation.token, mail.outbox[0].body)
        # Copiar otra vez no duplica.
        self.client.post(reverse("copy_players"), {"players": [self.ana.pk]})
        self.assertEqual(Player.objects.filter(club=self.lapi, name="Ana").count(), 1)

    def test_lapi_roster_hides_snp_points(self):
        page = self.client.get(reverse("list_players"))
        self.assertNotContains(page, "order_by=-snp_score")
        self._activate(self.snp)
        self.assertContains(self.client.get(reverse("list_players")), "order_by=-snp_score")

    def test_must_manage_both_teams(self):
        Membership.objects.filter(user=self.edu, club=self.snp).update(role=Membership.MEMBER)
        response = self.client.post(reverse("copy_players"), {"players": [self.luis.pk]})
        self.assertRedirects(response, reverse("list_players"), fetch_redirect_response=False)
        self.assertFalse(Player.objects.filter(club=self.lapi, name="Luis").exists())

    def test_roster_over_limit_warns_but_copies(self):
        for n in range(15):
            Player.objects.create(club=self.lapi, team=self.lapi.own_team, name=f"Jugador{n}", last_name="X")
        response = self.client.post(reverse("copy_players"), {"players": [self.luis.pk]}, follow=True)
        self.assertContains(response, "el máximo es 15")
        self.assertTrue(Player.objects.filter(club=self.lapi, name="Luis").exists())

    def _copy_ana(self):
        player_copy.copy_players(self.snp, self.lapi, [self.ana.pk], self.edu)
        return Player.objects.get(club=self.lapi, name="Ana")

    def test_accept_from_home_links_sheet(self):
        ana_copy = self._copy_ana()
        invitation = Invitation.objects.get(player=ana_copy)
        self.client.login(username="ana", password=PASSWORD)
        self._activate(self.snp)
        self.assertContains(self.client.get(reverse("home")), "Tienes una invitación")
        self.client.post(reverse("respond_copy_invitation", args=[invitation.token]), {"action": "accept"})
        ana_copy.refresh_from_db()
        self.assertEqual(ana_copy.user, self.ana_user)
        self.assertTrue(Membership.objects.filter(user=self.ana_user, club=self.lapi, role=Membership.MEMBER).exists())

    def test_decline_keeps_sheet_unlinked(self):
        ana_copy = self._copy_ana()
        invitation = Invitation.objects.get(player=ana_copy)
        self.client.login(username="ana", password=PASSWORD)
        self.client.post(reverse("respond_copy_invitation", args=[invitation.token]), {"action": "decline"})
        ana_copy.refresh_from_db()
        self.assertIsNone(ana_copy.user)
        self.assertFalse(Membership.objects.filter(user=self.ana_user, club=self.lapi).exists())
        self.assertEqual(player_copy.pending_for(self.ana_user), [])

    def test_linked_sheets_share_name_and_photo_not_position(self):
        ana_copy = self._copy_ana()
        player_copy.link_player(Invitation.objects.get(player=ana_copy), self.ana_user)
        ana_copy.refresh_from_db()
        ana_copy.position = "reves"
        ana_copy.save()
        self.ana.refresh_from_db()
        self.ana.name, self.ana.photo = "Anabel", "players/ana.jpg"
        self.ana.save()
        ana_copy.refresh_from_db()
        self.assertEqual((ana_copy.name, ana_copy.photo.name, ana_copy.position), ("Anabel", "players/ana.jpg", "reves"))
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.position, "drive")

    def test_profile_offers_sheets_copied_before_account(self):
        luis_copy = player_copy.copy_players(self.snp, self.lapi, [self.luis.pk], self.edu)["copied"][0]
        luis_user = User.objects.create_user("luis", password=PASSWORD, email="luis@example.com")
        Membership.objects.create(user=luis_user, club=self.snp, role=Membership.MEMBER)
        self.luis.user = luis_user
        self.luis.save()
        self.client.login(username="luis", password=PASSWORD)
        self._activate(self.snp)
        self.assertContains(self.client.get(reverse("my_profile")), "Tu ficha también está en otro equipo")
        self.client.post(reverse("link_related_sheet", args=[luis_copy.pk]))
        luis_copy.refresh_from_db()
        self.assertEqual(luis_copy.user, luis_user)
        self.assertEqual(self.client.session[SESSION_KEY], self.lapi.id)
        self.assertNotContains(self.client.get(reverse("my_profile")), "Tu ficha también está en otro equipo")

    def test_profile_not_mine_stops_offering(self):
        luis_copy = player_copy.copy_players(self.snp, self.lapi, [self.luis.pk], self.edu)["copied"][0]
        luis_user = User.objects.create_user("luis", password=PASSWORD, email="luis@example.com")
        Membership.objects.create(user=luis_user, club=self.snp, role=Membership.MEMBER)
        self.luis.user = luis_user
        self.luis.save()
        self.client.login(username="luis", password=PASSWORD)
        self.client.post(reverse("reject_related_sheet", args=[luis_copy.pk]))
        luis_copy.refresh_from_db()
        self.assertIsNone(luis_copy.copied_from)
        self.assertEqual(player_copy.related_unlinked(luis_user), [])
        self.assertEqual(self.client.post(reverse("link_related_sheet", args=[luis_copy.pk])).status_code, 404)

    def test_complete_team_same_player_gets_score(self):
        luis_lapi = Player.objects.create(club=self.lapi, team=self.lapi.own_team, name="Luis", last_name="Gil")
        self.lapi.competition = "snp"  # Completar equipo es de SNP: aquí el equipo copiado hace de SNP
        self.lapi.save()
        team_import = SnpTeamImport.objects.create(
            club=self.lapi, status=SnpTeamImport.READY, started_at=timezone.now(),
            to_add=[{"snp_name": "GIL PEREZ, LUIS", "name": "Luis", "last_name": "Gil Pérez", "score": 80}])
        self.assertIn(luis_lapi, snp_import.same_player_options(self.lapi))
        snp_import.confirm(team_import, same={"GIL PEREZ, LUIS": luis_lapi.pk})
        luis_lapi.refresh_from_db()
        self.assertEqual(luis_lapi.snp_score, 80)
        self.assertEqual(Player.objects.filter(club=self.lapi).count(), 1)
