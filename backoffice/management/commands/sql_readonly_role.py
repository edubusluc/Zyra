"""
Comando ``sql_readonly_role``: prepara en PostgreSQL el rol de solo lectura de la consola SQL.

El rol puede leer todas las tablas salvo las ocultas (sesiones, tokens de allauth), y de las
demás solo las columnas que no son sensibles (contraseñas, tokens, datos cifrados). Así, aunque
alguien burle la lista de nombres de ``backoffice/sql.py``, la base de datos se niega a darle esos datos.
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from backoffice import sql


def build_script(role, password_sql="'<contraseña>'", cursor=None):
    """
    Sentencias SQL (lista de textos) que crean el rol si no existe y le dan SELECT sobre las
    tablas y columnas permitidas. ``password_sql`` es el literal de la contraseña ya escapado.
    """
    q = connection.ops.quote_name
    statements = [
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN "
        f"CREATE ROLE {q(role)} LOGIN PASSWORD {password_sql}; END IF; END $$",
        f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {q(role)}",
        f"GRANT USAGE ON SCHEMA public TO {q(role)}",
    ]
    own_cursor = cursor is None
    cursor = cursor or connection.cursor()
    try:
        for table in sorted(connection.introspection.table_names(cursor)):
            if table in sql.HIDDEN_TABLES:
                continue
            columns = [c.name for c in connection.introspection.get_table_description(cursor, table)]
            allowed = [c for c in columns if not any(f in c.lower() for f in sql.BLOCKED_FRAGMENTS)]
            if len(allowed) == len(columns):
                statements.append(f"GRANT SELECT ON {q(table)} TO {q(role)}")
            elif allowed:
                statements.append(f"GRANT SELECT ({', '.join(q(c) for c in allowed)}) ON {q(table)} TO {q(role)}")
    finally:
        if own_cursor:
            cursor.close()
    return statements


class Command(BaseCommand):
    """Imprime (o aplica) el script que crea el rol de solo lectura de la consola SQL."""
    help = "Crea el rol de PostgreSQL de solo lectura de la consola SQL (sin columnas sensibles)."

    def add_arguments(self, parser):
        """``--role`` nombre del rol; ``--apply`` lo ejecuta (la contraseña va en SQL_CONSOLE_DB_PASSWORD)."""
        parser.add_argument("--role", default="zyra_sql_readonly", help="Nombre del rol (zyra_sql_readonly por defecto).")
        parser.add_argument("--apply", action="store_true",
                            help="Ejecuta el script con la conexión de la aplicación (necesita permiso para crear roles); "
                                 "la contraseña del rol se lee de la variable SQL_CONSOLE_DB_PASSWORD.")

    def handle(self, *args, role, apply, **options):
        """Solo PostgreSQL. Sin ``--apply`` muestra el script para revisarlo."""
        if connection.vendor != "postgresql":
            raise CommandError("Solo hace falta con PostgreSQL: SQLite usa PRAGMA query_only y la lista de nombres.")
        if not role.replace("_", "").isalnum():
            raise CommandError("El nombre del rol solo puede llevar letras, números y guiones bajos.")
        if not apply:
            for statement in build_script(role):
                self.stdout.write(statement + ";")
            self.stdout.write(
                "\n-- Después: SQL_CONSOLE_DATABASE_URL=postgres://%s:<contraseña>@<host>:5432/<base>" % role
            )
            return
        password = os.environ.get("SQL_CONSOLE_DB_PASSWORD", "")
        if len(password) < 16 or "$" in password:
            raise CommandError("Define SQL_CONSOLE_DB_PASSWORD (16 caracteres como mínimo y sin «$») para la contraseña del rol.")
        from psycopg import sql as pgsql
        with connection.cursor() as cursor:
            literal = pgsql.Literal(password).as_string(connection.connection)
            for statement in build_script(role, literal, cursor):
                cursor.execute(statement)
        self.stdout.write(self.style.SUCCESS(f"Rol {role} listo. Configura SQL_CONSOLE_DATABASE_URL con su contraseña."))
