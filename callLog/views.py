"""Vistas de las advertencias de una convocatoria."""
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from call.models import Call
from players.models import Player
from penalty.models import Penalty, KINDS
from django.views.decorators.http import require_http_methods
from core import spaces
from core.decorators import club_required

# Create your views here.
@spaces.follow_call
@club_required
@require_http_methods(["GET", "POST"])
def view_call_log(request, call_id):
    """
    Muestra las advertencias de una convocatoria del club y deja poner nuevas a los jugadores que siguen
    en el equipo (el capitán puede quitarlas).
    Requiere pertenecer al club. Si la convocatoria no existe o es de otro club, responde 404.
    """
    # Solo los jugadores que siguen en el equipo, por orden alfabético
    players = Player.objects.filter(club=request.club, in_team=True).order_by('name', 'last_name')
    get_object_or_404(Call, public_id=call_id, match__club=request.club)
    penalties = Penalty.objects.filter(
        call__public_id=call_id, call__match__club=request.club,
    ).select_related("player").order_by("-id")

    return render(request, "view_call_log.html", {
        "players": players,
        "call_id": call_id,
        "penalties": penalties,
        "penalty_kinds": KINDS,
    })
