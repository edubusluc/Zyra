"""Modelos de convocatorias y del envío de su informe PDF a los capitanes."""
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.public_id import PublicIdModel
from players.models import Player
from match.models import Match
from datetime import datetime

# Create your models here.
class Call(PublicIdModel):
    """
    Convocatoria de un partido (una por partido): los jugadores que se han apuntado.
    Mientras ``draft_mode`` es True sigue abierta.
    """
    PUBLIC_ID_PREFIX = "CAL"
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='match')
    players = models.ManyToManyField(Player, related_name='players')
    draft_mode = models.BooleanField(default=True)

    class Meta:
        unique_together = ('match',)

    def __str__(self):
        """«Local vs Visitante»."""
        return f"{self.match.local_name} vs {self.match.visiting_name}"


class ReportDelivery(PublicIdModel):
    """
    Envío del informe PDF de una convocatoria a un capitán del club (uno por
    destinatario). Hace de cola: al cerrar la convocatoria se intenta enviar al momento
    y, si falla, el proceso ``send_call_reports`` lo reintenta con esperas crecientes.
    """
    PUBLIC_ID_PREFIX = "RPD"
    PENDING, SENT, FAILED = "pending", "sent", "failed"
    STATUS_CHOICES = [(PENDING, _("Pendiente")), (SENT, _("Enviado")), (FAILED, _("Fallido"))]

    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="report_deliveries")
    email = models.EmailField()
    # A quién le llegan las respuestas: quien cerró la convocatoria.
    reply_to = models.EmailField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["call", "email"], name="unique_report_delivery")]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    def __str__(self):
        """Convocatoria, destinatario y estado del envío."""
        return f"Informe de {self.call} a {self.email} ({self.get_status_display()})"
