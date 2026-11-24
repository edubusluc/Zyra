"""``/api/v1/matches/<id>/call``: selección de jugadores de la convocatoria (crear y editar) para la app nativa."""
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from call import availability as availability_logic
from call.models import Call
from core.competitions import competition_for
from match import league, phase as match_phase
from match.views import EMPTY_CALL_ERROR, _edit_call_problem, annotate_availability, selectable_players
from players.models import Player

from .errors import ApiError
from .fields import invalid
from .responses import json_ok
from .views_base import ApiView
from .views_match import _managed_match


def _locked_reason(match, call):
    """Motivo por el que no se puede tocar la convocatoria (acta cerrada o resultados guardados), o ``None``."""
    if not match.draft_mode:
        return _("El acta está cerrada: reábrela para cambiar la convocatoria.")
    if call is not None and match_phase.has_results(match):
        return _("Hay resultados guardados: no se puede cambiar la convocatoria. "
                 "Borra el resultado del partido para poder hacerlo.")
    return None


class MatchCallView(ApiView):
    """``GET`` y ``PUT /api/v1/matches/<id>/call``: jugadores seleccionables y alta o cambio de la convocatoria."""

    def get(self, request, match_id):
        """
        Solo capitán y gestores (404 si no). Devuelve ``{"exists", "closed", "min", "locked", "finals", "players"}``:
        ``locked`` es el motivo si no se puede cambiar (o ``null``), ``finals`` el mínimo de la regla de fases finales
        (o ``null``) y ``players[]`` los seleccionables por puntos SNP (``id``, ``name``, ``snp``, ``played``,
        ``season_total``, ``answer`` ``yes``/``no``/``maybe``/``null``, ``comment``, ``penalties``, ``copy_pending``,
        ``finals_short``, ``finals_played`` y ``selected``). Sin convocatoria llegan marcados los «Sí» del enlace.
        """
        match, _membership = _managed_match(request.user, match_id)
        call = Call.objects.filter(match=match).first()
        current = set(call.players.values_list("id", flat=True)) if call else set()
        players = selectable_players(match.club, include_ids=current)
        annotate_availability(match, players)
        if call is None:
            listed = {p.id for p in players}
            current = {i for i in availability_logic.yes_player_ids(match) if i in listed}
        short = {p.id: played for p, played in league.finals_shortfall(match, players)}
        data = {
            "exists": call is not None, "closed": bool(call and not call.draft_mode),
            "min": competition_for(match).min_call_players, "locked": _locked_reason(match, call),
            "finals": ({"minimum": match.club.rules.finals_min_regular, "label": str(match.type_label)}
                       if league.applies_finals_rule(match) else None),
            "players": [{
                "id": str(p.public_id), "name": p.short_name, "snp": p.snp_score, "played": p.played,
                "season_total": p.season_total, "answer": p.availability[0] if p.availability else None,
                "comment": p.availability[1] if p.availability else "", "penalties": [str(r) for r in p.penalty_reasons],
                "copy_pending": p.copy_pending, "finals_short": p.id in short, "finals_played": short.get(p.id),
                "selected": p.id in current,
            } for p in players],
        }
        return json_ok(data)

    def put(self, request, match_id):
        """
        Cuerpo ``{"players": [id, …], "force_finals"?}``. Crea la convocatoria (si no había) o cambia sus jugadores, con las
        reglas de la web: 409 ``invalid_call`` con el motivo (vacía, por debajo del mínimo con la convocatoria cerrada, jugadores
        quitados que están en una pareja), 409 ``locked`` (acta cerrada o resultados guardados) y 409 ``finals_rule`` si se
        añade a quien no cumple el mínimo de liga de Playoffs o Fase final y no llega ``force_finals``. Devuelve
        ``{"created", "count"}``.
        """
        body = self.json_body(request)
        ids = body.get("players")
        force = body.get("force_finals", False)
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or not isinstance(force, bool):
            raise invalid("players")
        match, _membership = _managed_match(request.user, match_id)
        with transaction.atomic():
            call = Call.objects.select_for_update().filter(match=match).first()
            reason = _locked_reason(match, call)
            if reason:
                raise ApiError("locked", reason, 409)
            current = set(call.players.values_list("id", flat=True)) if call else set()
            chosen = list(Player.objects.filter(club=match.club, public_id__in=ids).filter(
                Q(in_team=True) | Q(id__in=current)))
            if len({str(p.public_id) for p in chosen}) != len(set(ids)):
                raise invalid("players")
            selected = {p.id for p in chosen}
            if not selected:
                raise ApiError("invalid_call", str(EMPTY_CALL_ERROR), 409)
            if call is not None:
                problem = _edit_call_problem(call, selected, current, competition_for(match).min_call_players)
                if problem:
                    raise ApiError("invalid_call", str(problem), 409)
            added = [p for p in chosen if p.id not in current]
            short = league.finals_shortfall(match, added)
            if short and not force:
                names = ", ".join(p.full_name for p, _n in short)
                raise ApiError("finals_rule", _(
                    "Según el reglamento, en esta fase solo pueden jugar quienes han jugado al menos %(n)s enfrentamientos "
                    "de liga esta temporada. No lo cumplen: %(names)s.") % {"n": match.club.rules.finals_min_regular,
                                                                           "names": names}, 409)
            created = call is None
            if created:
                call = Call.objects.create(match=match)
            call.players.set(selected)
            if not created:
                call.save()
        return json_ok({"created": created, "count": len(selected)})
