"""
Alineación de un enfrentamiento: las parejas del club y el orden de los partidos.

Cuántas parejas hay y cuánto vale cada partido lo dice la ficha de la competición
(``core.competitions``; en la SNP, 5 partidos que valen 3, 3, 2, 2 y 2 puntos).
Se valida y se guarda siempre la alineación completa, en una transacción: o se
guardan todos los partidos o ninguno. Así no pueden quedar partidos a medias ni
duplicados.
"""
import json

from django.db import transaction
from django.utils.translation import gettext as _

from core.competitions import competition_for

from .models import Game


class LineupError(Exception):
    """Error de validación de la alineación; su mensaje se muestra tal cual al usuario."""
    pass


def game_points(index, competition=None):
    """Puntos en juego según el orden del partido (en la SNP los dos primeros valen 3 y el resto 2)."""
    return (competition or competition_for()).points_for(index)


def parse_lineup(raw, call, match_games=None):
    """
    Convierte el JSON del formulario en una lista ordenada de
    (juego_existente_o_None, jugador_1, jugador_2). Lanza LineupError si algo no cuadra.
    """
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        raise LineupError(_("Los datos de la alineación no son válidos."))
    games_per_match = competition_for(call.match).games
    if not isinstance(data, list) or len(data) != games_per_match:
        raise LineupError(_("Hay que completar las %(n)s parejas antes de guardar.") % {"n": games_per_match})

    called = {p.id: p for p in call.players.all()}
    games_by_id = {g.id: g for g in (match_games or [])}
    used_players, used_games, lineup = set(), set(), []

    for n, item in enumerate(data, start=1):
        try:
            p1, p2 = called[int(item["player1Id"])], called[int(item["player2Id"])]
        except (KeyError, TypeError, ValueError):
            raise LineupError(_("Partido %(n)s: los dos jugadores deben estar en la convocatoria.") % {"n": n})
        if p1 == p2:
            raise LineupError(_("Partido %(n)s: una pareja necesita dos jugadores distintos.") % {"n": n})
        for p in (p1, p2):
            if p.id in used_players:
                raise LineupError(_("%(player)s aparece en más de una pareja.") % {"player": p})
            used_players.add(p.id)

        game = None
        if match_games is not None:
            try:
                game = games_by_id[int(item["gameId"])]
            except (KeyError, TypeError, ValueError):
                raise LineupError(_("La alineación no corresponde a los partidos de este enfrentamiento."))
            if game.id in used_games:
                raise LineupError(_("La alineación no corresponde a los partidos de este enfrentamiento."))
            used_games.add(game.id)
        lineup.append((game, p1, p2))

    return lineup


def _assign(game, match, n, p1, p2):
    """Pone la pareja en el lado del equipo propio, vacía el otro y fija número y puntos del partido."""
    side, other = ("local", "visiting") if match.own_is_local else ("visiting", "local")
    setattr(game, f"player_1_{side}", p1)
    setattr(game, f"player_2_{side}", p2)
    setattr(game, f"player_1_{other}", None)
    setattr(game, f"player_2_{other}", None)
    game.n_game = n
    game.score = game_points(n, competition_for(match))


@transaction.atomic
def create_games(match, lineup):
    """Crea los partidos del enfrentamiento a partir de la alineación ya validada.

    Bloquea el enfrentamiento mientras tanto y falla con LineupError si ya tenía partidos,
    para que dos envíos simultáneos no creen partidos duplicados.
    """
    if not (match.own_is_local or match.own_is_visiting):
        raise LineupError(_("El enfrentamiento no es del equipo del club."))
    # Bloquea el enfrentamiento para que dos envíos a la vez no creen partidos dobles
    type(match).objects.select_for_update().get(pk=match.pk)
    if Game.objects.filter(match=match).exists():
        raise LineupError(_("Los partidos de este enfrentamiento ya estaban creados."))
    games = []
    for n, (_game, p1, p2) in enumerate(lineup, start=1):
        game = Game(match=match, draft_mode=True, winner=None)
        _assign(game, match, n, p1, p2)
        games.append(game)
    Game.objects.bulk_create(games)
    return games


@transaction.atomic
def update_games(match, lineup):
    """Reasigna parejas y orden de los partidos existentes según la alineación validada."""
    games = [g for g, _p1, _p2 in lineup]
    # Primero se libera el número de cada partido para poder reordenarlos sin
    # chocar con la restricción de número único por enfrentamiento.
    Game.objects.filter(pk__in=[g.pk for g in games]).update(n_game=None)
    for n, (game, p1, p2) in enumerate(lineup, start=1):
        _assign(game, match, n, p1, p2)
        game.save()
    return games
