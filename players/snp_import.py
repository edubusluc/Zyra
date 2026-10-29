"""
«Completar equipo»: da de alta en Zyra los jugadores del equipo de SNP del club que
todavía no existen. De los que ya están (aunque se escriban algo distinto, con el mismo
criterio que la actualización de puntos) solo se actualizan los puntos SNP: su nombre,
posición y demás datos no se tocan.

Desde la web del club se hace en dos pasos (buscar y confirmar), solo una vez por temporada: en el alta,
tras registrar la cuenta SNP o al preparar la temporada (``web_import_done``). Si falla ``MAX_FAILED_SEARCHES`` veces se
oculta la opción y se avisa al personal (``web_blocked``); además hay un máximo de búsquedas
seguidas para no saturar SNP (``search_limit``). Después solo lo lanza el personal o el proceso
automático. Desde el back-office
(comando ``complete_snp_team``) en uno solo y sin esos límites. Los clubes que el personal marca
como ``Club.snp_unlimited`` (el equipo de pruebas) no tienen límites.

La búsqueda desde la web no se ejecuta en el proceso web: se deja en cola (``start_search``) y la
recoge el proceso programado ``process_snp_imports`` (``process_queue``), que las atiende de una
en una. Así nunca hay más de un Chromium abierto por las búsquedas de los capitanes.
"""
import asyncio
import datetime
import logging
import threading

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext

from core.crypto import DecryptionError

from .models import Player, SnpAccount, SnpScoreHistory, SnpTeamImport, current_season
from . import snp_service
from .scraper import SnpScrapeError, scrape_scores
from core.similarity import is_same_team, same_name

from .snp import team_options, match_scores, save_score, split_category

logger = logging.getLogger(__name__)

# Partículas que van unidas al apellido siguiente: "de la Fuente".
PARTICLES = {"de", "del", "la", "las", "los", "y", "san", "van", "von", "da", "do", "dos", "di"}
# Si una búsqueda lleva más de esto «en marcha», se da por perdida (p. ej. se reinició el servidor).
STALE_AFTER = datetime.timedelta(minutes=10)
# Si el proceso programado no recoge una búsqueda en cola en este tiempo, se da por perdida.
QUEUE_STALE_AFTER = datetime.timedelta(minutes=30)
# Búsquedas desde la web (canceladas y fallidas incluidas): como mucho SEARCHES_PER_DAY en 24 h
# y al menos SEARCH_COOLDOWN entre una y la siguiente.
SEARCHES_PER_DAY = 3
SEARCH_COOLDOWN = datetime.timedelta(minutes=1)
# Tras tantas búsquedas fallidas desde la web se oculta «Completar equipo» y se avisa al personal.
MAX_FAILED_SEARCHES = 3


def _capitalize(token):
    """Palabra de un nombre con mayúscula inicial; las partículas («de», «la»…) en minúscula."""
    return token.lower() if token.lower() in PARTICLES else token[:1].upper() + token[1:].lower()


def split_snp_name(snp_name):
    """
    Nombre y apellidos a partir del nombre de SNP, sin la categoría del final:
    "PEDRO RAPOSO BELLERIN 500" -> ("Pedro", "Raposo Bellerin");
    "MARIA JOSE GOMEZ RUIZ" -> ("Maria Jose", "Gomez Ruiz");
    "JUAN DE LA FUENTE LOPEZ" -> ("Juan", "de la Fuente Lopez").
    Se toman como apellidos los dos últimos (con sus partículas).
    """
    tokens = [_capitalize(t) for t in split_category(snp_name)[0].split()]
    if len(tokens) <= 1:
        return (tokens[0] if tokens else ""), ""
    start, surnames = len(tokens), 0
    while surnames < 2 and start > 1:
        start -= 1
        while start > 1 and tokens[start - 1].lower() in PARTICLES:
            start -= 1
        surnames += 1
    return " ".join(tokens[:start]), " ".join(tokens[start:])


def _by_clean_name(scores):
    """
    Un jugador por nombre (sin la categoría): SNP puede devolver al mismo jugador con
    y sin ella ("X 500" y "X"). Se queda la entrada que trae categoría.
    """
    unique = {}
    for entry in scores:
        name, category = split_category(entry["name"])
        if name not in unique or (category and not unique[name][1]):
            unique[name] = (entry, category)
    return [{**entry, "name": name, "category": category} for name, (entry, category) in unique.items()]


def plan_import(club, scores):
    """(a_añadir, ya_registrados) comparando los nombres de SNP con todos los jugadores del club."""
    scores = _by_clean_name(scores)
    players = list(Player.objects.filter(club=club))
    matched, unmatched, ambiguous = match_scores(players, scores)
    by_name = {entry["name"]: entry for entry in scores}
    category = {entry["name"]: entry["category"] for entry in scores}
    # De los que ya existen se guarda el jugador y los puntos: al confirmar se actualizan.
    existing = [{"snp_name": snp_name, "category": category[snp_name], "player": str(player),
                 "player_id": player.pk, "score": score}
                for player, score, snp_name in matched]
    existing += [{"snp_name": name, "category": category[name], "player": _("varios jugadores con un nombre parecido")}
                 for name in ambiguous]
    to_add = []
    for snp_name in unmatched:
        name, last_name = split_snp_name(snp_name)
        if name:
            to_add.append({"name": name, "last_name": last_name, "snp_name": snp_name,
                           "category": category[snp_name], "score": by_name[snp_name]["score"]})
    to_add.sort(key=lambda p: (p["name"], p["last_name"]))
    existing.sort(key=lambda p: p["snp_name"])
    return to_add, existing


def plan_group_teams(club, group_teams):
    """
    (a_crear, ya_existentes) comparando los equipos del grupo de SNP con los del club. Un equipo
    se considera ya existente si su nombre es igual o muy parecido al de alguno del club
    (``core.similarity``): no se duplica, solo se da de alta en el grupo si no lo estaba. El que
    SNP marca como propio (``own``) solo se crea con ``own`` si el club no tiene equipo propio.
    """
    from team.models import Team

    teams = list(Team.objects.filter(club=club))
    to_create, existing = [], []
    for entry in group_teams or []:
        match = next((t for t in teams if is_same_team(entry["name"], t.name)), None)
        if match is None:
            to_create.append({"snp_id": entry["snp_id"], "name": entry["name"], "own": bool(entry.get("own"))})
            continue
        existing.append({"snp_id": entry["snp_id"], "name": entry["name"], "team": match.name, "team_id": match.pk,
                         "in_group": match.in_group, "own": bool(entry.get("own"))})
    to_create.sort(key=lambda t: t["name"].lower())
    return to_create, existing


def _create_group_teams(club, teams_to_add, teams_existing):
    """
    Crea los equipos del grupo que faltan (género, nacionalidad, división y sede del equipo
    propio) y da de alta en el grupo los que ya existían fuera de él. Si el club no tiene equipo
    propio, el que SNP marca como propio lo será. Devuelve los nombres de los equipos creados.
    """
    from team.models import Team

    own = club.own_team
    base = {f: getattr(own, f) for f in ("gender", "country", "division", "location")} if own else {"location": ""}
    has_own = own is not None
    created = []
    for entry in teams_to_add:
        division = base.get("division", "")
        clash = Team.objects.filter(club=club, division__in=[division, ""]) if division else Team.objects.filter(club=club)
        if any(same_name(entry["name"], t.name) for t in clash):
            continue  # creado mientras tanto, o repetido en la división
        make_own = bool(entry.get("own")) and not has_own
        Team.objects.create(club=club, name=entry["name"], in_group=True, is_own=make_own, **base)
        has_own = has_own or make_own
        created.append(entry["name"])
    for entry in teams_existing:
        team = Team.objects.filter(club=club, pk=entry.get("team_id")).first()
        if team is None:
            continue
        if entry.get("own") and not has_own:
            team.is_own, has_own = True, True
        if not team.in_group or team.is_own:
            team.in_group = True
            team.save()
    return created


def _save_progress(pk, percent, text):
    """
    Guarda el avance de una búsqueda. El navegador corre con un bucle de eventos en su hilo y ahí Django
    no deja usar la base de datos: en ese caso se escribe desde un hilo aparte. Un fallo al guardar el
    avance nunca debe romper la búsqueda.
    """
    def write():
        """Escribe el avance y cierra las conexiones del hilo."""
        try:
            SnpTeamImport.objects.filter(pk=pk, status=SnpTeamImport.RUNNING).update(progress=percent, stage=text)
        except Exception:
            logger.warning("No se ha podido guardar el avance de la búsqueda %s", pk, exc_info=True)
        finally:
            if threading.current_thread() is not threading.main_thread():
                from django.db import connections
                connections.close_all()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        write()  # sin bucle de eventos: se escribe aquí mismo
        return
    worker = threading.Thread(target=write, name="snp-import-progress")
    worker.start()
    worker.join()


def search(team_import, scraper=None, **scrape_options):
    """Descarga el equipo de SNP y guarda en ``team_import`` qué se añadiría. Nunca lanza."""
    account = getattr(team_import.club, "snp_account", None)
    service_off = False
    try:
        if not snp_service.is_enabled():
            service_off = True  # SNP apagado a mano: no es culpa del club, no cuenta como fallo
            raise SnpScrapeError(str(snp_service.UNAVAILABLE_MESSAGE))
        if account is None:
            raise SnpScrapeError(_("El club no tiene cuenta SNP."), kind=SnpScrapeError.ACCOUNT)
        def progress(percent, text):
            """Guarda el avance para la barra de progreso (solo mientras sigue en marcha)."""
            _save_progress(team_import.pk, percent, text)
        progress(5, _("Conectando con SNP"))
        result = (scraper or scrape_scores)(account.username, account.password, account.team_id or None,
                                            with_group_teams=True, progress=progress,
                                            **team_options(account.club), **scrape_options)
        # Un scraper sin equipos del grupo devuelve solo los jugadores.
        scores, group_teams = result if isinstance(result, tuple) else (result, [])
    except (SnpScrapeError, DecryptionError) as exc:
        kind = exc.kind if isinstance(exc, SnpScrapeError) else SnpScrapeError.ACCOUNT
        changes = {"status": SnpTeamImport.ERROR, "message": str(exc), "error_kind": kind, "finished_at": timezone.now()}
        if getattr(exc, "retryable", False):
            snp_service.report_failure(str(exc))
    else:
        snp_service.report_success()
        to_add, existing = plan_import(team_import.club, scores)
        teams_to_add, teams_existing = plan_group_teams(team_import.club, group_teams)
        changes = {"status": SnpTeamImport.READY, "to_add": to_add, "existing": existing,
                   "teams_to_add": teams_to_add, "teams_existing": teams_existing,
                   "progress": 95, "stage": _("Creando jugadores y equipos")}
    # Solo si sigue en marcha: el capitán puede haberla cancelado mientras tanto.
    updated = SnpTeamImport.objects.filter(pk=team_import.pk, status=SnpTeamImport.RUNNING).update(**changes)
    team_import.refresh_from_db()
    if updated and changes["status"] == SnpTeamImport.ERROR:
        _register_failure(team_import, service_off)
    return team_import


def has_changes(team_import):
    """True si confirmar ``team_import`` hace algo: añadir jugadores o equipos, o actualizar lo que ya está."""
    return (bool(team_import.to_add) or bool(team_import.teams_to_add)
            or any(not e.get("in_group") for e in team_import.teams_existing)
            or any(e.get("player_id") for e in team_import.existing))


def _update_existing_scores(club, existing):
    """Actualiza los puntos SNP de los jugadores ya registrados; devuelve cuántos. Solo toca los puntos."""
    players = Player.objects.in_bulk([e["player_id"] for e in existing if e.get("player_id")])
    updated = 0
    for entry in existing:
        player = players.get(entry.get("player_id"))
        if player is not None and player.club_id == club.pk and entry.get("score") is not None:
            save_score(player, entry["score"])
            updated += 1
    return updated


def same_player_options(club):
    """
    Jugadores de la plantilla sin puntos SNP (p. ej. copiados de LAPI con otro nombre): en
    «Completar equipo» el capitán puede decir que un nombre nuevo de SNP es uno de ellos.
    """
    return list(Player.objects.filter(club=club, in_team=True, snp_score__isnull=True).order_by("name", "last_name"))


@transaction.atomic
def confirm(team_import, same=None):
    """
    Crea los jugadores pendientes de ``team_import`` y actualiza los puntos SNP de los que
    ya estaban. Antes vuelve a comprobar que los nuevos no existan (alguien puede haberlos
    creado entre la búsqueda y la confirmación). De un jugador existente solo cambian los
    puntos SNP, nunca el nombre, la posición ni el resto de sus datos.

    ``same`` ({nombre en SNP: id de jugador}) son los que el capitán ha dicho que ya están en
    el equipo con otro nombre («¿Es el mismo jugador?», p. ej. copiados de LAPI): no se crean y
    ese jugador recibe los puntos.
    """
    team_import = SnpTeamImport.objects.select_for_update().get(pk=team_import.pk)
    if team_import.status != SnpTeamImport.READY:
        return team_import
    club = team_import.club
    entries = [{"name": e["snp_name"], "score": e["score"]} for e in team_import.to_add]
    still_missing = {e["snp_name"] for e in plan_import(club, entries)[0]}
    created, today, season = [], timezone.localdate(), current_season()
    chosen = Player.objects.in_bulk([pid for pid in (same or {}).values()])
    for entry in team_import.to_add:
        player = chosen.get((same or {}).get(entry["snp_name"]))
        if player is not None and player.club_id == club.pk:
            team_import.existing.append({"snp_name": entry["snp_name"], "category": entry.get("category", ""),
                                         "player": str(player), "player_id": player.pk, "score": entry["score"]})
            continue
        if entry["snp_name"] not in still_missing:
            team_import.existing.append({"snp_name": entry["snp_name"], "player": _("creado mientras tanto")})
            continue
        player = Player.objects.create(
            club=club, team=club.own_team, name=entry["name"], last_name=entry["last_name"],
            snp_score=entry["score"], in_team=True,
        )
        SnpScoreHistory.objects.get_or_create(player=player, date=today, defaults={"score": entry["score"], "season": season})
        created.append(str(player))
    updated = _update_existing_scores(club, team_import.existing)
    team_import.created_teams = _create_group_teams(club, team_import.teams_to_add, team_import.teams_existing)
    team_import.created_players = created
    team_import.status = SnpTeamImport.DONE
    team_import.progress, team_import.stage = 100, _("Equipo sincronizado")
    team_import.finished_at = timezone.now()
    team_import.message = ngettext("%(n)s jugador añadido.", "%(n)s jugadores añadidos.", len(created)) % {"n": len(created)}
    if team_import.created_teams:
        team_import.message += " " + ngettext("%(n)s equipo del grupo añadido.", "%(n)s equipos del grupo añadidos.",
                                              len(team_import.created_teams)) % {"n": len(team_import.created_teams)}
    if updated:
        team_import.message += " " + ngettext(
            "Puntos SNP actualizados de %(n)s jugador que ya estaba.",
            "Puntos SNP actualizados de %(n)s jugadores que ya estaban.", updated) % {"n": updated}
    team_import.save()
    return team_import


@transaction.atomic
def apply_group_teams(team_import):
    """
    Como ``confirm`` pero solo con los equipos del grupo: crea los que faltan y da de alta en el
    grupo los existentes, sin crear jugadores ni tocar sus puntos. Es el proceso «add_group_teams»
    del back-office.
    """
    team_import = SnpTeamImport.objects.select_for_update().get(pk=team_import.pk)
    if team_import.status != SnpTeamImport.READY:
        return team_import
    team_import.created_teams = _create_group_teams(team_import.club, team_import.teams_to_add, team_import.teams_existing)
    team_import.status = SnpTeamImport.DONE
    team_import.finished_at = timezone.now()
    team_import.message = ngettext("%(n)s equipo del grupo añadido.", "%(n)s equipos del grupo añadidos.",
                                   len(team_import.created_teams)) % {"n": len(team_import.created_teams)}
    team_import.save()
    return team_import


# ---------- Límites (solo desde la web del club) ----------

def is_unlimited(club):
    """
    True si el club no tiene límites en «Completar equipo»: el personal lo ha marcado así en el
    back-office (``Club.snp_unlimited``). Es para el equipo de pruebas.
    """
    return club.snp_unlimited


def search_limit(club, now=None):
    """
    None si el club puede lanzar ahora otra búsqueda desde la web; si no, cuándo podrá
    (datetime). Cuenta las búsquedas web hechas o fallidas, no las canceladas ni las rechazadas por la
    cuenta SNP que el capitán ya ha corregido: así pulsar el botón muchas veces no lanza muchas
    lecturas de SNP, pero cancelar o arreglar los datos no deja bloqueado al capitán.
    """
    if is_unlimited(club):
        return None
    now = now or timezone.now()
    counted = SnpTeamImport.objects.filter(
        club=club, source=SnpTeamImport.WEB, created_at__gte=now - datetime.timedelta(days=1),
    ).exclude(status=SnpTeamImport.CANCELLED)
    # Una cuenta rechazada por SNP no cuenta una vez corregida: el capitán debe poder reintentar ya.
    account_updated = SnpAccount.objects.filter(club=club).values_list("updated_at", flat=True).first()
    if account_updated:
        counted = counted.exclude(status=SnpTeamImport.ERROR, error_kind=SnpScrapeError.ACCOUNT, created_at__lt=account_updated)
    recent = list(counted.order_by("-created_at").values_list("created_at", flat=True))
    waits = []
    if recent and now - max(recent) < SEARCH_COOLDOWN:
        waits.append(max(recent) + SEARCH_COOLDOWN)
    # Las SEARCHES_PER_DAY más recientes: hasta que la más antigua de ellas cumpla un día.
    latest = recent[:SEARCHES_PER_DAY]
    if len(latest) == SEARCHES_PER_DAY:
        waits.append(min(latest) + datetime.timedelta(days=1))
    return max(waits) if waits else None


def season_window_start(today=None):
    """
    Inicio (datetime con zona horaria) de la ventana de la temporada para «Completar equipo»: el último
    1 de julio, que es cuando el club prepara la temporada que empieza en agosto. Una búsqueda web
    correcta hecha desde entonces cuenta como la de esta temporada.
    """
    today = today or timezone.localdate()
    year = today.year if today.month >= 7 else today.year - 1
    return timezone.make_aware(datetime.datetime(year, 7, 1))


def imported_this_season(club, today=None):
    """La búsqueda web de «Completar equipo» correcta de esta temporada (desde el último 1 de julio), o None."""
    return SnpTeamImport.objects.filter(
        club=club, source=SnpTeamImport.WEB, status=SnpTeamImport.DONE, created_at__gte=season_window_start(today),
    ).first()


def web_import_done(club):
    """
    El «Completar equipo» hecho desde la web esta temporada (en el alta, desde Jugadores o preparando la
    temporada), o None si todavía no se ha hecho. Solo se puede hacer una vez por temporada: después el
    proceso lo lanza el personal o el automático. Siempre None para los clubes sin límites.
    """
    if is_unlimited(club):
        return None
    return imported_this_season(club)


def failed_web_import(club):
    """
    La última búsqueda web de «Completar equipo» del club si terminó con error o se canceló y nada
    después la arregló (ni hecha ni en curso), o None. La portada del capitán la usa para ofrecer «Reintentar».
    """
    latest = SnpTeamImport.objects.filter(club=club, source=SnpTeamImport.WEB).order_by("-created_at").first()
    if latest and latest.status in (SnpTeamImport.ERROR, SnpTeamImport.CANCELLED) and not web_import_done(club):
        return latest
    return None


def sync_task(club, this_season=False):
    """
    La tarea «Sincronizar datos» de la portada del capitán: hasta que «Completar equipo» haya devuelto
    un resultado correcto (una búsqueda web ``DONE``) hay que poder lanzarlo, seguirlo o reintentarlo.
    Con ``this_season`` solo cuenta una búsqueda correcta de esta temporada (la tarjeta «Prepara la
    temporada»). None si no hace falta (ya hecho o sin cuenta SNP). Si no, un diccionario con ``state``:
    ``running`` (en cola o buscando), ``ready`` (a la espera de confirmar), ``failed`` (error o cancelada)
    o ``idle`` (aún no se ha lanzado), más ``message``, ``blocked``, ``wait``, ``service_off`` y ``can_retry``.
    """
    if not SnpAccount.objects.filter(club=club).exists():
        return None
    if this_season:
        if imported_this_season(club):
            return None
    elif SnpTeamImport.objects.filter(club=club, source=SnpTeamImport.WEB, status=SnpTeamImport.DONE).exists():
        return None
    active = active_import(club)
    failed = None if active else failed_web_import(club)
    if active:
        state, message = ("running" if active.status == SnpTeamImport.RUNNING else "ready"), ""
    elif failed:
        state, message = "failed", failed.message
    else:
        state, message = "idle", ""
    blocked, wait, service_off = web_blocked(club), search_limit(club), not snp_service.is_enabled()
    same_account = account_unchanged_after_failure(club)
    own = club.own_team
    team_fix_url = reverse("edit_team", args=[own.public_id]) if failed and failed.error_kind == SnpScrapeError.TEAM and own else ""
    return {"team_fix_url": team_fix_url,
        "state": state, "message": message, "import": active or failed, "blocked": blocked, "wait": wait,
        "service_off": service_off, "same_account": same_account,
        "can_retry": not (blocked or wait or service_off or same_account),
    }


def account_unchanged_after_failure(club):
    """
    True si la última búsqueda web falló porque SNP rechazó el usuario o la contraseña y la cuenta SNP
    sigue igual desde entonces: repetirla con los mismos datos fallaría igual (y arriesga el bloqueo de la cuenta).
    """
    latest = SnpTeamImport.objects.filter(club=club, source=SnpTeamImport.WEB).order_by("-created_at").first()
    if not (latest and latest.status == SnpTeamImport.ERROR and latest.error_kind == SnpScrapeError.ACCOUNT):
        return False
    account_updated = SnpAccount.objects.filter(club=club).values_list("updated_at", flat=True).first()
    return account_updated is None or account_updated <= latest.created_at


def web_blocked(club):
    """True si la web ya no ofrece «Completar equipo» por fallos repetidos (se avisó al personal)."""
    return not is_unlimited(club) and club.snp_import_failures >= MAX_FAILED_SEARCHES


def _register_failure(team_import, service_off):
    """
    Cuenta un fallo de una búsqueda web (no si SNP estaba apagado a mano). Al llegar al máximo anota el
    bloqueo en la auditoría y avisa por correo al personal para que revise el proceso.
    """
    from core.models import Club
    if team_import.source != SnpTeamImport.WEB or service_off:
        return
    Club.objects.filter(pk=team_import.club_id).update(snp_import_failures=F("snp_import_failures") + 1)
    club = Club.objects.get(pk=team_import.club_id)
    if club.snp_import_failures == MAX_FAILED_SEARCHES:
        try:
            _notify_staff(club, team_import.message)
        except Exception:  # el aviso al personal nunca debe tapar el motivo real del fallo
            logger.exception("No se ha podido avisar al personal del bloqueo de %s", club)


def _notify_staff(club, reason):
    """Avisa al personal de que a un club se le ha cerrado «Completar equipo» tras varios fallos."""
    from backoffice.alerts import _send
    from backoffice.audit import audit
    audit(None, "club.snp_import_blocked", club, reason=reason[:300], failures=club.snp_import_failures)
    text = _("El club %(club)s ha fallado %(n)s veces en «Completar equipo» (último error: %(reason)s). "
             "Se le ha ocultado la opción: revisa su equipo y su cuenta SNP en el back-office.") % {
        "club": club.name, "n": club.snp_import_failures, "reason": reason}
    _send(_("Zyra · «Completar equipo» bloqueado en %(club)s") % {"club": club.name}, text)


# ---------- Búsqueda en segundo plano desde la web ----------

def active_import(club, now=None):
    """
    La búsqueda en cola, en curso o pendiente de confirmar del club, si la hay. Una en curso que
    lleva más de ``STALE_AFTER`` o una en cola que lleva más de ``QUEUE_STALE_AFTER`` sin que la
    recoja el proceso programado se dan por perdidas.
    """
    now = now or timezone.now()
    current = SnpTeamImport.objects.filter(
        club=club, source=SnpTeamImport.WEB, status__in=[SnpTeamImport.RUNNING, SnpTeamImport.READY],
    ).first()
    if current and current.status == SnpTeamImport.RUNNING:
        stale = (now - current.started_at > STALE_AFTER) if current.started_at else (now - current.created_at > QUEUE_STALE_AFTER)
        if stale:
            current.status = SnpTeamImport.ERROR
            current.message = _("La búsqueda en SNP no ha terminado. Vuelve a intentarlo.")
            current.finished_at = now
            current.save(update_fields=["status", "message", "finished_at"])
            return None
    return current


def _search_and_maybe_confirm(team_import, auto_confirm):
    """Busca y, con ``auto_confirm``, confirma en el acto lo encontrado (alta del club con cuenta SNP)."""
    team_import = search(team_import)
    if auto_confirm and team_import.status == SnpTeamImport.READY:
        team_import = confirm(team_import)
    return team_import


def _run(team_import):
    """
    Ejecuta una búsqueda ya cogida de la cola. Si algo inesperado falla, la marca como errónea
    para que la página deje de esperar. Al terminar cierra las conexiones a la base de datos del hilo.
    """
    try:
        return _search_and_maybe_confirm(team_import, team_import.auto_confirm)
    except Exception:
        logger.exception("Ha fallado la búsqueda de «Completar equipo» de %s", team_import.club)
        # Solo si sigue en marcha: si ya quedó con su error real, no se tapa con uno genérico.
        SnpTeamImport.objects.filter(pk=team_import.pk, status=SnpTeamImport.RUNNING).update(
            status=SnpTeamImport.ERROR, message=_("Error inesperado al leer SNP."), finished_at=timezone.now(),
        )
        team_import.refresh_from_db()
        return team_import


def start_search(club, user, auto_confirm=False):
    """
    Pone en cola la búsqueda de «Completar equipo» (la página va preguntando cómo va) y la recoge
    el proceso programado ``process_snp_imports``. Con ``auto_confirm`` se confirma sola al
    terminar: es la del alta del club con cuenta SNP.
    """
    team_import = SnpTeamImport.objects.create(
        club=club, started_by=user, source=SnpTeamImport.WEB, auto_confirm=auto_confirm,
    )
    if getattr(settings, "SNP_IMPORT_INLINE", False):  # tests
        team_import.started_at = timezone.now()
        team_import.save(update_fields=["started_at"])
        return _run(team_import)
    _wake_queue()
    return team_import


def _wake_queue():
    """
    Hace que la búsqueda recién puesta en cola empiece cuanto antes en vez de esperar a la pasada
    del minuto. Con el lanzador en marcha pide una ejecución de ``process_snp_imports`` (la recoge
    en su próxima pasada, como mucho en segundos); sin lanzador (desarrollo) la atiende en un hilo.
    """
    from backoffice.models import ScheduledJob
    from backoffice.scheduler import scheduler_is_alive
    if getattr(settings, "TESTING", False):
        return
    if scheduler_is_alive():
        ScheduledJob.objects.filter(
            name="process_snp_imports", running_since__isnull=True, run_requested_at__isnull=True,
        ).update(run_requested_at=timezone.now())
        return

    def target():
        """Cuerpo del hilo: atiende la cola y cierra sus conexiones a la base de datos."""
        from django.db import connections
        try:
            process_queue(max_items=1)
        finally:
            connections.close_all()

    threading.Thread(target=target, name="snp-import-queue", daemon=True).start()


def claim_next():
    """
    Coge de la cola la búsqueda web más antigua que nadie ha empezado y la marca como empezada
    (devuelve None si no hay). Es atómico: dos procesos nunca cogen la misma.
    """
    for candidate in SnpTeamImport.objects.filter(
        source=SnpTeamImport.WEB, status=SnpTeamImport.RUNNING, started_at__isnull=True,
    ).order_by("created_at", "pk"):
        claimed = SnpTeamImport.objects.filter(
            pk=candidate.pk, status=SnpTeamImport.RUNNING, started_at__isnull=True,
        ).update(started_at=timezone.now())
        if claimed:
            candidate.refresh_from_db()
            return candidate
    return None


def process_queue(max_items=10, log=None):
    """
    Atiende de una en una las búsquedas en cola (como mucho ``max_items``) y devuelve cuántas ha
    hecho. Las que el capitán canceló mientras esperaban no se tocan: ``claim_next`` solo coge las
    que siguen en espera.
    """
    log = log or (lambda message: None)
    done = 0
    while done < max_items:
        team_import = claim_next()
        if team_import is None:
            break
        log(f"Búsqueda de {team_import.club}…")
        team_import = _run(team_import)
        log(f"  {team_import.get_status_display()}: {team_import.message}")
        done += 1
    return done
