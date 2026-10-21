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
    # Salidas del comando que significan «no había nada que hacer». Una ejecución programada
    # correcta con una de ellas no se guarda en el log (procesos que corren cada pocos minutos).
    idle_output: tuple = field(default_factory=tuple)


# Id de equipo del club: el público (TEA...) o el numérico interno.
TEAM_ID_PATTERN = r"(TEA[A-Za-z0-9]{12}|\d+)"

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
        name="purge_backoffice_data",
        description=_("Borra consultas SQL, auditoría, registro de correos, errores y actividad diaria antiguos, y vacía el contenido de las importaciones terminadas."),
        command="purge_backoffice_data",
        schedule="20 3 * * *",
    ),
    JobSpec(
        name="snapshot_daily_metrics",
        description=_("Guarda el resumen del día (usuarios activos, clubes, partidos, errores) para ver tendencias."),
        command="snapshot_daily_metrics",
        schedule="55 23 * * *",
    ),
    JobSpec(
        name="send_staff_alerts",
        description=_("Avisa por correo al personal cuando empieza un problema (informes fallidos, SNP, errores, procesos) y cuando se resuelve."),
        command="send_staff_alerts",
        schedule="*/15 * * * *",
        idle_output=("Sin avisos nuevos.",),
    ),
    JobSpec(
        name="send_staff_digest",
        description=_("Envía al personal el resumen semanal de la plataforma (los lunes a las 08:00)."),
        command="send_staff_digest",
        schedule="0 8 * * 1",
        options=(JobOption("dry", _("Simulacro"), "--dry-run", _("Solo muestra el resumen, sin enviarlo.")),),
    ),
    JobSpec(
        name="send_query_exports",
        description=_("Envía por correo el CSV de las consultas SQL guardadas con exportación programada (a las 07:00)."),
        command="send_query_exports",
        schedule="0 7 * * *",
        idle_output=("Nada que enviar.",),
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
                      "pausas. Se ejecuta los lunes y miércoles a las 05:00 (los partidos del fin de semana tardan en "
                      "verificarse en SNP) y cada ejecución actualiza a todos los clubes."),
        command="update_snp_scores",
        # Lunes y miércoles a las 05:00 (hora de Madrid): cada ejecución es un ciclo
        # (SNP_SYNC_CYCLE en el comando) que procesa a todos los clubes.
        schedule="0 5 * * 1,3",
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
        name="process_snp_imports",
        description=_("Atiende de una en una las búsquedas de «Completar equipo» pedidas desde la web (cola). "
                      "Sin búsquedas pendientes termina al momento."),
        command="process_snp_imports",
        schedule="* * * * *",
        idle_output=("", "Servicio de SNP apagado."),
    ),
    JobSpec(
        name="send_call_reports",
        description=_("Envía los informes de convocatoria y los avisos de resultado pendientes y reintenta los que "
                      "fallaron (esperas crecientes; tras 5 intentos se dan por fallidos y se avisa al personal)."),
        command="send_call_reports",
        schedule="*/5 * * * *",
        idle_output=("No hay informes pendientes de enviar.",),
    ),
    JobSpec(
        name="send_monthly_reports",
        description=_("Envía a cada jugador con cuenta su informe PDF del mes anterior (el día 1 a las 09:00). Es "
                      "idempotente: no repite el correo de un mes ya enviado y reintenta los que fallaron. Hace falta SITE_URL."),
        command="send_monthly_reports",
        schedule="0 9 1 * *",
        options=(
            JobOption("dry", _("Simulacro"), "--dry-run", _("Solo lista a quién se enviaría, sin enviar nada.")),
            JobOption("month", _("Mes"), "--month", _("AAAA-MM; por defecto, el mes natural anterior."),
                      pattern=r"\d{4}-(0[1-9]|1[0-2])"),
            JobOption("user", _("Enviar solo a este email"), "--user",
                      _("Envío manual a una cuenta, aunque ya haya recibido el informe de ese mes (queda anotado). "
                        "Ignora que haya desactivado los correos."),
                      pattern=r"[^\s@]+@[^\s@]+\.[^\s@]+"),
        ),
    ),
    JobSpec(
        name="complete_snp_team",
        description=_("«Completar equipo»: da de alta los jugadores del equipo de SNP de un club que todavía "
                      "no están en Zyra y actualiza los puntos SNP de los que ya existen. Solo a mano y sin los límites de la web."),
        command="complete_snp_team",
        params=(JobParam("team_id", _("Id del equipo"), _("Id del equipo propio del club en Zyra, TEA... (aparece en la ficha del club)."), TEAM_ID_PATTERN),),
    ),
    JobSpec(
        name="add_group_teams",
        description=_("Añade al grupo los equipos de la clasificación de SNP de un club: crea los que todavía no existen "
                      "en Zyra y da de alta en el grupo los que estaban fuera. No toca los jugadores. Solo a mano y sin los límites de la web."),
        command="add_group_teams",
        params=(JobParam("team_id", _("Id del equipo"), _("Id del equipo propio del club en Zyra, TEA... (aparece en la ficha del club)."), TEAM_ID_PATTERN),),
    ),
]


def get_spec(name):
    """Definición (JobSpec) del proceso con ese nombre, o None si ya no existe en JOBS."""
    return next((spec for spec in JOBS if spec.name == name), None)
