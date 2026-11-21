"""Visibilidad del listado de la convocatoria para los jugadores (``Club.call_list_public``)."""
from django.urls import reverse

from call.models import Call
from core.models import Membership
from match.tests_ux import FUTURE, UxBase, User


class CallListVisibilityTests(UxBase):
    def setUp(self):
        super().setUp()
        self.match_ = self.match(FUTURE)
        self.member = User.objects.create_user("socio", password="pass-12345")
        Membership.objects.create(user=self.member, club=self.club, role=Membership.MEMBER)

    def ficha(self, user, stage=True):
        from core.models import UserPreference
        self.client.force_login(user)
        UserPreference.objects.update_or_create(user=user, defaults={"match_stage_view": stage})
        return self.client.get(reverse("call_for_match", args=[self.match_.public_id]))

    def call(self, closed):
        call = Call.objects.create(match=self.match_, draft_mode=not closed)
        call.players.set(self.players[:4])
        return call

    def set_public(self, value):
        self.club.call_list_public = value
        self.club.save()

    def test_private_by_default_hides_names_open_and_closed(self):
        for closed in (False, True):
            Call.objects.all().delete()
            self.call(closed)
            for stage in (True, False):
                page = self.ficha(self.member, stage)
                self.assertNotContains(page, "Jug00")
                self.assertNotContains(page, "Jug03")

    def test_public_hides_names_and_count_while_open(self):
        self.set_public(True)
        self.call(False)
        for stage in (True, False):
            page = self.ficha(self.member, stage)
            self.assertNotContains(page, "Jug00")
            self.assertNotContains(page, "4 de 10")
            self.assertNotContains(page, "z-stage-card")

    def test_hidden_list_shows_no_count_and_a_compact_card(self):
        from players.models import Player
        Player.objects.filter(id=self.players[10].id).update(user=self.member)
        self.call(True)
        for stage in (True, False):
            page = self.ficha(self.member, stage)
            self.assertNotContains(page, "apuntados</")
            self.assertNotContains(page, "convocados</")
            self.assertNotContains(page, "z-stage-card")
            self.assertNotContains(page, "has-focus")
            self.assertContains(page, "No convocado")

    def test_public_shows_final_list_once_closed(self):
        self.set_public(True)
        self.call(True)
        for stage in (True, False):
            page = self.ficha(self.member, stage)
            self.assertContains(page, "Jug00")

    def test_player_still_sees_own_status_when_list_is_hidden(self):
        from players.models import Player
        Player.objects.filter(id=self.players[0].id).update(user=self.member)
        self.call(False)
        from call.models import Availability
        Availability.objects.create(match=self.match_, player=self.players[0], answer=Availability.YES)
        page = self.ficha(self.member)
        self.assertContains(page, "Te has apuntado")
        self.assertNotContains(page, "4 de 10")

    def test_managers_always_see_the_list_and_the_tip(self):
        self.call(False)
        for stage in (True, False):
            page = self.ficha(self.user, stage)
            self.assertContains(page, "Jug00")
            self.assertContains(page, "Los jugadores no ven esta lista")
        self.set_public(True)
        self.assertContains(self.ficha(self.user), "Los jugadores ven la lista de convocados")

    def test_player_does_not_get_the_tip(self):
        self.call(False)
        self.assertNotContains(self.ficha(self.member), "El capitán puede cambiarlo en Equipo")

    def test_only_the_captain_changes_the_setting(self):
        url = reverse("set_call_list_visibility")
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url, {"public": "1", "team": self.club.public_id}).status_code, 403)
        manager = User.objects.create_user("gestor", password="pass-12345")
        Membership.objects.create(user=manager, club=self.club, role=Membership.MANAGER)
        self.client.force_login(manager)
        self.assertEqual(self.client.post(url, {"public": "1", "team": self.club.public_id}).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url, {"public": "1", "team": self.club.public_id})
        self.club.refresh_from_db()
        self.assertTrue(self.club.call_list_public)
        self.client.post(url, {"team": self.club.public_id})
        self.club.refresh_from_db()
        self.assertFalse(self.club.call_list_public)

    def test_club_page_shows_the_switch_to_the_captain_only(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("club_home")), 'name="public"')
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse("club_home")), 'name="public"')

    def link_player(self):
        from players.models import Player
        Player.objects.filter(id=self.players[10].id).update(user=self.member)

    def test_player_without_list_gets_no_phase_cards_while_the_call_is_open(self):
        self.link_player()
        for call in (False, None):
            Call.objects.all().delete()
            if call is not None:
                self.call(call)
            for stage in (True, False):
                page = self.ficha(self.member, stage)
                self.assertNotContains(page, "Fases del enfrentamiento")
                self.assertContains(page, "¿Puedes jugar?")

    def test_phase_cards_come_back_once_the_call_is_closed_or_for_managers(self):
        self.link_player()
        self.call(True)
        self.assertContains(self.ficha(self.member), "Fases del enfrentamiento")
        Call.objects.all().delete()
        self.call(False)
        self.assertContains(self.ficha(self.user), "Fases del enfrentamiento")

    def test_closed_call_shows_a_check_if_called_and_a_red_cross_if_not(self):
        from players.models import Player
        call = self.call(True)
        Player.objects.filter(id=self.players[10].id).update(user=self.member)
        for stage in (True, False):
            page = self.ficha(self.member, stage)
            self.assertContains(page, "is-missed")
            self.assertContains(page, "No convocado")
        Player.objects.filter(id=self.players[10].id).update(user=None)
        Player.objects.filter(id=self.players[0].id).update(user=self.member)
        for stage in (True, False):
            page = self.ficha(self.member, stage)
            self.assertNotContains(page, "is-missed")
            self.assertContains(page, "Estás convocado")

    def test_not_called_pill_is_red_once_the_call_is_closed(self):
        from players.models import Player
        Player.objects.filter(id=self.players[10].id).update(user=self.member)
        self.call(True)
        page = self.ficha(self.member)
        self.assertContains(page, "z-stage-me is-missed")
        self.assertContains(page, "No estás convocado")

    def test_captain_signing_a_player_up_is_not_an_answer_in_any_view(self):
        from players.models import Player
        Player.objects.filter(id=self.players[0].id).update(user=self.member)
        self.call(False)
        for stage in (True, False):
            page = self.ficha(self.member, stage)
            for text in ("Te has apuntado", "Has dicho que no", "Tu respuesta está pendiente"):
                self.assertNotContains(page, text)
        from call.models import Availability
        Availability.objects.create(match=self.match_, player=self.players[0], answer=Availability.NO)
        for stage in (True, False):
            self.assertContains(self.ficha(self.member, stage), "Has dicho que no")
