"""Modelo de equipo: el propio de cada club y sus rivales."""
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.images import connect_photo_cleanup, team_photo_path
from core.public_id import PublicIdModel
from core.models import Club

# Create your models here.

class Team(PublicIdModel):
    """
    Equipo de un club. Cada club tiene un equipo propio (``is_own``), al que pertenecen sus
    jugadores; el resto son rivales. ``in_group`` marca los equipos de su grupo.
    """
    PUBLIC_ID_PREFIX = "TEA"
    MALE = "M"
    FEMALE = "F"
    GENDERS = [(MALE, _("Masculino")), (FEMALE, _("Femenino"))]
    COUNTRIES = [
        ("ES", _("España")),
        ("MX", _("México")),
        ("PT", _("Portugal")),
        ("IT", _("Italia")),
        ("SE", _("Suecia")),
    ]
    # Divisiones de todas las competiciones; cada club solo ofrece las de la suya
    # (``Competition.divisions``, ver ``divisions_for``).
    DIVISIONS = [
        ("future", "Future"),
        ("500", "500"),
        ("1000", "1000"),
        ("grand_slam", "Grand Slam"),
        ("lapi_1", _("1.ª división")),
        ("lapi_2", _("2.ª división")),
        ("lapi_3", _("3.ª división")),
        ("lapi_4", _("4.ª división")),
        ("lapi_5", _("5.ª división")),
    ]
    # null=True solo para poder migrar datos existentes (ver comando assign_default_club).
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="teams", null=True)
    # True para el equipo que representa al propio club; el resto son rivales.
    is_own = models.BooleanField(default=False)
    name = models.CharField(max_length=100)
    in_group = models.BooleanField(default=False)
    location = models.CharField(max_length=100)
    photo = models.ImageField(upload_to=team_photo_path, null=True, blank=True)
    # Vacíos solo en los equipos creados antes de existir estos campos; los formularios los piden.
    gender = models.CharField(_("Categoría"), max_length=1, choices=GENDERS, blank=True, default="")
    country = models.CharField(_("Nacionalidad del equipo"), max_length=2, choices=COUNTRIES, blank=True, default="")
    division = models.CharField(_("División"), max_length=10, choices=DIVISIONS, blank=True, default="")

    class Meta:
        constraints = [
            # El nombre no puede repetirse dentro de una división: lo comprueba Teamform
            # (sin distinguir mayúsculas ni tildes, que una restricción no puede).
            models.UniqueConstraint(fields=["club"], condition=models.Q(is_own=True), name="unique_own_team_per_club"),
        ]

    def save(self, *args, **kwargs):
        """
        Guarda el equipo y pasa su categoría (masculino/femenino) a sus jugadores. El equipo
        propio siempre está en el grupo: no puede darse de baja.
        """
        if self.is_own:
            self.in_group = True
        super().save(*args, **kwargs)
        # Los jugadores tienen la categoría (masculino/femenino) de su equipo.
        if self.gender:
            self.team_players.exclude(gender=self.gender).update(gender=self.gender)

    def __str__(self):
        """Nombre del equipo."""
        return self.name


# Al cambiar o borrar la foto se borra el fichero antiguo (core/images.py).
connect_photo_cleanup(Team)


def divisions_for(competition):
    """Divisiones (código, nombre) de ``Team.DIVISIONS`` que usa la competición ``competition``."""
    return [(code, label) for code, label in Team.DIVISIONS if code in competition.divisions]
