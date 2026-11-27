"""
Advertencias de una convocatoria en la API: ``GET/POST /matches/<id>/penalties`` y ``DELETE …/penalties/<advertencia>``.
Las reglas son las de ``penalty.views.create_penalty`` y ``delete_penalty`` (solo capitán y gestores, solo jugadores
actuales del club, «Otro» exige detalle, sin duplicar la misma advertencia).
"""
from django.utils.translation import gettext as _

from call.models import Call
from penalty.models import KIND_LABELS, KINDS, OTHER, REASON_MAX_LENGTH, Penalty
from players.models import Player

from .errors import ApiError
from .responses import json_ok
from .views_base import ApiView
from .views_match import _managed_match


def _call(user, match_id):
    """Convocatoria del enfrentamiento que la cuenta gestiona; 404 si no hay convocatoria."""
    match, _membership = _managed_match(user, match_id)
    call = Call.objects.filter(match=match).first()
    if call is None:
        raise ApiError("not_found", _("No encontrado."), 404)
    return match, call


def _penalty(p):
    """Una advertencia: jugador, motivo (código y texto) y detalle."""
    return {"id": str(p.public_id), "player": {"id": str(p.player.public_id), "name": p.player.short_name},
            "kind": p.kind, "detail": p.reason, "text": p.display_reason}


class PenaltiesView(ApiView):
    """``/api/v1/matches/<id>/penalties``: advertencias de la convocatoria."""

    def get(self, request, match_id):
        """``{"kinds", "penalties", "players"}``: motivos, las advertencias (la más reciente primero) y los jugadores actuales."""
        match, call = _call(request.user, match_id)
        penalties = Penalty.objects.filter(call=call, call__match__club=match.club).select_related("player").order_by("-id")
        players = Player.objects.filter(club=match.club, in_team=True).order_by("name", "last_name")
        return json_ok({
            "kinds": [{"key": key, "label": str(label)} for key, label in KINDS],
            "penalties": [_penalty(p) for p in penalties],
            "players": [{"id": str(p.public_id), "name": p.full_name} for p in players],
        })

    def post(self, request, match_id):
        """
        Cuerpo ``{"kind", "detail"?, "players": ["<id>"]}``. 400 ``validation_error`` si falta el motivo, si «Otro» no lleva
        detalle o si no se marca a nadie del equipo. Una advertencia idéntica no se duplica (``skipped``). Devuelve
        ``{"created": [advertencia], "skipped": n}``.
        """
        match, call = _call(request.user, match_id)
        body = self.json_body(request)
        kind = str(body.get("kind") or "")
        detail = str(body.get("detail") or "").strip()[:REASON_MAX_LENGTH]
        if kind not in KIND_LABELS:
            raise ApiError("validation_error", _("Elige el motivo de la advertencia."), 400, extra={"fields": {"kind": [_("Elige el motivo de la advertencia.")]}})
        if kind == OTHER and not detail:
            message = _("Escribe el detalle de la advertencia cuando el motivo es «Otro».")
            raise ApiError("validation_error", message, 400, extra={"fields": {"detail": [message]}})
        ids = body.get("players")
        if not isinstance(ids, list):
            ids = []
        candidates = list(Player.objects.filter(club=match.club, in_team=True, public_id__in=[str(i) for i in ids]))
        if not candidates:
            message = _("Marca al menos un jugador del equipo para advertirle.")
            raise ApiError("validation_error", message, 400, extra={"fields": {"players": [message]}})
        already = set(Penalty.objects.filter(call=call, kind=kind, reason=detail, player__in=candidates)
                      .values_list("player_id", flat=True))
        created = [Penalty.objects.create(player=p, kind=kind, reason=detail, call=call)
                   for p in candidates if p.id not in already]
        return json_ok({"created": [_penalty(p) for p in created], "skipped": len(candidates) - len(created)}, status=201)


class PenaltyView(ApiView):
    """``DELETE /api/v1/matches/<id>/penalties/<advertencia>``: retira una advertencia de la convocatoria."""

    def delete(self, request, match_id, penalty_id):
        """Idempotente: ``{"deleted": true}``; una advertencia de otra convocatoria o club es 404."""
        match, call = _call(request.user, match_id)
        penalty = Penalty.objects.filter(public_id=penalty_id, call=call, player__club=match.club).first()
        if penalty is None:
            raise ApiError("not_found", _("No encontrado."), 404)
        penalty.delete()
        return json_ok({"deleted": True})
