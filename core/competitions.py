"""
Reglas de cada competición: una ficha por competición con todo lo que cambia de una a otra
(número de partidos, puntos de cada partido, convocados mínimos, partido de desempate).

El resto del código no debe dar por hecho ningún número («5 partidos», «3-3-2-2-2»,
«10 convocados»): lo pide a la ficha con ``competition_for``. Por ahora solo existe la SNP;
cuando un club tenga su propia competición (espacios), ``competition_for`` la leerá del club
y añadir una competición nueva será añadir su ficha aquí.
"""
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Competition:
    """Ficha de reglas de una competición.

    ``game_points`` son los puntos de cada partido en orden de juego (su longitud es el número
    de partidos del enfrentamiento). ``tiebreak_game`` es el partido que decide un empate a
    puntos en los tipos de enfrentamiento sin empate (Reto y Play Off en la SNP).
    """
    code: str
    name: str
    game_points: tuple
    min_call_players: int
    tiebreak_game: int

    @property
    def games(self):
        """Partidos por enfrentamiento."""
        return len(self.game_points)

    @property
    def players_per_lineup(self):
        """Jugadores que juegan un enfrentamiento: dos por partido."""
        return 2 * self.games

    @property
    def total_points(self):
        """Puntos en juego en un enfrentamiento."""
        return sum(self.game_points)

    def points_for(self, n_game):
        """Puntos que vale el partido número ``n_game`` (empezando en 1)."""
        return self.game_points[n_game - 1]


SNP = Competition(
    code="snp",
    name=_("SNP"),
    game_points=(3, 3, 2, 2, 2),
    min_call_players=10,
    tiebreak_game=3,
)

COMPETITIONS = {SNP.code: SNP}
DEFAULT = SNP


def get_competition(code):
    """Ficha de la competición con código ``code``; la de por defecto si no existe."""
    return COMPETITIONS.get(code, DEFAULT)


def competition_for(obj=None):
    """Ficha de la competición de un club, de un enfrentamiento o de cualquier objeto de un club.

    Mientras los clubes no guarden su competición todos juegan la de por defecto (SNP), así
    que no se consulta nada: los listados que piden la ficha de muchos enfrentamientos no
    hacen consultas de más. Cuando exista ``Club.competition`` se leerá aquí.
    """
    return DEFAULT
