"""
Lista de «Primeros pasos» que ve el capitán en la portada de un club recién registrado.

Cada paso lleva a una parte de la aplicación y se marca solo cuando el club ya tiene
lo que pide (un equipo de su grupo, una invitación, un jugador, un partido). La lista
desaparece al completarla o cuando el capitán la cierra (Club.onboarding_dismissed_at).
"""
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from match.models import Match
from players.models import Player
from team.models import Team


def onboarding_steps(club):
    """Pasos de la lista para ``club``: diccionarios con key, title, help, url, action y done."""
    return [
        {
            "key": "team",
            "title": _("Añade un equipo de tu grupo"),
            "help": _("Da de alta a los rivales de tu grupo para poder crear partidos contra ellos."),
            "url": reverse("create_team"),
            "action": _("Añadir equipo"),
            "done": Team.objects.filter(club=club, in_group=True, is_own=False).exists(),
        },
        {
            "key": "invite",
            "title": _("Invita a tus jugadores"),
            "help": _("Envíales una invitación por email o comparte un enlace para que se unan al club."),
            "url": reverse("club_members") + "#invitaciones",
            "action": _("Invitar"),
            "done": club.invitations.exists() or club.memberships.count() > 1,
        },
        {
            "key": "player",
            "title": _("Crea un jugador"),
            "help": _("Para los jugadores que no vayan a aceptar la invitación, añádelos tú a la plantilla."),
            "url": reverse("create_player"),
            "action": _("Crear jugador"),
            "done": Player.objects.filter(club=club).exists(),
        },
        {
            "key": "match",
            "title": _("Crea un partido"),
            "help": _("Programa el próximo partido para preparar la convocatoria y las parejas."),
            "url": reverse("create_match"),
            "action": _("Crear partido"),
            "done": Match.objects.filter(club=club).exists(),
        },
    ]


def onboarding_for(membership):
    """
    Pasos que se muestran en la portada a ``membership``, o None si no toca mostrarlos:
    solo los capitanes, mientras no la hayan cerrado ni completado todos los pasos.
    """
    if membership is None or not membership.is_admin or membership.club.onboarding_dismissed_at is not None:
        return None
    steps = onboarding_steps(membership.club)
    if all(step["done"] for step in steps):
        return None
    return steps
