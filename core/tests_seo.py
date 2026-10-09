import json
import re

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse


class PublicPagesTests(TestCase):
    """robots.txt, sitemap, páginas legales, metadatos al compartir y monitor de caídas."""

    def test_robots_txt_blocks_private_sections_and_points_to_sitemap(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertContains(response, "Disallow: /backoffice/")
        self.assertNotContains(response, "Disallow: /\n")
        self.assertContains(response, "Sitemap: http://testserver/sitemap.xml")

    @override_settings(SITE_URL="https://zyra.es", ALLOWED_HOSTS=["zyra.es"])
    def test_sitemap_lists_public_pages_on_site_url(self):
        response = self.client.get("/sitemap.xml", HTTP_HOST="zyra.es")
        self.assertContains(response, "<loc>https://zyra.es/privacidad/</loc>")
        self.assertContains(response, "<loc>https://zyra.es/core/login/</loc>")
        self.assertNotContains(response, "/players/")

    def test_legal_pages_are_public_and_linked_from_footer(self):
        for name in ("privacy", "terms", "cookies"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'href="{reverse(name)}"')
        self.assertContains(self.client.get(reverse("home")), 'href="mailto:')

    @override_settings(LEGAL_OWNER_NAME="Ana Pérez", LEGAL_OWNER_ID="12345678Z")
    def test_terms_show_owner_data(self):
        response = self.client.get(reverse("terms"))
        self.assertContains(response, "Ana Pérez")
        self.assertContains(response, "12345678Z")

    def test_landing_has_canonical_and_share_preview_and_no_noindex(self):
        response = self.client.get(reverse("home") + "?utm_source=x")
        self.assertContains(response, '<link rel="canonical" href="http://testserver/">')
        self.assertContains(response, 'property="og:image" content="http://testserver/static/zyra/icon-512.png"')
        self.assertNotContains(response, "noindex")
        self.assertNotContains(response, "fonts.googleapis.com")

    @override_settings(SITE_URL="https://zyra.es", ALLOWED_HOSTS=["zyra.es"])
    def test_sitemap_has_english_versions_with_hreflang_except_legal_pages(self):
        content = self.client.get("/sitemap.xml", HTTP_HOST="zyra.es").content.decode()
        self.assertIn("<loc>https://zyra.es/?lang=en</loc>", content)
        self.assertIn('hreflang="en" href="https://zyra.es/core/login/?lang=en"', content)
        self.assertIn('hreflang="x-default" href="https://zyra.es/"', content)
        self.assertNotIn("/privacidad/?lang=en", content)
        self.assertIn("<priority>1.0</priority>", content)

    def test_landing_has_hreflang_alternates(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, '<link rel="alternate" hreflang="es" href="http://testserver/">')
        self.assertContains(response, '<link rel="alternate" hreflang="en" href="http://testserver/?lang=en">')
        self.assertContains(response, '<link rel="alternate" hreflang="x-default" href="http://testserver/">')

    def test_lang_param_serves_english_with_own_canonical_and_remembers_it(self):
        response = self.client.get(reverse("home") + "?lang=en")
        self.assertContains(response, '<html lang="en"')
        self.assertContains(response, '<link rel="canonical" href="http://testserver/?lang=en">')
        self.assertContains(response, "Padel team management app")
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")
        # La siguiente página, sin parámetro, sigue en inglés por la cookie.
        self.assertContains(self.client.get(reverse("login")), '<html lang="en"')
        # El selector de idioma vuelve a la página sin ?lang= (si no, el parámetro mandaría).
        self.assertContains(response, '<input type="hidden" name="next" value="/">')

    def test_unknown_lang_param_is_ignored(self):
        response = self.client.get(reverse("home") + "?lang=xx")
        self.assertContains(response, '<html lang="es"')
        self.assertContains(response, '<link rel="canonical" href="http://testserver/">')
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, response.cookies)

    def test_legal_pages_are_spanish_only_for_search_engines(self):
        response = self.client.get(reverse("privacy") + "?lang=en")
        self.assertContains(response, '<link rel="canonical" href="http://testserver/privacidad/">')
        self.assertNotContains(response, "hreflang")

    def test_landing_structured_data_is_valid_json_ld(self):
        response = self.client.get(reverse("home"))
        match = re.search(r'<script type="application/ld\+json">(.*?)</script>', response.content.decode(), re.S)
        data = json.loads(match.group(1))
        types = {node["@type"] for node in data["@graph"]}
        self.assertEqual(types, {"Organization", "WebSite", "WebApplication", "FAQPage"})
        faq = next(node for node in data["@graph"] if node["@type"] == "FAQPage")
        # Las preguntas del JSON-LD son las que se ven en la página.
        for question in faq["mainEntity"]:
            self.assertContains(response, question["name"])

    @override_settings(CONTACT_EMAIL="x</script><script>alert(1)</script>@zyra.es")
    def test_structured_data_cannot_close_its_script_tag(self):
        content = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("<script>alert(1)", content)
        self.assertIn("x\\u003C/script\\u003E", content)

    def test_landing_has_one_h1_and_keyword_title(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.content.decode().count("<h1"), 1)
        self.assertContains(response, "<title>Zyra · App para gestionar equipos de pádel</title>", html=False)

    def test_healthz(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_public_endpoints_only_accept_get_and_head(self):
        for url in ("/healthz/", "/robots.txt", "/privacidad/"):
            self.assertEqual(self.client.head(url).status_code, 200)
            self.assertEqual(self.client.post(url).status_code, 405)


@override_settings(SITE_URL="https://zyra.es", ALLOWED_HOSTS=["zyra.es", "www.zyra.es"])
class CanonicalHostTests(TestCase):
    """Una sola versión del dominio: el resto redirige con 301 a SITE_URL."""

    def test_www_redirects_permanently_keeping_path_and_query(self):
        response = self.client.get("/core/login/?next=/match/", HTTP_HOST="www.zyra.es")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://zyra.es/core/login/?next=/match/")

    def test_canonical_host_is_served(self):
        response = self.client.get("/core/login/", HTTP_HOST="zyra.es", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<link rel="canonical" href="https://zyra.es/core/login/">')
