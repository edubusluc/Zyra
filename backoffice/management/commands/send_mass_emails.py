"""Comando ``send_mass_emails``: envía lo pendiente de los correos a varios usuarios en cola, respetando el cupo diario."""
from django.core.management.base import BaseCommand

from backoffice import mass_email
from backoffice.models import MassEmail


class Command(BaseCommand):
    """Cada pasada envía a los destinatarios pendientes mientras quede cupo (menos la reserva de la web)."""
    help = "Envía los correos masivos en cola. Reanudable: lo ya enviado no se repite; el resto sale cuando haya cupo."

    def handle(self, *args, **options):
        """Una línea con lo enviado y fallido, o «Sin envíos masivos pendientes.»."""
        if not MassEmail.objects.filter(status=MassEmail.PENDING).exists():
            self.stdout.write("Sin envíos masivos pendientes.")
            return
        sent, failed = mass_email.send_pending()
        self.stdout.write(f"Enviados {sent} correos masivos; {failed} fallidos.")
