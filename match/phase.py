"""
Fase de un enfrentamiento: una única regla para saber en qué punto del ciclo está y cuál es
el siguiente paso (convocatoria, parejas, resultados, acta). La usan la página del partido,
el inicio («Pendiente») y el listado, para que todas digan lo mismo.

Estado visible (``MatchPhase.label``): dice lo que falta y es el mismo en la ficha, el listado, el
calendario y el inicio: «Por convocar», «Convocatoria abierta», «Por alinear», «Faltan 2 resultados»,
«Acta por cerrar» y «Acta cerrada».
"""
from dataclasses import dataclass

from django.db.models import Count
from django.utils.translation import gettext_lazy as _, ngettext

from call.models import Call
from core.competitions import competition_for, get_competition
from core.models import Club
from .models import Game, Result

DRAFT, CALLED, LINED_UP, PLAYED, CLOSED = "draft", "called", "lined_up", "played", "closed"

# Siguiente acción de cada estado (clave que interpretan las plantillas y el inicio).
CREATE_CALL, CLOSE_CALL, CREATE_GAMES, ENTER_RESULTS, CLOSE_MATCH, NOTHING = (
    "create_call", "close_call", "create_games", "enter_results", "close_match", "nothing")

# Estado visible de cada siguiente acción (el de «Poner resultados» lleva cuántos faltan: MatchPhase.label).
ACTION_LABELS = {
    CREATE_CALL: _("Por convocar"),
    CLOSE_CALL: _("Convocatoria abierta"),
    CREATE_GAMES: _("Por alinear"),
    CLOSE_MATCH: _("Acta por cerrar"),
    NOTHING: _("Acta cerrada"),
}

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
        """Estado para mostrar, según lo que falta: «Por convocar», «Convocatoria abierta», «Faltan 2 resultados»..."""
        if self.action == ENTER_RESULTS:
            missing = max(self.total_games - self.results, 0)
            return ngettext("Falta %(n)s resultado", "Faltan %(n)s resultados", missing) % {"n": missing}
        return ACTION_LABELS[self.action]

    @property
    def missing_players(self):
        """Convocados que faltan para poder cerrar la convocatoria (0 si ya hay suficientes)."""
        return max(self.min_call - self.called, 0)

    @property
    def pending_label(self):
        """
        Siguiente acción con su progreso, con cada número explicado: «Cerrar convocatoria · 8 apuntados
        (mín. 6)», «Faltan 2 para cerrar la convocatoria (4 de 6)», «Poner resultados · faltan 2»...
        """
        if self.action == CREATE_CALL:
            return _("Convocar")
        if self.action == CLOSE_CALL:
            if self.missing_players:
                return ngettext(
                    "Falta %(missing)s para cerrar la convocatoria (%(n)s de %(total)s)",
                    "Faltan %(missing)s para cerrar la convocatoria (%(n)s de %(total)s)",
                    self.missing_players) % {"missing": self.missing_players, "n": self.called, "total": self.min_call}
            return ngettext("Cerrar convocatoria · %(n)s apuntado (mín. %(total)s)",
                            "Cerrar convocatoria · %(n)s apuntados (mín. %(total)s)",
                            self.called) % {"n": self.called, "total": self.min_call}
        if self.action == CREATE_GAMES:
            return _("Alinear parejas")
        if self.action == ENTER_RESULTS:
            missing = max(self.total_games - self.results, 0)
            return ngettext("Poner resultados · falta %(n)s", "Poner resultados · faltan %(n)s", missing) % {"n": missing}
        if self.action == CLOSE_MATCH:
            return _("Cerrar acta")
        return ""


def phase_of(match, *, has_call, call_closed, called, games, results, competition=None):
    """Fase de ``match`` a partir de los recuentos de su convocatoria, partidos y resultados.

    ``competition`` es la ficha de su competición; si no se da, se pide a ``competition_for``.
    """
    competition = competition or competition_for(match)
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
    Hace cuatro consultas en total, sea cual sea el número de enfrentamientos.
    """
    matches = list(matches)
    ids = [m.id for m in matches]
    club_rules = {pk: get_competition(code) for pk, code in
                  Club.objects.filter(pk__in={m.club_id for m in matches}).values_list("pk", "competition")}
    calls = {c.match_id: c for c in Call.objects.filter(match_id__in=ids).annotate(n_players=Count("players"))}
    games = dict(Game.objects.filter(match_id__in=ids).values_list("match_id").annotate(n=Count("id")))
    results = dict(Result.objects.filter(game__match_id__in=ids).values_list("game__match_id").annotate(n=Count("game_id", distinct=True)))
    phases = {}
    for m in matches:
        call = calls.get(m.id)
        phases[m.id] = phase_of(
            m, has_call=bool(call), call_closed=bool(call and not call.draft_mode),
            called=call.n_players if call else 0, games=games.get(m.id, 0), results=results.get(m.id, 0),
            competition=club_rules.get(m.club_id),
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
