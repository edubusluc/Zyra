"""Sitemap de las páginas públicas (las del club requieren iniciar sesión)."""
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class PublicPagesSitemap(Sitemap):
    """Portada, alta de club, inicio de sesión y páginas legales."""

    def items(self):
        """Nombres de URL de las páginas públicas."""
        return ["home", "register_club", "login", "privacy", "terms", "cookies"]

    def location(self, item):
        """Ruta de cada página."""
        return reverse(item)

    def get_domain(self, site=None):
        """Dominio de SITE_URL (no usa django.contrib.sites)."""
        if settings.SITE_URL:
            return settings.SITE_URL.split("://", 1)[1]
        return super().get_domain(site)

    def get_protocol(self, protocol=None):
        """https en producción."""
        return "http" if settings.DEBUG and not settings.SITE_URL else "https"
