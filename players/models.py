"""Modelos de jugadores y de la integración con SNP (cuenta, histórico de puntos y «Completar equipo»)."""
import datetime

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext, gettext_lazy as _

from core import crypto
from core.models import Club
from core.images import connect_photo_cleanup, player_photo_path
from core.public_id import PublicIdModel
from team.models import Team

# Mes en el que empieza la temporada (9 = septiembre).
# Con esto, entre septiembre de 2026 y agosto de 2027 la temporada actual es "2026-2027".
SEASON_START_MONTH = 9


def current_season():
    """Temporada actual ("2026-2027"). Función a nivel de módulo: las migraciones la referencian."""
    today = datetime.date.today()
    start = today.year if today.month >= SEASON_START_MONTH else today.year - 1
    return f"{start}-{start + 1}"


class Player(PublicIdModel):
    """
    Jugador de un club. Pertenece siempre al equipo propio del club y hereda su categoría.
    ``in_team`` indica si sigue en la plantilla; los que se van se conservan para las
    estadísticas. Puede estar enlazado a la cuenta de un usuario (``user``).
    """
    PUBLIC_ID_PREFIX = "PLY"
    POSITIONS = [
        ("Derecha", _("Derecha")),
        ("Revés", _("Revés")),
        ("Mixto", _(" Mixto")),
        ("NONE", "—"),  # sin indicar; los formularios lo muestran como «Elige una opción»
    ]
    HAND = [
        ("Diestro", _("Diestro")),
        ("Zurdo", _("Zurdo")),
        ("NONE", "—"),
    ]
    name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    position = models.CharField(max_length=10, choices=POSITIONS, default="NONE")
    skillfull_hand = models.CharField(max_length=10, choices=HAND, default="NONE")
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="players", null=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="team")
    photo = models.ImageField(upload_to=player_photo_path, null=True, blank=True)
    # Cuenta del jugador: puede editar su posición, mano hábil y foto. Se enlaza al
    # aceptar una invitación (vista my_player) y el capitán puede desenlazarla.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="players",
    )
    snp_score = models.FloatField(null=True)
    in_team = models.BooleanField(default=True)
    # Copia de la categoría de su equipo (Team.gender): se asigna al guardar.
    gender = models.CharField(_("Categoría"), max_length=1, choices=Team.GENDERS, blank=True, default="")
    joined_season = models.CharField(
        _("Temporada en la que se unió"),
        max_length=9,
        default=current_season,
        validators=[RegexValidator(r'^\d{4}-\d{4}$', _('Usa el formato 2024-2025.'))],
        help_text=_("Formato 2024-2025. Se usa para contar a cuántas convocatorias no se ha apuntado."),
    )

    class Meta:
        constraints = [
            # Una cuenta es como mucho un jugador en cada club.
            models.UniqueConstraint(
                fields=["club", "user"], condition=models.Q(user__isnull=False), name="unique_player_user_per_club",
            ),
        ]

    def save(self, *args, **kwargs):
        """Asigna el equipo propio del club si no tiene equipo y copia su categoría antes de guardar."""
        if self.club_id and not self.team_id:
            self.team = self.club.own_team
        if self.team_id:
            self.gender = self.team.gender
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """
        Nombre y apellidos en mayúsculas. Lo guardado no se toca: los formularios de edición
        siguen mostrando name/last_name tal cual.
        """
        return f'{self.name} {self.last_name}'.strip().upper()

    @property
    def short_name(self):
        """Nombre y primer apellido, en mayúsculas."""
        return f'{self.name} {self.get_first_last_name()}'.strip().upper()

    def __str__(self):
        """Nombre completo en mayúsculas."""
        return self.full_name

    def get_first_last_name(self):
        """Primer apellido (cadena vacía si no tiene)."""
        parts = self.last_name.split()
        return parts[0] if parts else ""  # Obtiene el primer apellido

class SnpAccount(PublicIdModel):
    """
    Cuenta de SNP (snpgalaxy.com) del capitán de un club, con la que el proceso
    ``update_snp_scores`` descarga cada semana los puntos SNP de sus jugadores.
    Usuario y contraseña se guardan cifrados (core/crypto.py).
    """
    PUBLIC_ID_PREFIX = "SNA"
    club = models.OneToOneField(Club, on_delete=models.CASCADE, related_name="snp_account")
    username_encrypted = models.TextField()
    password_encrypted = models.TextField()
    # Número del equipo en SNP (4380 en .../equipo/view/4380). Vacío: el único equipo de la cuenta.
    team_id = models.CharField(_("Equipo en SNP"), max_length=20, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_ok = models.BooleanField(null=True)
    # El último fallo fue pasajero (red, SNP lento o limitándonos): se reintenta en la
    # siguiente pasada del proceso. Los fallos de usuario o contraseña no se reintentan.
    last_sync_retryable = models.BooleanField(default=False)
    last_sync_message = models.TextField(blank=True)

    @property
    def username(self):
        """Usuario de SNP descifrado (lanza DecryptionError si la clave de cifrado ha cambiado)."""
        return crypto.decrypt(self.username_encrypted)

    @username.setter
    def username(self, value):
        """Guarda el usuario de SNP cifrado."""
        self.username_encrypted = crypto.encrypt(value)

    @property
    def password(self):
        """Contraseña de SNP descifrada (lanza DecryptionError si la clave de cifrado ha cambiado)."""
        return crypto.decrypt(self.password_encrypted)

    @password.setter
    def password(self, value):
        """Guarda la contraseña de SNP cifrada."""
        self.password_encrypted = crypto.encrypt(value)

    def __str__(self):
        """«Cuenta SNP de <club>»."""
        return gettext("Cuenta SNP de %(club)s") % {"club": self.club}


class SnpScoreHistory(PublicIdModel):
    """Puntos SNP de un jugador en cada actualización (una fila por jugador y día)."""
    PUBLIC_ID_PREFIX = "SNH"
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="snp_history")
    season = models.CharField(max_length=9, default=current_season)
    date = models.DateField()
    score = models.FloatField()

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["player", "date"], name="unique_snp_score_per_player_day"),
        ]

    def __str__(self):
        """Jugador, puntos y fecha."""
        return f"{self.player}: {self.score:g} ({self.date})"


class SnpTeamImport(PublicIdModel):
    """
    «Completar equipo»: alta de los jugadores que aparecen en el equipo de SNP del club y
    todavía no están en Zyra. Primero se descarga la lista y se guarda lo que se va a
    añadir (``to_add``) y lo que no porque ya existe (``existing``); el capitán lo
    revisa y lo confirma. Desde el back-office se crea y se confirma en un solo paso.
    Nunca modifica jugadores existentes.
    """
    PUBLIC_ID_PREFIX = "SNI"
    RUNNING = "running"
    READY = "ready"
    ERROR = "error"
    DONE = "done"
    CANCELLED = "cancelled"
    STATUSES = [(RUNNING, _("Buscando en SNP")), (READY, _("Pendiente de confirmar")), (ERROR, _("Con error")),
                (DONE, _("Hecha")), (CANCELLED, _("Cancelada"))]

    WEB = "web"
    BACKOFFICE = "backoffice"
    SOURCES = [(WEB, _("Web del club")), (BACKOFFICE, _("Back-office"))]

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="snp_imports")
    source = models.CharField(max_length=12, choices=SOURCES, default=WEB)
    status = models.CharField(max_length=10, choices=STATUSES, default=RUNNING)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # [{"name", "last_name", "snp_name", "score"}]
    to_add = models.JSONField(default=list, blank=True)
    # [{"snp_name", "player"}]: nombres de SNP que ya tienen jugador en Zyra.
    existing = models.JSONField(default=list, blank=True)
    created_players = models.JSONField(default=list, blank=True)
    message = models.TextField(blank=True)
    # Si ha fallado, dónde puede arreglarlo el capitán (SnpScrapeError.kind): "account" en la
    # cuenta SNP, "team" en los datos de su equipo, o vacío.
    error_kind = models.CharField(max_length=10, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        """Club y estado de la búsqueda."""
        return gettext("Completar equipo de %(club)s (%(status)s)") % {"club": self.club, "status": self.get_status_display()}


# Al cambiar o borrar la foto se borra el fichero antiguo (core/images.py).
connect_photo_cleanup(Player)
