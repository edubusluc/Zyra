"""
Qué cuenta corresponde a una identidad de Google ya verificada (``api.google``): la enlazada, una existente con el
mismo email o una nueva. La identidad es la misma que usa la web (``allauth.SocialAccount``, proveedor ``google``), así
que una cuenta creada desde la app entra también con Google en la web y al revés. El email lo ha verificado Google; sin eso
no se enlaza ni se crea nada.
"""
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from core.adapters import claim_account, find_account_by_email
from core.blocklist import is_blocked

from .apple_accounts import create_user
from .errors import ApiError

User = get_user_model()
PROVIDER = "google"


def _invalid():
    """Error genérico: no distingue cuenta desactivada de cuenta inexistente."""
    return ApiError("invalid_google_token", _("No se pudo iniciar sesión con Google."), 401)


def resolve_user(claims):
    """
    Cuenta de ``claims`` (resultado de ``verify_id_token``). Orden: 1) la ya enlazada a ese ``sub`` (entra aunque cambie
    el email); 2) la que tenga ese email (Google lo verificó), igual que en la web: si la cuenta no lo tenía
    verificado, se anula su contraseña y se borran sus otros emails y conexiones (``core.adapters.claim_account``); 3) una cuenta nueva sin contraseña, con el email ya verificado. Un email bloqueado
    por el personal o una cuenta desactivada no entran.
    """
    linked = SocialAccount.objects.select_related("user").filter(provider=PROVIDER, uid=claims["sub"]).first()
    if linked is not None:
        if not linked.user.is_active:
            raise _invalid()
        return linked.user
    email = claims["email"]
    if not email or not claims["email_verified"]:
        raise ApiError("google_email_unverified", _("Google no ha facilitado un email verificado."), 403)
    if is_blocked(email):
        raise ApiError("email_blocked", _("Este email no puede usarse en Zyra."), 403)
    try:
        with transaction.atomic():
            return _link_or_create(claims, email)
    except IntegrityError:
        # Dos peticiones a la vez con la misma identidad: gana la primera.
        return resolve_user(claims)


def _link_or_create(claims, email):
    """Enlaza ``claims["sub"]`` con la cuenta de ese email o crea una nueva (dentro de una transacción)."""
    user = find_account_by_email(email)
    if user is None:
        if User.objects.filter(email__iexact=email).exists():
            raise _invalid()  # solo hay cuentas desactivadas con ese email
        user = create_user(email, claims["first_name"], claims["last_name"], fallback="google")
    else:
        claim_account(user, email)
    SocialAccount.objects.create(user=user, provider=PROVIDER, uid=claims["sub"], extra_data={"email": email})
    return user
