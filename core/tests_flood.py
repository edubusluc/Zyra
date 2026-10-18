"""Pruebas del freno general contra inundaciones de peticiones."""
from django.core.cache import caches
from django.test import TestCase, override_settings


@override_settings(RATE_LIMITS_ENABLED=True, FLOOD_LIMIT_GET_PER_MINUTE=3, FLOOD_LIMIT_POST_PER_MINUTE=2)
class FloodProtectionTests(TestCase):
    """El middleware responde 429 al pasar el límite por IP y no limita /healthz/."""

    def setUp(self):
        """Vacía los contadores de la caché en memoria."""
        caches["ratelimit"].clear()

    def test_get_flood_gets_429(self):
        """Pasado el límite de GET, la IP recibe 429 con Retry-After."""
        codes = [self.client.get("/robots.txt").status_code for _ in range(5)]
        self.assertEqual(codes[3:], [429, 429])
        self.assertNotIn(429, codes[:3])
        self.assertEqual(self.client.get("/robots.txt")["Retry-After"], "60")

    def test_post_has_lower_limit(self):
        """Los POST tienen su propio límite, más bajo."""
        codes = [self.client.post("/accounts/login/", {}).status_code for _ in range(4)]
        self.assertEqual(codes[2:], [429, 429])

    def test_healthz_exempt(self):
        """El monitor de caídas nunca se limita."""
        codes = {self.client.get("/healthz/").status_code for _ in range(10)}
        self.assertNotIn(429, codes)

    @override_settings(RATE_LIMITS_ENABLED=False)
    def test_disabled(self):
        """Con los límites desactivados no se limita nada."""
        codes = {self.client.get("/robots.txt").status_code for _ in range(10)}
        self.assertNotIn(429, codes)
