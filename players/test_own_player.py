import datetime
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Invitation, Membership, PhotoCheck, PhotoRemoval
from core.services import create_club
from core.test_images import image_bytes
from players.models import Player

User = get_user_model()


def upload(name="foto.jpg"):
    return SimpleUploadedFile(name, image_bytes((600, 600)), content_type="image/jpeg")


class MediaMixin:
    def use_temp_media(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)


class OwnPlayerTests(MediaMixin, TestCase):
    def setUp(self):
        self.use_temp_media()
        self.captain = User.objects.create_user("capitan", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.captain, gender="M")
        self.user = User.objects.create_user("ana", password="pass-12345", email="ana@example.com")
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.ana = Player.objects.create(club=self.club, name="Ana", last_name="Ruiz Gómez", joined_season="2024-2025")
        self.other = Player.objects.create(club=self.club, name="Luis", last_name="Pérez")
        self.client.force_login(self.user)

    def test_joining_with_invitation_goes_to_choose_player(self):
        newcomer = User.objects.create_user("nuevo", password="pass-12345")
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain)
        self.client.force_login(newcomer)
        response = self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertRedirects(response, reverse("my_player"), fetch_redirect_response=False)
        page = self.client.get(reverse("my_player"))
        self.assertContains(page, "ANA RUIZ GÓMEZ")
        self.assertContains(page, "Soy yo")

    def test_link_to_existing_player(self):
        response = self.client.post(reverse("link_player", args=[self.ana.public_id]))
        self.assertRedirects(response, reverse("my_player"), fetch_redirect_response=False)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.user, self.user)
        # Ya enlazado: «Mi jugador» es el formulario de su jugador y no puede enlazar otro.
        self.assertContains(self.client.get(reverse("my_player")), "Editar mi jugador")
        self.client.post(reverse("link_player", args=[self.other.public_id]))
        self.other.refresh_from_db()
        self.assertIsNone(self.other.user)

    def test_cannot_take_player_linked_to_someone_else(self):
        intruder = User.objects.create_user("otro", password="pass-12345")
        Membership.objects.create(user=intruder, club=self.club, role=Membership.MEMBER)
        self.ana.user = intruder
        self.ana.save()
        self.client.post(reverse("link_player", args=[self.ana.public_id]))
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.user, intruder)
        # Aparece apagado y sin «Soy yo»; el libre, en lima con su botón.
        page = self.client.get(reverse("my_player")).content.decode()
        self.assertRegex(page, r'class="z-claim is-taken" data-name="ANA RUIZ GÓMEZ"')
        self.assertRegex(page, r'class="z-claim is-free" data-name="LUIS PÉREZ"')
        self.assertEqual(page.count("data-claim-pick"), 1)

    def test_choose_player_page_has_live_search_and_confirmation(self):
        page = self.client.get(reverse("my_player"))
        self.assertContains(page, "data-claim-search")
        self.assertContains(page, 'id="claimModal"')
        self.assertContains(page, "js/link-player.js")
        # Los disponibles van primero.
        intruder = User.objects.create_user("otro", password="pass-12345")
        Player.objects.create(club=self.club, name="Abel", last_name="Alonso", user=intruder)
        html = self.client.get(reverse("my_player")).content.decode()
        self.assertLess(html.index("LUIS PÉREZ"), html.index("ABEL ALONSO"))

    def test_cannot_link_player_of_another_club(self):
        other_captain = User.objects.create_user("c2", password="pass-12345")
        other_club = create_club("Club B", "Huelva", other_captain)
        foreign = Player.objects.create(club=other_club, name="Eva", last_name="Sanz")
        response = self.client.post(reverse("link_player", args=[foreign.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_create_own_player(self):
        response = self.client.post(reverse("my_player"), {
            "name": "Marta", "last_name": "López", "position": "Revés", "skillfull_hand": "Zurdo", "photo": upload(),
        })
        player = Player.objects.get(name="Marta")
        self.assertRedirects(response, reverse("show_player", args=[player.public_id]), fetch_redirect_response=False)
        self.assertEqual((player.user, player.club, player.team, player.in_team), (self.user, self.club, self.club.own_team, True))
        self.assertTrue(player.photo.name.startswith("players/"))

    def test_create_own_player_blocks_same_name(self):
        response = self.client.post(reverse("my_player"), {
            "name": "ana", "last_name": "Ruiz Gomez", "position": "NONE", "skillfull_hand": "NONE",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un jugador con ese nombre")
        self.assertEqual(Player.objects.filter(club=self.club).count(), 2)

    def test_linked_player_edits_position_hand_and_photo_but_not_name_or_season(self):
        self.ana.user = self.user
        self.ana.save()
        response = self.client.post(reverse("my_player"), {
            "position": "Derecha", "skillfull_hand": "Zurdo", "photo": upload(),
            "name": "Otro", "last_name": "Nombre", "joined_season": "2020-2021",
        })
        self.assertRedirects(response, reverse("show_player", args=[self.ana.public_id]), fetch_redirect_response=False)
        self.ana.refresh_from_db()
        self.assertEqual((self.ana.position, self.ana.skillfull_hand), ("Derecha", "Zurdo"))
        self.assertEqual((self.ana.name, self.ana.last_name, self.ana.joined_season), ("Ana", "Ruiz Gómez", "2024-2025"))
        self.assertTrue(self.ana.photo.name.startswith("players/"))
        check = PhotoCheck.objects.get(player=self.ana)
        self.assertEqual((check.uploaded_by, check.photo, check.club), (self.user, self.ana.photo.name, self.club))

    def test_member_cannot_use_captain_edit(self):
        self.ana.user = self.user
        self.ana.save()
        self.client.post(reverse("edit_player", args=[self.ana.public_id]), {"name": "X", "last_name": "Y"})
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.name, "Ana")

    def test_captain_unlinks(self):
        self.ana.user = self.user
        self.ana.save()
        self.client.force_login(self.captain)
        self.assertContains(self.client.get(reverse("edit_player", args=[self.ana.public_id])), "ana@example.com")
        self.client.post(reverse("unlink_player", args=[self.ana.public_id]))
        self.ana.refresh_from_db()
        self.assertIsNone(self.ana.user)

    def test_captain_changes_player_photo(self):
        self.client.force_login(self.captain)
        self.assertContains(self.client.get(reverse("edit_player", args=[self.ana.public_id])), 'enctype="multipart/form-data"')
        data = {"name": "Ana", "last_name": "Ruiz Gómez", "position": "NONE", "skillfull_hand": "NONE",
                "joined_season": "2024-2025", "in_team": "on"}
        response = self.client.post(reverse("edit_player", args=[self.ana.public_id]), {**data, "photo": upload()})
        self.assertRedirects(response, reverse("list_players"), fetch_redirect_response=False)
        self.ana.refresh_from_db()
        photo = self.ana.photo.name
        self.assertTrue(photo.startswith("players/"))
        self.assertEqual(PhotoCheck.objects.get(player=self.ana).uploaded_by, self.captain)
        # Guardar sin elegir otra foto mantiene la que tenía.
        self.client.post(reverse("edit_player", args=[self.ana.public_id]), data)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.photo.name, photo)

    def test_removed_member_is_unlinked_and_rejoins_without_player(self):
        self.ana.user = self.user
        self.ana.save()
        membership = Membership.objects.get(user=self.user, club=self.club)
        self.client.force_login(self.captain)
        self.client.post(reverse("remove_member", args=[membership.public_id]))
        self.assertFalse(Membership.objects.filter(user=self.user, club=self.club).exists())
        self.ana.refresh_from_db()
        self.assertIsNone(self.ana.user)

        invitation = Invitation.objects.create(club=self.club, created_by=self.captain, reusable=True)
        self.client.force_login(self.user)
        self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertContains(self.client.get(reverse("my_player")), "¿Quién eres en el equipo?")

    def test_member_leaves_club_and_is_unlinked(self):
        self.ana.user = self.user
        self.ana.save()
        self.assertContains(self.client.get(reverse("home")), "Abandonar el club")
        response = self.client.post(reverse("leave_club"))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertFalse(Membership.objects.filter(user=self.user, club=self.club).exists())
        self.ana.refresh_from_db()
        self.assertIsNone(self.ana.user)
        self.assertEqual(Player.objects.filter(club=self.club).count(), 2)  # el jugador se conserva
        self.assertRedirects(self.client.get(reverse("home")), reverse("no_club"))

    def test_leave_club_needs_post(self):
        self.assertEqual(self.client.get(reverse("leave_club")).status_code, 405)
        self.assertTrue(Membership.objects.filter(user=self.user, club=self.club).exists())

    def test_last_captain_cannot_leave(self):
        self.client.force_login(self.captain)
        self.client.post(reverse("leave_club"))
        self.assertTrue(Membership.objects.filter(user=self.captain, club=self.club).exists())

    def test_captain_leaves_when_there_is_another_captain(self):
        Membership.objects.filter(user=self.user).update(role=Membership.ADMIN)
        self.client.force_login(self.captain)
        self.client.post(reverse("leave_club"))
        self.assertFalse(Membership.objects.filter(user=self.captain, club=self.club).exists())

    def test_leaving_one_club_keeps_the_others(self):
        other_club = create_club("Club B", "Huelva", self.user)
        session = self.client.session
        session["club_id"] = self.club.id
        session.save()
        self.client.post(reverse("leave_club"))
        self.assertEqual(list(Membership.objects.filter(user=self.user).values_list("club", flat=True)), [other_club.id])
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_member_cannot_unlink(self):
        self.ana.user = self.user
        self.ana.save()
        self.client.post(reverse("unlink_player", args=[self.ana.public_id]))
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.user, self.user)


REKOGNITION_ON = dict(
    REKOGNITION_ENABLED=True, REKOGNITION_ACCESS_KEY_ID="key", REKOGNITION_SECRET_ACCESS_KEY="secret",
    REKOGNITION_FREE_UNTIL=datetime.date(2099, 1, 1), REKOGNITION_MONTHLY_LIMIT=2,
)


class PhotoModerationTests(MediaMixin, TestCase):
    def setUp(self):
        self.use_temp_media()
        self.captain = User.objects.create_user("capitan", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Ruiz", user=self.captain)
        self.client.force_login(self.captain)
        patcher = mock.patch("core.moderation._client")
        self.client_mock = patcher.start()
        self.addCleanup(patcher.stop)
        self.detect = self.client_mock.return_value.detect_moderation_labels
        self.detect.return_value = {"ModerationLabels": []}

    def post_photo(self):
        return self.client.post(reverse("my_player"), {"position": "NONE", "skillfull_hand": "NONE", "photo": upload()})

    @override_settings(**REKOGNITION_ON)
    def test_clean_photo_is_approved(self):
        self.post_photo()
        self.player.refresh_from_db()
        self.assertTrue(self.player.photo)
        check = PhotoCheck.objects.get()
        self.assertEqual((check.status, check.api_called), (PhotoCheck.APPROVED, True))
        # Se envía en JPEG (Rekognition no admite WebP).
        sent = self.detect.call_args.kwargs["Image"]["Bytes"]
        self.assertTrue(sent.startswith(b"\xff\xd8"))

    @override_settings(**REKOGNITION_ON)
    def test_sensitive_photo_is_rejected_and_not_saved(self):
        self.detect.return_value = {"ModerationLabels": [
            {"Name": "Exposed Female Nipple", "ParentName": "Explicit Nudity", "Confidence": 97.0},
        ]}
        response = self.post_photo()
        self.assertContains(response, "no se puede usar")
        self.player.refresh_from_db()
        self.assertFalse(self.player.photo)
        check = PhotoCheck.objects.get()
        self.assertEqual((check.status, check.photo), (PhotoCheck.REJECTED, ""))
        self.assertIn("Exposed Female Nipple", check.reason)

    @override_settings(**REKOGNITION_ON)
    def test_harmless_labels_are_allowed(self):
        self.detect.return_value = {"ModerationLabels": [
            {"Name": "Swimwear or Underwear", "ParentName": "", "Confidence": 90.0},
        ]}
        self.post_photo()
        self.assertEqual(PhotoCheck.objects.get().status, PhotoCheck.APPROVED)

    @override_settings(**REKOGNITION_ON)
    def test_monthly_free_limit_stops_calling_aws(self):
        self.post_photo()
        self.post_photo()
        self.post_photo()
        self.assertEqual(self.detect.call_count, 2)
        last = PhotoCheck.objects.order_by("-id").first()
        self.assertEqual(last.status, PhotoCheck.UNCHECKED)
        self.assertIn("Límite gratuito", last.reason)
        self.player.refresh_from_db()
        self.assertEqual(self.player.photo.name, last.photo)

    @override_settings(**{**REKOGNITION_ON, "REKOGNITION_FREE_UNTIL": datetime.date(2020, 1, 1)})
    def test_after_free_period_photos_are_unchecked(self):
        self.post_photo()
        self.detect.assert_not_called()
        self.assertIn("Periodo gratuito terminado", PhotoCheck.objects.get().reason)

    def test_disabled_by_default_photos_are_unchecked(self):
        self.post_photo()
        self.detect.assert_not_called()
        self.assertEqual(PhotoCheck.objects.get().status, PhotoCheck.UNCHECKED)

    @override_settings(**{**REKOGNITION_ON, "REKOGNITION_ACCESS_KEY_ID": ""})
    def test_not_configured_photos_are_unchecked(self):
        self.post_photo()
        self.detect.assert_not_called()
        self.assertEqual(PhotoCheck.objects.get().status, PhotoCheck.UNCHECKED)

    @override_settings(**REKOGNITION_ON)
    def test_aws_error_accepts_photo_unchecked(self):
        self.detect.side_effect = RuntimeError("sin red")
        self.post_photo()
        check = PhotoCheck.objects.get()
        self.assertEqual(check.status, PhotoCheck.UNCHECKED)
        self.assertIn("sin red", check.reason)
        self.player.refresh_from_db()
        self.assertTrue(self.player.photo)


class BackofficePhotoTests(MediaMixin, TestCase):
    def setUp(self):
        self.use_temp_media()
        self.captain = User.objects.create_user("capitan", password="pass-12345", email="capitan@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.player_user = User.objects.create_user("ana", password="pass-12345", email="ana@example.com")
        Membership.objects.create(user=self.player_user, club=self.club, role=Membership.MEMBER)
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Ruiz", user=self.player_user)
        self.client.force_login(self.player_user)
        self.client.post(reverse("my_player"), {"position": "NONE", "skillfull_hand": "NONE", "photo": upload()})
        self.player.refresh_from_db()
        self.check = PhotoCheck.objects.get()
        self.staff = User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.client.force_login(self.staff)

    def delete(self, check=None, reason=""):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("backoffice:photo_delete", args=[(check or self.check).public_id]), {"reason": reason},
            )

    def test_new_photos_wait_for_review(self):
        response = self.client.get(reverse("backoffice:photo_list"))
        self.assertContains(response, self.player.photo.url)
        self.assertContains(response, "Revisión manual")
        self.assertEqual(self.check.status, PhotoCheck.UNCHECKED)

    def test_approving_unknown_photo_is_404(self):
        response = self.client.post(reverse("backoffice:photo_approve", args=["PHC" + "x" * 12]))
        self.assertEqual(response.status_code, 404)

    def test_not_staff_gets_404(self):
        self.client.force_login(self.captain)
        self.assertEqual(self.client.get(reverse("backoffice:photo_list")).status_code, 404)

    def test_removal_counts_for_who_uploaded_it(self):
        # El capitán sube la foto al jugador de Ana: el aviso y el registro son para él.
        self.check.uploaded_by = self.captain
        self.check.save()
        self.delete()
        self.assertEqual(PhotoRemoval.objects.get().user, self.captain)
        self.assertEqual(mail.outbox[0].to, ["capitan@example.com"])

    def test_old_photo_without_uploader_counts_for_a_captain(self):
        self.player.user = None
        self.player.save()
        self.check.uploaded_by = None
        self.check.save()
        self.delete()
        self.assertEqual(PhotoRemoval.objects.get().user, self.captain)

    def test_replaced_pending_photo_can_leave_the_queue(self):
        self.player.photo = None
        self.player.save()
        self.assertContains(self.client.get(reverse("backoffice:photo_list")), "Quitar de pendientes")

    def test_delete_photo_emails_the_player(self):
        self.delete(reason="Imagen ofensiva")
        self.player.refresh_from_db()
        self.assertFalse(self.player.photo)
        self.assertFalse(PhotoCheck.objects.exists())
        removal = PhotoRemoval.objects.get()
        self.assertEqual((removal.user, removal.club, removal.removed_by, removal.email_sent), (self.player_user, self.club, self.staff, True))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["ana@example.com"])
        self.assertIn("términos y condiciones", email.body)
        self.assertIn("Foto de ANA RUIZ", email.body)
        self.assertIn("Imagen ofensiva", email.body)
        self.assertIn("Si se repite, podemos suspender tu cuenta y eliminar el equipo", email.body)

    def test_repeated_removal_warns_and_shows_count(self):
        PhotoRemoval.objects.create(user=self.player_user, club=self.club, subject="Foto anterior")
        self.assertContains(self.client.get(reverse("backoffice:photo_list")), 'z-badge--danger">1<')
        self.delete()
        self.assertIn("Ya hemos eliminado imágenes tuyas 2 veces", mail.outbox[0].body)
        page = self.client.get(reverse("backoffice:user_detail", args=[self.player_user.pk]))
        self.assertContains(page, "2 fotos eliminadas por no cumplir los términos")
        self.assertContains(page, "Reincidente")

    def test_team_photo_email_goes_to_uploader(self):
        self.client.force_login(self.captain)
        self.client.post(reverse("edit_team", args=[self.club.own_team.public_id]), {
            "name": "Club A", "location": "Sevilla", "gender": "M", "country": "ES", "division": "500", "photo": upload(),
        })
        check = PhotoCheck.objects.get(team=self.club.own_team)
        self.client.force_login(self.staff)
        self.delete(check)
        self.assertEqual(mail.outbox[0].to, ["capitan@example.com"])
        self.assertIn("Escudo de Club A", mail.outbox[0].body)

    def test_user_without_email_is_recorded_as_not_notified(self):
        self.player_user.email = ""
        self.player_user.save()
        response = self.delete()
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(PhotoRemoval.objects.get().email_sent)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("No se ha podido avisar" in m for m in messages))

    def test_staff_approval_is_validated(self):
        self.client.post(reverse("backoffice:photo_approve", args=[self.check.public_id]))
        self.check.refresh_from_db()
        self.assertEqual(self.check.status, PhotoCheck.APPROVED)

    def test_delete_all_photos_of_user_sends_one_email(self):
        self.assertContains(self.client.get(reverse("backoffice:user_detail", args=[self.player_user.pk])), "Eliminar todas sus fotos")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("backoffice:user_photos_delete", args=[self.player_user.pk]))
        self.player.refresh_from_db()
        self.assertFalse(self.player.photo)
        self.assertEqual(len(mail.outbox), 1)

    def test_suspend_and_reactivate_account(self):
        url = reverse("backoffice:user_toggle_active", args=[self.player_user.pk])
        self.client.post(url, {"action": "suspend"})
        self.player_user.refresh_from_db()
        self.assertFalse(self.player_user.is_active)
        # Un segundo envío (doble clic, pestaña antigua) no la reactiva.
        self.client.post(url, {"action": "suspend"})
        self.player_user.refresh_from_db()
        self.assertFalse(self.player_user.is_active)
        self.client.post(url, {"action": "activate"})
        self.player_user.refresh_from_db()
        self.assertTrue(self.player_user.is_active)

    def test_cannot_suspend_yourself(self):
        self.client.post(reverse("backoffice:user_toggle_active", args=[self.staff.pk]), {"action": "suspend"})
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)


class InvitationJoinRedirectTests(TestCase):
    def test_expired_link_does_not_go_to_player_choice(self):
        captain = User.objects.create_user("capitan", password="pass-12345")
        club = create_club("Club A", "Sevilla", captain)
        invitation = Invitation.objects.create(club=club, created_by=captain, expires_at=timezone.now())
        self.client.force_login(User.objects.create_user("x", password="pass-12345"))
        response = self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertEqual(response.status_code, 410)


class ClubSuspensionTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user("capitan", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.staff = User.objects.create_user("staff", password="pass-12345", is_staff=True)

    def suspend(self, reason="Fotos inapropiadas repetidas"):
        self.client.force_login(self.staff)
        return self.client.post(reverse("backoffice:club_toggle_suspended", args=[self.club.public_id]), {"action": "suspend", "reason": reason})

    def test_staff_suspends_and_members_cannot_enter(self):
        self.suspend()
        self.club.refresh_from_db()
        self.assertTrue(self.club.is_suspended)
        self.assertEqual(self.club.suspension_reason, "Fotos inapropiadas repetidas")
        self.assertContains(self.client.get(reverse("backoffice:club_detail", args=[self.club.public_id])), "Reactivar club")

        self.client.force_login(self.captain)
        self.assertRedirects(self.client.get(reverse("list_players")), reverse("no_club"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("no_club")), "está suspendido")

    def test_member_of_another_club_keeps_access_to_it(self):
        other = create_club("Club B", "Huelva", self.captain)
        self.suspend()
        self.client.force_login(self.captain)
        response = self.client.get(reverse("list_players"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.club, other)

    def test_double_submit_does_not_undo_suspension(self):
        self.suspend()
        self.suspend()
        self.club.refresh_from_db()
        self.assertTrue(self.club.is_suspended)

    def test_reactivate(self):
        self.suspend()
        self.client.post(reverse("backoffice:club_toggle_suspended", args=[self.club.public_id]), {"action": "reactivate"})
        self.club.refresh_from_db()
        self.assertFalse(self.club.is_suspended)
        self.client.force_login(self.captain)
        self.assertEqual(self.client.get(reverse("list_players")).status_code, 200)

    def test_suspended_club_rejects_invitations(self):
        self.suspend()
        invitation = Invitation.objects.create(club=self.club, created_by=self.captain)
        newcomer = User.objects.create_user("nuevo", password="pass-12345")
        self.client.force_login(newcomer)
        self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertFalse(Membership.objects.filter(user=newcomer).exists())

    def test_only_staff(self):
        self.client.force_login(self.captain)
        response = self.client.post(reverse("backoffice:club_toggle_suspended", args=[self.club.public_id]), {"action": "suspend"})
        self.assertEqual(response.status_code, 404)
        self.club.refresh_from_db()
        self.assertFalse(self.club.is_suspended)
