"""
«Completar equipo»: da de alta en Zyra los jugadores del equipo de SNP del club que
todavía no existen. De los que ya están (aunque se escriban algo distinto, con el mismo
criterio que la actualización de puntos) solo se actualizan los puntos SNP: su nombre,
posición y demás datos no se tocan.

Desde la web del club se hace en dos pasos (buscar y confirmar), solo una vez al mes y
con un máximo de búsquedas para no saturar SNP (``search_limit``); desde el back-office
(comando ``complete_snp_team``) en uno solo y sin esos límites. Los clubes que el personal marca
como ``Club.snp_unlimited`` (el equipo de pruebas) no tienen límites.

La búsqueda desde la web no se ejecuta en el proceso web: se deja en cola (``start_search``) y la
recoge el proceso programado ``process_snp_imports`` (``process_queue``), que las atiende de una
en una. Así nunca hay más de un Chromium abierto por las búsquedas de los capitanes.
"""
import datetime
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext

from core.crypto import DecryptionError

from .models import Player, SnpScoreHistory, SnpTeamImport, current_season
from . import snp_service
from .scraper import SnpScrapeError, scrape_scores
from core.similarity import is_similar, same_name

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
SEARCH_COOLDOWN = datetime.timedelta(minutes=5)


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
        match = next((t for t in teams if is_similar(entry["name"], t.name)), None)
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


def search(team_import, scraper=None, **scrape_options):
    """Descarga el equipo de SNP y guarda en ``team_import`` qué se añadiría. Nunca lanza."""
    account = getattr(team_import.club, "snp_account", None)
    try:
        if not snp_service.is_enabled():
            raise SnpScrapeError(str(snp_service.UNAVAILABLE_MESSAGE))
        if account is None:
            raise SnpScrapeError(_("El club no tiene cuenta SNP."), kind=SnpScrapeError.ACCOUNT)
        result = (scraper or scrape_scores)(account.username, account.password, account.team_id or None,
                                            with_group_teams=True, **team_options(account.club), **scrape_options)
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
                   "teams_to_add": teams_to_add, "teams_existing": teams_existing}
    # Solo si sigue en marcha: el capitán puede haberla cancelado mientras tanto.
    SnpTeamImport.objects.filter(pk=team_import.pk, status=SnpTeamImport.RUNNING).update(**changes)
    team_import.refresh_from_db()
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


@transaction.atomic
def confirm(team_import):
    """
    Crea los jugadores pendientes de ``team_import`` y actualiza los puntos SNP de los que
    ya estaban. Antes vuelve a comprobar que los nuevos no existan (alguien puede haberlos
    creado entre la búsqueda y la confirmación). De un jugador existente solo cambian los
    puntos SNP, nunca el nombre, la posición ni el resto de sus datos.
    """
    team_import = SnpTeamImport.objects.select_for_update().get(pk=team_import.pk)
    if team_import.status != SnpTeamImport.READY:
        return team_import
    club = team_import.club
    entries = [{"name": e["snp_name"], "score": e["score"]} for e in team_import.to_add]
    still_missing = {e["snp_name"] for e in plan_import(club, entries)[0]}
    created, today, season = [], timezone.localdate(), current_season()
    for entry in team_import.to_add:
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
    (datetime). Cuenta todas las búsquedas web, también las canceladas o fallidas: así
    pulsar el botón muchas veces no lanza muchas lecturas de SNP.
    """
    if is_unlimited(club):
        return None
    now = now or timezone.now()
    recent = list(SnpTeamImport.objects.filter(
        club=club, source=SnpTeamImport.WEB, created_at__gte=now - datetime.timedelta(days=1),
    ).order_by("-created_at").values_list("created_at", flat=True))
    waits = []
    if recent and now - max(recent) < SEARCH_COOLDOWN:
        waits.append(max(recent) + SEARCH_COOLDOWN)
    # Las SEARCHES_PER_DAY más recientes: hasta que la más antigua de ellas cumpla un día.
    latest = recent[:SEARCHES_PER_DAY]
    if len(latest) == SEARCHES_PER_DAY:
        waits.append(min(latest) + datetime.timedelta(days=1))
    return max(waits) if waits else None


def _month_start(now=None):
    """Primer instante del mes actual (o del de ``now``) en hora local."""
    local = timezone.localtime(now or timezone.now())
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def last_import_this_month(club, now=None):
    """
    Último «Completar equipo» hecho desde la web este mes, o None si todavía no se ha hecho
    (siempre None para los clubes sin límites).
    """
    if is_unlimited(club):
        return None
    return SnpTeamImport.objects.filter(
        club=club, source=SnpTeamImport.WEB, status=SnpTeamImport.DONE, finished_at__gte=_month_start(now),
    ).first()


def next_month_start(now=None):
    """Primer día del mes siguiente: cuándo se podrá volver a completar el equipo desde la web."""
    start = _month_start(now)
    return (start + datetime.timedelta(days=32)).replace(day=1)


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
        SnpTeamImport.objects.filter(pk=team_import.pk).update(
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
    return team_import


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
