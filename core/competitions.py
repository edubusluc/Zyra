"""
Reglas de cada competición: una ficha por competición con todo lo que cambia de una a otra
(número de partidos, puntos de cada partido, convocados mínimos, partido de desempate).

El resto del código no debe dar por hecho ningún número («5 partidos», «3-3-2-2-2»,
«10 convocados»): lo pide a la ficha con ``competition_for``, que la lee del club
(``Club.competition``). Cada club es un «espacio» de una competición; añadir una competición
nueva es añadir su ficha aquí.
"""
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Competition:
    """Ficha de reglas de una competición.

    ``game_points`` son los puntos de cada partido en orden de juego (su longitud es el número
    de partidos del enfrentamiento). ``tiebreak_game`` es el partido que decide un empate a
    puntos en los tipos de enfrentamiento sin empate (Reto y Play Off en la SNP); None si la
    competición no puede empatar a puntos. ``divisions`` son las divisiones de sus equipos
    (códigos de ``Team.DIVISIONS``) y ``has_snp`` si sus jugadores tienen puntos SNP (cuenta
    SNP, sincronización, «Completar equipo»).
    """
    code: str
    name: str
    game_points: tuple
    min_call_players: int
    tiebreak_game: int | None
    divisions: tuple = ()
    has_snp: bool = False

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
    divisions=("future", "500", "1000", "grand_slam"),
    has_snp=True,
)

# Liga Andaluza de Pádel por Equipos: 3 partidos de 1 punto (al mejor de 3, sin empate posible).
LAPI = Competition(
    code="lapi",
    name=_("LAPI"),
    game_points=(1, 1, 1),
    min_call_players=6,
    tiebreak_game=None,
    divisions=("lapi_1", "lapi_2", "lapi_3", "lapi_4", "lapi_5"),
)

COMPETITIONS = {SNP.code: SNP, LAPI.code: LAPI}
CHOICES = [(c.code, c.name) for c in COMPETITIONS.values()]
DEFAULT = SNP


def get_competition(code):
    """Ficha de la competición con código ``code``; la de por defecto si no existe."""
    return COMPETITIONS.get(code, DEFAULT)


def competition_for(obj=None):
    """Ficha de la competición de un club, de un enfrentamiento o de cualquier objeto con ``club``.

    Sin objeto, la de por defecto (SNP). Si el club del objeto no está ya cargado se lee solo su
    competición (una consulta): los listados de muchos enfrentamientos deben pedir la ficha al
    club (``request.club``) una vez y no a cada enfrentamiento.
    """
    if obj is None:
        return DEFAULT
    code = getattr(obj, "competition", None)
    if code is None and hasattr(obj, "club_id"):
        club = obj._state.fields_cache.get("club")
        if club is not None:
            code = club.competition
        elif obj.club_id is not None:
            from core.models import Club
            code = Club.objects.filter(pk=obj.club_id).values_list("competition", flat=True).first()
    return get_competition(code)
