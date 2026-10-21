"""
Actualización de los puntos SNP (lunes y miércoles), por lotes.

Cada lunes y miércoles a las 05:00 (SNP_SYNC_CYCLE) empieza un ciclo. El proceso procesa los
clubes pendientes del ciclo: los que todavía no se han intentado desde que empezó y los que
fallaron por algo pasajero. Al empezar el ciclo son todos; si una ejecución queda a medias,
una nueva pasada manual retoma lo que falte.

Los clubes se procesan en lotes (SNP_BATCH_SIZE, 50 por defecto):

- cada club se guarda en su propia transacción y un fallo en uno no afecta a los demás;
- cada lote usa un navegador nuevo (si uno se queda colgado, solo afecta a su lote);
- entre club y club hay una pausa aleatoria y entre lote y lote una más larga, para no
  hacer a SNP más peticiones de las que haría una persona;
- si SNP responde que le estamos haciendo demasiadas peticiones, o fallan varios clubes
  seguidos por problemas de red, el proceso para: los clubes que faltan se hacen en la
  siguiente pasada, y el personal recibe el aviso de fallo del back-office.

Primero van los clubes que nunca se han actualizado y después los que llevan más tiempo
sin actualizarse, así una pasada interrumpida retoma por donde iba.
"""
import datetime
import random
import time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q
from django.utils import timezone

from backoffice.cron import Cron
from backoffice.jobs import SCHEDULER_TIME_ZONE
from players import snp_service
from players.models import SnpAccount
from players.scraper import SnpBrowser
from players.snp import sync_club

# Inicio de cada ciclo de actualización: lunes y miércoles a las 05:00 (hora de Madrid).
SNP_SYNC_CYCLE = "0 5 * * 1,3"


def cycle_start(now=None):
    """Último inicio de ciclo anterior o igual a ``now``."""
    local = (now or timezone.now()).astimezone(ZoneInfo(SCHEDULER_TIME_ZONE))
    cron = Cron(SNP_SYNC_CYCLE)
    start = cron.next_after(local - datetime.timedelta(days=8))
    while True:
        following = cron.next_after(start)
        if following > local:
            return start
        start = following


def pending_accounts(now=None):
    """Cuentas que faltan en el ciclo actual: sin intentar desde que empezó o con un fallo pasajero."""
    start = cycle_start(now)
    return SnpAccount.objects.filter(
        Q(last_sync_at__isnull=True) | Q(last_sync_at__lt=start) | Q(last_sync_ok=False, last_sync_retryable=True)
    )


def _pause(low, high):
    """Espera un tiempo aleatorio entre ``low`` y ``high`` segundos (nada si ``high`` es 0)."""
    if high > 0:
        time.sleep(random.uniform(low, max(low, high)))


class Command(BaseCommand):
    """Actualiza por lotes los puntos SNP de los clubes pendientes en el ciclo semanal."""
    help = ("Descarga de SNP los puntos de los jugadores de los clubes con cuenta SNP pendientes en el ciclo "
            "semanal, por lotes y con pausas para no saturar SNP.")

    def add_arguments(self, parser):
        """Opciones: un club concreto, todos los clubes, tamaño de lote y navegador a la vista."""
        parser.add_argument("--club", help="Nombre o slug de un club concreto (aunque ya esté actualizado).")
        parser.add_argument("--all", action="store_true",
                            help="Todos los clubes con cuenta SNP, aunque ya estén actualizados en este ciclo.")
        parser.add_argument("--batch-size", type=int, default=None,
                            help=f"Clubes por lote (por defecto {settings.SNP_BATCH_SIZE}).")
        parser.add_argument("--headed", action="store_true",
                            help="Abre el navegador a la vista para seguir la ejecución (necesita pantalla). "
                                 "Con --headed o -v 2 se muestran también los pasos y los puntos de cada jugador.")

    def handle(self, *args, club=None, all=False, batch_size=None, headed=False, **options):
        """
        Elige las cuentas (un club, todas o las pendientes del ciclo, las más antiguas primero),
        las procesa por lotes con pausas y para si SNP nos limita o fallan demasiados clubes
        seguidos. Lanza CommandError si se ha parado o no se ha actualizado ningún club.
        """
        if not snp_service.is_enabled():
            self.stdout.write("El servicio de SNP está apagado desde el back-office (Servicios): no se actualiza nada.")
            return
        accounts = SnpAccount.objects.select_related("club")
        if club:
            accounts = accounts.filter(Q(club__slug=club) | Q(club__name__iexact=club))
            if not accounts:
                with_account = ", ".join(f"{a.club.name} ({a.club.slug})" for a in SnpAccount.objects.select_related("club"))
                raise CommandError(f"El club «{club}» no existe o no tiene cuenta SNP. Clubes con cuenta: {with_account or 'ninguno'}.")
        elif not all:
            accounts = accounts.filter(pk__in=pending_accounts().values("pk"))
        accounts = list(accounts.order_by(F("last_sync_at").asc(nulls_first=True), "club__name"))

        size = max(1, batch_size or settings.SNP_BATCH_SIZE)
        batches = [accounts[i:i + size] for i in range(0, len(accounts), size)]
        verbose = options["verbosity"] >= 2 or headed
        if not accounts:
            start = timezone.localtime(cycle_start(), ZoneInfo(SCHEDULER_TIME_ZONE))
            self.stdout.write(f"No hay equipos pendientes: todos se han actualizado desde el {start:%d/%m/%Y %H:%M}. "
                              "Usa --all para repetirlos.")
            return
        self.stdout.write(f"Equipos a actualizar: {len(accounts)}")
        self.stdout.write(f"Lotes: {len(batches)} de hasta {size} equipos")

        ok = failed = consecutive = 0
        stop_reason = None
        done = 0
        for number, batch in enumerate(batches, 1):
            if number > 1:
                self.stdout.write("")
                self.stdout.write(f"Pausa entre lotes ({settings.SNP_BATCH_PAUSE_SECONDS} s)…")
                _pause(settings.SNP_BATCH_PAUSE_SECONDS, settings.SNP_BATCH_PAUSE_SECONDS)
            self.stdout.write("")
            self.stdout.write(f"=== Lote {number} de {len(batches)} ({len(batch)} equipos) ===")
            batch_ok = batch_failed = 0
            with SnpBrowser(headed=headed) as browser:
                for position, account in enumerate(batch):
                    if position:
                        _pause(settings.SNP_PAUSE_MIN_SECONDS, settings.SNP_PAUSE_MAX_SECONDS)
                    result = self._sync(account, browser, headed, verbose)
                    done += 1
                    if result.ok:
                        ok += 1
                        batch_ok += 1
                        consecutive = 0
                        continue
                    failed += 1
                    batch_failed += 1
                    consecutive = consecutive + 1 if result.retryable else 0
                    if result.blocked:
                        stop_reason = "SNP está limitando o rechazando nuestras peticiones"
                    elif consecutive >= settings.SNP_MAX_CONSECUTIVE_FAILURES:
                        stop_reason = f"han fallado {consecutive} equipos seguidos por problemas de red o de SNP"
                    if stop_reason:
                        break
            self.stdout.write(f"Lote {number}: {batch_ok} correctos, {batch_failed} con error.")
            if stop_reason:
                break

        left = len(accounts) - done
        self.stdout.write("")
        self.stdout.write(f"Resumen: {ok} equipos actualizados, {failed} con error, {left} sin procesar.")
        if stop_reason:
            raise CommandError(f"Proceso detenido: {stop_reason}. Los {left} equipos que faltan (y los que han "
                               "fallado por esto) se reintentan en la siguiente pasada.")
        if failed and not ok:
            raise CommandError("No se ha podido actualizar ningún equipo.")

    def _sync(self, account, browser, headed, verbose):
        """Actualiza un club con el navegador del lote, escribe el resumen y devuelve el SyncResult."""
        self.stdout.write("")
        self.stdout.write(f"Equipo que se actualiza: {account.club}")
        log = (lambda message: self.stdout.write(f"  {message}")) if verbose else None
        result = sync_club(account, headed=headed, log=log, browser=browser)
        if not result.ok:
            again = " (se reintentará en la siguiente pasada)" if result.retryable else ""
            self.stdout.write(f"Error: {result.message}{again}")
            return result
        self.stdout.write(f"Jugadores a actualizar: {result.total}")
        self.stdout.write(f"Jugadores actualizados correctamente: {len(result.updated)}")
        missing = f" ({', '.join(result.missing)})" if result.missing else ""
        self.stdout.write(f"Jugadores no actualizados: {len(result.missing)}{missing}")
        # Ayuda a entender por qué un jugador no se ha actualizado.
        if result.unmatched:
            self.stdout.write("Nombres de SNP sin jugador en Zyra: " + ", ".join(result.unmatched))
        if result.ambiguous:
            self.stdout.write("Nombres de SNP que encajan con varios jugadores: " + ", ".join(result.ambiguous))
        if verbose:
            for name, score in result.updated:
                self.stdout.write(f"  {name}: {score:g}")
        return result
