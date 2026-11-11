"""
Baja de plantilla = salir del equipo: dar de baja a un jugador con cuenta le quita la membresía y lo saca de las
convocatorias y alineaciones por jugar; salir del club también lo da de baja de la plantilla; el capitán no puede
darse de baja; las estadísticas y la otra competición se conservan.
"""
import datetime

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from call.models import Call
from core.models import Invitation, Membership
from core.services import AltaError, RemovalError, alta_blocker, dar_de_alta, create_club, dar_de_baja, leave_open_matches
from match.models import Game, Match, Result
from players.models import Player
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"


class BajaFixture(TestCase):
    """Un capitán, un jugador con cuenta y otro sin cuenta en el mismo club SNP, con un enfrentamiento abierto y uno cerrado."""

    def setUp(self):
        self.captain = User.objects.create_user("cap", password=PASSWORD, email="cap@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain, division="500",
                                player_name="Cap", player_last_name="Tain")
        self.captain_sheet = Player.objects.get(club=self.club, user=self.captain)
        self.user = User.objects.create_user("edu", password=PASSWORD, email="edu@example.com")
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.sheet = Player.objects.create(club=self.club, user=self.user, name="Edu", last_name="B")
        self.free = Player.objects.create(club=self.club, name="Sin", last_name="Cuenta")
        self.open_match, self.open_call = self._match(draft_mode=True, days=7)
        self.closed_match, self.closed_call = self._match(draft_mode=False, days=-7)

    def _match(self, draft_mode, days):
        """Enfrentamiento con convocatoria que incluye a las tres fichas de prueba."""
        rival = Team.objects.create(club=self.club, name=f"Rival {days}", location="X", in_group=True)
        match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival, draft_mode=draft_mode,
                                     start_date=timezone.localdate() + datetime.timedelta(days=days))
        call = Call.objects.create(match=match, draft_mode=draft_mode)
        call.players.add(self.sheet, self.free, self.captain_sheet)
        return match, call


class BajaTests(BajaFixture):
    """Efectos de la baja de plantilla."""

    def test_baja_with_account_removes_membership_and_keeps_history(self):
        dar_de_baja(self.sheet)
        self.sheet.refresh_from_db()
        self.assertFalse(Membership.objects.filter(user=self.user, club=self.club).exists())
        self.assertIsNone(self.sheet.user)
        self.assertEqual(self.sheet.past_user, self.user)
        self.assertFalse(self.sheet.in_team)
        self.assertEqual(self.sheet.left_on, timezone.localdate())

    def test_baja_removes_from_open_call_but_not_from_closed_one(self):
        dar_de_baja(self.sheet)
        self.assertNotIn(self.sheet, self.open_call.players.all())
        self.assertIn(self.sheet, self.closed_call.players.all())
        self.assertIn(self.captain_sheet, self.open_call.players.all())

    def test_baja_without_account_only_leaves_the_squad_and_open_call(self):
        self.assertIsNone(dar_de_baja(self.free))
        self.free.refresh_from_db()
        self.assertFalse(self.free.in_team)
        self.assertEqual(self.free.left_on, timezone.localdate())
        self.assertNotIn(self.free, self.open_call.players.all())
        self.assertIn(self.free, self.closed_call.players.all())

    def test_captain_cannot_be_dado_de_baja(self):
        with self.assertRaises(RemovalError):
            dar_de_baja(self.captain_sheet)
        self.captain_sheet.refresh_from_db()
        self.assertTrue(self.captain_sheet.in_team)
        self.assertTrue(Membership.objects.filter(user=self.captain, club=self.club).exists())

    def test_manager_loses_the_role_with_the_membership(self):
        Membership.objects.filter(user=self.user, club=self.club).update(role=Membership.MANAGER)
        dar_de_baja(self.sheet)
        self.assertFalse(Membership.objects.filter(user=self.user, club=self.club).exists())

    def test_lineup_slot_cleared_only_in_open_match_without_result(self):
        open_game = Game.objects.create(match=self.open_match, n_game=1, draft_mode=True,
                                        player_1_local=self.sheet, player_2_local=self.free)
        played = Game.objects.create(match=self.open_match, n_game=2, score=1, winner="Local", draft_mode=False,
                                     player_1_local=self.sheet, player_2_local=self.free)
        Result.objects.create(game=played, result="6-0 6-0", set1_local=6, set1_visiting=0, set2_local=6, set2_visiting=0)
        closed_game = Game.objects.create(match=self.closed_match, n_game=1, score=1, winner="Local", draft_mode=False,
                                          player_1_local=self.sheet, player_2_local=self.free)
        dar_de_baja(self.sheet)
        open_game.refresh_from_db(), played.refresh_from_db(), closed_game.refresh_from_db()
        self.assertIsNone(open_game.player_1_local)
        self.assertEqual(open_game.player_2_local, self.free)
        self.assertEqual(played.player_1_local, self.sheet)
        self.assertEqual(closed_game.player_1_local, self.sheet)

    def test_leave_open_matches_without_players_does_nothing(self):
        self.assertEqual(leave_open_matches([]), 0)

    def test_leaving_the_club_is_a_baja_from_the_squad(self):
        self.client.login(username="edu", password=PASSWORD)
        self.client.post(reverse("leave_club"))
        self.sheet.refresh_from_db()
        self.assertFalse(self.sheet.in_team)
        self.assertEqual(self.sheet.past_user, self.user)
        self.assertNotIn(self.sheet, self.open_call.players.all())

    def test_captain_removing_a_member_is_a_baja_from_the_squad(self):
        self.client.login(username="cap", password=PASSWORD)
        membership = Membership.objects.get(user=self.user, club=self.club)
        self.client.post(reverse("remove_member", args=[membership.public_id]))
        self.sheet.refresh_from_db()
        self.assertFalse(self.sheet.in_team)
        self.assertNotIn(self.sheet, self.open_call.players.all())

    def test_other_competition_is_untouched(self):
        lapi_captain = User.objects.create_user("lcap", password=PASSWORD, email="lcap@example.com")
        lapi = create_club("Club LAPI", "Sevilla", lapi_captain, competition="lapi")
        Membership.objects.create(user=self.user, club=lapi, role=Membership.MEMBER)
        lapi_sheet = Player.objects.create(club=lapi, user=self.user, name="Edu", last_name="B")
        dar_de_baja(self.sheet)
        lapi_sheet.refresh_from_db()
        self.assertEqual(lapi_sheet.user, self.user)
        self.assertTrue(lapi_sheet.in_team)
        self.assertTrue(Membership.objects.filter(user=self.user, club=lapi).exists())

    def test_edit_player_unticking_en_el_equipo_is_a_baja(self):
        self.client.login(username="cap", password=PASSWORD)
        data = {"name": "Edu", "last_name": "B", "position": "NONE", "skillfull_hand": "NONE",
                "joined_season": self.sheet.joined_season or ""}
        self.client.post(reverse("edit_player", args=[self.sheet.public_id]), data)
        self.assertFalse(Membership.objects.filter(user=self.user, club=self.club).exists())
        self.assertNotIn(self.sheet, self.open_call.players.all())

    def test_edit_player_cannot_untick_the_captain(self):
        self.client.login(username="cap", password=PASSWORD)
        data = {"name": "Cap", "last_name": "Tain", "position": "NONE", "skillfull_hand": "NONE",
                "joined_season": self.captain_sheet.joined_season or ""}
        self.client.post(reverse("edit_player", args=[self.captain_sheet.public_id]), data)
        self.captain_sheet.refresh_from_db()
        self.assertTrue(self.captain_sheet.in_team)

    def test_manage_roster_bulk_baja_skips_the_captain(self):
        self.client.login(username="cap", password=PASSWORD)
        self.client.post(reverse("manage_roster"), {
            "team": self.club.public_id, "leave": [self.sheet.pk, self.captain_sheet.pk]})
        self.sheet.refresh_from_db(), self.captain_sheet.refresh_from_db()
        self.assertFalse(self.sheet.in_team)
        self.assertFalse(Membership.objects.filter(user=self.user, club=self.club).exists())
        self.assertTrue(self.captain_sheet.in_team)

    def test_returning_to_the_previous_sheet_is_an_alta(self):
        dar_de_baja(self.sheet)
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.client.login(username="edu", password=PASSWORD)
        self.client.post(reverse("link_player", args=[self.sheet.public_id]))
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.user, self.user)
        self.assertTrue(self.sheet.in_team)
        self.assertIsNone(self.sheet.left_on)


class BajaEmailAndPopupTests(BajaFixture):
    """Correo al jugador dado de baja y datos del popup de confirmación."""

    def _baja(self, player, by=None):
        """Da de baja ``player`` ejecutando los correos que quedan para después de confirmar la transacción."""
        with self.captureOnCommitCallbacks(execute=True):
            dar_de_baja(player, by or self.captain)

    def test_baja_with_account_emails_the_player(self):
        self._baja(self.sheet)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["edu@example.com"])
        self.assertIn("Club A", message.subject)
        self.assertIn("Mis estadísticas", message.body)

    def test_baja_without_account_sends_nothing(self):
        self._baja(self.free)
        self.assertEqual(mail.outbox, [])

    def test_baja_without_email_or_with_muted_club_emails_sends_nothing(self):
        User.objects.filter(pk=self.user.pk).update(email="")
        self.sheet.refresh_from_db()
        self.sheet.user.refresh_from_db()
        self._baja(self.sheet)
        self.assertEqual(mail.outbox, [])
        other = User.objects.create_user("ana", password=PASSWORD, email="ana@example.com")
        Membership.objects.create(user=other, club=self.club, role=Membership.MEMBER)
        muted = Player.objects.create(club=self.club, user=other, name="Ana", last_name="C", emails_muted=True)
        self._baja(muted)
        self.assertEqual(mail.outbox, [])

    def test_leaving_the_club_yourself_sends_nothing(self):
        self.client.login(username="edu", password=PASSWORD)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("leave_club"))
        self.assertEqual(mail.outbox, [])

    def test_captain_removing_a_member_emails_them(self):
        self.client.login(username="cap", password=PASSWORD)
        membership = Membership.objects.get(user=self.user, club=self.club)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("remove_member", args=[membership.public_id]))
        self.assertEqual([m.to for m in mail.outbox], [["edu@example.com"]])

    def test_edit_player_baja_via_the_form_emails_the_player(self):
        self.client.login(username="cap", password=PASSWORD)
        data = {"name": "Edu", "last_name": "B", "position": "NONE", "skillfull_hand": "NONE",
                "joined_season": self.sheet.joined_season or ""}
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("edit_player", args=[self.sheet.public_id]), data)
        self.assertEqual(len(mail.outbox), 1)

    def test_pages_carry_the_confirmation_data(self):
        self.client.login(username="cap", password=PASSWORD)
        page = self.client.get(reverse("edit_player", args=[self.sheet.public_id]))
        self.assertContains(page, "data-baja-confirm")
        self.assertContains(page, 'data-linked="1"')
        self.assertContains(page, "baja-confirm.js")
        roster = self.client.get(reverse("manage_roster"))
        self.assertContains(roster, "data-baja-confirm")
        self.assertContains(roster, 'data-linked="0"')


class AltaTests(BajaFixture):
    """Alta de una ficha que dejó una cuenta: invitación por email, comprobada por email y competición."""

    def setUp(self):
        super().setUp()
        dar_de_baja(self.sheet, self.captain)
        self.sheet.refresh_from_db()
        mail.outbox.clear()

    def _alta(self, player=None):
        """Da de alta ejecutando los correos que quedan para después de confirmar la transacción."""
        with self.captureOnCommitCallbacks(execute=True):
            return dar_de_alta(player or self.sheet, self.captain, "https://zyra.test/")

    def test_alta_invites_the_former_account_to_return(self):
        invitation = self._alta()
        self.assertEqual((invitation.email, invitation.player, invitation.club), ("edu@example.com", self.sheet, self.club))
        self.assertEqual([m.to for m in mail.outbox], [["edu@example.com"]])
        self.assertIn(invitation.token, mail.outbox[0].body)
        self.sheet.refresh_from_db()
        self.assertTrue(self.sheet.in_team)
        self.assertFalse(Membership.objects.filter(user=self.user, club=self.club).exists())

    def test_accepting_the_invitation_restores_membership_sheet_and_stats(self):
        invitation = self._alta()
        self.client.login(username="edu", password=PASSWORD)
        self.client.post(reverse("respond_copy_invitation", args=[invitation.token]), {"action": "accept"})
        self.sheet.refresh_from_db()
        self.assertTrue(Membership.objects.filter(user=self.user, club=self.club).exists())
        self.assertEqual(self.sheet.user, self.user)
        self.assertIsNone(self.sheet.past_user)
        self.assertIsNone(self.sheet.left_on)
        self.assertTrue(self.sheet.in_team)

    def test_declining_keeps_the_sheet_in_the_squad_unlinked(self):
        invitation = self._alta()
        self.client.login(username="edu", password=PASSWORD)
        self.client.post(reverse("respond_copy_invitation", args=[invitation.token]), {"action": "decline"})
        self.sheet.refresh_from_db()
        self.assertTrue(self.sheet.in_team)
        self.assertIsNone(self.sheet.user)
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())

    def test_alta_is_refused_if_the_email_already_has_a_team_in_the_competition(self):
        other_captain = User.objects.create_user("otro", password=PASSWORD, email="otro@example.com")
        other = create_club("Club B", "Sevilla", other_captain, division="500")
        Membership.objects.create(user=self.user, club=other, role=Membership.MEMBER)
        self.assertIn("ya tiene un equipo", alta_blocker(self.sheet))
        with self.assertRaises(AltaError):
            self._alta()
        self.sheet.refresh_from_db()
        self.assertFalse(self.sheet.in_team)
        self.assertEqual(mail.outbox, [])

    def test_alta_in_another_competition_is_allowed(self):
        lapi_captain = User.objects.create_user("lcap", password=PASSWORD, email="lcap@example.com")
        lapi = create_club("Club LAPI", "Sevilla", lapi_captain, competition="lapi")
        Membership.objects.create(user=self.user, club=lapi, role=Membership.MEMBER)
        self.assertIsNotNone(self._alta())

    def test_alta_needs_an_email(self):
        User.objects.filter(pk=self.user.pk).update(email="")
        self.sheet.refresh_from_db()
        self.assertIn("no tiene email", alta_blocker(self.sheet))

    def test_second_alta_replaces_the_pending_invitation(self):
        first = self._alta()
        Player.objects.filter(pk=self.sheet.pk).update(in_team=False)
        second = self._alta()
        self.assertFalse(Invitation.objects.filter(pk=first.pk).exists())
        self.assertEqual(Invitation.objects.filter(player=self.sheet).count(), 1)
        self.assertNotEqual(first.token, second.token)

    def test_sheet_without_account_just_returns_to_the_squad(self):
        dar_de_baja(self.free)
        self.assertIsNone(self._alta(self.free))
        self.free.refresh_from_db()
        self.assertTrue(self.free.in_team)
        self.assertIsNone(self.free.left_on)
        self.assertEqual(mail.outbox, [])

    def test_ticking_en_el_equipo_in_edit_player_sends_the_invitation(self):
        self.client.login(username="cap", password=PASSWORD)
        data = {"name": "Edu", "last_name": "B", "position": "NONE", "skillfull_hand": "NONE", "in_team": "on",
                "joined_season": self.sheet.joined_season or ""}
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("edit_player", args=[self.sheet.public_id]), data)
        self.assertEqual(Invitation.objects.filter(player=self.sheet).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_ticking_in_manage_roster_sends_the_invitation_and_refuses_a_taken_email(self):
        self.client.login(username="cap", password=PASSWORD)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("manage_roster"), {
                "team": self.club.public_id, "join": [self.sheet.pk, self.free.pk]})
        self.assertEqual(Invitation.objects.filter(player=self.sheet).count(), 1)
        self.assertEqual(len(mail.outbox), 1)


class AuditPhaseATests(BajaFixture):
    """Fase A de la auditoría: permisos de la baja, invitación solo para la cuenta titular y «Sin equipo»."""

    def test_manager_cannot_give_baja_to_a_sheet_with_account(self):
        manager = User.objects.create_user("man", password=PASSWORD, email="man@example.com")
        Membership.objects.create(user=manager, club=self.club, role=Membership.MANAGER)
        with self.assertRaises(RemovalError):
            dar_de_baja(self.sheet, manager)
        self.assertTrue(Membership.objects.filter(user=self.user, club=self.club).exists())
        self.assertIsNone(dar_de_baja(self.free, manager))

    def test_nobody_gives_baja_to_themselves(self):
        with self.assertRaises(RemovalError):
            dar_de_baja(self.sheet, self.user)

    def test_rejoin_invitation_is_refused_to_another_account(self):
        from core.services import accept_invitation
        dar_de_baja(self.sheet, self.captain)
        self.sheet.refresh_from_db()
        invitation = dar_de_alta(self.sheet, self.captain, "https://zyra.test/")
        other = User.objects.create_user("otro", password=PASSWORD, email="otro@example.com")
        with self.assertRaises(Exception):
            accept_invitation(invitation, other)
        self.sheet.refresh_from_db()
        self.assertIsNone(self.sheet.user)

    def test_no_club_page_shows_the_pending_invitation(self):
        dar_de_baja(self.sheet, self.captain)
        self.sheet.refresh_from_db()
        invitation = dar_de_alta(self.sheet, self.captain, "https://zyra.test/")
        self.client.login(username="edu", password=PASSWORD)
        response = self.client.get(reverse("no_club"))
        self.assertContains(response, reverse("respond_copy_invitation", args=[invitation.token]))
        self.assertContains(response, "recuperas tu histórico")


class AltaOptionBTests(BajaFixture):
    """Opción B: al dar de alta la ficha entra ya en la plantilla; aceptar enlaza sin tocar las estadísticas."""

    def setUp(self):
        super().setUp()
        self.game = Game.objects.create(match=self.closed_match, player_1_local=self.sheet)
        Result.objects.create(game=self.game, set1_local=6, set1_visiting=2, set2_local=6, set2_visiting=3)
        dar_de_baja(self.sheet, self.captain)
        self.sheet.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.invitation = dar_de_alta(self.sheet, self.captain, "https://zyra.test/")

    def test_sheet_is_in_the_squad_and_without_left_date_until_answered(self):
        self.sheet.refresh_from_db()
        self.assertTrue(self.sheet.in_team)
        self.assertIsNone(self.sheet.left_on)
        self.assertIsNone(self.sheet.user)

    def test_accepting_links_the_same_sheet_and_keeps_its_games(self):
        sheet_id = self.sheet.pk
        self.client.login(username="edu", password=PASSWORD)
        self.client.post(reverse("respond_copy_invitation", args=[self.invitation.token]), {"action": "accept"})
        self.assertEqual(Player.objects.filter(club=self.club, user=self.user).get().pk, sheet_id)
        self.game.refresh_from_db()
        self.assertEqual(self.game.player_1_local_id, sheet_id)
        self.assertEqual(Result.objects.filter(game=self.game).count(), 1)
        self.assertEqual(Player.objects.filter(club=self.club, name="Edu").count(), 1)

    def test_soy_yo_consumes_the_pending_invitation(self):
        from players import copy as player_copy
        player_copy._link(self.sheet, self.user)
        self.assertFalse(Invitation.objects.filter(pk=self.invitation.pk).exists())


class AuditPhaseCTests(BajaFixture):
    """Fase C de la auditoría: disponibilidades, borrar cuenta como baja y aviso de huecos."""

    def test_baja_deletes_availability_of_open_matches_only(self):
        from call.models import Availability
        Availability.objects.create(match=self.open_match, player=self.sheet, answer=Availability.YES)
        Availability.objects.create(match=self.closed_match, player=self.sheet, answer=Availability.YES)
        dar_de_baja(self.sheet, self.captain)
        self.assertFalse(Availability.objects.filter(match=self.open_match, player=self.sheet).exists())
        self.assertTrue(Availability.objects.filter(match=self.closed_match, player=self.sheet).exists())

    def test_delete_account_is_a_baja_of_the_sheet(self):
        from core.services import delete_account
        delete_account(self.user)
        self.sheet.refresh_from_db()
        self.assertFalse(self.sheet.in_team)
        self.assertIsNone(self.sheet.user)
        self.assertEqual(self.sheet.left_on, timezone.localdate())
        self.assertNotIn(self.sheet, self.open_call.players.all())
        self.assertIn(self.sheet, self.closed_call.players.all())

    def test_open_matches_with_counts_the_matches_that_change(self):
        from core.services import open_matches_with
        self.assertEqual(open_matches_with([self.sheet.pk]), {self.open_match.pk})
        self.assertEqual(open_matches_with([]), set())

    def test_baja_in_the_form_warns_about_open_matches(self):
        self.client.login(username="cap", password=PASSWORD)
        response = self.client.post(reverse("edit_player", args=[self.free.public_id]), {
            "name": "Sin", "last_name": "Cuenta", "position": "Derecha",
            "skillfull_hand": "Diestro", "joined_season": "2026-2027"}, follow=True)
        self.assertContains(response, "La baja deja huecos en 1 enfrentamiento abierto")
