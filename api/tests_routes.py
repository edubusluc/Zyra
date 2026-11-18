"""Garantía de que ninguna ruta de la API queda sin proteger: cada una usa ``ApiView`` y las públicas se declaran aquí."""
from django.test import SimpleTestCase
from django.urls import get_resolver

from api.views_base import ApiView

# Rutas que no exigen token, con el motivo. Una ruta pública nueva se añade aquí a propósito.
PUBLIC_ROUTES = {
    "api_login": "aún no hay token: se obtiene aquí (freno de login compartido con la web)",
    "api_apple": "aún no hay token: se obtiene aquí con el identity_token de Apple (404 si no está configurado)",
    "api_not_found": "404 en JSON para lo desconocido",
}


def _api_patterns():
    """Patrones de ``api.urls`` colgados de ``/api/v1/``."""
    for pattern in get_resolver().url_patterns:
        if str(pattern.pattern) == "api/v1/":
            return pattern.url_patterns
    return []


class ApiRoutesAreProtectedTests(SimpleTestCase):
    """Toda ruta de la API pasa por la clase base y solo es pública si está declarada."""

    def test_there_are_api_routes(self):
        """La API está montada en /api/v1/."""
        self.assertTrue(_api_patterns())

    def test_every_route_uses_the_base_view(self):
        """Todas las vistas heredan de ``ApiView`` (CSRF, autenticación, límites y errores en un solo sitio)."""
        for pattern in _api_patterns():
            view_class = getattr(pattern.callback, "view_class", None)
            self.assertTrue(view_class and issubclass(view_class, ApiView), f"{pattern.name} no usa ApiView")

    def test_public_routes_are_declared(self):
        """Una vista es pública si y solo si está en ``PUBLIC_ROUTES``."""
        for pattern in _api_patterns():
            is_public = pattern.callback.view_class.public
            self.assertEqual(is_public, pattern.name in PUBLIC_ROUTES,
                             f"{pattern.name}: público={is_public}; decláralo en PUBLIC_ROUTES o protégelo")

    def test_declared_public_routes_still_exist(self):
        """La lista no arrastra rutas que ya no existen."""
        names = {pattern.name for pattern in _api_patterns()}
        self.assertEqual([n for n in PUBLIC_ROUTES if n not in names], [])
