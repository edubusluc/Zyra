"""
Límites de uso por IP contra el abuso (registro en masa, fuerza bruta) con la caché de Django.

En producción la caché es compartida entre procesos (``CACHES`` en zyra/settings.py), así que
el límite vale lo mismo con uno que con veinte procesos de gunicorn. Si la caché falla (por
ejemplo, falta la tabla ``django_cache``), los límites se desactivan y se anota el error: es
mejor dejar pasar a un visitante que dejar a todos sin poder entrar.
"""
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def client_ip(request):
    """
    IP del visitante. Detrás de un proxy de confianza (``TRUSTED_PROXY_COUNT`` > 0) es la que
    ese proxy añadió a ``X-Forwarded-For``: se cuenta desde la derecha porque lo de la izquierda
    lo puede escribir cualquiera. Sin proxy, la dirección de la conexión.
    """
    count = settings.TRUSTED_PROXY_COUNT
    if count > 0:
        parts = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
        if len(parts) >= count:
            return parts[-count]
    return request.META.get("REMOTE_ADDR", "")


def get_count(key):
    """Veces apuntadas en ``key`` (0 si no hay o la caché falla)."""
    try:
        return cache.get(key, 0)
    except Exception:
        logger.exception("Caché no disponible: límite de uso desactivado")
        return 0


def add_hit(key, window):
    """Suma una al contador ``key`` (que caduca a los ``window`` segundos) y devuelve el total."""
    try:
        cache.add(key, 0, window)
        try:
            return cache.incr(key)
        except ValueError:
            cache.set(key, 1, window)
            return 1
    except Exception:
        logger.exception("Caché no disponible: límite de uso desactivado")
        return 0


def clear(key):
    """Pone a cero el contador ``key``."""
    try:
        cache.delete(key)
    except Exception:
        logger.exception("Caché no disponible al borrar un límite de uso")


def too_many(request, scope, limit, window):
    """
    Apunta una petición de ``scope`` desde la IP del visitante y devuelve True si ya ha pasado
    de ``limit`` en los últimos ``window`` segundos. Con ``RATE_LIMITS_ENABLED`` desactivado
    (los tests) nunca limita.
    """
    if not settings.RATE_LIMITS_ENABLED:
        return False
    return add_hit(f"rl:{scope}:{client_ip(request)}", window) > limit


def too_many_user(request, scope, limit, window):
    """
    Como ``too_many`` pero por usuario con sesión (o por IP si no la hay): para los endpoints
    caros (PDF, reenvío de informes), donde varios usuarios tras la misma IP no deben pisarse.
    """
    if not settings.RATE_LIMITS_ENABLED:
        return False
    who = request.user.pk if getattr(request, "user", None) and request.user.is_authenticated else client_ip(request)
    return add_hit(f"rl:{scope}:u:{who}", window) > limit
