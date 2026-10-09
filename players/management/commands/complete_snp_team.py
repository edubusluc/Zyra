"""
Comando ``complete_snp_team``: «Completar equipo» desde el back-office, en un solo paso
(busca en SNP y crea los jugadores que faltan) y sin el límite mensual de la web.
"""
from django.core.management.base import BaseCommand, CommandError

from players.models import SnpAccount, SnpTeamImport
from players.snp_import import confirm, search
from team.models import Team


class Command(BaseCommand):
    """Completa el equipo propio de un club con los jugadores de SNP que todavía no están en Zyra."""
    help = ("«Completar equipo»: da de alta en Zyra los jugadores del equipo de SNP del club que todavía "
            "no existen. Nunca modifica los jugadores que ya están. Desde aquí no se aplica el límite "
            "de una vez al mes de la web.")

    def add_arguments(self, parser):
        """``team_id`` del equipo propio; ``--dry-run`` solo muestra y ``--headed`` enseña el navegador."""
        parser.add_argument("team_id", help="Id del equipo propio del club en Zyra, TEA... (se ve en el back-office, ficha del club).")
        parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué jugadores se añadirían, sin crearlos.")
        parser.add_argument("--headed", action="store_true", help="Abre el navegador a la vista (necesita pantalla).")

    def handle(self, *args, team_id, dry_run=False, headed=False, **options):
        """
        Comprueba que el equipo sea el propio de un club con cuenta SNP, busca en SNP, muestra qué
        se añadiría y qué ya existe y, salvo con ``--dry-run``, crea los jugadores. Lanza
        CommandError si algo falla.
        """
        team_id = team_id.strip()
        # También acepta el id numérico interno, por si se lanza a mano desde la consola
        lookup = {"pk": int(team_id)} if team_id.isdigit() else {"public_id": team_id}
        team = Team.objects.select_related("club").filter(**lookup).first()
        if team is None:
            raise CommandError(f"No existe ningún equipo con id {team_id}.")
        if not team.is_own or team.club is None:
            raise CommandError(f"El equipo {team_id} ({team}) es un rival, no el equipo propio de un club.")
        club = team.club
        if not SnpAccount.objects.filter(club=club).exists():
            raise CommandError(f"El club {club} no tiene cuenta SNP.")

        self.stdout.write(f"Equipo que se completa: {team} (club {club})")
        verbose = options["verbosity"] >= 2 or headed
        log = (lambda message: self.stdout.write(f"  {message}")) if verbose else None
        team_import = SnpTeamImport.objects.create(club=club, source=SnpTeamImport.BACKOFFICE)
        team_import = search(team_import, headed=headed, log=log)
        if team_import.status == SnpTeamImport.ERROR:
            raise CommandError(team_import.message)

        to_add = [f"{p['name']} {p['last_name']}" for p in team_import.to_add]
        self.stdout.write(f"Jugadores a añadir: {len(to_add)}" + (f" ({', '.join(to_add)})" if to_add else ""))
        existing = [f"{p['snp_name']} → {p['player']}" for p in team_import.existing]
        self.stdout.write(f"Ya registrados (solo se actualizan sus puntos SNP): {len(existing)}"
                          + (f" ({', '.join(existing)})" if existing else ""))

        if dry_run:
            team_import.status = SnpTeamImport.CANCELLED
            team_import.message = "Simulación (--dry-run): no se ha creado ningún jugador."
            team_import.save(update_fields=["status", "message"])
            self.stdout.write(team_import.message)
            return
        team_import = confirm(team_import)
        self.stdout.write(f"Resultado: {team_import.message}")
