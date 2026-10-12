"""Sitemap de las páginas públicas (las del club requieren iniciar sesión)."""
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils.translation import get_language

from .seo import language_url

# Páginas legales: solo en español (es el texto que vale legalmente).
SPANISH_ONLY = {"privacy", "terms", "cookies"}


class PublicPagesSitemap(Sitemap):
    """
    Portada, alta de club, inicio de sesión y páginas legales, con una entrada por idioma
    (``?lang=en``) y sus alternativas hreflang, x-default incluido.
    """

    i18n = True
    alternates = True
    x_default = True

    def items(self):
        """Nombres de URL de las páginas públicas."""
        return ["home", "register_club", "login", "privacy", "terms", "cookies"]

    def get_languages_for_item(self, item):
        """Las páginas legales solo existen en español; el resto, en todos los idiomas."""
        if item in SPANISH_ONLY:
            return [settings.LANGUAGE_CODE]
        return super().get_languages_for_item(item)

    def location(self, item):
        """Ruta de cada página en el idioma activo (el sitemap activa cada uno)."""
        return language_url(reverse(item), get_language())

    def priority(self, item):
        """La portada y el alta de club son las páginas que interesa posicionar."""
        return {"home": 1.0, "register_club": 0.8}.get(item, 0.3)

    def get_domain(self, site=None):
        """Dominio de SITE_URL (no usa django.contrib.sites)."""
        if settings.SITE_URL:
            return settings.SITE_URL.split("://", 1)[1]
        return super().get_domain(site)

    def get_protocol(self, protocol=None):
        """https en producción."""
        return "http" if settings.DEBUG and not settings.SITE_URL else "https"
