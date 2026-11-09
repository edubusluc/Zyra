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
        """El popup avisa del cierre y pide escribir el nombre del club."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Si lo abandonas, el equipo se cerrará")
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

    def test_confirmed_leave_archives_club_and_keeps_the_history(self):
        """Con el nombre correcto el club se archiva: sin miembros ni invitaciones, con el historial de quien jugó."""
        self.assertTrue(os.path.exists(self.photo_path))
        stranger = Player.objects.create(
            club=self.club, team=self.club.own_team, name="Sin", last_name="Cuenta",
            photo=SimpleUploadedFile("sin.jpg", image_bytes(), content_type="image/jpeg"))
        stranger_path = stranger.photo.path
        with self.captureOnCommitCallbacks(execute=True):  # las fotos se borran al confirmar la transacción
            response = self.client.post(reverse("leave_club"), {"confirm_name": "  los gladiadores "})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.club.refresh_from_db()
        self.assertTrue(self.club.is_archived)
        self.assertFalse(Membership.objects.filter(club=self.club).exists())
        self.assertFalse(Invitation.objects.filter(club_id=self.club.pk).exists())
        # Se conservan equipos, jugadores y partidos; la ficha de la cuenta pasa a ser su ficha anterior y conserva su foto.
        self.assertTrue(Team.objects.filter(club_id=self.club.pk).exists())
        self.assertTrue(Match.objects.filter(club_id=self.club.pk).exists())
        self.assertEqual(Game.objects.get().player_1_local, self.player)
        self.player.refresh_from_db()
        self.assertEqual((self.player.user, self.player.past_user), (None, self.captain))
        self.assertIsNotNone(self.player.left_on)
        self.assertTrue(os.path.exists(self.photo_path))
        # La foto de la ficha sin cuenta sí se borra.
        stranger.refresh_from_db()
        self.assertFalse(stranger.photo)
        self.assertFalse(os.path.exists(stranger_path))
        self.assertTrue(User.objects.filter(pk=self.captain.pk).exists())  # la cuenta se conserva
        self.assertRedirects(self.client.get(reverse("home")), reverse("no_club"))
        # Y la persona sigue viendo sus estadísticas de ese equipo en «Yo».
        page = self.client.get(reverse("my_statistics") + "?season=all")
        self.assertEqual([(r["club"], r["former"]) for r in page.context["rows"]], [(self.club, True)])

    def test_staff_delete_removes_everything(self):
        """El personal sí puede borrar un club del todo (``delete_club``): jugadores, partidos, fotos e historial."""
        from core.services import delete_club
        with self.captureOnCommitCallbacks(execute=True):
            delete_club(self.club)
        self.assertFalse(Club.objects.filter(pk=self.club.pk).exists())
        self.assertFalse(Player.objects.filter(club_id=self.club.pk).exists())
        self.assertFalse(Game.objects.exists())
        self.assertFalse(os.path.exists(self.photo_path))

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
