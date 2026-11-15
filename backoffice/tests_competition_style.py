"""Aspecto de las competiciones en el back-office: color y escudo en imagen que llegan al selector del alta de equipo."""
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.competition_picker import picker_entries
from core.competitions import COMPETITIONS, SNP
from core.models import CompetitionStyle
from core.test_images import image_bytes

User = get_user_model()
PASSWORD = "pass-12345"


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="zyra-test-media-"))
class CompetitionStyleTests(TestCase):
    """Solo el personal ajusta color y escudo; lo ajustado se ve en el selector."""

    def setUp(self):
        self.staff = User.objects.create_user(username="staff", email="staff@example.com", password=PASSWORD, is_staff=True)
        self.client.force_login(self.staff)

    def entry(self, code="snp"):
        return next(e for e in picker_entries(list(COMPETITIONS.values()), []) if e["code"] == code)

    def test_defaults_come_from_the_competition_sheet(self):
        page = self.client.get(reverse("backoffice:competition_list"))
        self.assertContains(page, "Series Nacionales de Pádel")
        self.assertEqual(self.entry()["color"], SNP.color)
        self.assertEqual(self.entry()["crest"], "")

    def test_staff_sets_color_and_crest(self):
        crest = SimpleUploadedFile("snp.png", image_bytes(fmt="PNG"), content_type="image/png")
        self.client.post(reverse("backoffice:competition_style_save", args=["snp"]), {"color": "#112233", "crest": crest})
        entry = self.entry()
        self.assertEqual(entry["color"], "#112233")
        self.assertTrue(entry["crest"])
        self.assertEqual(self.entry("lapi")["crest"], "")

    def test_invalid_color_is_rejected_and_default_color_is_stored_empty(self):
        url = reverse("backoffice:competition_style_save", args=["snp"])
        self.client.post(url, {"color": "rojo"})
        self.assertEqual(self.entry()["color"], SNP.color)
        self.client.post(url, {"color": SNP.color.lower()})
        self.assertEqual(CompetitionStyle.objects.get(code="snp").color, "")

    def test_remove_crest_and_reset_color(self):
        url = reverse("backoffice:competition_style_save", args=["snp"])
        crest = SimpleUploadedFile("snp.png", image_bytes(fmt="PNG"), content_type="image/png")
        self.client.post(url, {"color": "#112233", "crest": crest})
        self.client.post(url, {"reset_color": "on", "remove_crest": "on"})
        entry = self.entry()
        self.assertEqual((entry["color"], entry["crest"]), (SNP.color, ""))

    def test_unknown_competition_and_non_staff(self):
        self.assertEqual(self.client.post(reverse("backoffice:competition_style_save", args=["nope"])).status_code, 404)
        self.client.logout()
        user = User.objects.create_user(username="u", email="u@example.com", password=PASSWORD)
        self.client.force_login(user)
        self.assertNotEqual(self.client.get(reverse("backoffice:competition_list")).status_code, 200)
