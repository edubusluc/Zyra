"""
Protección contra el doble clic: todo formulario POST de la web lleva el texto de su acción.

El bloqueo en sí lo hace ``static/js/submit-lock.js`` (cargado desde ``base.html`` y desde el
base del back-office) en cualquier formulario POST; estas pruebas comprueban lo que se puede
verificar sin navegador: que cada formulario declara su texto de carga (o se excluye a
propósito), que ese texto está traducido y que las dos plantillas base cargan el script.
"""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from core.services import create_club

User = get_user_model()

ROOT = Path(settings.BASE_DIR)
FORM_TAG = re.compile(r"<form\b[^>]*>", re.IGNORECASE | re.DOTALL)
LOADING_TEXT = re.compile(r"""data-loading-text="\{% translate '([^']+)' %\}\"""")


def templates():
    """Plantillas HTML de las apps (sin la documentación ni las librerías)."""
    for path in ROOT.glob("*/templates/**/*.html"):
        yield path, path.read_text(encoding="utf-8")


def post_forms():
    """(plantilla, etiqueta <form>) de cada formulario que no es de consulta (GET)."""
    for path, html in templates():
        for tag in FORM_TAG.findall(html):
            if not re.search(r"""method=["']get["']""", tag, re.IGNORECASE):
                yield path, tag


class SubmitLockTemplatesTests(SimpleTestCase):
    def test_every_post_form_declares_its_loading_text(self):
        missing = [f"{path.relative_to(ROOT)}: {tag[:90]}" for path, tag in post_forms()
                   if "data-loading-text" not in tag and "data-no-submit-lock" not in tag]
        self.assertEqual(missing, [], "Formularios POST sin data-loading-text (ni data-no-submit-lock)")

    def test_loading_texts_are_translated_to_english(self):
        texts = {m for _, tag in post_forms() for m in LOADING_TEXT.findall(tag)}
        texts |= {m for path, html in templates() for m in LOADING_TEXT.findall(html)}
        self.assertTrue(texts)
        with translation.override("en"):
            untranslated = sorted(t for t in texts if translation.gettext(t) == t)
        self.assertEqual(untranslated, [])

    def test_default_text_is_translated_in_the_js_catalog(self):
        po = (ROOT / "locale/en/LC_MESSAGES/djangojs.po").read_text(encoding="utf-8")
        self.assertIn('msgid "Procesando…"', po)

    def test_both_base_templates_load_the_script(self):
        for base in ("core/templates/base.html", "backoffice/templates/backoffice/base.html"):
            self.assertIn("js/submit-lock.js", (ROOT / base).read_text(encoding="utf-8"), base)


class SubmitLockRenderedTests(TestCase):
    """Las páginas que ve el usuario sirven el script y los textos en su idioma."""

    def setUp(self):
        user = User.objects.create_user("capi", password="pass-12345")
        create_club("Club A", "Sevilla", user)
        self.client.login(username="capi", password="pass-12345")

    def test_logout_and_language_forms_carry_text_in_both_languages(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "js/submit-lock.js")
        self.assertContains(response, 'data-loading-text="Cerrando sesión…"')
        self.client.post(reverse("set_language"), {"language": "en", "next": "/"})
        self.assertContains(self.client.get(reverse("home")), 'data-loading-text="Logging out…"')

    def test_create_match_form_names_its_action(self):
        response = self.client.get(reverse("create_match"))
        self.assertContains(response, 'data-loading-text="Creando el enfrentamiento…"')
