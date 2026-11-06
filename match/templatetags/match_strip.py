"""Etiqueta de plantilla de la cabecera compacta del enfrentamiento (escudos, VS, fecha y tipo)."""
from django import template

register = template.Library()


@register.inclusion_tag("includes/match_strip.html")
def match_strip(match):
    """Cabecera compacta de ``match`` para las pantallas a las que se llega desde las tarjetas de la ficha."""
    from match.views import match_kind

    return {"match": match, "kind": match_kind(match)}
