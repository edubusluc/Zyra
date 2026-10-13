"""Variables de plantilla del back-office: aviso de «Entrar como» y contadores del menú."""
import datetime

from django.core.cache import cache
from django.utils import timezone

from .impersonation import MAX_DURATION, SESSION_KEY


def impersonation(request):
    """Datos del modo «Entrar como» para la franja de aviso de la web (vacío si no está activo)."""
    impersonator = getattr(request, "impersonator", None)
    if impersonator is None:
        return {}
    data = request.session.get(SESSION_KEY, {})
    started = datetime.datetime.fromisoformat(data["started"]) if data.get("started") else timezone.now()
    return {
        "impersonator": impersonator,
        "impersonation_ends": started + MAX_DURATION,
    }


def menu_counters(request):
    """
    Contadores del menú del back-office (fotos sin validar, cuentas sin confirmar vencidas, procesos
    con error en 24 h, tareas de hoy), en caché 60 s. Solo se calculan dentro de /backoffice/.
    """
    if not request.path.startswith("/backoffice/"):
        return {}
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_staff:
        return {}
    counters = cache.get("backoffice:menu_counters")
    if counters is None:
        from .metrics import attention_counts
        counters = attention_counts()
        cache.set("backoffice:menu_counters", counters, 60)
    return {"bo_counters": counters}
