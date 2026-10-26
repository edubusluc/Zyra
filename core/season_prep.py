"""
«Prepara la temporada»: tarjeta del Inicio con tres pasos para dejar el club listo antes de agosto.

Se ve a capitanes y gestores entre el 1 de julio y el 31 de octubre en los clubes que ya existían el 1 de
julio, hasta que los tres pasos estén hechos u omitidos o el capitán la oculte. Los pasos «Plantilla» y
«Rivales» los marca a mano quien los revisa; el de SNP se marca solo cuando «Completar equipo» ha salido
bien esta temporada (o se omite). El progreso vive en ``Club.season_prep`` y solo vale para el año en curso.
"""
import datetime

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from players import snp_import, snp_requests
from players.models import SnpAccount

# Meses (julio a octubre) en los que se ofrece la tarjeta.
PREP_MONTHS = range(7, 11)
ROSTER, SNP, RIVALS = "roster", "snp", "rivals"
SNP_SKIPPED = "snp_skipped"
# Pasos que marca a mano quien los revisa (el capitán o un gestor).
MANUAL_STEPS = (ROSTER, RIVALS)


def prep_year(today=None):
    """Año en que empieza la temporada que se prepara (la de agosto), o None fuera de julio-octubre."""
    today = today or timezone.localdate()
    return today.year if today.month in PREP_MONTHS else None


def season_label(year):
    """Etiqueta de la temporada que empieza en ``year``: «2026/27»."""
    return f"{year}/{str(year + 1)[-2:]}"


def _progress(club, year):
    """Progreso guardado del club para ``year``; si es de otra temporada, uno vacío."""
    data = club.season_prep or {}
    if data.get("year") != year:
        return {"year": year, "done": [], "closed": False}
    return {"year": year, "done": list(data.get("done", [])), "closed": bool(data.get("closed"))}


def _save(club, progress):
    """Guarda el progreso en el club."""
    club.season_prep = progress
    club.save(update_fields=["season_prep"])


def _steps(club, progress, is_captain):
    """Los tres pasos con su estado. ``sync`` solo se calcula para el capitán (la cuenta SNP es suya)."""
    done = progress["done"]
    snp_done = snp_import.imported_this_season(club) is not None or snp_requests.fulfilled_this_season(club) is not None
    snp_skipped = SNP_SKIPPED in done
    return [
        {"key": ROSTER, "title": _("Revisa tu plantilla"), "manual": True, "done": ROSTER in done,
         "help": _("Marca quién sigue en el equipo y da de baja a quien se va."),
         "url": reverse("manage_roster"), "action": _("Revisar plantilla")},
        {"key": SNP, "title": _("Actualiza desde SNP"), "manual": False, "done": snp_done or snp_skipped,
         "skipped": snp_skipped and not snp_done, "captain_only": True,
         "help": _("Trae los jugadores nuevos y los puntos de la nueva temporada. Se puede hacer una vez por temporada."),
         "sync": snp_import.sync_task(club, this_season=True) if is_captain and not (snp_done or snp_skipped) else None,
         "has_account": SnpAccount.objects.filter(club=club).exists(), "request": snp_requests.open_request(club)},
        {"key": RIVALS, "title": _("Revisa rivales y divisiones"), "manual": True, "done": RIVALS in done,
         "help": _("Cambia la división de tu grupo y añade los equipos nuevos."),
         "url": reverse("manage_teams"), "action": _("Revisar rivales")},
    ]


def season_prep_for(membership, today=None):
    """
    Datos de la tarjeta para ``membership`` (``year``, ``label``, ``steps``, ``done``, ``total``,
    ``percent``) o None si no toca verla: no es capitán ni gestor, fuera de julio-octubre, club creado
    después del 1 de julio, oculta por el capitán o con los tres pasos hechos.
    """
    today = today or timezone.localdate()
    year = prep_year(today)
    if membership is None or year is None or not membership.can_manage:
        return None
    club = membership.club
    if timezone.localtime(club.created_at).date() >= datetime.date(year, 7, 1):
        return None
    progress = _progress(club, year)
    if progress["closed"]:
        return None
    steps = _steps(club, progress, membership.is_admin)
    done = sum(step["done"] for step in steps)
    if done == len(steps):
        return None
    return {"year": year, "label": season_label(year), "steps": steps, "done": done, "total": len(steps),
            "percent": round(100 * done / len(steps)), "is_captain": membership.is_admin}


def mark_step(club, key, today=None):
    """
    Marca como hecho el paso ``key`` (``roster``, ``rivals`` o ``snp_skipped``). Devuelve True si con él
    quedan los tres pasos hechos; False si no, o si no es época de preparar la temporada.
    """
    year = prep_year(today)
    if year is None or key not in (*MANUAL_STEPS, SNP_SKIPPED):
        return False
    progress = _progress(club, year)
    if key not in progress["done"]:
        progress["done"].append(key)
    _save(club, progress)
    steps = _steps(club, progress, False)
    return all(step["done"] for step in steps)


def close(club, today=None):
    """El capitán oculta la tarjeta («Ahora no») hasta la próxima temporada."""
    year = prep_year(today)
    if year is None:
        return
    progress = _progress(club, year)
    progress["closed"] = True
    _save(club, progress)
