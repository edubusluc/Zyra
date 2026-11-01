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
