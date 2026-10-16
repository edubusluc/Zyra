"""Filtros de formato comunes: así los mismos datos se ven igual en todas las pantallas."""
from django import template
from django.utils.formats import number_format
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
