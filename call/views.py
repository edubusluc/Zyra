"""Vistas de convocatorias."""
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from core.decorators import club_admin_required
from .models import Call


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
