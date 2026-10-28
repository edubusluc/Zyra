"""Vistas de advertencias."""
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from .models import Penalty, KINDS, KIND_LABELS, OTHER, REASON_MAX_LENGTH
from players.models import Player
from call.models import Call
from core.decorators import club_manager_required

# Prefijo de ``extra_tags`` con el que un aviso lleva un botón «Deshacer» (la URL va detrás);
# lo pinta ``core/templates/includes/messages_popup.html``.
UNDO_TAG = "undo="


def _ids_from(request):
    """Identificadores públicos de ``ids`` (POST o ``?ids=a,b`` de la URL del botón «Deshacer»)."""
    raw = request.POST.getlist("ids") + request.GET.getlist("ids")
    return [part.strip() for chunk in raw for part in chunk.split(",") if part.strip()]


@club_manager_required
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


def _safe_next(request):
    """Destino interno de ``next`` (POST o GET) o ``None`` si falta o apunta fuera de la web."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return None


@club_manager_required
def edit_penalty(request, penalty_id):
    """
    Edita el motivo (``kind``) y el detalle (``reason``) de una advertencia del club; el jugador y
    la convocatoria no cambian. «Otro» exige detalle. Solo capitán y gestores. Vuelve a ``next``
    (el historial de advertencias) o al registro de la convocatoria.
    """
    penalty = get_object_or_404(
        Penalty.objects.select_related("player", "call__match__local", "call__match__visiting"),
        public_id=penalty_id, call__match__club=request.club, player__club=request.club,
    )
    back = _safe_next(request) or reverse("view_call_log", args=[penalty.call.public_id])
    error = ""
    kind, detail = penalty.kind, penalty.reason
    if request.method == "POST":
        kind = request.POST.get("kind", "")
        detail = request.POST.get("reason", "").strip()[:REASON_MAX_LENGTH]
        if kind not in KIND_LABELS:
            error = _("Elige el motivo de la advertencia.")
        elif kind == OTHER and not detail:
            error = _("Escribe el detalle de la advertencia cuando el motivo es «Otro».")
        else:
            penalty.kind, penalty.reason = kind, detail
            penalty.save(update_fields=["kind", "reason"])
            messages.success(request, _("Advertencia actualizada."))
            return redirect(back)
    return render(request, "edit_penalty.html", {
        "penalty": penalty, "penalty_kinds": KINDS, "kind": kind, "detail": detail,
        "error": error, "back": back, "next": _safe_next(request) or "",
    })


@club_manager_required
@require_POST
def delete_penalty(request):
    """
    Retira advertencias del club (identificadores en ``ids``): lo usan el botón «Deshacer» del
    aviso y «Quitar» del registro de la convocatoria. Solo capitanes; las de otros clubes se
    ignoran. Vuelve a ``next`` si viene (p. ej. el historial) o, si no, al registro de la
    convocatoria de la primera retirada.
    """
    penalties = list(Penalty.objects.filter(
        public_id__in=_ids_from(request), call__match__club=request.club, player__club=request.club,
    ).select_related("call"))
    if not penalties:
        messages.info(request, _("No hay advertencias que retirar."))
        return redirect(_safe_next(request) or "list_match")
    call = penalties[0].call
    for penalty in penalties:
        penalty.delete()
    messages.success(request, _("Advertencia retirada.") if len(penalties) == 1 else _("Advertencias retiradas."))
    return redirect(_safe_next(request) or reverse("view_call_log", args=[call.public_id]))
