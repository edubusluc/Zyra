"""
Freno a la fuerza bruta del inicio de sesión con contraseña, compartido por la web (``ThrottledLoginView``)
y por la API de la app (``api/views_auth.py``): así los dos cierran el paso igual y no pueden divergir.

Dos contadores en la caché compartida (``core/ratelimit.py``), que caducan a los ``LOGIN_LOCKOUT_SECONDS``:
fallos de una IP contra un usuario escrito y fallos contra una cuenta (da igual la IP o si se escribió usuario
o email, para el ataque repartido entre muchas IP). Un acierto los pone a cero.
"""
from django.contrib.auth import get_user_model

from . import ratelimit

# Tras LOGIN_MAX_FAILURES contraseñas erróneas seguidas para el mismo usuario desde la misma IP, se bloquea
# durante LOGIN_LOCKOUT_SECONDS.
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60
# Contador adicional por CUENTA (da igual la IP o si se escribió usuario o email): frena el ataque
# repartido entre muchas IP. Es más alto que el de IP para que no sea fácil dejar fuera a alguien.
LOGIN_MAX_FAILURES_PER_ACCOUNT = 30


def _ip_key(request, typed):
    """Clave de caché del contador de fallos: IP y usuario escrito."""
    return f"login-failures:{ratelimit.client_ip(request)}:{(typed or '').strip().lower()}"


def _account_key_for_pk(pk):
    """Clave del contador por cuenta de un usuario."""
    return f"login-failures-account:{pk}"


def _account_key(typed):
    """Clave del contador por cuenta: la persona que corresponde al usuario o email escrito (None si no existe)."""
    typed = (typed or "").strip()
    if not typed:
        return None
    users = get_user_model().objects
    user = users.filter(username__iexact=typed).first() or users.filter(email__iexact=typed).order_by("pk").first()
    return _account_key_for_pk(user.pk) if user else None


def is_locked(request, typed):
    """True si ``typed`` (usuario o email escrito) ya no admite más intentos desde esta IP o contra esa cuenta."""
    account_key = _account_key(typed)
    return (ratelimit.get_count(_ip_key(request, typed)) >= LOGIN_MAX_FAILURES
            or bool(account_key and ratelimit.get_count(account_key) >= LOGIN_MAX_FAILURES_PER_ACCOUNT))


def record_failure(request, typed):
    """Suma un fallo a los contadores de IP y de cuenta (caducan a los ``LOGIN_LOCKOUT_SECONDS``)."""
    ratelimit.add_hit(_ip_key(request, typed), LOGIN_LOCKOUT_SECONDS)
    account_key = _account_key(typed)
    if account_key:
        ratelimit.add_hit(account_key, LOGIN_LOCKOUT_SECONDS)


def record_success(request, typed, user):
    """Inicio de sesión correcto: pone a cero el contador de fallos de la IP y el de la cuenta."""
    ratelimit.clear(_ip_key(request, typed))
    ratelimit.clear(_account_key_for_pk(user.pk))
