"""Comando ``snapshot_daily_metrics``: guarda el resumen diario (usuarios activos, clubes, partidos, errores)."""
import datetime

from django.core.management.base import BaseCommand, CommandError

from backoffice.metrics import snapshot_daily_metrics


class Command(BaseCommand):
    """Calcula el DailyMetric de un día (hoy por defecto)."""
    help = "Guarda el resumen diario de métricas. Con --date AAAA-MM-DD recalcula un día concreto."

    def add_arguments(self, parser):
        """Opción ``--date``."""
        parser.add_argument("--date", help="Día a calcular (AAAA-MM-DD); hoy por defecto.")

    def handle(self, *args, date=None, **options):
        """Guarda el resumen y escribe sus cifras."""
        try:
            day = datetime.date.fromisoformat(date) if date else None
        except ValueError:
            raise CommandError("La fecha tiene que ser AAAA-MM-DD.")
        m = snapshot_daily_metrics(day)
        self.stdout.write(f"{m.date}: {m.users} usuarios, {m.dau} activos hoy, {m.wau} en 7 días, {m.mau} en 30 días, "
                          f"{m.clubs} clubes ({m.active_clubs} activos), {m.errors_5xx} errores 500.")
