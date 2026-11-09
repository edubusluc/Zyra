"""Vistas de convocatorias."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.translation import gettext as _, ngettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from core import spaces
from core.decorators import club_admin_required, club_required
from match.models import Match
from players.models import Player
from . import availability as availability_logic
from .models import Availability, Call


@club_admin_required
@require_POST
def delete_call(request, match_id):
    """
    Borra la convocatoria de un partido del club. Solo capitanes y por POST. No se borra si
    el partido ya está confirmado. Vuelve a la convocatoria del partido.
    """
    call = get_object_or_404(Call, match__public_id=match_id, match__club=request.club)
    # Un partido con el acta cerrada no se toca: borrar su convocatoria rompería sus estadísticas.
    if not call.match.draft_mode:
        messages.error(request, _("No se puede borrar la convocatoria de un enfrentamiento ya confirmado."))
    else:
        call.delete()
    return redirect('call_for_match', match_id)


def _match_by_token(token):
    """Enfrentamiento del enlace de disponibilidad, o ``None`` si el enlace no existe o ya se sustituyó por otro."""
    return Match.objects.select_related("club", "local", "visiting").filter(availability_token=token).first()


def _link_player(request, match):
    """«Soy yo» desde el enlace: enlaza la cuenta con un jugador libre de la plantilla (POST ``player``)."""
    with transaction.atomic():
        player = Player.objects.select_for_update().filter(
            public_id=request.POST.get("player", ""), club=match.club).first()
        if player is None or Player.objects.filter(club=match.club, user=request.user).exists():
            return
        if not player.is_claimable_by(request.user):
            messages.error(request, _("Ese jugador ya está enlazado a otra cuenta. Si eres tú, habla con tu capitán."))
            return
        player.user = request.user
        player.save(update_fields=["user"])
        if not (request.user.first_name or request.user.last_name):
            request.user.first_name, request.user.last_name = player.name, player.last_name
            request.user.save(update_fields=["first_name", "last_name"])
        messages.success(request, _("Tu cuenta está enlazada a %(player)s.") % {"player": player.short_name})


def _save_own_answer(request, match, player):
    """Guarda la respuesta del propio jugador (POST ``answer`` y ``comment``) y avisa del resultado."""
    answer = request.POST.get("answer", "")
    if not availability_logic.is_open(match):
        messages.error(request, _("La convocatoria está cerrada: ya no se puede cambiar la respuesta."))
    elif availability_logic.set_answer(match, player, answer, request.POST.get("comment", "")):
        messages.success(request, _("Respuesta guardada."))
    else:
        messages.error(request, _("Elige Sí, No o Pendiente."))


@never_cache
@login_required
def availability(request, token):
    """
    Página del enlace de disponibilidad (solo datos del enfrentamiento, nunca otros jugadores). Pide
    iniciar sesión y pertenecer al equipo; a quien no pertenece no se le enseña ningún dato del
    enfrentamiento. Si la cuenta no está enlazada a un jugador, ofrece enlazarla antes de responder. En POST
    (``action``: «link» o «answer») enlaza o guarda Sí / No / Pendiente (con comentario solo en «Pendiente»),
    hasta que se cierra la convocatoria. Capitán y gestores ven además el resumen de respuestas. Un enlace
    que no existe o que el capitán sustituyó por otro da la misma página «enlace no válido» (404).
    """
    match = _match_by_token(token)
    if match is None:
        return render(request, "availability.html", {"state": "invalid", "can_manage": False}, status=404)
    membership = spaces.membership_for(request, match.club)
    if membership is None:
        suspended = any(c.id == match.club_id for c in getattr(request, "suspended_clubs", []))
        return render(request, "availability.html", {
            "state": "suspended" if suspended else "not_member", "can_manage": False, "team": match.club}, status=403)
    spaces.switch_to(request, match.club)
    player = Player.objects.filter(club=match.club, user=request.user).first()
    is_open = availability_logic.is_open(match)

    if request.method == "POST":
        if request.POST.get("action") == "link" and player is None:
            _link_player(request, match)
        elif request.POST.get("action") == "answer" and player is not None:
            _save_own_answer(request, match, player)
        return redirect("availability", token=token)

    mine = Availability.objects.filter(match=match, player=player).first() if player else None
    context = {
        "match": match, "is_open": is_open, "player": player, "mine": mine,
        "editing": bool(request.GET.get("cambiar")), "can_manage": membership.can_manage, "answers": Availability.ANSWERS,
        "max_comment": Availability.MAX_COMMENT,
        "state": "closed" if not is_open else "link" if player is None else "answer",
    }
    if player is None and is_open:
        context["free_players"] = Player.objects.filter(club=match.club, user__isnull=True, in_team=True).filter(
            Q(past_user__isnull=True) | Q(past_user=request.user)).order_by("name", "last_name")
    return render(request, "availability.html", context)


@spaces.follow_match
@club_required
@require_POST
def availability_answer(request, match_id):
    """El jugador responde desde la ficha del enfrentamiento (no depende del token del enlace)."""
    match = get_object_or_404(Match, public_id=match_id, club=request.club)
    player = Player.objects.filter(club=match.club, user=request.user).first()
    if player is not None:
        _save_own_answer(request, match, player)
    return redirect("call_for_match", match.public_id)


@spaces.follow_match
@club_admin_required
@require_POST
def availability_remind(request, match_id):
    """
    Recordatorio manual, solo del capitán: correo con el enlace a quienes aún no han respondido, como mucho
    uno por hora y enfrentamiento y diez al día por club (solo POST y mientras se pueda responder). La espera
    se reserva antes de enviar y se devuelve si no salió ningún correo.
    """
    match = get_object_or_404(Match, public_id=match_id, club=request.club)
    if not availability_logic.is_open(match):
        messages.error(request, _("La convocatoria está cerrada."))
    elif not availability_logic.pending_players(match):
        messages.info(request, _("Nadie tiene pendiente responder."))
    elif not availability_logic.claim_reminder(match):
        minutes = availability_logic.reminder_minutes_left(match) or 1
        messages.error(request, ngettext(
            "Ya enviaste un recordatorio hace poco. Podrás enviar otro en %(n)s minuto.",
            "Ya enviaste un recordatorio hace poco. Podrás enviar otro en %(n)s minutos.", minutes) % {"n": minutes})
    elif availability_logic.club_over_daily_limit(request.club):
        availability_logic.release_reminder(match)
        messages.error(request, _("Has enviado muchos recordatorios hoy. Prueba de nuevo mañana."))
    else:
        n = availability_logic.send_reminder(request, match)
        if n:
            messages.success(request, ngettext("Recordatorio enviado a %(n)s jugador.",
                                               "Recordatorio enviado a %(n)s jugadores.", n) % {"n": n})
        else:
            availability_logic.release_reminder(match)
            messages.error(request, _("No se pudo enviar ningún correo. Inténtalo de nuevo en unos minutos."))
    return redirect("call_for_match", match.public_id)
