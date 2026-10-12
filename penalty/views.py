"""Vistas de advertencias."""
from django.shortcuts import redirect, get_object_or_404
from .models import Penalty
from players.models import Player
from call.models import Call
from core.decorators import club_admin_required

@club_admin_required
def create_penalty(request, call_id):
    """
    Crea una advertencia para cada jugador marcado en el POST (solo jugadores actuales del
    club, estén o no en la convocatoria). Solo capitanes. Siempre vuelve a la convocatoria
    del partido.
    """
    call = get_object_or_404(Call, public_id=call_id, match__club=request.club)
    match = call.match
    if request.method == "POST":
        selected_players_ids = request.POST.getlist('players')
        # Solo jugadores actuales del club (estén o no en la convocatoria:
        # lo habitual es sancionar a quien se ha borrado de ella)
        ids = [i for i in selected_players_ids if i.isdigit()]
        for player in Player.objects.filter(club=request.club, in_team=True, id__in=ids):
            Penalty.objects.create(
                player = player,
                reason = "Advertencia en el partido " + match.local_name + " VS " + match.visiting_name + ".",
                call = call
            )

        return redirect("call_for_match", match.public_id)
    return redirect("call_for_match", match.public_id)
