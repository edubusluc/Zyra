"""
Mapa de URLs del proyecto.

- ADMIN_URL: Django admin (solo superusuarios).
- backoffice/: back-office del personal de Zyra (app backoffice).
- "" (raíz): portada (core.views.home), robots.txt, sitemap.xml, páginas legales
  (privacidad/, terminos/, cookies/) y healthz/ (monitor de caídas).
- players/: jugadores (app players).
- match/: partidos (app match).
- data_analyse/: estadísticas (app data_analyse).
- team/: equipos (app team).
- callLog/: registro de convocatorias (app callLog).
- penalty/: sanciones (app penalty).
- core/: inicio de sesión, alta de club, miembros e invitaciones (app core).
- accounts/: cuentas de django-allauth (inicio de sesión con Google, contraseñas...).
- i18n/ y jsi18n/: selector de idioma y traducciones para el JavaScript.

En local también sirve las fotos subidas (MEDIA_URL). Registra el conversor ``<pid:...>``
y las vistas de error 403 y 404.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, register_converter
from django.views.i18n import JavaScriptCatalog

from core.public_id import PublicIdConverter

from django.contrib.sitemaps.views import sitemap

from core.sitemaps import PublicPagesSitemap
from core.views import error_403_view, error_404_view, healthz, home, legal_page, robots_txt

# <pid:...>: identificador público de un objeto (core/public_id.py). Se registra antes de
# cargar las URLs de cada aplicación, que lo usan.
register_converter(PublicIdConverter, "pid")

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('backoffice/', include('backoffice.urls')),
    path("", home, name="home"),
    # Páginas públicas para buscadores y obligaciones legales.
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap, {"sitemaps": {"public": PublicPagesSitemap}}, name="sitemap"),
    path("privacidad/", legal_page, {"template": "legal/privacy.html"}, name="privacy"),
    path("terminos/", legal_page, {"template": "legal/terms.html"}, name="terms"),
    path("cookies/", legal_page, {"template": "legal/cookies.html"}, name="cookies"),
    # Para el servicio que avisa si la web se cae.
    path("healthz/", healthz, name="healthz"),
    path('players/', include('players.urls')),
    path('match/', include('match.urls')),
    path('data_analyse/',include('data_analyse.urls')),
    path('team/',include('team.urls')),
    path('callLog/',include('callLog.urls')),
    path('penalty/',include('penalty.urls')),
    path('core/', include('core.urls')),
    path('accounts/', include('allauth.urls')),
    # Selector de idioma (vista set_language) y traducciones de los textos de static/js.
    path('i18n/', include('django.conf.urls.i18n')),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
]

# Fotos subidas (MEDIA_URL): en local las sirve Django; en producción, el servidor web.
# static() no añade nada si DEBUG está desactivado.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = error_403_view
handler404 = error_404_view
