"""Etiqueta de plantilla de la «Previa» de un enfrentamiento (balance contra ese rival)."""
from urllib.parse import urlencode

from django import template
from django.urls import reverse

from data_analyse import rivals

register = template.Library()


@register.simple_tag
def rival_preview(match):
    """Datos de la «Previa» de ``match`` (``data_analyse.rivals.rival_preview``) o None si no hay historial."""
    return rivals.rival_preview(match)


@register.simple_tag
def rival_history_url(match):
    """
    URL de la ficha de Estadísticas › Rivales del rival de ``match`` (todas las temporadas y todos los tipos, en la
    competición del enfrentamiento); cadena vacía si no hay rival identificable. La ven igual capitanes y jugadores.
    """
    team = match.visiting if match.own_is_local else match.local
    if team:
        who = {"team": team.public_id}
    elif (match.rival_name or "").strip():
        who = {"name": match.rival_name.strip()}
    else:
        return ""
    query = {"en": match.club.competition, **who, "season": "all", "match_type": "todos"}
    return f"{reverse('rival_detail')}?{urlencode(query)}"
