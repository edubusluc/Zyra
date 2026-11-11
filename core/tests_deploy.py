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


class ProductionImageTests(SimpleTestCase):
    """La imagen, el despliegue y los scripts peligrosos no dejan puertas abiertas en producción."""

    root = Path(__file__).resolve().parent.parent

    def _read(self, name):
        """Devuelve el texto de un fichero del repositorio."""
        return (self.root / name).read_text(encoding="utf-8")

    def test_clear_database_se_niega_en_produccion(self):
        """Con DEBUG apagado el script que vacía la base sale con error, salvo permiso explícito."""
        import clear_database

        with override_settings(DEBUG=False), self.assertRaises(SystemExit):
            clear_database.refuse_in_production()
        with override_settings(DEBUG=True):
            clear_database.refuse_in_production()

    def test_clear_database_fuera_de_la_imagen(self):
        """`.dockerignore` deja fuera `clear_database.py` y el Dockerfile no lo copia."""
        self.assertIn("clear_database.py", self._read(".dockerignore").splitlines())
        self.assertNotIn("clear_database", self._read("Dockerfile"))

    def test_imagenes_base_fijadas_por_digest(self):
        """Python, PostgreSQL y Caddy se descargan por digest, no por etiqueta móvil."""
        self.assertRegex(self._read("Dockerfile"), r"FROM python:[\w.-]+@sha256:[0-9a-f]{64} AS base")
        compose = self._read("docker-compose.yml")
        for image in ("postgres:16", "caddy:2"):
            self.assertRegex(compose, rf"image: {image}@sha256:[0-9a-f]{{64}}")

    def test_chromium_solo_en_el_lanzador(self):
        """La instalación de Chromium está en la etapa `scheduler`, no en la base común ni en la web."""
        dockerfile = self._read("Dockerfile")
        base, rest = dockerfile.split("FROM base AS scheduler")
        scheduler, web = rest.split("FROM base AS web")
        self.assertNotIn("playwright install", base + web)
        self.assertIn("playwright install", scheduler)

    def test_despliegue_espera_tests_y_fija_la_huella(self):
        """El despliegue depende de los tests, usa un known_hosts fijo y no acepta huellas nuevas."""
        deploy = self._read(".github/workflows/deploy.yml")
        self.assertIn("needs: [image, tests]", deploy)
        self.assertNotIn("accept-new", deploy)
        self.assertIn("DEPLOY_KNOWN_HOSTS", deploy)
        self.assertNotIn("zyra@", deploy)

    def test_acciones_de_los_workflows_fijadas_por_sha(self):
        """Ninguna acción de terceros se referencia por etiqueta (`@v4`), solo por SHA."""
        for name in ("tests.yml", "deploy.yml"):
            for line in self._read(f".github/workflows/{name}").splitlines():
                if "uses:" in line and "./.github" not in line:
                    self.assertRegex(line, r"@[0-9a-f]{40}\b", line)

    def test_deploy_sh_conserva_la_version_anterior(self):
        """El script no borra todas las imágenes: conserva la versión anterior para volver atrás."""
        script = self._read("deploy/deploy.sh")
        self.assertNotIn("prune -af", script)
        self.assertIn(".previous", script)
