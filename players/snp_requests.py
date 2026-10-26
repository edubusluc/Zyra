"""
«Pedir actualización a Zyra»: el capitán pide al personal que complete el equipo desde SNP por él.

Una sola petición abierta por club. El personal la atiende desde el back-office (lanza «Completar equipo»
sin el límite de la web) y la marca como hecha; con ella hecha, el paso de SNP de «Prepara la temporada»
cuenta como cumplido. Si hay más de ``ALERT_OPEN_REQUESTS`` abiertas, el aviso al personal sale por las
alertas del back-office (``backoffice.alerts``).
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import SnpUpdateRequest
from .snp_import import season_window_start

# Con más peticiones abiertas que estas, se avisa por correo al personal.
ALERT_OPEN_REQUESTS = 5


def open_request(club):
    """La petición abierta del club, o None."""
    return SnpUpdateRequest.objects.filter(club=club, status=SnpUpdateRequest.OPEN).first()


def open_count():
    """Cuántas peticiones abiertas hay en total."""
    return SnpUpdateRequest.objects.filter(status=SnpUpdateRequest.OPEN).count()


def fulfilled_this_season(club, today=None):
    """La última petición del club atendida esta temporada (desde el último 1 de julio), o None."""
    return SnpUpdateRequest.objects.filter(
        club=club, status=SnpUpdateRequest.DONE, done_at__gte=season_window_start(today),
    ).order_by("-done_at").first()


def create_request(club, user, note=""):
    """Crea la petición del club con una nota opcional. Devuelve ``(petición, creada)``; si ya había una abierta, esa."""
    existing = open_request(club)
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            return SnpUpdateRequest.objects.create(club=club, requested_by=user, note=note.strip()[:200]), True
    except IntegrityError:
        return open_request(club), False


def finish(request, user):
    """Marca la petición como hecha por ``user`` (personal). Devuelve False si ya lo estaba."""
    if request.status == SnpUpdateRequest.DONE:
        return False
    request.status = SnpUpdateRequest.DONE
    request.done_at = timezone.now()
    request.done_by = user
    request.save(update_fields=["status", "done_at", "done_by"])
    return True
