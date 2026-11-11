"""«Plantilla» envía solo cambios y el equipo: un envío antiguo o de otra pestaña no da de baja a nadie."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.middleware import SESSION_KEY
from core.models import Membership
from core.services import create_club
from players.models import Player

User = get_user_model()
PASSWORD = "pass-12345"


class RosterChangesTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.snp = create_club("Gladiadores", "Sevilla", self.captain)
        self.lapi = create_club("Gladiadores LAPI", "Sevilla", self.captain, competition="lapi")
        self.snp_players = [Player.objects.create(club=self.snp, name=f"S{i}", last_name="X") for i in range(3)]
        self.lapi_players = [Player.objects.create(club=self.lapi, name=f"L{i}", last_name="X") for i in range(4)]
        self.client.login(username="capi", password=PASSWORD)

    def activate(self, club):
        """Deja ``club`` como equipo activo de la sesión."""
        session = self.client.session
        session[SESSION_KEY] = club.id
        session.save()
        page = self.client.get(reverse("manage_roster"))
        self.assertContains(page, club.name)

    def post(self, club, **data):
        return self.client.post(reverse("manage_roster"), {"team": club.public_id, **data}, follow=True)

    def test_page_carries_the_team_and_posts_changes_only(self):
        self.activate(self.snp)
        page = self.client.get(reverse("manage_roster"))
        self.assertContains(page, f'name="team" value="{self.snp.public_id}"')
        self.assertContains(page, "data-roster-fields")

    def test_cross_tab_submit_does_not_touch_the_active_team(self):
        """Página del equipo SNP enviada cuando el activo es el LAPI: no se da de baja a nadie del LAPI."""
        self.activate(self.lapi)
        response = self.post(self.snp, leave=[p.pk for p in self.snp_players])
        self.assertContains(response, "ya no es la del equipo activo")
        self.assertEqual(Player.objects.filter(club=self.lapi, in_team=True).count(), 4)
        self.assertEqual(Player.objects.filter(club=self.snp, in_team=True).count(), 3)
        self.assertTrue(Membership.objects.filter(user=self.captain, club=self.lapi).exists())

    def test_old_form_without_team_is_refused(self):
        """El formato antiguo (estado completo, sin equipo) no hace nada."""
        self.activate(self.snp)
        before = Player.objects.filter(club=self.snp, in_team=True).count()
        response = self.client.post(reverse("manage_roster"), {"in_team": [self.snp_players[0].pk]}, follow=True)
        self.assertContains(response, "No se ha guardado ningún cambio")
        self.assertEqual(Player.objects.filter(club=self.snp, in_team=True).count(), before)

    def test_new_player_created_after_page_load_is_not_removed(self):
        """Un jugador creado después de cargar la página no cae por no estar en el envío."""
        self.activate(self.snp)
        newcomer = Player.objects.create(club=self.snp, name="Nuevo", last_name="Z")
        self.post(self.snp, leave=[self.snp_players[0].pk])
        newcomer.refresh_from_db()
        self.assertTrue(newcomer.in_team)

    def test_changes_apply_to_the_named_players_only(self):
        self.activate(self.snp)
        self.post(self.snp, leave=[self.snp_players[0].pk])
        states = {p.name: p.in_team for p in Player.objects.filter(club=self.snp, name__startswith="S")}
        self.assertEqual(states, {"S0": False, "S1": True, "S2": True})

    def test_ids_from_another_club_are_ignored(self):
        self.activate(self.snp)
        self.post(self.snp, leave=[self.lapi_players[0].pk])
        self.assertTrue(Player.objects.get(pk=self.lapi_players[0].pk).in_team)
