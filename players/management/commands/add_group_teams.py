"""
Comando ``add_group_teams``: crea desde el back-office los equipos del grupo de un club leyéndolos
de la «Clasificación» de SNP, sin tocar los jugadores y sin el límite mensual de la web.
"""
from django.core.management.base import CommandError

from players.management.commands._snp_import_command import SnpImportCommand
from players.snp_import import apply_group_teams


class Command(SnpImportCommand):
    """Añade al grupo del club los equipos de su clasificación en SNP que todavía no están en Zyra."""
    help = ("Crea en Zyra los equipos del grupo del club (tabla «Clasificación» de SNP) que todavía no "
            "existen y da de alta en el grupo los que ya estaban fuera. No toca los jugadores ni aplica "
            "el límite de una vez al mes de la web.")
    intro = "Equipo propio"
    group_only = True
    dry_run_help = "Solo muestra qué equipos se crearían, sin crearlos."
    dry_run_message = "Simulación (--dry-run): no se ha creado ningún equipo."

    def describe(self, team_import):
        """Muestra los equipos a crear y los que ya existen; falla si SNP no devolvió ninguno."""
        to_create = [t["name"] for t in team_import.teams_to_add]
        self.stdout.write(f"Equipos a crear: {len(to_create)}" + (f" ({', '.join(to_create)})" if to_create else ""))
        existing = [f"{t['name']} → {t['team']}" + ("" if t.get("in_group") else " (se da de alta en el grupo)")
                    for t in team_import.teams_existing]
        self.stdout.write(f"Ya existen: {len(existing)}" + (f" ({', '.join(existing)})" if existing else ""))
        if not to_create and not team_import.teams_existing:
            raise CommandError("SNP no ha devuelto ningún equipo en la clasificación.")

    def apply(self, team_import):
        """Crea los equipos del grupo que faltan, sin tocar jugadores."""
        return apply_group_teams(team_import)
