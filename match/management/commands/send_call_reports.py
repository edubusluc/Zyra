"""Comando que envía los correos pendientes (informes de convocatoria y avisos de resultado) y reintenta los fallidos (pensado para cron)."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from call.models import ReportDelivery
from match import result_email
from match.models import MatchResultDelivery
from match.notifications import MAX_ATTEMPTS, deliver, due_deliveries


class Command(BaseCommand):
    """Envía los informes de convocatoria y los avisos de resultado pendientes; falla si alguno se da por perdido."""
    help = ("Envía los informes de convocatoria y los avisos de resultado pendientes y reintenta los que fallaron "
            f"(como mucho EMAIL_MAX_PER_RUN por pasada; tras {MAX_ATTEMPTS} intentos se dan por fallidos).")

    def handle(self, *args, **options):
        """Envía como mucho EMAIL_MAX_PER_RUN correos pendientes (informes primero) y muestra el resultado de cada uno.

        Termina con CommandError si alguno ha agotado los reintentos, para que se note en el cron.
        """
        limit = settings.EMAIL_MAX_PER_RUN
        reports = due_deliveries(limit=limit)
        results = result_email.due_deliveries(limit=max(limit - len(reports), 0))
        if not reports and not results:
            self.stdout.write("No hay informes pendientes de enviar.")
            return
        self.stdout.write(f"Informes a enviar: {len(reports)} · avisos de resultado: {len(results)}")
        failed = []
        for delivery in deliver(reports):
            label = f"{delivery.call} a {delivery.email}"
            if self._report(delivery, label, delivery.status == ReportDelivery.SENT):
                failed.append(label)
        for delivery in result_email.deliver(results):
            label = f"resultado de {delivery.match} a {delivery.email}"
            if self._report(delivery, label, delivery.status == MatchResultDelivery.SENT):
                failed.append(label)
        if failed:
            raise CommandError(f"{len(failed)} correos no se han podido enviar tras {MAX_ATTEMPTS} intentos: "
                               + ", ".join(failed)
                               + ". Los informes de convocatoria se pueden descargar o reenviar desde la convocatoria.")

    def _report(self, delivery, label, sent):
        """Escribe cómo ha ido un envío; True si se ha dado por perdido (sin más reintentos)."""
        if sent:
            self.stdout.write(f"Enviado: {label}")
            return False
        if delivery.status == delivery.FAILED:
            self.stdout.write(f"Fallido definitivamente: {label}: {delivery.last_error}")
            return True
        self.stdout.write(f"Error (intento {delivery.attempts} de {MAX_ATTEMPTS}, se reintentará): "
                          f"{label}: {delivery.last_error}")
        return False
