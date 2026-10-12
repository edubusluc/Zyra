"""Comando que envía a cada jugador su informe PDF del mes anterior (pensado para cron, una vez al mes)."""
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from match.monthly_email import send_monthly_reports
from match.monthly_report import previous_month


class Command(BaseCommand):
    """Envía los informes mensuales; se puede lanzar varias veces sin repetir correos."""
    help = ("Envía por email a cada jugador con cuenta su informe PDF del mes anterior. Es idempotente: "
            "quien ya lo recibió no vuelve a recibirlo, y los fallos se reintentan en la siguiente pasada.")

    def add_arguments(self, parser):
        """Opciones: mes concreto, simulacro y límite de envíos."""
        parser.add_argument("--month", help="Mes a enviar, AAAA-MM (por defecto, el mes natural anterior).")
        parser.add_argument("--dry-run", action="store_true", help="Solo muestra a quién se enviaría.")
        parser.add_argument("--limit", type=int, help="Máximo de correos en esta pasada (por defecto EMAIL_MAX_PER_RUN).")

    def handle(self, *args, **options):
        """Envía los informes y falla si alguno no ha podido salir, para que se note en el cron."""
        if options["month"]:
            try:
                month = datetime.datetime.strptime(options["month"], "%Y-%m").date()
            except ValueError:
                raise CommandError("--month debe tener el formato AAAA-MM, por ejemplo 2026-09.")
        else:
            month = previous_month()
        if not settings.SITE_URL and not options["dry_run"]:
            raise CommandError("Define SITE_URL para que el enlace de baja del correo lleve al dominio de la web.")
        limit = options["limit"] or settings.EMAIL_MAX_PER_RUN
        summary = send_monthly_reports(month, dry_run=options["dry_run"], limit=limit)
        verb = "Se enviarían" if options["dry_run"] else "Enviados"
        self.stdout.write(f"{verb} ({month:%Y-%m}): {len(summary.sent)}")
        for email in summary.sent:
            self.stdout.write(f"  {email}")
        for reason, n in summary.skipped.items():
            self.stdout.write(f"Saltados ({reason}): {n}")
        if "límite de la pasada" in summary.skipped:
            self.stdout.write("Quedan informes por enviar: vuelve a lanzar el comando.")
        if summary.failed:
            raise CommandError(f"{len(summary.failed)} informes no se han podido enviar (se reintentarán): "
                               + ", ".join(f"{email}: {error}" for email, error in summary.failed))
