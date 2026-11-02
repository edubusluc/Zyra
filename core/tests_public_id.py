import datetime
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core.public_id import LENGTH, PREFIXES, public_id_models
from core.services import create_club
from match.models import Game, Match
from players.models import Player
from team.models import Team

User = get_user_model()


class PublicIdTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club", "Sevilla", self.user)
        self.client.login(username="admin", password="pass-12345")

    def test_new_objects_get_a_prefixed_id(self):
        player = Player.objects.create(club=self.club, name="Ana", last_name="Alpha")
        self.assertEqual(len(player.public_id), LENGTH)
        self.assertTrue(player.public_id.startswith("PLY"))
        self.assertTrue(self.club.public_id.startswith("CLB"))
        self.assertNotEqual(player.public_id, Player.objects.create(club=self.club, name="Bea", last_name="Beta").public_id)

    def test_prefixes_are_unique_per_model(self):
        models = public_id_models()
        self.assertEqual(len({m.PUBLIC_ID_PREFIX for m in models}), len(models))
        self.assertEqual(PREFIXES["MAT"], "match.Match")

    def test_bulk_create_assigns_ids(self):
        rival = Team.objects.create(club=self.club, name="Rival", location="X")
        match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                     start_date=datetime.date(2025, 10, 1))
        Game.objects.bulk_create([Game(match=match, n_game=1), Game(match=match, n_game=2)])
        self.assertFalse(Game.objects.filter(public_id__isnull=True).exists())

    def test_urls_use_public_id_and_numbers_give_404(self):
        player = Player.objects.create(club=self.club, name="Ana", last_name="Alpha")
        self.assertEqual(self.client.get(f"/players/player_details/{player.public_id}/", follow=True).status_code, 200)
        self.assertEqual(self.client.get(f"/players/player_details/{player.pk}/").status_code, 404)

    def test_assign_public_ids_fills_existing_rows(self):
        player = Player.objects.create(club=self.club, name="Ana", last_name="Alpha")
        Player.objects.filter(pk=player.pk).update(public_id=None)
        out = io.StringIO()
        call_command("assign_public_ids", stdout=out)
        player.refresh_from_db()
        self.assertTrue(player.public_id.startswith("PLY"))
        self.assertIn("players.Player: 1 fila", out.getvalue())
        # Segunda vez: no queda nada por rellenar y no cambia los que ya tienen
        call_command("assign_public_ids", stdout=io.StringIO())
        self.assertEqual(Player.objects.get(pk=player.pk).public_id, player.public_id)
