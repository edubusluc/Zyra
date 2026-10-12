"""
Comando ``add_group_teams``: crea desde el back-office los equipos del grupo de un club leyéndolos
de la «Clasificación» de SNP, sin tocar los jugadores y sin el límite mensual de la web.
"""
from django.core.management.base import BaseCommand, CommandError

from players.management.commands.complete_snp_team import resolve_own_team
from players.models import SnpTeamImport
from players.snp_import import apply_group_teams, search


class Command(BaseCommand):
    """Añade al grupo del club los equipos de su clasificación en SNP que todavía no están en Zyra."""
    help = ("Crea en Zyra los equipos del grupo del club (tabla «Clasificación» de SNP) que todavía no "
            "existen y da de alta en el grupo los que ya estaban fuera. No toca los jugadores ni aplica "
            "el límite de una vez al mes de la web.")

    def add_arguments(self, parser):
        """``team_id`` del equipo propio; ``--dry-run`` solo muestra y ``--headed`` enseña el navegador."""
        parser.add_argument("team_id", help="Id del equipo propio del club en Zyra, TEA... (se ve en el back-office, ficha del club).")
        parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué equipos se crearían, sin crearlos.")
        parser.add_argument("--headed", action="store_true", help="Abre el navegador a la vista (necesita pantalla).")

    def handle(self, *args, team_id, dry_run=False, headed=False, **options):
        """
        Comprueba que el equipo sea el propio de un club con cuenta SNP, lee SNP, muestra qué equipos
        se crearían y cuáles ya existen y, salvo con ``--dry-run``, los crea. Lanza CommandError si algo falla.
        """
        team = resolve_own_team(team_id)
        club = team.club
        self.stdout.write(f"Equipo propio: {team} (club {club})")
        verbose = options["verbosity"] >= 2 or headed
        log = (lambda message: self.stdout.write(f"  {message}")) if verbose else None
        team_import = SnpTeamImport.objects.create(club=club, source=SnpTeamImport.BACKOFFICE)
        team_import = search(team_import, headed=headed, log=log)
        if team_import.status == SnpTeamImport.ERROR:
            raise CommandError(team_import.message)

        to_create = [t["name"] for t in team_import.teams_to_add]
        self.stdout.write(f"Equipos a crear: {len(to_create)}" + (f" ({', '.join(to_create)})" if to_create else ""))
        existing = [f"{t['name']} → {t['team']}" + ("" if t.get("in_group") else " (se da de alta en el grupo)")
                    for t in team_import.teams_existing]
        self.stdout.write(f"Ya existen: {len(existing)}" + (f" ({', '.join(existing)})" if existing else ""))
        if not to_create and not team_import.teams_existing:
            raise CommandError("SNP no ha devuelto ningún equipo en la clasificación.")

        if dry_run:
            team_import.status = SnpTeamImport.CANCELLED
            team_import.message = "Simulación (--dry-run): no se ha creado ningún equipo."
            team_import.save(update_fields=["status", "message"])
            self.stdout.write(team_import.message)
            return
        team_import = apply_group_teams(team_import)
        self.stdout.write(f"Resultado: {team_import.message}")
