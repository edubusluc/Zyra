"""Vistas de convocatorias."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.translation import gettext as _, ngettext
from django.views.decorators.http import require_POST
from core import spaces
from core.decorators import club_admin_required, club_manager_required
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
    """Enfrentamiento del enlace de disponibilidad o 404 (el token es impredecible)."""
    return get_object_or_404(Match.objects.select_related("club", "local", "visiting"), availability_token=token)


def _link_player(request, match):
    """«Soy yo» desde el enlace: enlaza la cuenta con un jugador libre de la plantilla (POST ``player``)."""
    with transaction.atomic():
        player = Player.objects.select_for_update().filter(
            public_id=request.POST.get("player", ""), club=match.club).first()
        if player is None or Player.objects.filter(club=match.club, user=request.user).exists():
            return
        if player.user_id:
            messages.error(request, _("Ese jugador ya está enlazado a otra cuenta. Si eres tú, habla con tu capitán."))
            return
        player.user = request.user
        player.save(update_fields=["user"])
        if not (request.user.first_name or request.user.last_name):
            request.user.first_name, request.user.last_name = player.name, player.last_name
            request.user.save(update_fields=["first_name", "last_name"])
        messages.success(request, _("Tu cuenta está enlazada a %(player)s.") % {"player": player.short_name})


@login_required
def availability(request, token):
    """
    Página del enlace de disponibilidad (solo datos del enfrentamiento, nunca otros jugadores). Pide
    iniciar sesión y pertenecer al equipo. Si la cuenta no está enlazada a un jugador, ofrece enlazarla antes
    de responder. En POST (``action``: «link» o «answer») enlaza o guarda Sí / No / Aún no sé (con
    comentario solo en «Aún no sé»), hasta que se cierra la convocatoria. Capitán y gestores ven además
    el resumen de respuestas.
    """
    match = _match_by_token(token)
    membership = spaces.membership_for(request, match.club)
    if membership is None:
        return render(request, "availability.html", {"match": match, "state": "not_member", "can_manage": False, "team": match.club}, status=403)
    spaces.switch_to(request, match.club)
    player = Player.objects.filter(club=match.club, user=request.user).first()
    is_open = availability_logic.is_open(match)

    if request.method == "POST":
        if request.POST.get("action") == "link" and player is None:
            _link_player(request, match)
        elif request.POST.get("action") == "answer" and player is not None:
            if not is_open:
                messages.error(request, _("La convocatoria está cerrada: ya no se puede cambiar la respuesta."))
            elif availability_logic.set_answer(match, player, request.POST.get("answer", ""), request.POST.get("comment", "")):
                messages.success(request, _("Respuesta guardada."))
        if request.POST.get("next") == "ficha":
            return redirect("call_for_match", match.public_id)
        return redirect("availability", token=token)

    mine = Availability.objects.filter(match=match, player=player).first() if player else None
    context = {
        "match": match, "is_open": is_open, "player": player, "mine": mine,
        "editing": bool(request.GET.get("cambiar")), "can_manage": membership.can_manage, "answers": Availability.ANSWERS,
        "max_comment": Availability.MAX_COMMENT,
        "state": "closed" if not is_open else "link" if player is None else "answer",
    }
    if player is None and is_open:
        context["free_players"] = Player.objects.filter(club=match.club, user__isnull=True, in_team=True).order_by("name", "last_name")
    return render(request, "availability.html", context)


@spaces.follow_match
@club_manager_required
@require_POST
def availability_set(request, match_id):
    """El capitán o un gestor cambia la respuesta de un jugador (POST ``player``, ``answer``, ``comment``)."""
    match = get_object_or_404(Match, public_id=match_id, club=request.club)
    player = get_object_or_404(Player, public_id=request.POST.get("player", ""), club=request.club)
    if availability_logic.set_answer(match, player, request.POST.get("answer", ""), request.POST.get("comment", ""),
                               by_manager=True):
        messages.success(request, _("Respuesta de %(player)s actualizada.") % {"player": player.short_name})
    else:
        messages.error(request, _("No se puede cambiar la respuesta: la convocatoria está cerrada."))
    return redirect("call_for_match", match.public_id)


@spaces.follow_match
@club_manager_required
@require_POST
def availability_regenerate(request, match_id):
    """Genera un enlace nuevo: el anterior deja de funcionar (solo POST, capitán o gestor)."""
    match = get_object_or_404(Match, public_id=match_id, club=request.club)
    availability_logic.regenerate_token(match)
    messages.success(request, _("Enlace nuevo creado. El anterior ya no funciona."))
    return redirect("call_for_match", match.public_id)


@spaces.follow_match
@club_manager_required
@require_POST
def availability_remind(request, match_id):
    """
    Recordatorio manual: correo a quienes aún no han respondido, como mucho uno por hora y
    enfrentamiento (solo POST, capitán o gestor, y mientras se pueda responder).
    """
    match = get_object_or_404(Match, public_id=match_id, club=request.club)
    if not availability_logic.is_open(match):
        messages.error(request, _("La convocatoria está cerrada."))
    elif availability_logic.reminder_blocked(match):
        messages.error(request, _("Ya enviaste un recordatorio hace poco. Espera un rato antes de enviar otro."))
    else:
        n = availability_logic.send_reminder(request, match)
        messages.success(request, ngettext("Recordatorio enviado a %(n)s jugador.",
                                           "Recordatorio enviado a %(n)s jugadores.", n) % {"n": n} if n
                         else _("Nadie tiene pendiente responder."))
    return redirect("call_for_match", match.public_id)
