"""
«Completar equipo»: da de alta en Zyra los jugadores del equipo de SNP del club que
todavía no existen. De los que ya están (aunque se escriban algo distinto, con el mismo
criterio que la actualización de puntos) solo se actualizan los puntos SNP: su nombre,
posición y demás datos no se tocan.

Desde la web del club se hace en dos pasos (buscar y confirmar), solo una vez al mes y
con un máximo de búsquedas para no saturar SNP (``search_limit``); desde el back-office
(comando ``complete_snp_team``) en uno solo y sin esos límites. Los clubes de
``settings.SNP_IMPORT_UNLIMITED_CLUBS`` (el equipo de pruebas) no tienen límites.
"""
import datetime
import logging
import threading

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext

from core.crypto import DecryptionError

from .models import Player, SnpScoreHistory, SnpTeamImport, current_season
from .scraper import SnpScrapeError, scrape_scores
from core.similarity import same_name

from .snp import team_options, match_scores, save_score, split_category

logger = logging.getLogger(__name__)

# Partículas que van unidas al apellido siguiente: "de la Fuente".
PARTICLES = {"de", "del", "la", "las", "los", "y", "san", "van", "von", "da", "do", "dos", "di"}
# Si una búsqueda lleva más de esto «en marcha», se da por perdida (p. ej. se reinició el servidor).
STALE_AFTER = datetime.timedelta(minutes=10)
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


def search(team_import, scraper=None, **scrape_options):
    """Descarga el equipo de SNP y guarda en ``team_import`` qué se añadiría. Nunca lanza."""
    account = getattr(team_import.club, "snp_account", None)
    try:
        if account is None:
            raise SnpScrapeError(_("El club no tiene cuenta SNP."), kind=SnpScrapeError.ACCOUNT)
        scores = (scraper or scrape_scores)(account.username, account.password, account.team_id or None,
                                          **team_options(account.club), **scrape_options)
    except (SnpScrapeError, DecryptionError) as exc:
        kind = exc.kind if isinstance(exc, SnpScrapeError) else SnpScrapeError.ACCOUNT
        changes = {"status": SnpTeamImport.ERROR, "message": str(exc), "error_kind": kind, "finished_at": timezone.now()}
    else:
        to_add, existing = plan_import(team_import.club, scores)
        changes = {"status": SnpTeamImport.READY, "to_add": to_add, "existing": existing}
    # Solo si sigue en marcha: el capitán puede haberla cancelado mientras tanto.
    SnpTeamImport.objects.filter(pk=team_import.pk, status=SnpTeamImport.RUNNING).update(**changes)
    team_import.refresh_from_db()
    return team_import


def has_changes(team_import):
    """True si confirmar ``team_import`` hace algo: añadir jugadores o actualizar puntos de los que ya están."""
    return bool(team_import.to_add) or any(e.get("player_id") for e in team_import.existing)


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
    team_import.created_players = created
    team_import.status = SnpTeamImport.DONE
    team_import.finished_at = timezone.now()
    team_import.message = ngettext("%(n)s jugador añadido.", "%(n)s jugadores añadidos.", len(created)) % {"n": len(created)}
    if updated:
        team_import.message += " " + ngettext(
            "Puntos SNP actualizados de %(n)s jugador que ya estaba.",
            "Puntos SNP actualizados de %(n)s jugadores que ya estaban.", updated) % {"n": updated}
    team_import.save()
    return team_import


# ---------- Límites (solo desde la web del club) ----------

def is_unlimited(club):
    """
    True si el club no tiene límites en «Completar equipo»: su nombre (o el de su equipo
    propio) está en ``settings.SNP_IMPORT_UNLIMITED_CLUBS``, sin distinguir mayúsculas ni tildes.
    Es para el equipo de pruebas (Los Gladiadores).
    """
    names = [club.name] + ([club.own_team.name] if club.own_team else [])
    return any(same_name(name, allowed) for name in names for allowed in getattr(settings, "SNP_IMPORT_UNLIMITED_CLUBS", ()))


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
    """La búsqueda en curso o pendiente de confirmar del club, si la hay."""
    now = now or timezone.now()
    current = SnpTeamImport.objects.filter(
        club=club, source=SnpTeamImport.WEB, status__in=[SnpTeamImport.RUNNING, SnpTeamImport.READY],
    ).first()
    if current and current.status == SnpTeamImport.RUNNING and now - current.created_at > STALE_AFTER:
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


def start_search(club, user, auto_confirm=False):
    """
    Crea la búsqueda y la lanza en segundo plano (la página va preguntando cómo va). Con
    ``auto_confirm`` se confirma sola al terminar: es la del alta del club con cuenta SNP.
    """
    team_import = SnpTeamImport.objects.create(club=club, started_by=user, source=SnpTeamImport.WEB)
    if getattr(settings, "SNP_IMPORT_INLINE", False):  # tests
        return _search_and_maybe_confirm(team_import, auto_confirm)

    def target():
        """
        Hilo de la búsqueda: si algo inesperado falla, la marca como errónea para que la página
        deje de esperar. Al terminar cierra sus conexiones a la base de datos.
        """
        try:
            _search_and_maybe_confirm(team_import, auto_confirm)
        except Exception:
            logger.exception("Ha fallado la búsqueda de «Completar equipo» de %s", club)
            SnpTeamImport.objects.filter(pk=team_import.pk).update(
                status=SnpTeamImport.ERROR, message=_("Error inesperado al leer SNP."), finished_at=timezone.now(),
            )
        finally:
            connections.close_all()

    threading.Thread(target=target, name=f"snp-import-{club.pk}", daemon=True).start()
    return team_import
