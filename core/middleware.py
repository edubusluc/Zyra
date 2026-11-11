"""Middlewares propios de Zyra: club activo del usuario, idioma de la interfaz y dominio único."""
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import caches
from django.shortcuts import render
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.utils import translation
from django.utils.cache import patch_vary_headers

from . import seo
from .competitions import COMPETITIONS
from .models import Membership

SESSION_KEY = "club_id"


def default_membership(memberships):
    """
    Membresía que se usa cuando la sesión aún no tiene espacio activo (primer acceso, otro dispositivo,
    tras cerrar sesión): el primer equipo que gestiona (capitán o gestor) y, entre varios, por orden
    de competición (SNP antes que LAPI) y de nombre. Si no gestiona ninguno, el primero con el mismo
    orden. Devuelve None si no hay membresías.
    """
    order = list(COMPETITIONS)

    def key(m):
        """Gestiona primero, luego competición según ``COMPETITIONS`` y, al final, nombre."""
        code = m.club.competition
        return (not m.can_manage, order.index(code) if code in order else len(order), m.club.name)

    return min(memberships, key=key) if memberships else None


class CurrentClubMiddleware:
    """
    Resuelve el club activo del usuario y lo deja en request.club / request.membership.

    El club activo se guarda en sesión; si no hay ninguno (o el guardado ya no es
    válido) se usa ``default_membership``. Un usuario sin membresías
    tiene request.club = None.
    """

    def __init__(self, get_response):
        """Guarda la siguiente capa de la cadena de middlewares."""
        self.get_response = get_response

    def __call__(self, request):
        """
        Rellena request.club, request.membership, request.user_memberships (sin los clubes
        suspendidos) y request.suspended_clubs, y guarda en sesión el club elegido.
        """
        request.club = None
        request.membership = None
        request.suspended_clubs = []

        if request.user.is_authenticated:
            memberships = Membership.objects.filter(user=request.user).select_related("club").order_by("club__name")
            # Los clubes suspendidos desde el back-office no se pueden usar (no_club lo explica).
            request.suspended_clubs = [m.club for m in memberships if m.club.is_suspended]
            memberships = [m for m in memberships if not m.club.is_suspended and not m.club.is_archived]
            club_id = request.session.get(SESSION_KEY)
            membership = None
            if club_id:
                membership = next((m for m in memberships if m.club_id == club_id), None)
            if membership is None:
                membership = default_membership(memberships)

            if membership:
                request.membership = membership
                request.club = membership.club
                if club_id != membership.club_id:
                    request.session[SESSION_KEY] = membership.club_id
            request.user_memberships = memberships
        else:
            request.user_memberships = []

        return self.get_response(request)


class LanguageMiddleware:
    """
    Activa el idioma de la interfaz: el de la URL (``?lang=en``, core.seo), el que el usuario
    eligió en el selector (cookie que guarda la vista set_language) o, si no eligió ninguno,
    el español (LANGUAGE_CODE).

    A diferencia de LocaleMiddleware de Django, no mira el idioma del navegador: la web
    sale siempre en español hasta que alguien elige otro idioma.
    """

    def __init__(self, get_response):
        """Guarda la siguiente capa de la cadena de middlewares."""
        self.get_response = get_response

    def __call__(self, request):
        """
        Activa el idioma de la URL (``?lang=en``, la que enlazan los buscadores), si no el de
        la cookie (o LANGUAGE_CODE), y añade a la respuesta Content-Language y Vary: Cookie,
        para que las cachés no mezclen idiomas. El idioma de la URL se guarda en la cookie
        para que el visitante siga en ese idioma al pasar a otras páginas.
        """
        url_language = seo.url_language(request)
        language = url_language or request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if language not in dict(settings.LANGUAGES):
            language = settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()

        response = self.get_response(request)

        if url_language and request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) != url_language:
            # Como la de la vista set_language, pero solo por HTTPS y sin acceso desde
            # JavaScript (los navegadores aceptan cookies Secure también en localhost).
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                url_language,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN,
                secure=True,
                httponly=True,
                samesite="Lax",
            )

        response.headers.setdefault("Content-Language", request.LANGUAGE_CODE)
        patch_vary_headers(response, ("Cookie",))
        return response


class CanonicalHostMiddleware:
    """
    Una sola versión del dominio: si SITE_URL está definida, cualquier petición a otro
    dominio (www.zyra.es, el dominio antiguo...) se redirige con un 301 a la misma ruta en
    SITE_URL. Ese otro dominio tiene que estar en ALLOWED_HOSTS para llegar hasta aquí.
    """

    def __init__(self, get_response):
        """Guarda la siguiente capa de la cadena de middlewares y el dominio canónico."""
        self.get_response = get_response
        self.site_url = settings.SITE_URL
        self.host = urlsplit(self.site_url).netloc if self.site_url else ""

    def __call__(self, request):
        """Redirige (301) si la petición no llega por el dominio de SITE_URL."""
        if self.host and request.get_host() != self.host:
            return HttpResponsePermanentRedirect(self.site_url + request.get_full_path())
        return self.get_response(request)


class FloodProtectionMiddleware:
    """
    Freno general contra inundaciones de peticiones (GET/POST flood) desde una misma IP.

    Cuenta las peticiones por IP y minuto en una caché en memoria de cada proceso (``ratelimit``:
    sin tocar la base de datos, así que rechazar una avalancha es barato). Con N procesos de
    gunicorn el límite efectivo es hasta N veces mayor. Los POST tienen un límite más bajo que
    los GET. Responde 429 con la página «Demasiadas solicitudes». Se salta ``/healthz/`` y los
    estáticos (los sirve WhiteNoise antes de llegar aquí). Si la caché falla deja pasar.
    """

    EXEMPT_PREFIXES = ("/healthz/", "/static/", "/media/")

    def __init__(self, get_response):
        """Guarda la siguiente capa de la cadena de middlewares."""
        self.get_response = get_response

    def __call__(self, request):
        """Responde 429 si la IP ha superado el límite del minuto; si no, sigue la cadena."""
        if settings.RATE_LIMITS_ENABLED and not request.path.startswith(self.EXEMPT_PREFIXES):
            from .ratelimit import client_ip
            is_write = request.method not in ("GET", "HEAD", "OPTIONS")
            limit = settings.FLOOD_LIMIT_POST_PER_MINUTE if is_write else settings.FLOOD_LIMIT_GET_PER_MINUTE
            key = f"flood:{'w' if is_write else 'r'}:{client_ip(request)}"
            try:
                cache = caches["ratelimit"]
                cache.add(key, 0, 60)
                try:
                    hits = cache.incr(key)
                except ValueError:
                    cache.set(key, 1, 60)
                    hits = 1
            except Exception:
                hits = 0
            if hits > limit:
                response = render(request, "429.html", status=429)
                response["Retry-After"] = "60"
                return response
        return self.get_response(request)


logger = logging.getLogger(__name__)
CSP_REPORT_PATH = "/csp-report/"


class ContentSecurityPolicyMiddleware:
    """
    Añade la cabecera Content-Security-Policy (``settings.CSP_POLICY``) a las respuestas HTML: en modo
    ``report-only`` (``CSP_MODE``) el navegador no bloquea nada y avisa a ``/csp-report/``; en ``enforce`` bloquea.
    Con ``CSP_MODE=off`` no añade nada. No pisa una cabecera que ya tenga la respuesta.

    También recibe los avisos del navegador (POST a ``/csp-report/``, JSON) y los anota en el log
    (``CSP violation``) para decidir cuándo pasar a ``enforce``. El navegador los envía sin sesión ni token
    CSRF y no cambian ningún dato, así que se atienden aquí, antes de llegar a ninguna vista.
    """

    def __init__(self, get_response):
        """Guarda la siguiente capa de la cadena de middlewares."""
        self.get_response = get_response

    def __call__(self, request):
        """Atiende ``/csp-report/`` y pone la cabecera según ``CSP_MODE`` en las respuestas HTML."""
        if request.path == CSP_REPORT_PATH and request.method == "POST":
            from .ratelimit import too_many
            if not too_many(request, "csp-report", 60, 60):
                logger.warning("CSP violation: %s", request.body[:2000].decode("utf-8", "replace"))
            return HttpResponse(status=204)
        response = self.get_response(request)
        header = {"enforce": "Content-Security-Policy", "report-only": "Content-Security-Policy-Report-Only"}.get(settings.CSP_MODE)
        if header and header not in response and response.get("Content-Type", "").startswith("text/html"):
            response[header] = settings.CSP_POLICY
        return response
