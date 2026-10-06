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

    def test_healthz(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")


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
