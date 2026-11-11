"""
Fase 3 de la hoja de ruta (navegación y equipo activo): las páginas de estadísticas de jugador, pareja y rival
funcionan aunque el equipo activo de la sesión sea otro (NAV-01, NAV-03).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.middleware import SESSION_KEY
from core.services import create_club
from players.models import Player
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"


class QueryObjectsFollowTheirTeamTests(TestCase):
    """Un capitán con dos equipos (SNP y LAPI) abre enlaces del uno estando activo el otro."""

    def setUp(self):
        self.user = User.objects.create_user("capi", password=PASSWORD)
        self.snp = create_club("Club SNP", "Sevilla", self.user)
        self.lapi = create_club("Club LAPI", "Sevilla", self.user, competition="lapi")
        self.ana = Player.objects.create(club=self.snp, name="Ana", last_name="SNP")
        self.bea = Player.objects.create(club=self.snp, name="Bea", last_name="SNP")
        self.rival = Team.objects.create(club=self.snp, name="Rival SNP", location="X", in_group=True)
        self.client.login(username="capi", password=PASSWORD)

    def activate(self, club):
        """Deja ``club`` como equipo activo de la sesión."""
        session = self.client.session
        session[SESSION_KEY] = club.id
        session.save()

    def test_player_link_works_with_the_other_team_active(self):
        self.activate(self.lapi)
        response = self.client.get(reverse("player_statistics"), {"player": self.ana.public_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[SESSION_KEY], self.snp.id)

    def test_pair_link_works_with_the_other_team_active(self):
        self.activate(self.lapi)
        response = self.client.get(reverse("pair_statistics"), {"p1": self.ana.public_id, "p2": self.bea.public_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[SESSION_KEY], self.snp.id)

    def test_rival_link_works_with_the_other_team_active(self):
        self.activate(self.lapi)
        response = self.client.get(reverse("rival_detail"), {"team": self.rival.public_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[SESSION_KEY], self.snp.id)

    def test_explicit_space_wins_and_a_foreign_object_is_still_404(self):
        self.activate(self.snp)
        response = self.client.get(reverse("player_statistics"), {"player": self.ana.public_id, "en": "lapi"})
        self.assertEqual(response.status_code, 404)

    def test_player_of_another_user_is_404(self):
        other = User.objects.create_user("otro", password=PASSWORD)
        club = create_club("Club Otro", "Cádiz", other)
        stranger = Player.objects.create(club=club, name="Eva", last_name="Otra")
        self.assertEqual(self.client.get(reverse("player_statistics"), {"player": stranger.public_id}).status_code, 404)

    def test_switching_competition_from_a_rival_page_returns_to_the_list(self):
        """El selector de competición no lleva el rival (no existe en el otro equipo): vuelve a la lista de rivales."""
        response = self.client.get(reverse("rival_detail"), {"en": "lapi"})
        self.assertRedirects(response, reverse("rival_statistics"))
        self.assertEqual(self.client.session[SESSION_KEY], self.lapi.id)


class PlayerHomeLinksTests(TestCase):
    """El Inicio de un jugador solo enlaza a páginas que puede abrir (NAV-02)."""

    def test_photo_task_links_to_my_sheet_not_to_the_manager_edit_page(self):
        captain = User.objects.create_user("capi", password=PASSWORD)
        club = create_club("Club SNP", "Sevilla", captain)
        member = User.objects.create_user("jug", password=PASSWORD, email="jug@example.com")
        from core.models import Membership
        Membership.objects.create(user=member, club=club, role=Membership.MEMBER)
        sheet = Player.objects.create(club=club, user=member, name="Jug", last_name="Uno")
        self.client.login(username="jug", password=PASSWORD)
        page = self.client.get(reverse("home"))
        self.assertContains(page, "Sube tu foto")
        self.assertContains(page, f'href="{reverse("my_player")}?en=snp"')
        self.assertNotContains(page, reverse("edit_player", args=[sheet.public_id]))
        self.assertEqual(self.client.get(f'{reverse("my_player")}?en=snp').status_code, 200)


class StaleTeamFormsTests(TestCase):
    """Cuenta SNP, copiar jugadores e importar con el equipo de la página (FUN-04)."""

    def setUp(self):
        from players.models import SnpAccount
        self.user = User.objects.create_user("capi", password=PASSWORD)
        self.snp = create_club("Club SNP", "Sevilla", self.user)
        self.lapi = create_club("Club LAPI", "Sevilla", self.user, competition="lapi")
        self.account = SnpAccount(club=self.snp)
        self.account.username, self.account.password = "capitan", "secreto"
        self.account.save()
        self.client.login(username="capi", password=PASSWORD)
        session = self.client.session
        session[SESSION_KEY] = self.lapi.id  # otra pestaña dejó activo el equipo LAPI
        session.save()

    def test_snp_account_delete_of_the_page_team_is_rejected_when_another_is_active(self):
        from players.models import SnpAccount
        response = self.client.post(reverse("snp_account_delete"), {"team": self.snp.public_id}, follow=True)
        self.assertContains(response, "ya no es la del equipo activo")
        self.assertTrue(SnpAccount.objects.filter(club=self.snp).exists())

    def test_snp_account_delete_without_team_is_rejected(self):
        from players.models import SnpAccount
        self.client.post(reverse("snp_account_delete"))
        self.assertTrue(SnpAccount.objects.filter(club=self.snp).exists())

    def test_snp_account_save_goes_only_to_the_page_team(self):
        from players.models import SnpAccount
        self.client.post(reverse("snp_account"), {"team": self.snp.public_id, "username": "otro", "password": "x"})
        self.assertEqual(SnpAccount.objects.get(club=self.snp).username, "capitan")
        self.assertFalse(SnpAccount.objects.filter(club=self.lapi).exists())

    def test_complete_team_start_and_copy_players_reject_a_stale_page(self):
        from players.models import SnpTeamImport
        self.client.post(reverse("complete_team_start"), {"team": self.snp.public_id})
        self.assertFalse(SnpTeamImport.objects.exists())
        response = self.client.post(reverse("copy_players"), {"team": self.snp.public_id, "players": []}, follow=True)
        self.assertContains(response, "ya no es la del equipo activo")

    def test_forms_carry_the_team_of_the_page(self):
        session = self.client.session
        session[SESSION_KEY] = self.snp.id
        session.save()
        page = self.client.get(reverse("snp_account"))
        self.assertContains(page, f'name="team" value="{self.snp.public_id}"', count=1)


class CallOnlyInTeamPlayersTests(TestCase):
    """La convocatoria no acepta por POST a jugadores dados de baja (FUN-07)."""

    def setUp(self):
        import datetime
        from call.models import Call
        from match.models import Match
        self.user = User.objects.create_user("capi", password=PASSWORD)
        self.club = create_club("Club SNP", "Sevilla", self.user)
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                          start_date=datetime.date.today() + datetime.timedelta(days=5))
        self.active = Player.objects.create(club=self.club, name="Ana", last_name="Activa", in_team=True)
        self.left = Player.objects.create(club=self.club, name="Luis", last_name="Baja", in_team=False)
        self.call_model = Call
        self.client.login(username="capi", password=PASSWORD)

    def test_create_call_ignores_a_player_who_left(self):
        self.client.post(reverse("create_call", args=[self.match.public_id]),
                         {"players": [self.active.pk, self.left.pk]})
        self.assertEqual(list(self.call_model.objects.get(match=self.match).players.all()), [self.active])

    def test_edit_call_cannot_add_a_player_who_left_but_keeps_one_already_called(self):
        call = self.call_model.objects.create(match=self.match)
        call.players.set([self.left])
        self.client.post(reverse("edit_call", args=[call.public_id]), {"players": [self.active.pk, self.left.pk]})
        self.assertEqual(set(call.players.all()), {self.active, self.left})
        call.players.set([self.active])
        self.client.post(reverse("edit_call", args=[call.public_id]), {"players": [self.active.pk, self.left.pk]})
        self.assertEqual(set(call.players.all()), {self.active})


class CallLogNotFoundTests(TestCase):
    """«Advertencias y cambios» de una convocatoria que no existe o es de otro club responde 404 (NAV-04)."""

    def test_missing_or_foreign_call_is_404(self):
        import datetime
        from call.models import Call
        from match.models import Match
        mine = User.objects.create_user("capi", password=PASSWORD)
        create_club("Club A", "Sevilla", mine)
        other = User.objects.create_user("otro", password=PASSWORD)
        club = create_club("Club B", "Cádiz", other)
        rival = Team.objects.create(club=club, name="Rival", location="X", in_group=True)
        match = Match.objects.create(club=club, local=club.own_team, visiting=rival, start_date=datetime.date.today())
        foreign = Call.objects.create(match=match)
        self.client.login(username="capi", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("view_call_log", args=["ZZZZZZZZZZZZZZZ"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("view_call_log", args=[foreign.public_id])).status_code, 404)
