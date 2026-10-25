"""Vistas del registro de convocatorias."""
from django.shortcuts import render
from django.utils.translation import gettext as _
from call.models import Call
from callLog.models import CallLog
from players.models import Player
from penalty.models import Penalty, KINDS
from django.views.decorators.http import require_http_methods
from core.decorators import club_required

# Create your views here.
@club_required
@require_http_methods(["GET", "POST"])
def view_call_log(request, call_id):
    """
    Muestra el registro de una convocatoria del club, línea a línea, junto con los jugadores
    que siguen en el equipo y las advertencias ya aplicadas (el capitán puede quitarlas).
    Requiere pertenecer al club. Si la convocatoria no existe, muestra un mensaje de error en
    la misma plantilla.
    """
    # Solo los jugadores que siguen en el equipo, por orden alfabético
    players = Player.objects.filter(club=request.club, in_team=True).order_by('name', 'last_name')
    if not Call.objects.filter(public_id=call_id, match__club=request.club).exists():
        return render(request, "view_call_log.html", {
            "error_message": _("No se encontró el registro de llamada con el ID especificado."),
            "log_lines": [],
            "players": players,
            "call_id": call_id,
        })
    # Una convocatoria sin registro (creada sin cambios) se ve igual, con la lista vacía.
    call_log = CallLog.objects.filter(call__public_id=call_id, call__match__club=request.club).first()

    penalties = Penalty.objects.filter(
        call__public_id=call_id, call__match__club=request.club,
    ).select_related("player").order_by("-id")

    if call_log and call_log.text:
        log_lines = call_log.text.split(";")
    else:
        log_lines = []  # Si no tiene contenido, usar una lista vacía

    return render(request, "view_call_log.html", {
        "log_lines": log_lines,
        "players": players,
        "call_id": call_id,
        "penalties": penalties,
        "penalty_kinds": KINDS,
    })
