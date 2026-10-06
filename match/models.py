"""Modelos de los partidos del club.

- Match: un enfrentamiento entre dos equipos (uno de ellos, el propio del club).
- Game: cada uno de los 5 partidos por parejas de un enfrentamiento.
- Result: el resultado por sets de un Game.

En los Game solo se guardan los jugadores del propio club, en el lado (local o
visitante) en el que juega su equipo.
"""
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from players.models import Player
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy as _
from . import scoring
from datetime import datetime
from urllib.parse import quote

# Create your models here.

from django.db import models
from core.public_id import PublicIdModel
from core.models import Club
from team.models import Team

class Match(PublicIdModel):
    """Enfrentamiento entre dos equipos del club (uno de ellos, el propio).

    La temporada y la ubicación se rellenan solas al guardar. ``result`` y
    ``result_points`` se fijan al cerrar el acta; ``draft_mode`` es True mientras
    sigue abierta.
    """
    PUBLIC_ID_PREFIX = "MAT"
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='matches', null=True)
    local = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='local_matches', null=True, blank=True)
    visiting = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='visiting_matches', null=True, blank=True)
    
    
    POSSIBLE_RESULT = [
        ("Victoria Local", _("Victoria Local")),
        ("Victoria Visitante", _("Victoria Visitante")),
        ("EMPATE", _("Empate")),
        ("NONE", _("Ninguno")),
    ]
    
    ENFRENTAMIENTO = "enfrentamiento"
    RETO = "reto"
    PLAYOFF = "playoff"
    AMISTOSO = "amistoso"
    # Tipos de un partido competitivo; un amistoso no tiene tipo propio y se guarda como AMISTOSO.
    COMPETITIVE_TYPES = [
        (ENFRENTAMIENTO, _("Enfrentamiento")),
        (RETO, _("Reto")),
        (PLAYOFF, _("Play Off")),
    ]
    MATCH_TYPES = COMPETITIVE_TYPES + [(AMISTOSO, _("Amistoso"))]

    start_date = models.DateField()
    match_type = models.CharField(_("Tipo de partido"), max_length=15, choices=MATCH_TYPES, default=ENFRENTAMIENTO)
    result = models.CharField(max_length=20, choices=POSSIBLE_RESULT, blank = True, default="NONE")
    result_points = models.CharField(max_length=20, blank = True, default="NONE")
    draft_mode = models.BooleanField(default=True)
    season = models.CharField(max_length=9, blank = True, default="NONE")
    # Copia de la ubicación del equipo local al crear el partido. Es una copia, no un
    # enlace: si el equipo cambia de sede después, los partidos ya creados no cambian.
    location = models.CharField(max_length=100, blank=True, default="")
    # Rival de un amistoso que no es un equipo del grupo: solo se guarda su nombre en el
    # propio partido (no se crea ningún equipo) y ese lado (local o visiting) queda vacío.
    rival_name = models.CharField(_("Rival"), max_length=100, blank=True, default="")
    
    class Meta:
        indexes = [
            models.Index(fields=["club", "season", "start_date"], name="match_club_season_idx"),
        ]

    def save(self, *args, **kwargs):
        """Rellena la temporada a partir de la fecha y copia la ubicación del equipo local.

        La temporada va de septiembre a agosto (p. ej. '2024-2025'). Solo se asignan si
        están vacías, así que no cambian en guardados posteriores.
        """
        # Asignar la temporada según la fecha de inicio
        if not self.season or self.season == "NONE":
            if self.start_date:
                if self.start_date.month >= 9:  # Septiembre o después
                    self.season = f"{self.start_date.year}-{self.start_date.year + 1}"
                else:  # Antes de septiembre (enero a agosto)
                    self.season = f"{self.start_date.year - 1}-{self.start_date.year}"

        if not self.location and self.local_id:
            self.location = self.local.location

        # Llama al método de guardado del padre
        super().save(*args, **kwargs)
    
    @property
    def maps_url(self):
        """Enlace de Google Maps a la ubicación del partido; '' si no tiene."""
        if not self.location:
            return ""
        return "https://www.google.com/maps/search/?api=1&query=" + quote(self.location)

    @property
    def is_friendly(self):
        """True si es un partido amistoso."""
        return self.match_type == self.AMISTOSO

    @property
    def own_is_local(self):
        """True si el equipo propio del club juega como local."""
        return bool(self.local and self.local.is_own)

    @property
    def own_is_visiting(self):
        """True si el equipo propio del club juega como visitante."""
        return bool(self.visiting and self.visiting.is_own)

    def _side_name(self, team):
        """Nombre del equipo de un lado; si ese lado está vacío, el rival escrito a mano."""
        return team.name if team else self.rival_name

    @property
    def local_name(self):
        """Nombre del equipo local (o del rival escrito a mano si juega como local)."""
        return self._side_name(self.local)

    @property
    def visiting_name(self):
        """Nombre del equipo visitante (o del rival escrito a mano si juega como visitante)."""
        return self._side_name(self.visiting)

    @property
    def rival_label(self):
        """Nombre del rival del equipo propio, sea del grupo o escrito a mano."""
        return self.visiting_name if self.own_is_local else self.local_name

    def __str__(self):
        """'Local - Visitante'."""
        return f'{self.local_name} - {self.visiting_name}'



class Game(PublicIdModel):
    """Partido por parejas dentro de un enfrentamiento (del 1 al 5).

    Solo se rellenan los jugadores del lado del equipo propio. ``score`` son los
    puntos en juego (3 en los partidos 1 y 2, 2 en el resto) y ``winner`` es
    'Local' o 'Visitante'.
    """
    PUBLIC_ID_PREFIX = "GAM"
    NUMBER_GAME = [
        ("1", "1"),
        ("2", "2"),
        ("3", "3"),
        ("4", "4"),
        ("5", "5"),
    ]

    WINNER = [
        ("Local", "Local"),
        ("Visitante", "Visitante"),
    ]

    SCORE = [
        ("3","3"),
        ("2","2"),
    ]

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='games')
    n_game = models.IntegerField(choices= NUMBER_GAME, null = True)
    # SET_NULL: al eliminar un jugador el partido y su resultado se conservan; su nombre
    # queda guardado en removed_player_names para seguir mostrando la pareja.
    player_1_local = models.ForeignKey(Player, on_delete=models.SET_NULL, related_name='player_1_local', null=True)
    player_2_local = models.ForeignKey(Player, on_delete=models.SET_NULL, related_name='player_2_local', null=True)
    player_1_visiting = models.ForeignKey(Player, on_delete=models.SET_NULL, related_name='player_1_visiting', null=True)
    player_2_visiting = models.ForeignKey(Player, on_delete=models.SET_NULL, related_name='player_2_visiting', null=True)
    # {"player_1_local": "Ana López", ...}: jugadores eliminados que jugaron este partido.
    removed_player_names = models.JSONField(default=dict, blank=True)
    score = models.IntegerField(choices= NUMBER_GAME, null = True)
    winner = models.CharField(max_length=10, null=True)
    draft_mode = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # Cada enfrentamiento tiene como mucho un partido 1, un partido 2... (evita duplicados)
            models.UniqueConstraint(fields=["match", "n_game"], name="unique_game_number_per_match"),
            models.CheckConstraint(check=models.Q(n_game__gte=1, n_game__lte=5) | models.Q(n_game__isnull=True),
                                   name="game_number_between_1_and_5"),
        ]

    def save(self, *args, **kwargs):
        """Valida el partido con clean() antes de guardarlo."""
        self.clean()  # Llamar a la validación antes de guardar
        super().save(*args, **kwargs)


    PLAYER_SLOTS = ("player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting")

    def player_name(self, slot):
        """Nombre del jugador de esa posición, también si ya se ha eliminado."""
        player = getattr(self, slot)
        return str(player) if player else self.removed_player_names.get(slot, "").upper()

    def _pair_label(self, first, second):
        """'Jugador 1 / Jugador 2' de esas dos posiciones; '' si falta alguno."""
        names = [self.player_name(first), self.player_name(second)]
        return " / ".join(names) if all(names) else ""

    @property
    def local_pair_label(self):
        """Nombre de la pareja local ('' si no hay)."""
        return self._pair_label("player_1_local", "player_2_local")

    @property
    def visiting_pair_label(self):
        """Nombre de la pareja visitante ('' si no hay)."""
        return self._pair_label("player_1_visiting", "player_2_visiting")

    @property
    def pair_label(self):
        """Nombre de la pareja propia (solo se guarda la del equipo del club)."""
        return self.local_pair_label or self.visiting_pair_label

    def __str__(self):
        """Enfrentamiento, número de partido y pareja local; si no hay, la pareja visitante."""
        if self.player_1_local:
            return f'{self.match}-{self.n_game}: {self.player_1_local} - {self.player_2_local}'
        else:
            return f'{self.player_1_visiting} - {self.player_2_visiting}'


@receiver(pre_delete, sender=Player)
def keep_name_in_games(sender, instance, **kwargs):
    """Antes de eliminar un jugador guarda su nombre en sus partidos (el FK pasará a NULL)."""
    for slot in Game.PLAYER_SLOTS:
        for game in Game.objects.filter(**{slot: instance}).only("id", "removed_player_names"):
            game.removed_player_names = {**game.removed_player_names, slot: str(instance)}
            # update() en lugar de save(): save() valida el partido y aquí solo cambia el nombre.
            Game.objects.filter(pk=game.pk).update(removed_player_names=game.removed_player_names)


def validate_set_value(value):
    """Validador de campo: los juegos de un set deben estar entre 0 y 30.

    El límite es amplio para admitir un super tie-break en el tercer set; las reglas
    completas de pádel están en match/scoring.py (Result.clean).
    """
    if value < 0 or value > 30:
        raise ValidationError(gettext('El valor debe estar entre 0 y 30.'))


class Result(PublicIdModel):
    """Resultado por sets de un partido (uno por partido); el set 3 es opcional."""
    PUBLIC_ID_PREFIX = "RES"
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='results')
    result = models.CharField(max_length=100, null = True)
    set1_local = models.IntegerField(validators=[validate_set_value])
    set1_visiting = models.IntegerField(validators=[validate_set_value])
    set2_local = models.IntegerField(validators=[validate_set_value])
    set2_visiting = models.IntegerField(validators=[validate_set_value])
    set3_local = models.IntegerField(validators=[validate_set_value], null=True)
    set3_visiting = models.IntegerField(validators=[validate_set_value], null=True)
    draft_mode = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # Un solo resultado por partido
            models.UniqueConstraint(fields=["game"], name="unique_result_per_game"),
        ]

    def sets(self):
        """Los tres sets como lista de tuplas (local, visitante); el set 3 puede ser (None, None)."""
        return [
            (self.set1_local, self.set1_visiting),
            (self.set2_local, self.set2_visiting),
            (self.set3_local, self.set3_visiting),
        ]

    def clean(self):
        """Valida el resultado con las reglas del pádel y normaliza el set 3 no jugado."""
        values = [scoring.to_int(v) for pair in self.sets() for v in pair]
        sets, self._winner = scoring.validate_padel_result(
            (values[0], values[1]), (values[2], values[3]), (values[4], values[5])
        )
        (self.set1_local, self.set1_visiting), (self.set2_local, self.set2_visiting), \
            (self.set3_local, self.set3_visiting) = sets

    def determine_winner(self):
        """'Victoria Local' o 'Victoria Visitante'; valida el resultado si aún no se ha hecho."""
        winner = getattr(self, "_winner", None)
        if winner is None:
            self.clean()
            winner = self._winner
        return "Victoria Local" if winner == "local" else "Victoria Visitante"

    def save(self, *args, **kwargs):
        """Valida y normaliza el resultado con clean() antes de guardarlo."""
        self.clean() 
        super().save(*args, **kwargs)
        






