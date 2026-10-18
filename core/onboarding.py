"""
Lista de «Primeros pasos» que ve el capitán en la portada de un club recién registrado.

Cada paso lleva a una parte de la aplicación y se marca solo cuando el club ya tiene
lo que pide (jugadores o cuenta SNP, una invitación, un enfrentamiento). La lista
desaparece al completarla o cuando el capitán la cierra (Club.onboarding_dismissed_at).
"""
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from match.models import Match
from .models import Membership
from players.models import Player, SnpTeamImport


def onboarding_steps(club):
    """Pasos de la lista para ``club``: diccionarios con key, title, help, url, action y done."""
    return [
        {
            "key": "players",
            "title": _("Conecta SNP o añade a tus jugadores"),
            "help": _("Con tu cuenta de SNP traemos a todo el equipo con sus puntos. Si prefieres, añade los jugadores a mano."),
            "url": reverse("snp_account"),
            "action": _("Conectar SNP"),
            "alt_url": reverse("create_player"),
            "alt_action": _("Prefiero añadir jugadores a mano"),
            # El jugador del capitán se crea al registrar el club: no cuenta como plantilla.
            # La cuenta SNP solo cuenta cuando «Completar equipo» ha salido bien: si falla, la tarea sigue pendiente.
            "done": SnpTeamImport.objects.filter(club=club, source=SnpTeamImport.WEB, status=SnpTeamImport.DONE).exists()
            or Player.objects.filter(club=club).exclude(
                user_id__in=club.memberships.filter(role=Membership.ADMIN).values("user_id")
            ).exists(),
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
            "key": "match",
            "title": _("Crea tu primer enfrentamiento"),
            "help": _("Programa el próximo enfrentamiento para preparar la convocatoria y las parejas."),
            "url": reverse("create_match"),
            "action": _("Crear enfrentamiento"),
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
