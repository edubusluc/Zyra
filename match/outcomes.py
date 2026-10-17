"""
Valores guardados de los resultados de un enfrentamiento y de cada partido: una sola definición
para todo el código (modelos, vistas, estadísticas e informes).

- ``Match.result``: ``LOCAL_WIN``, ``VISITING_WIN``, ``DRAW`` (empate a puntos, p. ej. 6-6) o
  ``NONE`` mientras el acta sigue abierta.
- ``Match.result_points``: ``"local/visitante"`` (p. ej. ``"7/5"``) o ``NONE``.
- ``Game.winner``: ``WINNER_LOCAL`` o ``WINNER_VISITING``.
  En Reto y Play Off no hay empate: el 6-6 lo decide el ganador del partido 3 (``tiebreak_result``).
- ``Result.result``: ``LOCAL_WIN`` o ``VISITING_WIN`` (un partido no puede acabar en empate).

Los textos son los que ya había guardados en la base de datos; ``normalize`` convierte cualquier
variante antigua (otra capitalización, «Empate») en el valor canónico.
"""
LOCAL_WIN = "Victoria Local"
VISITING_WIN = "Victoria Visitante"
DRAW = "EMPATE"
NONE = "NONE"

WINNER_LOCAL = "Local"
WINNER_VISITING = "Visitante"
WINNERS = (WINNER_LOCAL, WINNER_VISITING)

_VARIANTS = {
    "victoria local": LOCAL_WIN,
    "victoria visitante": VISITING_WIN,
    "empate": DRAW,
    "none": NONE,
    "": NONE,
}


def normalize(value):
    """Valor canónico de un resultado guardado con otra capitalización o escrito a mano (NONE si no se reconoce)."""
    return _VARIANTS.get((value or "").strip().lower(), NONE)


def winner_of(result):
    """``WINNER_LOCAL`` o ``WINNER_VISITING`` según el resultado de un partido (``Result.result``)."""
    return WINNER_LOCAL if normalize(result) == LOCAL_WIN else WINNER_VISITING


def from_points(points_local, points_visiting):
    """Resultado del enfrentamiento según los puntos de cada lado."""
    if points_local > points_visiting:
        return LOCAL_WIN
    if points_local < points_visiting:
        return VISITING_WIN
    return DRAW


def tiebreak_result(game_winner):
    """Resultado del enfrentamiento empatado a puntos en Reto o Play Off: gana el lado que ganó
    el partido de desempate (``Game.winner``, ``WINNER_LOCAL`` o ``WINNER_VISITING``)."""
    return LOCAL_WIN if game_winner == WINNER_LOCAL else VISITING_WIN
