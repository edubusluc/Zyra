"""
Cuenta SNP y «Completar equipo» en la API: ``GET/PUT/DELETE /teams/<id>/snp-account`` y la revisión de lo que trae SNP
(``GET /teams/<id>/snp-import``, ``POST …/<import>/confirm`` y ``…/cancel``). Las reglas son las de ``players.views``
(``snp_account``, ``complete_team_confirm``, ``complete_team_cancel``); aquí solo cambia la entrada y la salida.
La contraseña nunca sale de la API.
"""
from django.utils import timezone
from django.utils.translation import gettext as _

from core.crypto import DecryptionError
from core.models import Club
from players import snp_import
from players.forms import SnpAccountForm
from players.models import Player, SnpAccount, SnpTeamImport

from .errors import ApiError
from .responses import json_ok
from .teams import membership_for_team
from .views_base import ApiView


def _account_json(account):
    """Estado de la cuenta SNP del club: usuario (si se puede leer), última sincronización y su resultado."""
    if account is None:
        return {"has_account": False, "username": None, "readable": True, "last_sync_at": None, "last_sync_ok": None}
    try:
        username, readable = account.username, True
    except DecryptionError:
        username, readable = None, False
    return {"has_account": True, "username": username, "readable": readable,
            "last_sync_at": timezone.localtime(account.last_sync_at).isoformat() if account.last_sync_at else None,
            "last_sync_ok": account.last_sync_ok if account.last_sync_at else None}


def _fields_error(form):
    """400 ``validation_error`` con los errores del formulario como ``fields``."""
    return ApiError("validation_error", _("Revisa los datos del formulario."), 400,
                    extra={"fields": {name: [str(e) for e in errors] for name, errors in form.errors.items()}})


class SnpAccountView(ApiView):
    """``/api/v1/teams/<id>/snp-account``: la cuenta SNP del capitán (solo capitán)."""

    def get(self, request, team_id):
        """``{"has_account", "username", "readable", "last_sync_at", "last_sync_ok"}``; la contraseña no se devuelve."""
        club = membership_for_team(request.user, team_id, admin=True).club
        return json_ok(_account_json(SnpAccount.objects.filter(club=club).first()))

    def put(self, request, team_id):
        """
        Cuerpo ``{"username", "password"?}``. Sin cuenta la contraseña es obligatoria; con cuenta, vacía mantiene la actual.
        Guardar datos nuevos devuelve al capitán la opción de «Sincronizar datos» (``snp_import_failures`` a 0), como la web.
        400 ``validation_error`` con ``fields``; ``{"changed": false}`` si no cambia nada.
        """
        club = membership_for_team(request.user, team_id, admin=True).club
        if not club.rules.has_snp:
            raise ApiError("not_found", _("No encontrado."), 404)
        body = self.json_body(request)
        account = SnpAccount.objects.filter(club=club).first()
        form = SnpAccountForm({"username": str(body.get("username") or "").strip(), "password": str(body.get("password") or "")},
                              has_password=account is not None)
        if not form.is_valid():
            raise _fields_error(form)
        old_username = None
        if account:
            try:
                old_username = account.username
            except DecryptionError:
                pass
        new_password = form.cleaned_data["password"]
        changed = True
        if account and not account.team_id and old_username == form.cleaned_data["username"] and (
                not new_password or _same_password(account, new_password)):
            changed = False
        else:
            account = account or SnpAccount(club=club)
            account.username = form.cleaned_data["username"]
            if new_password:
                account.password = new_password
            account.team_id = ""
            account.updated_by = request.user
            account.save()
            Club.objects.filter(pk=club.pk).update(snp_import_failures=0)
        return json_ok({**_account_json(SnpAccount.objects.filter(club=club).first()), "changed": changed})

    def delete(self, request, team_id):
        """Borra la cuenta SNP del club. Idempotente: ``{"deleted": true}``."""
        club = membership_for_team(request.user, team_id, admin=True).club
        SnpAccount.objects.filter(club=club).delete()
        return json_ok({"deleted": True})


def _same_password(account, password):
    """True si ``password`` es la ya guardada (si no se puede leer, cuenta como distinta)."""
    try:
        return account.password == password
    except DecryptionError:
        return False


def _import_json(team_import, club):
    """
    Estado de una búsqueda de «Completar equipo»: ``status`` (``running``, ``ready``, ``error``, ``done``, ``cancelled``),
    avance, mensaje y, si está lista, los jugadores nuevos (``to_add``, con ``index`` para ``same``) y los que ya estaban.
    """
    out = {"id": str(team_import.public_id), "status": team_import.status, "progress": team_import.progress,
           "stage": str(team_import.stage or ""), "message": team_import.message or "", "error_kind": team_import.error_kind or "",
           "has_changes": False, "to_add": [], "existing": [], "teams_to_add": [], "same_options": []}
    if team_import.status == SnpTeamImport.READY:
        out["has_changes"] = snp_import.has_changes(team_import)
        out["to_add"] = [{"index": i, "name": e["snp_name"], "category": e.get("category", ""), "score": e.get("score"),
                          "doubtful": bool(e.get("doubtful_id"))} for i, e in enumerate(team_import.to_add)]
        out["existing"] = [{"name": e["snp_name"], "player": str(e.get("player", "")), "score": e.get("score")}
                           for e in team_import.existing if e.get("player_id")]
        out["teams_to_add"] = [{"name": t["name"], "own": bool(t.get("own"))} for t in team_import.teams_to_add]
        out["same_options"] = [{"id": str(p.public_id), "name": p.full_name} for p in snp_import.same_player_options(club)]
    return out


def _team_import(club, import_id):
    """Búsqueda ``import_id`` del club (de la web); 404 si no existe."""
    team_import = SnpTeamImport.objects.filter(public_id=import_id, club=club, source=SnpTeamImport.WEB).first()
    if team_import is None:
        raise ApiError("not_found", _("No encontrado."), 404)
    return team_import


class SnpImportView(ApiView):
    """``GET /api/v1/teams/<id>/snp-import``: la última búsqueda de «Completar equipo» del equipo (solo capitán)."""

    def get(self, request, team_id):
        """``{"import": null}`` si no hay ninguna; si no, ``{"import": {...}}`` con su estado y, si está lista, lo que cambiaría."""
        club = membership_for_team(request.user, team_id, admin=True).club
        latest = SnpTeamImport.objects.filter(club=club, source=SnpTeamImport.WEB).order_by("-created_at", "-pk").first()
        return json_ok({"import": _import_json(latest, club) if latest else None})


class SnpImportConfirmView(ApiView):
    """``POST /api/v1/teams/<id>/snp-import/<import>/confirm``: confirma lo encontrado (como ``complete_team_confirm``)."""

    def post(self, request, team_id, import_id):
        """
        Cuerpo ``{"same"?: {"<index>": "<id de jugador>"}}`` («¿Es el mismo jugador?»). 409 ``not_ready`` si ya no está lista
        o no hay nada que confirmar; si no, ``{"message", "created_players", "position_notice"}``.
        """
        club = membership_for_team(request.user, team_id, admin=True).club
        team_import = _team_import(club, import_id)
        if (team_import.status != SnpTeamImport.READY or not snp_import.has_changes(team_import)
                or snp_import.web_import_done(club) or snp_import.web_blocked(club)):
            raise ApiError("not_ready", _("Esta búsqueda ya no se puede confirmar."), 409)
        raw = self.json_body(request).get("same") or {}
        if not isinstance(raw, dict):
            raise ApiError("validation_error", _("Revisa los datos del formulario."), 400)
        public_ids = [str(v) for v in raw.values()]
        by_public = {str(p.public_id): p for p in Player.objects.filter(club=club, public_id__in=public_ids)}
        same = {}
        for key, value in raw.items():
            if not str(key).isdigit() or str(value) not in by_public or int(key) >= len(team_import.to_add):
                continue
            same[team_import.to_add[int(key)]["snp_name"]] = by_public[str(value)].pk
        done = snp_import.confirm(team_import, same=same)
        return json_ok({"message": done.message, "created_players": list(done.created_players or []),
                        "position_notice": bool(done.created_players)})


class SnpImportCancelView(ApiView):
    """``POST /api/v1/teams/<id>/snp-import/<import>/cancel``: cancela la búsqueda en curso o pendiente."""

    def post(self, request, team_id, import_id):
        """Idempotente: ``{"cancelled": true}``."""
        club = membership_for_team(request.user, team_id, admin=True).club
        SnpTeamImport.objects.filter(
            public_id=_team_import(club, import_id).public_id, club=club, source=SnpTeamImport.WEB,
            status__in=[SnpTeamImport.RUNNING, SnpTeamImport.READY]).update(status=SnpTeamImport.CANCELLED)
        return json_ok({"cancelled": True})
