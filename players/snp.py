"""
Actualización de los puntos SNP: cruza los nombres que devuelve SNP con los jugadores
del club y guarda la puntuación. Lo usan el proceso programado ``update_snp_scores``
y el botón «Actualizar ahora» de la página de la cuenta SNP.
"""
import logging
import re
import unicodedata
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext, gettext as _

from core.crypto import DecryptionError

from .models import Player, SnpScoreHistory, current_season
from .scraper import SnpBlockedError, SnpScrapeError, scrape_scores

logger = logging.getLogger(__name__)

# Coincidencia exacta > nombre completo al principio (sobra o falta el 2º apellido o la
# categoría) > nombre y primer apellido presentes.
EXACT, PREFIX, PARTIAL = 3, 2, 1


def normalize(text):
    """Sin tildes, en minúsculas y solo letras y números: 'José  Pérez-Ruíz' -> 'jose perez ruiz'."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9ñ]+", " ", text).split())


def split_category(text):
    """
    Separa la categoría que SNP pone tras el nombre del jugador:
    "PEDRO RAPOSO BELLERIN 500" -> ("PEDRO RAPOSO BELLERIN", "500");
    "ANA RUIZ GRAND SLAM" -> ("ANA RUIZ", "GRAND SLAM"); sin categoría -> (nombre, "").
    """
    tokens = (text or "").split()
    if len(tokens) > 2 and [t.upper() for t in tokens[-2:]] == ["GRAND", "SLAM"]:
        return " ".join(tokens[:-2]), "GRAND SLAM"
    if len(tokens) > 1 and (tokens[-1].isdigit() or tokens[-1].upper() == "FUTURE"):
        return " ".join(tokens[:-1]), tokens[-1].upper()
    return " ".join(tokens), ""


def _snp_tokens(name):
    """Palabras normalizadas del nombre de SNP sin la categoría del final ("500", "Future", "Grand Slam"…)."""
    return normalize(split_category(name)[0]).split()


def _match_level(player_tokens, snp_tokens):
    """
    Grado de coincidencia entre el nombre de un jugador y el de SNP (listas de palabras
    normalizadas): EXACT, PREFIX, PARTIAL o 0 si no encajan.
    """
    if not player_tokens or not snp_tokens:
        return 0
    if player_tokens == snp_tokens:
        return EXACT
    shorter = min(len(player_tokens), len(snp_tokens))
    if len(player_tokens) >= 2 and player_tokens[:shorter] == snp_tokens[:shorter] and shorter >= 2:
        return PREFIX
    if len(player_tokens) >= 2 and player_tokens[0] == snp_tokens[0] and player_tokens[1] in snp_tokens[1:]:
        return PARTIAL
    return 0


def match_scores(players, scores):
    """
    Empareja jugadores y puntuaciones de SNP. Devuelve (emparejados, sin_jugador, ambiguos):
    emparejados es una lista de (jugador, puntos, nombre_en_snp); sin_jugador, los nombres
    de SNP que no se han podido asignar; ambiguos, los que encajan igual de bien con varios.
    """
    tokens = {p.pk: normalize(f"{p.name} {p.last_name}").split() for p in players}
    candidates = []  # (nivel, jugador, entrada de SNP)
    unmatched, ambiguous = [], []
    for entry in scores:
        snp_tokens = _snp_tokens(entry["name"])
        levels = [(_match_level(tokens[p.pk], snp_tokens), p) for p in players]
        best = max((level for level, _ in levels), default=0)
        best_players = [p for level, p in levels if level == best and level > 0]
        if not best_players:
            unmatched.append(entry["name"])
        elif len(best_players) > 1:
            ambiguous.append(entry["name"])
        else:
            candidates.append((best, best_players[0], entry))

    # Un jugador solo puede recibir una puntuación: la de la coincidencia más clara.
    by_player = {}
    for level, player, entry in candidates:
        by_player.setdefault(player.pk, []).append((level, player, entry))
    matched = []
    for options in by_player.values():
        options.sort(key=lambda o: o[0], reverse=True)
        if len(options) > 1 and options[0][0] == options[1][0]:
            ambiguous.extend(o[2]["name"] for o in options)
            continue
        level, player, entry = options[0]
        matched.append((player, entry["score"], entry["name"]))
        unmatched.extend(o[2]["name"] for o in options[1:])
    return matched, unmatched, ambiguous


@dataclass
class SyncResult:
    """
    Resultado de actualizar los puntos SNP de un club. ``updated`` son pares (jugador, puntos);
    ``unmatched``, ``ambiguous`` y ``missing`` son nombres que no se han podido actualizar.
    ``retryable`` indica un fallo pasajero que se reintenta en la siguiente pasada y
    ``blocked`` que SNP nos está limitando.
    """
    ok: bool
    message: str
    total: int = 0
    updated: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)
    ambiguous: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    # Fallo pasajero que se reintenta en la siguiente pasada / SNP nos está limitando.
    retryable: bool = False
    blocked: bool = False

    def report(self):
        """Texto para el capitán: el mensaje y los nombres sin jugador, ambiguos o que faltan en SNP."""
        lines = [self.message]
        if self.unmatched:
            lines.append(_("En SNP pero sin jugador en Zyra: %(names)s") % {"names": ", ".join(self.unmatched)})
        if self.ambiguous:
            lines.append(_("Nombres que encajan con varios jugadores (no se han tocado): %(names)s") % {"names": ", ".join(self.ambiguous)})
        if self.missing:
            lines.append(_("Jugadores de Zyra que no aparecen en SNP: %(names)s") % {"names": ", ".join(self.missing)})
        return "\n".join(lines)


def team_options(club):
    """
    Datos del equipo propio que necesita el scraper: nacionalidad (vacía en equipos antiguos:
    el scraper usa España) y nombre (para elegir equipo si la cuenta SNP tiene varios).
    """
    team = club.own_team
    return {"country": team.country if team else "", "team_name": team.name if team else ""}


def sync_club(account, scraper=None, **scrape_options):
    """
    Descarga los puntos SNP del club de ``account`` y los guarda. Nunca lanza: devuelve
    un SyncResult. Los puntos del club se guardan en una sola transacción (o todos o
    ninguno), así un fallo a medias no deja el equipo con unos jugadores actualizados y
    otros no, ni afecta a los demás clubes.
    """
    try:
        scores = (scraper or scrape_scores)(account.username, account.password, account.team_id or None,
                                          **team_options(account.club), **scrape_options)
        with transaction.atomic():
            result = _save_scores(account, scores)
    except (SnpScrapeError, DecryptionError) as exc:
        result = SyncResult(ok=False, message=str(exc), retryable=getattr(exc, "retryable", False),
                            blocked=isinstance(exc, SnpBlockedError))
    except Exception as exc:  # un fallo inesperado en un club no debe parar a los demás
        logger.exception("Error inesperado al actualizar los puntos SNP de %s", account.club)
        result = SyncResult(ok=False, message=_("Error inesperado: %(error)s") % {"error": exc}, retryable=True)
    account.last_sync_at = timezone.now()
    account.last_sync_ok = result.ok
    account.last_sync_retryable = result.retryable
    account.last_sync_message = result.report()
    account.save(update_fields=["last_sync_at", "last_sync_ok", "last_sync_retryable", "last_sync_message"])
    return result


def save_score(player, score):
    """Guarda los puntos SNP de un jugador y su punto de hoy en el histórico (gráfico de la temporada)."""
    if player.snp_score != score:
        player.snp_score = score
        player.save(update_fields=["snp_score"])
    SnpScoreHistory.objects.update_or_create(
        player=player, date=timezone.localdate(), defaults={"score": score, "season": current_season()},
    )


def _save_scores(account, scores):
    """
    Guarda los puntos emparejados (y una fila de histórico por jugador y día) para los
    jugadores del equipo del club y devuelve el SyncResult. Se llama dentro de una transacción.
    """
    players = list(Player.objects.filter(club=account.club, in_team=True))
    matched, unmatched, ambiguous = match_scores(players, scores)
    for player, score, _ in matched:
        save_score(player, score)
    matched_ids = {p.pk for p, _, _ in matched}
    return SyncResult(
        ok=True,
        message=gettext("%(matched)s de %(total)s jugadores actualizados con los puntos de SNP.") % {
            "matched": len(matched), "total": len(players)},
        total=len(players),
        updated=[(str(p), score) for p, score, _ in matched],
        unmatched=unmatched, ambiguous=ambiguous,
        missing=[str(p) for p in players if p.pk not in matched_ids],
    )
