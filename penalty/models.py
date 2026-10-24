"""Modelo de advertencias a jugadores."""
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.public_id import PublicIdModel
from players.models import Player
from call.models import Call


# Motivos de una advertencia. Se guarda el código y se traduce al pintarlo; «Otro» pide un detalle.
NO_SHOW = "no_show"
LATE = "late"
LATE_DROP = "late_drop"
CONDUCT = "conduct"
OTHER = "other"
KINDS = [
    (NO_SHOW, _("No se presentó")),
    (LATE, _("Llegó tarde")),
    (LATE_DROP, _("Baja de última hora")),
    (CONDUCT, _("Comportamiento")),
    (OTHER, _("Otro")),
]
KIND_LABELS = dict(KINDS)
REASON_MAX_LENGTH = 100


def reason_text(kind, detail):
    """Motivo legible: «Llegó tarde: 20 min», «Llegó tarde» sin detalle o solo el detalle en «Otro»."""
    if kind not in KIND_LABELS:
        kind = OTHER
    label = str(KIND_LABELS[kind])
    detail = (detail or "").strip()
    if kind == OTHER:
        return detail or label
    return f"{label}: {detail}" if detail else label


# Create your models here.
class Penalty(PublicIdModel):
    """Advertencia a un jugador en una convocatoria, con su motivo (``kind``) y un detalle opcional (``reason``)."""
    PUBLIC_ID_PREFIX = "PEN"
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="penalties")
    kind = models.CharField(_("Motivo"), max_length=12, choices=KINDS, default=OTHER)
    # Detalle libre. Las advertencias anteriores al motivo guardan aquí su texto antiguo.
    reason = models.CharField(_("Detalle"), max_length=REASON_MAX_LENGTH, blank=True)
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="call")

    @property
    def display_reason(self):
        """Motivo con su detalle, traducido al idioma activo."""
        return reason_text(self.kind, self.reason)

    def __str__(self):
        """Jugador y motivo."""
        return f"{self.player}  {self.display_reason}"
