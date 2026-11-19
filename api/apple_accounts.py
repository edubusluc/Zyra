"""
Qué cuenta corresponde a una identidad de Apple ya verificada (``api.apple``): la enlazada, una existente con
el mismo email o una nueva. Nunca se enlaza ni se crea nada en silencio si el email no está demostrado.
"""
from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from core import email_verification
from core.blocklist import is_blocked

from .errors import ApiError
from .models import AppleIdentity

User = get_user_model()


def _invalid():
    """Error genérico: no distingue cuenta desactivada de cuenta inexistente."""
    return ApiError("invalid_apple_token", _("No se pudo iniciar sesión con Apple."), 401)


def resolve_user(claims, first_name="", last_name=""):
    """
    Cuenta de ``claims`` (resultado de ``verify_identity_token``). Orden: 1) la ya enlazada a ese ``sub`` (entra aunque
    cambie el email); 2) la que tenga ese email, solo si Apple lo verificó y la cuenta lo tenía verificado (si no,
    409 ``apple_account_unconfirmed``); 3) una cuenta nueva sin contraseña, con el email ya verificado. Un email
    bloqueado por el personal o una cuenta desactivada no entran.
    """
    identity = AppleIdentity.objects.select_related("user").filter(subject=claims["sub"]).first()
    if identity is not None:
        if not identity.user.is_active:
            raise _invalid()
        return identity.user
    email = claims["email"]
    if not email or not claims["email_verified"]:
        raise ApiError("apple_email_unverified", _("Apple no ha facilitado un email verificado."), 403)
    if is_blocked(email):
        raise ApiError("email_blocked", _("Este email no puede usarse en Zyra."), 403)
    try:
        with transaction.atomic():
            return _link_or_create(claims, email, first_name, last_name)
    except IntegrityError:
        # Dos peticiones a la vez con la misma identidad: gana la primera.
        return resolve_user(claims, first_name, last_name)


def _link_or_create(claims, email, first_name, last_name):
    """Enlaza ``claims["sub"]`` con la cuenta de ese email o crea una nueva (dentro de una transacción)."""
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = create_user(email, first_name, last_name)
    elif not user.is_active:
        raise _invalid()
    elif not email_verification.is_verified(user):
        raise ApiError("apple_account_unconfirmed", _(
            "Ya existe una cuenta con ese email sin confirmar. Confirma el email o usa «Olvidé mi contraseña»."), 409)
    AppleIdentity.objects.create(user=user, subject=claims["sub"])
    return user


def create_user(email, first_name, last_name, fallback="apple"):
    """Cuenta nueva sin contraseña (como las de Google) con el email verificado por el proveedor (Apple o Google)."""
    username = get_adapter().generate_unique_username([f"{first_name} {last_name}".strip(), email.split("@")[0], fallback])
    user = User(username=username, email=email, first_name=first_name[:150], last_name=last_name[:150])
    user.set_unusable_password()
    user.save()
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user
