"""Comando ``send_staff_digest``: envía al personal el resumen semanal de la plataforma."""
from django.core.management.base import BaseCommand

from backoffice.digest import build_digest, send_digest


class Command(BaseCommand):
    """Resumen de la última semana por correo (altas, actividad, informes, errores, tareas)."""
    help = "Envía al personal el resumen de los últimos 7 días. Con --dry-run solo lo escribe."

    def add_arguments(self, parser):
        """Opciones ``--days`` y ``--dry-run``."""
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--dry-run", action="store_true", help="Solo muestra el resumen.")

    def handle(self, *args, days, dry_run, **options):
        """Escribe el resumen y, salvo --dry-run, lo envía."""
        for line in build_digest(days):
            self.stdout.write(f"- {line}")
        if not dry_run:
            self.stdout.write(f"Enviado a {send_digest(days)} personas.")
