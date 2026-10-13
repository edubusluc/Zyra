"""
Middleware que mide la carga de la web y apunta la actividad de los usuarios.

Las métricas se acumulan en memoria por minuto y se vuelcan a RequestMetric cada
FLUSH_EVERY segundos (o al cambiar de minuto), para no escribir en cada petición.
"""
import threading
import time

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.utils import timezone

from .models import DailyActivity, ErrorEvent, RequestMetric, UserActivity

# Cada cuánto se guarda la actividad de un mismo usuario.
ACTIVITY_EVERY = 60
# Cada cuánto se vuelcan a la base de datos las métricas acumuladas en memoria.
FLUSH_EVERY = 15
SLOW_MS = 1000
# Las peticiones de más de esto (y todas las de error 500) se anotan con su ruta en ErrorEvent,
# como mucho MAX_EVENTS_PER_MINUTE por minuto para que un fallo en cadena no llene la tabla.
SLOW_EVENT_MS = 3000
MAX_EVENTS_PER_MINUTE = 30

# Ficheros estáticos y subidos no cuentan como carga de la aplicación. (MEDIA_URL vale "/"
# si no está configurado, y eso dejaría fuera todas las peticiones.)
_IGNORED_PREFIXES = tuple(
    p for p in (settings.STATIC_URL, getattr(settings, "MEDIA_URL", ""), "/favicon") if p and p != "/"
)


class _Buffer:
    """Contadores del minuto en curso, en memoria de este proceso, para no escribir en cada petición."""

    def __init__(self):
        """Buffer vacío; el intervalo de volcado empieza a contar ahora."""
        self.lock = threading.Lock()
        self.reset(None)
        self.flushed_at = time.monotonic()

    def reset(self, minute):
        """Pone los contadores a cero para el minuto indicado."""
        self.minute = minute
        self.requests = self.errors = self.slow = self.total_ms = self.max_ms = 0

    def add(self, minute, ms, status):
        """
        Suma una petición (duración en ms y código de respuesta) al minuto en curso. Si ha
        cambiado el minuto o toca volcar, guarda lo acumulado fuera del cerrojo.
        """
        pending = None
        with self.lock:
            if self.minute is not None and minute != self.minute:
                pending = self._take()
            if self.minute is None:
                self.minute = minute
            self.requests += 1
            self.total_ms += ms
            self.max_ms = max(self.max_ms, ms)
            self.errors += status >= 500
            self.slow += ms >= SLOW_MS
            if pending is None and time.monotonic() - self.flushed_at >= FLUSH_EVERY:
                pending = self._take()
        if pending:
            _save(pending)

    def take(self):
        """Saca lo acumulado (con el cerrojo) y deja el buffer vacío."""
        with self.lock:
            return self._take()

    def _take(self):
        """Como take, sin cerrojo: devuelve los contadores (o None si no hay nada) y los reinicia."""
        data = None
        if self.minute is not None and self.requests:
            data = dict(minute=self.minute, requests=self.requests, errors=self.errors,
                        slow=self.slow, total_ms=self.total_ms, max_ms=self.max_ms)
        self.reset(None)
        self.flushed_at = time.monotonic()
        return data


_buffer = _Buffer()


def _save(data):
    """Suma los contadores a la fila de su minuto (varios procesos pueden escribir en la misma)."""
    minute = data.pop("minute")
    changes = dict(
        requests=F("requests") + data["requests"], errors=F("errors") + data["errors"],
        slow=F("slow") + data["slow"], total_ms=F("total_ms") + data["total_ms"],
        max_ms=Greatest(F("max_ms"), data["max_ms"]),
    )
    if RequestMetric.objects.filter(minute=minute).update(**changes):
        return
    try:
        with transaction.atomic():
            RequestMetric.objects.create(minute=minute, **data)
    except IntegrityError:
        RequestMetric.objects.filter(minute=minute).update(**changes)


def flush_metrics():
    """Vuelca ya lo acumulado. Lo usan los tests y la página de carga."""
    data = _buffer.take()
    if data:
        _save(data)


def activity_cache_key(user_id):
    """Clave de caché que limita a una escritura por usuario cada ACTIVITY_EVERY segundos."""
    return f"backoffice:seen:{user_id}"


class ActivityMiddleware:
    """
    Mide cada petición (tiempo y código de respuesta) y apunta la última actividad del
    usuario. Va al principio de MIDDLEWARE para medir la petición completa.
    """

    def __init__(self, get_response):
        """Guarda la siguiente capa de la cadena de middleware."""
        self.get_response = get_response

    def process_exception(self, request, exception):
        """Guarda la excepción de la vista para anotarla si la petición acaba en error 500."""
        request._zyra_exception = exception
        return None

    def __call__(self, request):
        """
        Atiende la petición y, salvo estáticos y ficheros subidos, suma su tiempo y código a
        las métricas, anota los errores y las lentas (ErrorEvent) y actualiza UserActivity
        (como mucho una vez por minuto y usuario) y DailyActivity (una vez al día). Con
        «Entrar como» no cuenta como actividad del usuario visto.
        """
        if request.path.startswith(_IGNORED_PREFIXES):
            return self.get_response(request)

        start = time.monotonic()
        response = self.get_response(request)
        ms = int((time.monotonic() - start) * 1000)
        now = timezone.now()

        try:
            _buffer.add(now.replace(second=0, microsecond=0), ms, response.status_code)
            user = getattr(request, "user", None)
            seen = (
                user is not None and user.is_authenticated and getattr(request, "impersonator", None) is None
            )
            if seen and cache.add(activity_cache_key(user.pk), 1, ACTIVITY_EVERY):
                UserActivity.objects.update_or_create(user=user, defaults={
                    "last_seen": now,
                    "last_path": request.path[:200],
                    "club": getattr(request, "club", None),
                })
            if seen:
                today = timezone.localdate()
                if cache.add(f"backoffice:day:{user.pk}:{today}", 1, 24 * 3600):
                    DailyActivity.objects.get_or_create(user=user, date=today)
            if response.status_code >= 500 or ms >= SLOW_EVENT_MS:
                _record_event(request, response.status_code, ms, user)
        except Exception:  # la medición nunca debe romper una página
            pass
        return response


def _record_event(request, status, ms, user):
    """Anota una petición de error 500 o muy lenta, con un tope por minuto para no llenar la tabla."""
    key = f"backoffice:events:{timezone.now():%Y%m%d%H%M}"
    cache.add(key, 0, 120)
    if cache.incr(key) > MAX_EVENTS_PER_MINUTE:
        return
    exc = getattr(request, "_zyra_exception", None)
    ErrorEvent.objects.create(
        path=request.path[:200], method=request.method[:10], status=status, duration_ms=ms,
        exception=(f"{type(exc).__name__}: {exc}" if exc else "")[:300],
        user=user if user is not None and user.is_authenticated and getattr(request, "impersonator", None) is None else None,
    )
