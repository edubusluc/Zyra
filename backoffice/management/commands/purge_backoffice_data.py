"""Comando ``purge_backoffice_data``: borra datos del back-office que no deben guardarse para siempre."""
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from backoffice.models import (
    AuditLog, DailyActivity, EmailLog, ErrorEvent, ImportJob, QueryLog,
)


class Command(BaseCommand):
    """Purga consultas SQL, ficheros de importación, auditoría, correos, errores y actividad diaria antiguos."""
    help = ("Borra consultas SQL antiguas, vacía el contenido de importaciones ya terminadas y borra "
            "auditoría, registro de correos, eventos de error y actividad diaria pasado su plazo.")

    def add_arguments(self, parser):
        """Plazos en días de cada tipo de dato."""
        parser.add_argument("--query-days", type=int, default=365, help="Consultas SQL (365).")
        parser.add_argument("--import-days", type=int, default=30, help="Contenido de importaciones terminadas (30).")
        parser.add_argument("--audit-days", type=int, default=730, help="Auditoría (730).")
        parser.add_argument("--email-days", type=int, default=180, help="Registro de correos (180).")
        parser.add_argument("--error-days", type=int, default=30, help="Eventos de error y lentitud (30).")
        parser.add_argument("--activity-days", type=int, default=400, help="Actividad diaria (400).")

    def handle(self, *args, **options):
        """Aplica cada plazo y escribe cuántas filas ha tocado."""
        now = timezone.now()

        def before(days):
            """Fecha límite: lo anterior a ella se purga."""
            return now - datetime.timedelta(days=days)

        queries = QueryLog.objects.filter(created_at__lt=before(options["query_days"])).delete()[0]
        # El fichero de una importación terminada (o deshecha) solo hacía falta para hacerla: se vacía, no se borra la fila.
        imports = ImportJob.objects.filter(
            created_at__lt=before(options["import_days"]),
        ).exclude(status=ImportJob.DRAFT).exclude(content="").update(content="")
        drafts = ImportJob.objects.filter(status=ImportJob.DRAFT, created_at__lt=before(options["import_days"])).delete()[0]
        audit = AuditLog.objects.filter(created_at__lt=before(options["audit_days"])).delete()[0]
        emails = EmailLog.objects.filter(created_at__lt=before(options["email_days"])).delete()[0]
        errors = ErrorEvent.objects.filter(created_at__lt=before(options["error_days"])).delete()[0]
        activity = DailyActivity.objects.filter(date__lt=timezone.localdate() - datetime.timedelta(days=options["activity_days"])).delete()[0]
        self.stdout.write(
            f"Consultas SQL: {queries} · importaciones vaciadas: {imports} · borradores: {drafts} · "
            f"auditoría: {audit} · correos: {emails} · errores: {errors} · actividad diaria: {activity}"
        )
