"""Modelo de advertencias a jugadores."""
from django.db import models
from core.public_id import PublicIdModel
from players.models import Player
from call.models import Call

# Create your models here.
class Penalty(PublicIdModel):
    """Advertencia a un jugador en una convocatoria, con su motivo."""
    PUBLIC_ID_PREFIX = "PEN"
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="penalties")
    reason = models.CharField(max_length=100)
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="call")


    def __str__(self):
        """Jugador y motivo."""
        return f"{self.player}  {self.reason}"
