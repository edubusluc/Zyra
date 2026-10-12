"""
Comando ``process_snp_imports``: atiende la cola de búsquedas de «Completar equipo» pedidas desde
la web. Lo lanza el programador cada minuto (``backoffice/jobs.py``); las atiende de una en una,
así el navegador de SNP (Chromium) nunca corre dentro del proceso web ni varias veces a la vez.
"""
from django.core.management.base import BaseCommand

from players import snp_import, snp_service


class Command(BaseCommand):
    """Procesa las búsquedas de «Completar equipo» que esperan en cola."""
    help = "Atiende de una en una las búsquedas de «Completar equipo» pedidas desde la web."

    def add_arguments(self, parser):
        """Opción ``--max``: cuántas búsquedas como mucho en esta pasada."""
        parser.add_argument("--max", type=int, default=10, help="Búsquedas como máximo en esta pasada (10 por defecto).")

    def handle(self, *args, max=10, **options):
        """Atiende la cola; con el servicio de SNP apagado, las búsquedas en cola terminan con el aviso de no disponible."""
        done = snp_import.process_queue(max_items=max, log=self.stdout.write)
        if done:
            self.stdout.write(f"Búsquedas atendidas: {done}.")
        elif not snp_service.is_enabled():
            self.stdout.write("Servicio de SNP apagado.")
