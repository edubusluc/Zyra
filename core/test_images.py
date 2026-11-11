from core.testing import TeamClient
import shutil
import tempfile
from io import BytesIO, StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from core.services import create_club
from players.models import Player
from team.models import Team

User = get_user_model()


def image_bytes(size=(2000, 1000), fmt="JPEG", mode="RGB", exif_orientation=None):
    img = Image.new(mode, size, "red" if mode == "RGB" else (255, 0, 0, 0))
    out = BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()


class MediaTestCase(TestCase):
    """Cada prueba guarda las fotos en una carpeta temporal en lugar de media/."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user, gender="F", country="ES", division="500")
        self.client.force_login(self.user)

    def stored(self, name):
        return Path(self.media, name)


class PhotoUploadTests(MediaTestCase):
    client_class = TeamClient

    team_data = {"name": "Burguillos", "location": "X", "gender": "M", "country": "ES", "division": "500"}

    def create_team(self, content, filename="escudo.jpg"):
        return self.client.post(reverse("create_team"), {
            **self.team_data, "photo": SimpleUploadedFile(filename, content, content_type="image/jpeg"),
        })

    def test_team_photo_is_resized_to_webp_in_media(self):
        response = self.create_team(image_bytes((2000, 1000)))
        self.assertRedirects(response, reverse("list_teams"), fetch_redirect_response=False)
        team = Team.objects.get(name="Burguillos")
        self.assertRegex(team.photo.name, r"^teams/[0-9a-f]{32}\.webp$")
        self.assertEqual(team.photo.url, f"/media/{team.photo.name}")
        with Image.open(self.stored(team.photo.name)) as img:
            self.assertEqual((img.format, img.size), ("WEBP", (512, 256)))
            self.assertNotIn("exif", img.info)

    def test_small_image_is_not_enlarged_and_keeps_transparency(self):
        self.create_team(image_bytes((100, 80), fmt="PNG", mode="RGBA"), "escudo.png")
        with Image.open(self.stored(Team.objects.get(name="Burguillos").photo.name)) as img:
            self.assertEqual((img.size, img.mode), ((100, 80), "RGBA"))

    def test_phone_photo_is_rotated_with_exif_orientation(self):
        # Orientación 6: la cámara la guardó tumbada; se ve girada 90º.
        self.create_team(image_bytes((1000, 500), exif_orientation=6))
        with Image.open(self.stored(Team.objects.get(name="Burguillos").photo.name)) as img:
            self.assertEqual(img.size, (256, 512))

    def test_not_an_image_is_rejected(self):
        response = self.create_team(b"esto no es una imagen", "escudo.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["photo"])
        self.assertFalse(Team.objects.filter(name="Burguillos").exists())

    @override_settings(PHOTO_MAX_UPLOAD_MB=0)
    def test_too_big_file_is_rejected(self):
        response = self.create_team(image_bytes((10, 10)))
        self.assertIn("demasiado", str(response.context["form"].errors["photo"]))

    def test_player_photo_goes_to_players_folder(self):
        self.client.post(reverse("create_player"), {
            "name": "Ana", "last_name": "Ruiz", "position": "Derecha", "skillfull_hand": "Diestro",
            "photo": SimpleUploadedFile("ana.jpg", image_bytes((800, 800)), content_type="image/jpeg"),
        })
        player = Player.objects.get(name="Ana")
        self.assertRegex(player.photo.name, r"^players/[0-9a-f]{32}\.webp$")
        self.assertTrue(self.stored(player.photo.name).is_file())

    def test_replacing_photo_deletes_old_file(self):
        self.create_team(image_bytes())
        team = Team.objects.get(name="Burguillos")
        old = self.stored(team.photo.name)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("edit_team", args=[team.public_id]), {
                **self.team_data, "photo": SimpleUploadedFile("nuevo.jpg", image_bytes(), content_type="image/jpeg"),
            })
        team.refresh_from_db()
        self.assertFalse(old.exists())
        self.assertTrue(self.stored(team.photo.name).is_file())

    def test_editing_without_new_photo_keeps_it(self):
        self.create_team(image_bytes())
        team = Team.objects.get(name="Burguillos")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("edit_team", args=[team.public_id]), {**self.team_data, "location": "Y"})
        team.refresh_from_db()
        self.assertEqual(team.location, "Y")
        self.assertTrue(self.stored(team.photo.name).is_file())

    def test_deleting_team_deletes_photo_unless_shared(self):
        self.create_team(image_bytes())
        team = Team.objects.get(name="Burguillos")
        other = Team.objects.create(club=self.club, name="Otro", location="X", photo=team.photo.name)
        path = self.stored(team.photo.name)
        with self.captureOnCommitCallbacks(execute=True):
            team.delete()
        self.assertTrue(path.exists())  # aún la usa `other`
        with self.captureOnCommitCallbacks(execute=True):
            other.delete()
        self.assertFalse(path.exists())


class MovePhotosToMediaTests(MediaTestCase):
    def setUp(self):
        super().setUp()
        # Simula el proyecto antiguo: fotos dentro de <BASE_DIR>/static/team.
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        (self.base / "static" / "team").mkdir(parents=True)
        (self.base / "static" / "team" / "logo.png").write_bytes(image_bytes((1200, 1200), fmt="PNG"))
        override = override_settings(BASE_DIR=self.base, STATICFILES_DIRS=[self.base / "static"])
        override.enable()
        self.addCleanup(override.disable)
        self.team = Team.objects.create(club=self.club, name="Viejo", location="X", photo="static/team/logo.png")
        self.missing = Team.objects.create(club=self.club, name="Sin fichero", location="X", photo="static/team/no.png")

    def run_command(self, *args):
        out = StringIO()
        call_command("move_photos_to_media", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        output = self.run_command("--dry-run")
        self.assertIn("Se movería static/team/logo.png", output)
        self.team.refresh_from_db()
        self.assertEqual(self.team.photo.name, "static/team/logo.png")
        self.assertTrue((self.base / "static/team/logo.png").exists())

    def test_moves_photo_to_media_and_fixes_db(self):
        output = self.run_command()
        self.team.refresh_from_db()
        self.assertRegex(self.team.photo.name, r"^teams/[0-9a-f]{32}\.webp$")
        with Image.open(self.stored(self.team.photo.name)) as img:
            self.assertEqual(img.size, (512, 512))
        self.assertFalse((self.base / "static/team/logo.png").exists())
        # La que no tiene fichero se deja igual y se avisa.
        self.missing.refresh_from_db()
        self.assertEqual(self.missing.photo.name, "static/team/no.png")
        self.assertIn("No se encuentra static/team/no.png", output)
        # Se puede volver a ejecutar sin efecto.
        self.assertIn("Fotos movidas: 0", self.run_command())

    def test_keep_originals(self):
        self.run_command("--keep-originals")
        self.assertTrue((self.base / "static/team/logo.png").exists())

    def test_sample_photos_outside_static_are_copied_not_deleted(self):
        (self.base / "populate").mkdir()
        (self.base / "populate" / "a.jpg").write_bytes(image_bytes())
        team = Team.objects.create(club=self.club, name="Ejemplo", location="X", photo="populate/a.jpg")
        self.run_command()
        team.refresh_from_db()
        self.assertTrue(team.photo.name.startswith("teams/"))
        self.assertTrue((self.base / "populate" / "a.jpg").exists())

    def test_path_outside_project_is_ignored(self):
        Team.objects.create(club=self.club, name="Fuera", location="X", photo="../../etc/passwd")
        self.assertIn("No se encuentra ../../etc/passwd", self.run_command())
