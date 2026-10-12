"""
Verificación del email de las cuentas.

Quien se registra con usuario y contraseña recibe un enlace de confirmación (el de allauth).
Mientras el email no está verificado, entrar con Google con ese mismo email no conecta con la
cuenta sin más (``core.adapters.SocialAccountAdapter.authenticate_by_email``): así nadie puede
reservar el email de otra persona y quedarse con su cuenta cuando ella entre con Google.
"""
import logging

from allauth.account.models import EmailAddress

logger = logging.getLogger(__name__)


def is_verified(user):
    """True si el email actual de ``user`` está verificado."""
    return bool(user.email) and EmailAddress.objects.filter(
        user=user, email__iexact=user.email, verified=True
    ).exists()


def start_verification(request, user, *, verified=False):
    """
    Deja registrado el email de ``user`` en allauth como el principal. Con ``verified`` ya
    queda verificado (el usuario lo ha demostrado, p. ej. abriendo el enlace de una invitación
    enviada a ese email); si no, se le manda el enlace de confirmación. Un fallo al enviar el
    correo no interrumpe el registro: se anota y el usuario puede pedir otro desde «Mi perfil».
    Devuelve True si se ha enviado el correo.
    """
    email = (user.email or "").strip().lower()
    if not email:
        return False
    EmailAddress.objects.filter(user=user, primary=True).exclude(email__iexact=email).update(primary=False)
    address = EmailAddress.objects.filter(user=user, email__iexact=email).first()
    if address is None:
        address = EmailAddress.objects.create(user=user, email=email, verified=verified, primary=True)
    elif verified and not address.verified:
        address.verified = True
        address.save(update_fields=["verified"])
    if address.verified:
        return False
    try:
        address.send_confirmation(request)
    except Exception:
        logger.exception("No se pudo enviar el correo de confirmación a la cuenta %s", user.pk)
        return False
    return True


def unverified_users():
    """
    Cuentas con email que aún no lo han confirmado (sin contar al personal): quien se registró
    con usuario y contraseña y nunca abrió el enlace. Las de Google nacen verificadas.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Exists, OuterRef

    verified = EmailAddress.objects.filter(user=OuterRef("pk"), verified=True, email__iexact=OuterRef("email"))
    return (
        get_user_model().objects.exclude(email="").filter(is_staff=False, is_superuser=False)
        .exclude(Exists(verified)).order_by("date_joined")
    )


def confirmation_url(request, user):
    """
    Enlace absoluto para confirmar el email actual de ``user`` (registra la dirección en allauth
    si faltaba, como en las cuentas anteriores a la verificación). None si ya está verificado.
    """
    from allauth.account.adapter import get_adapter
    from allauth.account.models import EmailConfirmationHMAC

    email = user.email.strip().lower()
    address = EmailAddress.objects.filter(user=user, email__iexact=email).first()
    if address is None:
        EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
        address = EmailAddress.objects.create(user=user, email=email, verified=False, primary=True)
    if address.verified:
        return None
    return get_adapter(request).get_email_confirmation_url(request, EmailConfirmationHMAC(address))
