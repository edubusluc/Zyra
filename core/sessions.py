"""
Duración de las sesiones, como en Amazon: la sesión se mantiene mientras se use la cuenta. Dura un año
desde la última visita (``SESSION_SAVE_EVERY_REQUEST`` la renueva en cada petición), tanto con «Mantener la sesión
iniciada» como con Google; quien desmarca la casilla la pierde al cerrar el navegador y el personal de Zyra
(``is_staff``) solo tiene 12 horas. Cambiar el email o la contraseña sigue pidiendo la contraseña actual. «Cerrar sesión en todos los
dispositivos» (Mi perfil) borra las demás sesiones de la cuenta.
"""
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.utils import timezone

REMEMBER_SESSION_AGE = 60 * 60 * 24 * 365
STAFF_SESSION_AGE = 60 * 60 * 12


def apply_login_expiry(request, user, remember):
    """
    Fija la duración de la sesión recién creada de ``user``: 12 h si es del personal, 30 días con
    «Mantener la sesión iniciada» y hasta cerrar el navegador sin ella.
    """
    if user.is_staff or user.is_superuser:
        request.session.set_expiry(STAFF_SESSION_AGE)
    elif remember:
        request.session.set_expiry(REMEMBER_SESSION_AGE)
    else:
        request.session.set_expiry(0)


def limit_staff_session(sender, request, user, **kwargs):
    """Señal ``user_logged_in``: sea cual sea el método (Google incluido), el personal no pasa de 12 horas."""
    if request is not None and (user.is_staff or user.is_superuser):
        request.session.set_expiry(STAFF_SESSION_AGE)


def end_other_sessions(user, keep_key):
    """Borra las sesiones activas de ``user`` salvo la de ``keep_key``. Devuelve cuántas cerró."""
    closed = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).exclude(session_key=keep_key).iterator():
        if session.get_decoded().get(SESSION_KEY) == str(user.pk):
            session.delete()
            closed += 1
    return closed
