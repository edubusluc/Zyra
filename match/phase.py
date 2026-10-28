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
from core.competitions import competition_for
from .models import Game, Result

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
    """Fase de un enfrentamiento: estado, paso actual (0-3; 4 = todo hecho) y siguiente acción.

    ``min_call`` y ``total_games`` vienen de la ficha de la competición del enfrentamiento.
    """
    state: str
    step: int
    action: str
    has_call: bool
    called: int
    games: int
    results: int
    min_call: int
    total_games: int

    @property
    def label(self):
        """Palabra de estado para mostrar («Borrador», «Convocado»...)."""
        return STATE_LABELS[self.state]

    @property
    def missing_players(self):
        """Convocados que faltan para poder cerrar la convocatoria (0 si ya hay suficientes)."""
        return max(self.min_call - self.called, 0)

    @property
    def pending_label(self):
        """Siguiente acción con su progreso: «Cerrar convocatoria (8/10)», «Poner resultados (3/5)»..."""
        if self.action == CREATE_CALL:
            return _("Convocar")
        if self.action == CLOSE_CALL:
            return _("Cerrar convocatoria (%(n)s/%(total)s)") % {"n": self.called, "total": self.min_call}
        if self.action == CREATE_GAMES:
            return _("Alinear parejas")
        if self.action == ENTER_RESULTS:
            return _("Poner resultados (%(n)s/%(total)s)") % {"n": self.results, "total": self.total_games}
        if self.action == CLOSE_MATCH:
            return _("Cerrar acta")
        return ""


def phase_of(match, *, has_call, call_closed, called, games, results):
    """Fase de ``match`` a partir de los recuentos de su convocatoria, partidos y resultados."""
    competition = competition_for(match)
    counts = (has_call, called, games, results, competition.min_call_players, competition.games)
    if not match.draft_mode:
        return MatchPhase(CLOSED, 4, NOTHING, *counts)
    if games >= competition.games and results >= competition.games:
        return MatchPhase(PLAYED, 3, CLOSE_MATCH, *counts)
    if games:
        return MatchPhase(LINED_UP, 2, ENTER_RESULTS, *counts)
    if has_call and call_closed:
        return MatchPhase(CALLED, 1, CREATE_GAMES, *counts)
    if has_call:
        return MatchPhase(DRAFT, 0, CLOSE_CALL, *counts)
    return MatchPhase(DRAFT, 0, CREATE_CALL, *counts)


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
