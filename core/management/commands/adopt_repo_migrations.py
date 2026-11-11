"""
Paso único para las bases de datos creadas cuando las migraciones no estaban en git.

Hasta octubre de 2026 cada entorno generaba sus propias migraciones con makemigrations,
así que el historial guardado en la tabla django_migrations no coincide con los ficheros
que ahora hay en el repositorio. Este comando:

1. Comprueba que la base de datos ya tiene todas las tablas y columnas que crean las
   migraciones 0001_initial del repositorio. Si falta algo, se para sin tocar nada.
2. Borra del historial las migraciones antiguas de las apps del proyecto que no existen
   en el repositorio (solo el historial: ninguna tabla ni dato).
3. Marca como aplicadas las 0001_initial del repositorio.

Después hay que ejecutar ``python manage.py migrate`` para aplicar las migraciones
posteriores (0002 en adelante). Se puede repetir sin riesgo.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

PROJECT_APPS = ["backoffice", "call", "callLog", "core", "data_analyse", "match", "penalty", "players", "team"]
INITIAL = "0001_initial"
# Tablas que crea una 0001_initial y borra una migración posterior (``callLog.0002_delete_calllog``): su ausencia no impide adaptar.
DROPPED_LATER = {"callLog_calllog"}


class Command(BaseCommand):
    """Adapta el historial de migraciones de una base de datos antigua a las del repositorio."""
    help = ("Adapta una base de datos creada con migraciones locales a las migraciones del repositorio "
            "(solo cambia el historial de migraciones; no toca tablas ni datos).")

    def add_arguments(self, parser):
        """Opción --dry-run."""
        parser.add_argument("--dry-run", action="store_true", help="Solo muestra lo que haría.")

    def handle(self, *args, dry_run=False, **options):
        """
        Comprueba el esquema, olvida las migraciones antiguas y marca las 0001_initial del
        repositorio como aplicadas (con --dry-run solo lo muestra).
        """
        loader = MigrationLoader(connection)
        recorder = MigrationRecorder(connection)
        repo = {key for key in loader.disk_migrations if key[0] in PROJECT_APPS}
        initials = sorted(key for key in repo if key[1] == INITIAL)
        applied = {key for key in recorder.applied_migrations() if key[0] in PROJECT_APPS}

        if not applied:
            self.stdout.write("La base de datos no tiene migraciones del proyecto: ejecuta directamente "
                              "python manage.py migrate.")
            return
        foreign = sorted(applied - repo)
        if not foreign and all(key in applied for key in initials):
            self.stdout.write(self.style.SUCCESS("El historial ya coincide con las migraciones del repositorio. "
                                                 "Nada que hacer."))
            return

        missing = self._missing_schema(loader, initials)
        if missing:
            raise CommandError(
                "La base de datos no tiene todo lo que crean las migraciones 0001_initial del repositorio, "
                "así que no se puede adaptar automáticamente. Falta:\n  " + "\n  ".join(missing) +
                "\nActualiza antes la base de datos con el código anterior (makemigrations + migrate) "
                "o empieza con una base de datos nueva."
            )

        self.stdout.write(f"Migraciones antiguas en el historial que se olvidarán: {len(foreign)}")
        for app, name in foreign:
            self.stdout.write(f"  - {app}.{name}")
        self.stdout.write("Migraciones del repositorio que se marcarán como aplicadas:")
        for app, name in initials:
            if (app, name) not in applied:
                self.stdout.write(f"  + {app}.{name}")
        if dry_run:
            self.stdout.write("--dry-run: no se ha cambiado nada.")
            return

        for app, name in foreign:
            recorder.record_unapplied(app, name)
        for app, name in initials:
            if (app, name) not in applied:
                recorder.record_applied(app, name)
        self.stdout.write(self.style.SUCCESS("Historial adaptado. Ahora ejecuta: python manage.py migrate"))

    def _missing_schema(self, loader, initials):
        """Tablas y columnas de las 0001_initial del repositorio que no existen en la base de datos."""
        state = loader.project_state(initials, at_end=True)
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            missing = []
            for model in state.apps.get_models():
                if model._meta.app_label not in PROJECT_APPS:
                    continue
                table = model._meta.db_table
                if table in DROPPED_LATER:
                    continue
                if table not in tables:
                    missing.append(f"tabla {table}")
                    continue
                columns = {c.name for c in connection.introspection.get_table_description(cursor, table)}
                missing += [f"columna {table}.{f.column}" for f in model._meta.local_fields if f.column not in columns]
                for m2m in model._meta.local_many_to_many:
                    through = m2m.remote_field.through
                    if through._meta.auto_created and through._meta.db_table not in tables:
                        missing.append(f"tabla {through._meta.db_table}")
        return missing
