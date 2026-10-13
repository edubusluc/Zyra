"""
Comando ``complete_snp_team``: «Completar equipo» desde el back-office, en un solo paso
(busca en SNP y crea los jugadores que faltan) y sin el límite mensual de la web.
"""
from players.management.commands._snp_import_command import SnpImportCommand
from players.snp_import import confirm


class Command(SnpImportCommand):
    """Completa el equipo propio de un club con los jugadores de SNP que todavía no están en Zyra."""
    help = ("«Completar equipo»: da de alta en Zyra los jugadores del equipo de SNP del club que todavía "
            "no existen. Nunca modifica los jugadores que ya están. Desde aquí no se aplica el límite "
            "de una vez al mes de la web.")
    intro = "Equipo que se completa"
    dry_run_help = "Solo muestra qué jugadores se añadirían, sin crearlos."
    dry_run_message = "Simulación (--dry-run): no se ha creado ningún jugador."

    def describe(self, team_import):
        """Muestra los jugadores a añadir y los ya registrados."""
        to_add = [f"{p['name']} {p['last_name']}" for p in team_import.to_add]
        self.stdout.write(f"Jugadores a añadir: {len(to_add)}" + (f" ({', '.join(to_add)})" if to_add else ""))
        existing = [f"{p['snp_name']} → {p['player']}" for p in team_import.existing]
        self.stdout.write(f"Ya registrados (solo se actualizan sus puntos SNP): {len(existing)}"
                          + (f" ({', '.join(existing)})" if existing else ""))

    def apply(self, team_import):
        """Crea los jugadores, actualiza puntos y da de alta los equipos del grupo."""
        return confirm(team_import)
