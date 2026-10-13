"""Comando del lanzador de procesos programados (cada minuto con cron, o con --loop)."""
import threading
import time

from django.core.management.base import BaseCommand

from backoffice.scheduler import run_due_jobs


class Command(BaseCommand):
    """Una pasada del lanzador de procesos programados, o un bucle de pasadas con ``--loop``."""
    help = ("Lanza los procesos programados a los que les toca. Ejecútalo cada minuto (cron o similar) "
            "o déjalo en marcha con --loop.")

    def add_arguments(self, parser):
        """``--loop`` repite la pasada cada ``--interval`` segundos; en ese modo cada proceso corre en su hilo."""
        parser.add_argument("--loop", action="store_true",
                            help="No termina: pasa cada --interval segundos y cada proceso corre en su hilo "
                                 "(desarrollo, contenedores u hostings sin cron).")
        parser.add_argument("--interval", type=int, default=30, help="Segundos entre pasadas con --loop (30 por defecto).")

    def handle(self, *args, loop=False, interval=30, **options):
        """Una pasada, o con ``--loop`` pasadas hasta Ctrl+C (espera a que acaben los procesos en marcha)."""
        if not loop:
            self._pass(parallel=False)
            return
        self.stdout.write(f"Lanzador en marcha (cada {interval} s). Ctrl+C para parar.")
        try:
            while True:
                self._pass(parallel=True)
                time.sleep(max(interval, 5))
        except KeyboardInterrupt:
            self.stdout.write("Parando: esperando a los procesos en marcha…")
            for thread in threading.enumerate():
                if thread.name.startswith("job-"):
                    thread.join()

    def _pass(self, parallel):
        """Una pasada: escribe una línea por proceso lanzado (o «Nada que ejecutar.»)."""
        runs = run_due_jobs(parallel=parallel)
        for run in runs:
            state = "lanzado" if parallel else run.get_status_display()
            self.stdout.write(f"{run.job.name}: {state}")
        if not runs and not parallel:
            self.stdout.write("Nada que ejecutar.")
