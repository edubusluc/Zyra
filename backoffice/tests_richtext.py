"""Pruebas del saneado del HTML de «Escribir al capitán»."""
from django.test import SimpleTestCase

from .richtext import html_to_text, sanitize_html


class SanitizeHtmlTests(SimpleTestCase):
    def test_keeps_whitelisted_formatting(self):
        html = sanitize_html("<h1>Hola</h1><p>Un <b>texto</b> y <i>otro</i></p><ul><li>uno</li></ul>")
        for fragment in ("<h2", "Hola</h2>", "<strong>texto</strong>", "<em>otro</em>", "<ul", "<li>uno</li>"):
            self.assertIn(fragment, html)

    def test_strips_scripts_handlers_and_unsafe_links(self):
        html = sanitize_html('<p onclick="x()">a</p><script>alert(1)</script><a href="javascript:alert(1)">mal</a>'
                             '<img src=x onerror=alert(1)><a href="https://zyra.app" target="_blank" onclick="y()">bien</a>')
        self.assertNotIn("script", html)
        self.assertNotIn("alert", html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("javascript", html)
        self.assertNotIn("<img", html)
        self.assertIn('<a href="https://zyra.app"', html)
        self.assertIn("mal", html)

    def test_plain_text_becomes_escaped_paragraphs(self):
        html = sanitize_html("Hola & adiós\nlínea 2\n\nOtro párrafo")
        self.assertEqual(html.count("<p"), 2)
        self.assertIn("Hola &amp; adiós<br>línea 2", html)

    def test_unbalanced_tags_are_closed(self):
        html = sanitize_html("<p>uno <strong>dos")
        self.assertTrue(html.endswith("</strong></p>"))

    def test_plain_text_alternative(self):
        text = html_to_text(sanitize_html('<h2>Título</h2><p>Hola <b>mundo</b></p><ul><li>a</li><li>b</li></ul><p><a href="https://x.es">web</a></p>'))
        self.assertIn("Título", text)
        self.assertIn("Hola mundo", text)
        self.assertIn("- a", text)
        self.assertIn("web (https://x.es)", text)
        self.assertNotIn("<", text)
