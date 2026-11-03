"""
«Pareja no presentada» (normativa SNP 2026, cap. 20.2): reparto de los puntos de un
enfrentamiento cuando alguna pareja no se presentó a su partido (``Game.no_show``).

- Si un equipo no presenta una pareja, el equipo cumplidor se lleva 6 puntos por ese partido y
  los 4 partidos jugados reparten los otros 6: 2 puntos a cada una de las dos mejores parejas
  que jugaron (las de número más bajo; la 1 es la más alta) y 1 a cada una de las otras dos.
  Si acaba 6-6, gana el equipo que ganó los 4 partidos jugados.
- Si un equipo no presenta dos parejas o más, pierde el enfrentamiento 0-12.
- Si falta la misma pareja en los dos equipos, ese partido se anula y el resto puntúa normal.
- Si cada equipo no presenta una pareja distinta, cada uno pierde la suya (6-0 / 6-0) con sus
  puntos normales y el resto puntúa normal.

``apply`` deja en cada ``Game`` los puntos (``score``) y el ganador (``winner``) que le tocan,
así las estadísticas que suman ``score`` (mayor victoria, por ejemplo) cuadran con el marcador.
"""
from . import outcomes
from .models import Game


def _side(own, match):
    """``WINNER_LOCAL`` o ``WINNER_VISITING`` del equipo propio (``own`` True) o del rival."""
    local = own == match.own_is_local
    return outcomes.WINNER_LOCAL if local else outcomes.WINNER_VISITING


def apply(match, games, rules):
    """
    Reparte los puntos de ``games`` (todos los partidos de ``match``) según sus parejas no
    presentadas y los deja en cada partido (sin guardar). Devuelve el resultado que se impone a
    los puntos (``outcomes.LOCAL_WIN``/``VISITING_WIN``) en el desempate 6-6, o None.

    Sin parejas no presentadas solo restaura los puntos normales de cada partido, por si el
    acta se reabrió y se quitó la marca.
    """
    games = sorted(games, key=lambda g: g.n_game)
    for g in games:
        g.score = rules.points_for(g.n_game)
    own_missing = [g for g in games if g.no_show in (Game.NO_SHOW_OWN, Game.NO_SHOW_BOTH)]
    rival_missing = [g for g in games if g.no_show in (Game.NO_SHOW_RIVAL, Game.NO_SHOW_BOTH)]
    if not own_missing and not rival_missing:
        return None
    total = rules.total_points
    played = [g for g in games if not g.no_show]

    # Dos parejas o más sin presentarse: el enfrentamiento se pierde entero (0-12).
    if len(own_missing) >= 2 or len(rival_missing) >= 2:
        for g in games:
            g.score = 0
        if len(own_missing) >= 2 and len(rival_missing) >= 2:
            for g in games:
                g.winner = None
            return None
        loser_missing = own_missing if len(own_missing) >= 2 else rival_missing
        winner = _side(loser_missing is rival_missing, match)
        loser_missing[0].score, loser_missing[0].winner = total, winner
        for g in loser_missing[1:]:
            g.winner = winner
        return None

    both = [g for g in games if g.no_show == Game.NO_SHOW_BOTH]
    if both:
        # La misma pareja en los dos equipos: ese partido no cuenta.
        both[0].score, both[0].winner = 0, None
        return None
    if own_missing and rival_missing:
        # Una pareja distinta en cada equipo: cada uno pierde la suya con sus puntos normales.
        own_missing[0].winner = _side(False, match)
        rival_missing[0].winner = _side(True, match)
        return None

    # Un solo equipo sin una pareja: 6 puntos al cumplidor y 2/2/1/1 en los partidos jugados.
    missing = (own_missing or rival_missing)[0]
    keeper_is_own = bool(rival_missing)
    missing.score, missing.winner = total // 2, _side(keeper_is_own, match)
    for i, g in enumerate(played):
        g.score = 2 if i < 2 else 1
    infractor = _side(not keeper_is_own, match)
    if len(played) == 4 and all(g.winner == infractor for g in played):
        # 6-6: gana quien ganó los 4 partidos jugados (el infractor).
        return outcomes.LOCAL_WIN if infractor == outcomes.WINNER_LOCAL else outcomes.VISITING_WIN
    return None
