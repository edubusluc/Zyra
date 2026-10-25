"""Etiqueta de plantilla de la «Previa» de un enfrentamiento (balance contra ese rival)."""
from django import template

from data_analyse import rivals

register = template.Library()


@register.simple_tag
def rival_preview(match):
    """Datos de la «Previa» de ``match`` (``data_analyse.rivals.rival_preview``) o None si no hay historial."""
    return rivals.rival_preview(match)
