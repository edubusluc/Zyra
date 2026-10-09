"""
Posicionamiento en buscadores (SEO) de las páginas públicas.

- Idioma en la URL: ``?lang=en`` sirve la versión en inglés de una página con una URL
  propia que los buscadores pueden rastrear (no guardan cookies). La versión en español
  es la URL sin parámetro.
- URLs alternativas por idioma para ``<link rel="alternate" hreflang>`` y el sitemap.
- Datos estructurados (JSON-LD de schema.org) de la portada.
"""
import json

from django.conf import settings
from django.templatetags.static import static
from django.utils.translation import gettext as _

LANG_PARAM = "lang"


def url_language(request):
    """Idioma pedido en la URL (``?lang=en``) si es uno de LANGUAGES; si no, None."""
    language = request.GET.get(LANG_PARAM)
    return language if language in dict(settings.LANGUAGES) else None


def site_base(request):
    """SITE_URL o, si no está definida (en local), el esquema y dominio de la petición."""
    return settings.SITE_URL or f"{request.scheme}://{request.get_host()}"


def language_url(path, language):
    """Ruta de una página en un idioma: sin parámetro en español, con ``?lang=`` en el resto."""
    if language == settings.LANGUAGE_CODE:
        return path
    return f"{path}?{LANG_PARAM}={language}"


def alternate_urls(request):
    """Lista (código de idioma, URL absoluta) de la página actual en cada idioma."""
    page = site_base(request) + request.path
    return [(code, language_url(page, code)) for code, _name in settings.LANGUAGES]


def path_without_language(request):
    """Ruta actual con su query string pero sin ``?lang=``: destino del selector de idioma."""
    query = request.GET.copy()
    query.pop(LANG_PARAM, None)
    return request.path + (f"?{query.urlencode()}" if query else "")


def landing_faq():
    """Preguntas frecuentes de la portada (se muestran y van también en el JSON-LD)."""
    return [
        (
            _("¿Qué es Zyra?"),
            _("Zyra es una aplicación web para gestionar equipos de pádel que juegan ligas por equipos, como las SNP (Series Nacionales de Pádel): jugadores, convocatorias, parejas, resultados y estadísticas en un solo sitio."),
        ),
        (
            _("¿Cuánto cuesta?"),
            _("Registrar un club y usar Zyra es gratis."),
        ),
        (
            _("¿Quién puede ver los datos de mi equipo?"),
            _("Solo los miembros de tu club. El capitán invita al resto de jugadores con un enlace y nadie de fuera del club puede ver sus jugadores, partidos ni estadísticas."),
        ),
        (
            _("¿Sirve para la liga SNP?"),
            _("Sí. Zyra está pensada para equipos de ligas de pádel por equipos y puede traer los puntos SNP de tus jugadores para ordenar las parejas. Zyra es un proyecto independiente y no está afiliado a las SNP."),
        ),
        (
            _("¿Necesito instalar algo?"),
            _("No. Zyra funciona en el navegador del móvil y del ordenador, en español y en inglés."),
        ),
    ]


def landing_structured_data(request):
    """
    JSON-LD de la portada: la organización, el sitio web, la aplicación (gratis, en la web)
    y las preguntas frecuentes. Devuelve el texto listo para un ``<script>``, con ``<``
    escapado para que el contenido no pueda cerrar la etiqueta.
    """
    base = site_base(request)
    home = base + "/"
    languages = [code for code, _name in settings.LANGUAGES]
    description = _("Aplicación web para capitanes de equipos de pádel: convocatorias, parejas, resultados y estadísticas de cada jugador y pareja.")
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": home + "#organization",
                "name": "Zyra",
                "url": home,
                "logo": base + static("zyra/icon-512.png"),
                "email": settings.CONTACT_EMAIL,
            },
            {
                "@type": "WebSite",
                "@id": home + "#website",
                "name": "Zyra",
                "url": home,
                "inLanguage": languages,
                "publisher": {"@id": home + "#organization"},
            },
            {
                "@type": "WebApplication",
                "@id": home + "#app",
                "name": "Zyra",
                "url": home,
                "description": description,
                "applicationCategory": "SportsApplication",
                "operatingSystem": "Web",
                "inLanguage": languages,
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
                "featureList": [
                    _("Convocatorias con informe en PDF por email"),
                    _("Parejas y resultados de cada set"),
                    _("Estadísticas por jugador, pareja y temporada"),
                    _("Puntos SNP de los jugadores"),
                ],
                "publisher": {"@id": home + "#organization"},
            },
            {
                "@type": "FAQPage",
                "@id": home + "#faq",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": question,
                        "acceptedAnswer": {"@type": "Answer", "text": answer},
                    }
                    for question, answer in landing_faq()
                ],
            },
        ],
    }
    if not settings.CONTACT_EMAIL:
        del data["@graph"][0]["email"]
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
