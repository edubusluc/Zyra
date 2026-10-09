"""
Registro de los procesos programados de Zyra.

Cada proceso es un comando de Django (``python manage.py <comando>``). Para añadir
uno: crea el comando y añade aquí una entrada. La hora se interpreta en
SCHEDULER_TIME_ZONE (Madrid). En la base de datos solo se guarda el estado de cada
proceso (activo, última y próxima ejecución); la definición manda siempre el código.

Un proceso sin ``schedule`` solo se lanza a mano desde el back-office. Si tiene
``params``, el back-office pide esos datos al lanzarlo y se pasan al comando como
argumentos, en ese orden. Las ``options`` son opcionales: al lanzarlo a mano se pueden
marcar (casillas) o rellenar, y se añaden al comando como sus opciones (--all, --club …).
"""
from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

SCHEDULER_TIME_ZONE = "Europe/Madrid"


@dataclass(frozen=True)
class JobParam:
    """Dato obligatorio que se pide al lanzar un proceso a mano y se pasa al comando como argumento."""
    name: str
    label: str
    help: str = ""
    # Expresión regular que debe cumplir el valor (entero por defecto).
    pattern: str = r"\d+"


@dataclass(frozen=True)
class JobOption:
    """Opción del comando que se puede marcar o rellenar al lanzar un proceso a mano."""
    name: str
    label: str
    # Opción del comando que se añade: "--all", "--club"…
    flag: str
    help: str = ""
    # Sin patrón es una casilla; con patrón, un campo de texto opcional cuyo valor
    # (si se rellena) debe cumplirlo y se pasa tras la opción.
    pattern: str = ""


@dataclass(frozen=True)
class JobSpec:
    """
    Definición de un proceso: comando de Django, horario cron (vacío = solo a mano),
    argumentos fijos (``args``), datos que se piden al lanzarlo (``params``) y opciones.
    """
    name: str
    description: str
    command: str
    schedule: str = ""
    args: tuple = field(default_factory=tuple)
    params: tuple = field(default_factory=tuple)
    options: tuple = field(default_factory=tuple)


JOBS = [
    JobSpec(
        name="purge_request_metrics",
        description=_("Borra las métricas de carga por minuto de más de 30 días."),
        command="purge_request_metrics",
        args=("--days", "30"),
        schedule="0 3 * * *",
    ),
    JobSpec(
        name="purge_job_runs",
        description=_("Borra el log de ejecuciones de procesos de más de 90 días."),
        command="purge_job_runs",
        args=("--days", "90"),
        schedule="10 3 * * *",
    ),
    JobSpec(
        name="clear_sessions",
        description=_("Borra de la base de datos las sesiones de usuario caducadas."),
        command="clearsessions",
        schedule="30 3 * * *",
    ),
    JobSpec(
        name="update_snp_scores",
        description=_("Descarga de SNP los puntos de los jugadores de los clubes con cuenta SNP, por lotes de 50 y con "
                      "pausas. El ciclo empieza los lunes a las 23:00; el resto de días solo hace lo que quedó pendiente "
                      "(clubes sin procesar o con un fallo pasajero)."),
        command="update_snp_scores",
        # Cada día a las 23:00: el lunes empieza el ciclo semanal y los demás días se
        # completa lo que haya quedado pendiente (si no queda nada, termina al momento).
        schedule="0 23 * * *",
        options=(
            JobOption("all", _("Repetir todos los equipos"), "--all",
                      _("Aunque ya se hayan actualizado en este ciclo o su último error no se reintente solo.")),
            JobOption("club", _("Solo este club"), "--club", _("Nombre o slug del club (se actualiza aunque ya esté al día)."),
                      pattern=r"[\w .,'()&-]{1,100}"),
            JobOption("verbose", _("Traza detallada"), "--verbosity=2",
                      _("Muestra cada paso en SNP y los puntos de cada jugador.")),
        ),
    ),
    JobSpec(
        name="send_call_reports",
        description=_("Envía los informes de convocatoria pendientes y reintenta los que fallaron "
                      "(esperas crecientes; tras 5 intentos se dan por fallidos y se avisa al personal)."),
        command="send_call_reports",
        schedule="*/5 * * * *",
    ),
    JobSpec(
        name="complete_snp_team",
        description=_("«Completar equipo»: da de alta los jugadores del equipo de SNP de un club que todavía "
                      "no están en Zyra y actualiza los puntos SNP de los que ya existen. Solo a mano y sin los límites de la web."),
        command="complete_snp_team",
        params=(JobParam("team_id", _("Id del equipo"), _("Id del equipo propio del club en Zyra, TEA... (aparece en la ficha del club).")),),
    ),
]


def get_spec(name):
    """Definición (JobSpec) del proceso con ese nombre, o None si ya no existe en JOBS."""
    return next((spec for spec in JOBS if spec.name == name), None)
