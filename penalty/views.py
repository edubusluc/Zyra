"""Vistas de advertencias."""
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.urls import reverse
from .models import Penalty, KIND_LABELS, OTHER, REASON_MAX_LENGTH
from players.models import Player
from call.models import Call
from core.decorators import club_admin_required

# Prefijo de ``extra_tags`` con el que un aviso lleva un botón «Deshacer» (la URL va detrás);
# lo pinta ``core/templates/includes/messages_popup.html``.
UNDO_TAG = "undo="


def _ids_from(request):
    """Identificadores públicos de ``ids`` (POST o ``?ids=a,b`` de la URL del botón «Deshacer»)."""
    raw = request.POST.getlist("ids") + request.GET.getlist("ids")
    return [part.strip() for chunk in raw for part in chunk.split(",") if part.strip()]


@club_admin_required
def create_penalty(request, call_id):
    """
    Crea una advertencia con el mismo motivo para cada jugador marcado en el POST (solo jugadores
    actuales del club, estén o no en la convocatoria). El motivo (``kind``) es obligatorio y
    «Otro» exige un detalle (``reason``). Solo capitanes. Al aplicarlas, el aviso trae un botón
    «Deshacer»; si falta algo, vuelve al registro de la convocatoria con el error.
    """
    call = get_object_or_404(Call, public_id=call_id, match__club=request.club)
    match = call.match
    if request.method != "POST":
        return redirect("call_for_match", match.public_id)
    kind = request.POST.get("kind", "")
    detail = request.POST.get("reason", "").strip()[:REASON_MAX_LENGTH]
    if kind not in KIND_LABELS:
        messages.error(request, _("Elige el motivo de la advertencia."))
        return redirect("view_call_log", call.public_id)
    if kind == OTHER and not detail:
        messages.error(request, _("Escribe el detalle de la advertencia cuando el motivo es «Otro»."))
        return redirect("view_call_log", call.public_id)
    # Solo jugadores actuales del club (estén o no en la convocatoria:
    # lo habitual es sancionar a quien se ha borrado de ella)
    ids = [i for i in request.POST.getlist('players') if i.isdigit()]
    created = [
        Penalty.objects.create(player=player, kind=kind, reason=detail, call=call)
        for player in Player.objects.filter(club=request.club, in_team=True, id__in=ids)
    ]
    if not created:
        messages.error(request, _("Marca al menos un jugador del equipo para advertirle."))
        return redirect("view_call_log", call.public_id)
    undo = reverse("delete_penalty") + "?ids=" + ",".join(p.public_id for p in created)
    messages.success(
        request,
        _("Advertencia aplicada a %(names)s.") % {"names": ", ".join(p.player.short_name for p in created)},
        extra_tags=UNDO_TAG + undo,
    )
    return redirect("call_for_match", match.public_id)


@club_admin_required
@require_POST
def delete_penalty(request):
    """
    Retira advertencias del club (identificadores en ``ids``): lo usan el botón «Deshacer» del
    aviso y «Quitar» del registro de la convocatoria. Solo capitanes; las de otros clubes se
    ignoran. Vuelve al registro de la convocatoria de la primera retirada.
    """
    penalties = list(Penalty.objects.filter(
        public_id__in=_ids_from(request), call__match__club=request.club, player__club=request.club,
    ).select_related("call"))
    if not penalties:
        messages.info(request, _("No hay advertencias que retirar."))
        return redirect("list_match")
    call = penalties[0].call
    for penalty in penalties:
        penalty.delete()
    messages.success(request, _("Advertencia retirada.") if len(penalties) == 1 else _("Advertencias retiradas."))
    return redirect("view_call_log", call.public_id)
