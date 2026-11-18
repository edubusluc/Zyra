"""
Límites de uso de la API por token (o por IP en lo que aún no tiene token), con la caché en memoria de
cada proceso (``caches["ratelimit"]``, la del freno general): no escribe en la base de datos en cada
petición. Con N procesos de gunicorn el límite efectivo llega a N veces el configurado. Si la caché
falla, deja pasar (mejor que tumbar la API). Con ``RATE_LIMITS_ENABLED`` apagado (tests) nunca limita.
"""
import logging

from django.conf import settings
from django.core.cache import caches

logger = logging.getLogger(__name__)
WINDOW_SECONDS = 60


def _key(scope, ident):
    """Clave de caché de un ``scope`` («token», «authfail»…) y un identificador."""
    return f"api:{scope}:{ident}"


def count(scope, ident):
    """Veces apuntadas en este minuto (0 si no hay o la caché falla)."""
    if not settings.RATE_LIMITS_ENABLED:
        return 0
    try:
        return caches["ratelimit"].get(_key(scope, ident), 0)
    except Exception:
        logger.exception("Caché no disponible: límite de la API desactivado")
        return 0


def hit(scope, ident):
    """Suma una petición al minuto en curso y devuelve el total (0 si no se cuenta)."""
    if not settings.RATE_LIMITS_ENABLED:
        return 0
    key = _key(scope, ident)
    try:
        cache = caches["ratelimit"]
        cache.add(key, 0, WINDOW_SECONDS)
        try:
            return cache.incr(key)
        except ValueError:
            cache.set(key, 1, WINDOW_SECONDS)
            return 1
    except Exception:
        logger.exception("Caché no disponible: límite de la API desactivado")
        return 0
