"""Filtros de formato comunes: así los mismos datos se ven igual en todas las pantallas."""
from django import template
from django.utils import translation
from django.utils.formats import date_format, number_format
from django.utils.translation import gettext as _

register = template.Library()


@register.filter
def snp_points(value, empty=None):
    """
    Puntos SNP como entero con separador de miles («1.234»); sin dato, «Sin SNP» (o ``empty``).
    Acepta números, cadenas numéricas y None.
    """
    try:
        points = round(float(value))
    except (TypeError, ValueError):
        return empty if empty is not None else _("Sin SNP")
    return number_format(points, use_l10n=True, force_grouping=True)


def _date(value, fmt):
    """Fecha con el formato ``fmt``; en español el día y el mes van en minúscula («dom 4 oct»). Vacío sin dato."""
    if not value:
        return ""
    text = date_format(value, fmt)
    return text.lower() if translation.get_language() == "es" else text


@register.filter(expects_localtime=True)
def date_short(value):
    """Día de la semana, día y mes: «dom 4 oct»."""
    return _date(value, "D j M")


@register.filter(expects_localtime=True)
def date_long(value):
    """Día de la semana, día, mes y año: «dom 4 oct 2026»."""
    return _date(value, "D j M Y")


@register.filter(expects_localtime=True)
def date_day(value):
    """Día, mes y año, sin día de la semana: «4 oct 2026»."""
    return _date(value, "j M Y")


@register.filter(expects_localtime=True)
def date_day_time(value):
    """Día, mes, año y hora: «4 oct 2026 12:20»."""
    return _date(value, "j M Y H:i")


@register.filter
def crest_initials(name):
    """
    Siglas del escudo de reserva: la inicial de las dos primeras palabras («Atlético Isleño» → «AI»)
    o, con una sola palabra, sus dos primeras letras («NorthPadel» → «NO»). En mayúsculas.
    """
    words = [w for w in str(name or "").replace("-", " ").split() if w[:1].isalnum()]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else "").upper()


@register.filter
def crest_hue(name):
    """Tono (0-359) derivado del nombre del equipo para el escudo de reserva: el mismo nombre, el mismo tono."""
    return sum((i + 1) * ord(c) for i, c in enumerate(str(name or "").lower())) % 360



# Un nombre de equipo de hasta estas letras va en una sola línea en la tarjeta «Próximo enfrentamiento»;
# a partir de ahí se reparte en dos líneas en vez de encogerse.
TEAM_NAME_ONE_LINE_MAX = 16


def split_team_name(name):
    """
    Líneas con las que se pinta un nombre de equipo en la tarjeta «Próximo enfrentamiento».

    Hasta ``TEAM_NAME_ONE_LINE_MAX`` letras (o con una sola palabra), una línea. Si es más largo, dos líneas
    cortando entre palabras por el punto que deja la línea más larga lo más corta posible
    («Sonridental Avanzza Padel» → «Sonridental» / «Avanzza Padel»).
    """
    name = " ".join((name or "").split())
    words = name.split(" ")
    if len(name) <= TEAM_NAME_ONE_LINE_MAX or len(words) < 2:
        return [name]
    cut = min(
        range(1, len(words)),
        key=lambda i: max(len(" ".join(words[:i])), len(" ".join(words[i:]))),
    )
    return [" ".join(words[:cut]), " ".join(words[cut:])]


@register.simple_tag
def team_names_fit(local, visiting):
    """
    Nombres de local y visitante para la tarjeta «Próximo enfrentamiento», listos para pintar al mismo tamaño.

    Devuelve ``local`` y ``visiting`` (lista de líneas de cada nombre, ver :func:`split_team_name`) y ``width``:
    letras de la línea más larga de los dos. El CSS lo usa como ``--fit`` para elegir un tamaño común, así un
    nombre largo pasa a dos líneas en vez de encoger los dos.
    """
    local_lines, visiting_lines = split_team_name(local), split_team_name(visiting)
    width = max(len(line) for line in local_lines + visiting_lines)
    return {"local": local_lines, "visiting": visiting_lines, "width": max(width, 1)}
