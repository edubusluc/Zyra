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


def short_call_allowed(rules, count):
    """
    True si una convocatoria de ``count`` jugadores puede cerrarse por debajo del mínimo: la competición
    admite «pareja no presentada» (``rules.pair_no_show``) y hay al menos una pareja que formar.
    """
    return bool(rules.pair_no_show and count >= 2)


def required_pairs(call):
    """
    Parejas que hay que alinear: todas las de la competición o, si la convocatoria se cerró con menos
    jugadores de los que hacen falta y la competición admite «pareja no presentada», solo las que
    se pueden formar (de dos en dos); las demás parejas quedan como no presentadas.
    """
    games = competition_for(call.match).games
    if call.match.club.rules.pair_no_show and call.players.count() < 2 * games:
        return call.players.count() // 2
    return games


def parse_lineup(raw, call, match_games=None):
    """
    Convierte el JSON del formulario en una lista ordenada de
    (juego_existente_o_None, jugador_1, jugador_2). Lanza LineupError si algo no cuadra.
    """
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        raise LineupError(_("Los datos de la alineación no son válidos."))
    needed = required_pairs(call)
    if not isinstance(data, list) or len(data) != needed:
        raise LineupError(_("Hay que completar las %(n)s parejas antes de guardar.") % {"n": needed})

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
    for n in range(len(games) + 1, competition_for(match).games + 1):
        games.append(_missing_game(match, n))
    Game.objects.bulk_create(games)
    return games


def _missing_game(match, n):
    """Partido sin jugadores: la pareja del club no se presenta porque no hay jugadores para formarla."""
    game = Game(match=match, draft_mode=True, winner=None, no_show=Game.NO_SHOW_OWN)
    game.n_game = n
    game.score = game_points(n, competition_for(match))
    return game


@transaction.atomic
def update_games(match, lineup):
    """
    Reasigna parejas y orden de los partidos existentes según la alineación validada. Si algún partido
    con resultado se quedaría sin pareja (pasaría a «no presentada») no cambia nada y lanza ``LineupError``:
    un resultado ya introducido no se borra sin que el capitán lo haga a propósito.
    """
    games = [g for g, _p1, _p2 in lineup]
    others = [g for g in Game.objects.filter(match=match).order_by("n_game") if g.pk not in {x.pk for x in games}]
    with_result = [g for g in others if g.results.exists()]
    if with_result:
        raise LineupError(_("No se pueden quitar de las parejas partidos que ya tienen resultado "
                            "(partido %(n)s): bórralo primero.") % {"n": with_result[0].n_game})
    # Primero se libera el número de cada partido para poder reordenarlos sin
    # chocar con la restricción de número único por enfrentamiento.
    Game.objects.filter(pk__in=[g.pk for g in games]).update(n_game=None)
    Game.objects.filter(pk__in=[g.pk for g in others]).update(n_game=None)
    for n, (game, p1, p2) in enumerate(lineup, start=1):
        _assign(game, match, n, p1, p2)
        if game.no_show == Game.NO_SHOW_OWN:
            game.no_show = ""
        game.save()
    # Los partidos que quedan sin pareja pasan al final como «no presentada» (sin resultado ni jugadores).
    for n, game in enumerate(others, start=len(lineup) + 1):
        game.results.all().delete()
        _assign_none(game, n, competition_for(match))
        game.save()
    return games


def _assign_none(game, n, competition):
    """Deja el partido sin jugadores y con la pareja del club no presentada, con su número y puntos."""
    game.player_1_local = game.player_2_local = game.player_1_visiting = game.player_2_visiting = None
    game.no_show, game.winner, game.n_game = Game.NO_SHOW_OWN, None, n
    game.score = game_points(n, competition)
