"""Tests de la configuración de despliegue: estáticos con manifiesto y remitente de la plataforma."""
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.storage import TolerantManifestStaticFilesStorage


class TolerantStorageTests(SimpleTestCase):
    """El almacenamiento de producción no aborta por referencias rotas de librerías de terceros."""

    def test_css_con_referencia_inexistente_no_falla(self):
        """Un CSS que cita una fuente que no existe se procesa y la referencia queda como estaba."""
        with tempfile.TemporaryDirectory() as root:
            static = Path(root, "src")
            static.mkdir()
            (static / "a.css").write_text("@font-face{src:url(b.ttf)}", encoding="utf-8")
            with override_settings(STATIC_ROOT=Path(root, "out"), STATIC_URL="/static/"):
                storage = TolerantManifestStaticFilesStorage(location=Path(root, "out"))
                (Path(root, "out")).mkdir()
                (Path(root, "out") / "a.css").write_text((static / "a.css").read_text(), encoding="utf-8")
                results = list(storage.post_process({"a.css": (storage, "a.css")}, dry_run=False))
        self.assertFalse(any(isinstance(r[2], Exception) for r in results))


class ContactEmailTests(TestCase):
    """El correo de contacto que ve el usuario sale de CONTACT_EMAIL, no del remitente técnico."""

    @override_settings(CONTACT_EMAIL="contacto@ejemplo.com")
    def test_pie_usa_contact_email(self):
        """La página legal muestra el correo de contacto configurado."""
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "contacto@ejemplo.com")
