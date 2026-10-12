"""
Enlace de baja de los correos mensuales: un token firmado con la SECRET_KEY que identifica a la
cuenta sin pedir sesión. No caduca (la baja debe funcionar aunque el correo sea antiguo) y solo
permite una cosa: desactivar los correos mensuales de esa cuenta.
"""
from django.contrib.auth import get_user_model
from django.core import signing
from django.urls import reverse

SALT = "zyra.monthly-report-unsubscribe"


def unsubscribe_token(user):
    """Token firmado que identifica a ``user`` en el enlace de baja."""
    return signing.dumps(user.pk, salt=SALT)


def unsubscribe_path(user):
    """Ruta (sin dominio) de la página de baja de ``user``."""
    return reverse("monthly_unsubscribe", args=[unsubscribe_token(user)])


def user_from_token(token):
    """La cuenta del token, o None si está manipulado o la cuenta ya no existe."""
    try:
        pk = signing.loads(token, salt=SALT)
    except signing.BadSignature:
        return None
    return get_user_model().objects.filter(pk=pk).first()
