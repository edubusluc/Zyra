"""
Base común de los comandos del back-office que leen SNP y aplican el resultado
(``complete_snp_team`` y ``add_group_teams``): resolver el equipo propio, buscar, mostrar el plan y confirmar.
"""
from django.core.management.base import BaseCommand, CommandError

from players.models import SnpAccount, SnpTeamImport
from players.snp_import import search
from team.models import Team


def resolve_own_team(team_id):
    """
    Equipo propio de un club con cuenta SNP a partir de su id (``TEA...`` o el numérico interno,
    por si se lanza a mano desde la consola). Lanza CommandError si no existe, es un rival o el
    club no tiene cuenta SNP.
    """
    team_id = team_id.strip()
    lookup = {"pk": int(team_id)} if team_id.isdigit() else {"public_id": team_id}
    team = Team.objects.select_related("club").filter(**lookup).first()
    if team is None:
        raise CommandError(f"No existe ningún equipo con id {team_id}.")
    if not team.is_own or team.club is None:
        raise CommandError(f"El equipo {team_id} ({team}) es un rival, no el equipo propio de un club.")
    if not SnpAccount.objects.filter(club=team.club).exists():
        raise CommandError(f"El club {team.club} no tiene cuenta SNP.")
    return team


class SnpImportCommand(BaseCommand):
    """
    Plantilla de los comandos de importación desde SNP. Cada subclase define ``intro``, ``group_only``,
    ``dry_run_message``, ``describe`` (muestra el plan) y ``apply`` (confirma la importación).
    """
    intro = ""
    group_only = False
    dry_run_message = ""
    dry_run_help = ""

    def add_arguments(self, parser):
        """``team_id`` del equipo propio; ``--dry-run`` solo muestra y ``--headed`` enseña el navegador."""
        parser.add_argument("team_id", help="Id del equipo propio del club en Zyra, TEA... (se ve en el back-office, ficha del club).")
        parser.add_argument("--dry-run", action="store_true", help=self.dry_run_help)
        parser.add_argument("--headed", action="store_true", help="Abre el navegador a la vista (necesita pantalla).")

    def describe(self, team_import):
        """Escribe qué se crearía y qué ya existe; devuelve False si SNP no ha devuelto nada que aplicar."""
        raise NotImplementedError

    def apply(self, team_import):
        """Aplica la importación ya buscada y devuelve el ``SnpTeamImport`` resultante."""
        raise NotImplementedError

    def handle(self, *args, team_id, dry_run=False, headed=False, **options):
        """
        Comprueba que el equipo sea el propio de un club con cuenta SNP, busca en SNP, muestra el plan y,
        salvo con ``--dry-run``, lo aplica. Lanza CommandError si algo falla.
        """
        team = resolve_own_team(team_id)
        club = team.club
        self.stdout.write(f"{self.intro}: {team} (club {club})")
        verbose = options["verbosity"] >= 2 or headed
        log = (lambda message: self.stdout.write(f"  {message}")) if verbose else None
        team_import = SnpTeamImport.objects.create(club=club, source=SnpTeamImport.BACKOFFICE)
        team_import = search(team_import, headed=headed, log=log, group_only=self.group_only)
        if team_import.status == SnpTeamImport.ERROR:
            raise CommandError(team_import.message)
        self.describe(team_import)

        if dry_run:
            team_import.status = SnpTeamImport.CANCELLED
            team_import.message = self.dry_run_message
            team_import.save(update_fields=["status", "message"])
            self.stdout.write(team_import.message)
            return
        team_import = self.apply(team_import)
        self.stdout.write(f"Resultado: {team_import.message}")
