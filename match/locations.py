"""Sincroniza el lugar de los enfrentamientos abiertos cuando un equipo cambia de sede."""
from django.db.models import Q

from .models import Match


def propagate_team_location(team, old_location):
    """Cambia al lugar nuevo de ``team`` el de sus enfrentamientos con el acta abierta.

    ``Match.location`` es una copia del lugar del equipo al crear el partido. Al editar el lugar del
    equipo se actualizan solo los enfrentamientos del club con el acta abierta (``draft_mode``) en los que
    juega, como local o como visitante, y cuyo lugar es todavía el anterior: si alguien lo escribió a mano
    es distinto y no se toca (tampoco el de un partido como visitante que se juega en la pista del rival).
    Los enfrentamientos con el acta cerrada conservan el lugar que tenían, sea cual sea su fecha. No envía
    correos: el lugar se lee en el momento en la ficha, el enlace de disponibilidad y las imágenes de
    compartir, y el informe se genera al cerrar la convocatoria.

    Devuelve cuántos enfrentamientos se han actualizado.
    """
    if not old_location or old_location == team.location:
        return 0
    return Match.objects.filter(
        Q(local=team) | Q(visiting=team), club=team.club, location=old_location, draft_mode=True,
    ).update(location=team.location)
