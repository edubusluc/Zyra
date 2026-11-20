"""
Configuración del Inicio nativo para capitanes y gestores: «Primeros pasos», «Prepara la temporada» y SNP. Los datos
salen de ``core.onboarding``, ``core.season_prep`` y ``players.snp_import`` (las mismas reglas que la portada web);
aquí solo cambian la entrada (JSON con token) y la salida. ``HomeView`` incluye ``setup_blocks`` en ``setup``.
"""
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from core import onboarding, ratelimit, season_prep
from core.models import Membership
from players import snp_import, snp_requests, snp_service
from players.models import SnpAccount

from .errors import ApiError
from .fields import choice_field, invalid, text_field
from .responses import json_ok
from .views_base import ApiView

SYNC_LIMIT, SYNC_WINDOW = 10, 60 * 60


def _web(path, club):
    """Ruta web con ``?en=<competición>`` para que la web abra el equipo del bloque (antes de un posible ``#``)."""
    if not path:
        return None
    base, hash_, fragment = path.partition("#")
    base += ("&" if "?" in base else "?") + f"en={club.competition}"
    return base + hash_ + fragment


def _onboarding(membership):
    """Bloque «Primeros pasos» del equipo, o None si no toca (solo capitanes; ver ``core.onboarding``)."""
    steps = onboarding.onboarding_for(membership)
    if steps is None:
        return None
    club = membership.club
    done = sum(1 for s in steps if s["done"])
    return {
        "done": done, "total": len(steps), "percent": round(100 * done / len(steps)),
        "steps": [{"key": s["key"], "title": str(s["title"]), "help": str(s["help"]), "action": str(s["action"]),
                   "path": _web(s["url"], club), "done": bool(s["done"]),
                   "alt_action": str(s["alt_action"]) if s.get("alt_action") else None,
                   "alt_path": _web(s.get("alt_url"), club)} for s in steps],
    }


def _sync(club, sync):
    """Estado de «Sincronizar datos» (``snp_import.sync_task``) listo para JSON; None si no hace falta."""
    if sync is None:
        return None
    wait = sync["wait"]
    return {
        "state": sync["state"], "message": sync["message"] or "", "can_retry": bool(sync["can_retry"]),
        "blocked": bool(sync["blocked"]), "service_off": bool(sync["service_off"]),
        "same_account": bool(sync["same_account"]),
        "wait_until": timezone.localtime(wait).isoformat() if wait else None,
        "team_fix_path": _web(sync["team_fix_url"], club) or None,
    }


def _season_prep(membership):
    """Bloque «Prepara la temporada» del equipo, o None si no toca (``core.season_prep.season_prep_for``)."""
    prep = season_prep.season_prep_for(membership)
    if prep is None:
        return None
    club = membership.club
    steps = []
    for s in prep["steps"]:
        item = {"key": s["key"], "title": str(s["title"]), "help": str(s["help"]), "done": bool(s["done"]),
                "skipped": bool(s.get("skipped")), "manual": bool(s["manual"]),
                "captain_only": bool(s.get("captain_only")),
                "action": str(s["action"]) if s.get("action") else None, "path": _web(s.get("url"), club)}
        if s["key"] == season_prep.SNP:
            req = s["request"]
            item.update({
                "has_account": bool(s["has_account"]),
                "sync": _sync(club, s["sync"]),
                "request_open": bool(req),
                "request_date": timezone.localtime(req.created_at).date().isoformat() if req else None,
            })
        steps.append(item)
    return {"label": prep["label"], "done": prep["done"], "total": prep["total"], "percent": prep["percent"],
            "is_captain": prep["is_captain"], "steps": steps}


def setup_blocks(memberships):
    """
    Un bloque por equipo en el que haya algo que configurar: ``onboarding``, ``season_prep``, ``snp_missing`` (el
    capitán aún no registró su cuenta SNP) y ``snp_sync`` («Sincronizar datos»). Las mismas condiciones que ``home.html``:
    la preparación de temporada lleva dentro el paso SNP y los primeros pasos esconden el aviso de cuenta.
    """
    out = []
    for m in memberships:
        if not m.can_manage:
            continue
        club = m.club
        first = _onboarding(m)
        prep = _season_prep(m)
        has_account = SnpAccount.objects.filter(club=club).exists()
        missing = bool(m.is_admin and club.rules.has_snp and first is None and prep is None and not has_account)
        sync = None
        if m.is_admin and prep is None and club.rules.has_snp:
            sync = _sync(club, snp_import.sync_task(club))
        if not (first or prep or missing or sync):
            continue
        out.append({"team_id": str(club.public_id), "team_name": club.name, "competition": club.competition,
                    "is_captain": m.is_admin, "onboarding": first, "season_prep": prep, "snp_missing": missing,
                    "snp_sync": sync, "snp_account_path": _web(reverse("snp_account"), club)})
    return out


def _membership(request, body, admin=False):
    """Membresía de la cuenta en ``body["team_id"]`` (capitán si ``admin``, si no capitán o gestor). 404 si no es suya."""
    team_id = text_field(body, "team_id", max_length=64)
    m = (Membership.objects.select_related("club")
         .filter(user=request.user, club__public_id=team_id).first())
    if m is None or m.club.is_suspended or m.club.is_archived:
        raise ApiError("not_found", _("No encontrado."), 404)
    if not (m.is_admin if admin else m.can_manage):
        raise ApiError("forbidden", _("No tienes permiso para hacer esto en este equipo."), 403)
    return m


class DismissOnboardingView(ApiView):
    """``POST /api/v1/home/setup/onboarding/dismiss``: el capitán cierra «Primeros pasos» (como ``dismiss_onboarding``)."""

    def post(self, request):
        """Cuerpo ``{"team_id"}``. Idempotente: ``{"dismissed": true}``."""
        m = _membership(request, self.json_body(request), admin=True)
        m.club.onboarding_dismissed_at = timezone.now()
        m.club.save(update_fields=["onboarding_dismissed_at"])
        return json_ok({"dismissed": True})


class SeasonPrepView(ApiView):
    """``POST /api/v1/home/setup/season-prep``: marca un paso de «Prepara la temporada» o la oculta («Ahora no»)."""

    def post(self, request):
        """
        Cuerpo ``{"team_id", "action": "mark" | "close", "key"?}``. ``mark`` admite ``roster`` y ``rivals``
        (capitán o gestor) y ``snp_skipped`` (solo el capitán); ``close``, solo el capitán. Devuelve ``{"ok": true}``.
        """
        body = self.json_body(request)
        action = choice_field(body, "action", ("mark", "close"), "")
        m = _membership(request, body, admin=action == "close")
        if action == "close":
            season_prep.close(m.club)
            return json_ok({"ok": True})
        key = choice_field(body, "key", (*season_prep.MANUAL_STEPS, season_prep.SNP_SKIPPED), "")
        if key == season_prep.SNP_SKIPPED and not m.is_admin:
            raise ApiError("forbidden", _("Solo el capitán del club puede omitir el paso de SNP."), 403)
        season_prep.mark_step(m.club, key)
        return json_ok({"ok": True})


class SnpSyncView(ApiView):
    """``POST /api/v1/home/setup/snp-sync``: lanza «Completar equipo» desde el Inicio (como ``complete_team_start`` con ``from=home``)."""

    def post(self, request):
        """
        Cuerpo ``{"team_id"}``, solo capitán. Mismas condiciones que la web: cuenta SNP registrada (409 ``no_account``),
        servicio activo (503 ``service_off``), límite por hora (429), no hecho ya o bloqueado (409 ``closed``), cuenta cambiada tras
        un fallo (409 ``same_account``) y espera entre búsquedas (429 ``wait``). Si hay una en curso no crea otra.
        Devuelve ``{"started": bool}``; la búsqueda se confirma sola al terminar.
        """
        m = _membership(request, self.json_body(request), admin=True)
        club = m.club
        if not SnpAccount.objects.filter(club=club).exists():
            raise ApiError("no_account", _("Primero registra la cuenta SNP del capitán."), 409)
        if not snp_service.is_enabled():
            raise ApiError("service_off", snp_service.UNAVAILABLE_MESSAGE, 503)
        if ratelimit.too_many_user(request, "complete-team", SYNC_LIMIT, SYNC_WINDOW):
            raise ApiError("rate_limited", _("Demasiadas peticiones. Espera un momento."), 429)
        if snp_import.web_import_done(club) or snp_import.web_blocked(club):
            raise ApiError("closed", _("Esta temporada ya has completado el equipo desde SNP o ha fallado varias veces."), 409)
        if snp_import.active_import(club):
            return json_ok({"started": False})
        if snp_import.account_unchanged_after_failure(club):
            raise ApiError("same_account", _("SNP no aceptó el usuario o la contraseña. Cámbialos en la cuenta SNP antes de volver a intentarlo."), 409)
        wait = snp_import.search_limit(club)
        if wait:
            raise ApiError("wait", _("Has buscado tu equipo en SNP varias veces seguidas. Para no saturar SNP, "
                                     "podrás volver a intentarlo a partir del %(date)s.")
                           % {"date": f"{timezone.localtime(wait):%d/%m/%Y %H:%M}"}, 429)
        snp_import.start_search(club, request.user, auto_confirm=True)
        return json_ok({"started": True})


class SnpUpdateRequestView(ApiView):
    """``POST /api/v1/home/setup/snp-request``: «Pedir actualización a Zyra» (como ``snp_update_request``)."""

    def post(self, request):
        """Cuerpo ``{"team_id", "note"?}`` (máx. 200), solo capitán. ``{"created": bool}``: false si ya había una abierta."""
        body = self.json_body(request)
        m = _membership(request, body, admin=True)
        note = body.get("note", "")
        if not isinstance(note, str) or len(note) > 200:
            raise invalid("note")
        _req, created = snp_requests.create_request(m.club, request.user, note)
        return json_ok({"created": created})
