"""
Rutas de django-allauth que Zyra expone bajo ``/accounts/``.

En lugar de ``include('allauth.urls')`` (que activa todas las páginas de allauth) se
incluyen solo las que Zyra usa. Las demás, sobre todo ``/accounts/email/`` (cambiar el email
sin pedir la contraseña, que sí pide «Mi perfil») y ``/accounts/3rdparty/`` (conexiones
sociales), no existen o redirigen a «Mi perfil».

Para permitir otra ruta de allauth hay que añadir su nombre a ``APPROVED_NAMES``; el test
``core/tests_allauth_urls.py`` falla si aparece una ruta que no esté aprobada.
"""
from allauth.account import urls as account_urls
from allauth.socialaccount import urls as social_urls
from allauth.socialaccount.providers.google import urls as google_urls
from django.conf import settings
from django.http import Http404
from django.urls import URLPattern, URLResolver, include, path
from django.views.generic.base import RedirectView

# Nombres de las rutas de allauth que Zyra necesita (inicio y cierre de sesión, contraseñas,
# confirmación de email, errores del inicio de sesión con Google y el propio Google).
APPROVED_NAMES = frozenset({
    "account_login", "account_logout", "account_inactive", "account_signup",
    "account_reauthenticate", "account_email_verification_sent", "account_confirm_email",
    "account_change_password", "account_set_password", "account_reset_password",
    "account_reset_password_done", "account_reset_password_from_key",
    "account_reset_password_from_key_done",
    "socialaccount_login_cancelled", "socialaccount_login_error", "socialaccount_signup",
    "google_login", "google_callback",
})

# Rutas retiradas que siguen respondiendo (redirigen a «Mi perfil», donde sí se pide la
# contraseña). Conservan su nombre porque allauth lo usa internamente.
REDIRECTED_NAMES = ("account_email", "socialaccount_connections")


def _guard_google(view):
    """El login de Google responde 404 (y no 500) si no hay credenciales configuradas."""
    def wrapped(request, *args, **kwargs):
        if not settings.GOOGLE_LOGIN_ENABLED:
            raise Http404("El inicio de sesión con Google no está configurado.")
        return view(request, *args, **kwargs)
    wrapped.__name__ = getattr(view, "__name__", "google_view")
    wrapped.csrf_exempt = getattr(view, "csrf_exempt", False)
    return wrapped


def _keep_approved(patterns):
    """Devuelve las rutas aprobadas, recorriendo los ``include`` anidados del proveedor."""
    kept = []
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            inner = _keep_approved(pattern.url_patterns)
            if inner:
                kept.append(path(str(pattern.pattern), include(inner)))
        elif isinstance(pattern, URLPattern) and pattern.name in APPROVED_NAMES:
            if pattern.name.startswith("google_"):
                pattern = URLPattern(pattern.pattern, _guard_google(pattern.callback), pattern.default_args, pattern.name)
            kept.append(pattern)
    return kept


urlpatterns = [
    path("email/", RedirectView.as_view(pattern_name="my_profile"), name="account_email"),
    path("3rdparty/", RedirectView.as_view(pattern_name="my_profile"), name="socialaccount_connections"),
    *_keep_approved(account_urls.urlpatterns),
    path("3rdparty/", include(_keep_approved(social_urls.urlpatterns))),
    *_keep_approved(google_urls.urlpatterns),
]
