"""Tests de abandonar el club siendo su único miembro: el club se elimina con sus datos."""
import datetime
import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Club, Invitation, Membership
from core.services import create_club
from core.test_images import image_bytes
from match.models import Game, Match
from players.models import Player
from team.models import Team

User = get_user_model()


class DeleteClubOnLeaveTests(TestCase):
    """El último capitán, si es el único miembro, puede abandonar el club y eliminarlo."""

    def setUp(self):
        """Club con capitán único, un rival, un jugador con foto y un partido con su juego."""
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

        self.captain = User.objects.create_user("capitan", password="pass-12345")
        self.club = create_club("Los Gladiadores", "Sevilla", self.captain, gender="M")
        rival = Team.objects.create(club=self.club, name="Rival", location="Huelva")
        self.player = Player.objects.create(
            club=self.club, team=self.club.own_team, name="Ana", last_name="Ruiz", user=self.captain,
            photo=SimpleUploadedFile("ana.jpg", image_bytes(), content_type="image/jpeg"),
        )
        match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                     start_date=datetime.date(2026, 10, 1))
        Game.objects.create(match=match, n_game=1, player_1_local=self.player)
        Invitation.objects.create(club=self.club, created_by=self.captain, reusable=True)
        self.photo_path = self.player.photo.path
        self.client.force_login(self.captain)

    def test_modal_warns_that_the_club_will_be_deleted(self):
        """El popup avisa del borrado y pide escribir el nombre del club."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Si lo abandonas, el club se eliminará")
        self.assertContains(response, 'name="confirm_name"')

    def test_modal_is_the_usual_one_when_there_are_more_members(self):
        """Con más miembros el popup no habla de eliminar el club."""
        member = User.objects.create_user("luis", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, 'name="confirm_name"')
        self.client.force_login(member)
        self.assertNotContains(self.client.get(reverse("home")), 'name="confirm_name"')

    def test_wrong_name_keeps_the_club(self):
        """Sin el nombre del club (o con otro) no se borra nada."""
        for typed in (None, "", "Otro club"):
            data = {} if typed is None else {"confirm_name": typed}
            self.client.post(reverse("leave_club"), data)
            self.assertTrue(Club.objects.filter(pk=self.club.pk).exists())
            self.assertTrue(Membership.objects.filter(user=self.captain, club=self.club).exists())

    def test_confirmed_leave_deletes_club_and_its_data(self):
        """Con el nombre correcto se borra el club, sus equipos, jugadores, partidos y fotos."""
        self.assertTrue(os.path.exists(self.photo_path))
        with self.captureOnCommitCallbacks(execute=True):  # las fotos se borran al confirmar la transacción
            response = self.client.post(reverse("leave_club"), {"confirm_name": "  los gladiadores "})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertFalse(Club.objects.filter(pk=self.club.pk).exists())
        self.assertFalse(Team.objects.filter(club_id=self.club.pk).exists())
        self.assertFalse(Player.objects.filter(club_id=self.club.pk).exists())
        self.assertFalse(Match.objects.filter(club_id=self.club.pk).exists())
        self.assertFalse(Game.objects.exists())
        self.assertFalse(Invitation.objects.filter(club_id=self.club.pk).exists())
        self.assertFalse(os.path.exists(self.photo_path))
        self.assertTrue(User.objects.filter(pk=self.captain.pk).exists())  # la cuenta se conserva
        self.assertRedirects(self.client.get(reverse("home")), reverse("no_club"))

    def test_last_captain_with_members_still_cannot_leave(self):
        """Si quedan otros miembros sigue haciendo falta nombrar otro capitán; no se borra nada."""
        member = User.objects.create_user("luis", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.post(reverse("leave_club"), {"confirm_name": "Los Gladiadores"})
        self.assertTrue(Club.objects.filter(pk=self.club.pk).exists())
        self.assertTrue(Membership.objects.filter(user=self.captain, club=self.club).exists())

    def test_other_clubs_are_untouched(self):
        """Eliminar un club no toca los datos de los demás."""
        other_captain = User.objects.create_user("otro", password="pass-12345")
        other = create_club("Club B", "Cádiz", other_captain)
        self.client.post(reverse("leave_club"), {"confirm_name": "Los Gladiadores"})
        self.assertTrue(Club.objects.filter(pk=other.pk).exists())
        self.assertTrue(Team.objects.filter(club=other, is_own=True).exists())
