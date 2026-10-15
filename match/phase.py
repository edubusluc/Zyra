"""
Fase de un enfrentamiento: una única regla para saber en qué punto del ciclo está y cuál es
el siguiente paso (convocatoria, parejas, resultados, acta). La usan la página del partido,
el inicio («Pendiente») y el listado, para que todas digan lo mismo.

Estados (una palabra): borrador, convocado, alineado, jugado y acta cerrada.
"""
from dataclasses import dataclass

from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from call.models import Call
from .lineup import GAMES_PER_MATCH
from .models import Game, Result

# Convocados mínimos para cerrar la convocatoria y alinear parejas.
MIN_CALL_PLAYERS = 10

DRAFT, CALLED, LINED_UP, PLAYED, CLOSED = "draft", "called", "lined_up", "played", "closed"
STATE_LABELS = {
    DRAFT: _("Borrador"),
    CALLED: _("Convocado"),
    LINED_UP: _("Alineado"),
    PLAYED: _("Jugado"),
    CLOSED: _("Acta cerrada"),
}

# Siguiente acción de cada estado (clave que interpretan las plantillas y el inicio).
CREATE_CALL, CLOSE_CALL, CREATE_GAMES, ENTER_RESULTS, CLOSE_MATCH, NOTHING = (
    "create_call", "close_call", "create_games", "enter_results", "close_match", "nothing")

# Pasos del indicador de fases, en orden.
STEPS = (_("Convocatoria"), _("Parejas"), _("Resultados"), _("Acta"))


@dataclass(frozen=True)
class MatchPhase:
    """Fase de un enfrentamiento: estado, paso actual (0-3; 4 = todo hecho) y siguiente acción."""
    state: str
    step: int
    action: str
    has_call: bool
    called: int
    games: int
    results: int

    @property
    def label(self):
        """Palabra de estado para mostrar («Borrador», «Convocado»...)."""
        return STATE_LABELS[self.state]

    @property
    def missing_players(self):
        """Convocados que faltan para poder cerrar la convocatoria (0 si ya hay suficientes)."""
        return max(MIN_CALL_PLAYERS - self.called, 0)

    @property
    def pending_label(self):
        """Siguiente acción con su progreso: «Cerrar convocatoria (8/10)», «Poner resultados (3/5)»..."""
        if self.action == CREATE_CALL:
            return _("Convocar")
        if self.action == CLOSE_CALL:
            return _("Cerrar convocatoria (%(n)s/%(total)s)") % {"n": self.called, "total": MIN_CALL_PLAYERS}
        if self.action == CREATE_GAMES:
            return _("Alinear parejas")
        if self.action == ENTER_RESULTS:
            return _("Poner resultados (%(n)s/%(total)s)") % {"n": self.results, "total": GAMES_PER_MATCH}
        if self.action == CLOSE_MATCH:
            return _("Cerrar acta")
        return ""


def phase_of(match, *, has_call, call_closed, called, games, results):
    """Fase de ``match`` a partir de los recuentos de su convocatoria, partidos y resultados."""
    if not match.draft_mode:
        return MatchPhase(CLOSED, 4, NOTHING, has_call, called, games, results)
    if games >= GAMES_PER_MATCH and results >= GAMES_PER_MATCH:
        return MatchPhase(PLAYED, 3, CLOSE_MATCH, has_call, called, games, results)
    if games:
        return MatchPhase(LINED_UP, 2, ENTER_RESULTS, has_call, called, games, results)
    if has_call and call_closed:
        return MatchPhase(CALLED, 1, CREATE_GAMES, has_call, called, games, results)
    if has_call:
        return MatchPhase(DRAFT, 0, CLOSE_CALL, has_call, called, games, results)
    return MatchPhase(DRAFT, 0, CREATE_CALL, has_call, called, games, results)


def phases_for(matches):
    """
    Fase de cada enfrentamiento de ``matches`` (iterable): ``{match.id: MatchPhase}``.
    Hace tres consultas en total, sea cual sea el número de enfrentamientos.
    """
    matches = list(matches)
    ids = [m.id for m in matches]
    calls = {c.match_id: c for c in Call.objects.filter(match_id__in=ids).annotate(n_players=Count("players"))}
    games = dict(Game.objects.filter(match_id__in=ids).values_list("match_id").annotate(n=Count("id")))
    results = dict(Result.objects.filter(game__match_id__in=ids).values_list("game__match_id").annotate(n=Count("game_id", distinct=True)))
    phases = {}
    for m in matches:
        call = calls.get(m.id)
        phases[m.id] = phase_of(
            m, has_call=bool(call), call_closed=bool(call and not call.draft_mode),
            called=call.n_players if call else 0, games=games.get(m.id, 0), results=results.get(m.id, 0),
        )
    return phases


def phase_for(match):
    """Fase de un solo enfrentamiento."""
    return phases_for([match])[match.id]


def player_status(player, call, games):
    """
    Qué le toca a un jugador en un enfrentamiento: ``{"has_call", "called", "closed", "game",
    "partner"}`` (la pareja y el partido solo existen cuando ya están alineadas). ``games`` son
    los partidos del enfrentamiento con sus jugadores cargados.
    """
    game = next((g for g in games if player.id in (
        g.player_1_local_id, g.player_2_local_id, g.player_1_visiting_id, g.player_2_visiting_id)), None)
    partner = None
    if game:
        partner = next((p for p in (game.player_1_local, game.player_2_local, game.player_1_visiting,
                                    game.player_2_visiting) if p and p.id != player.id), None)
    return {
        "has_call": bool(call),
        "called": bool(call and call.players.filter(id=player.id).exists()),
        "closed": bool(call and not call.draft_mode),
        "game": game,
        "partner": partner,
    }
