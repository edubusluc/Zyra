"""
Deja la base de datos de Zyra vacía y con el esquema actual, para empezar de cero.

    python clear_database.py          # pide confirmación
    python populate_db.py             # opcional: carga los datos de partida

Qué hace:
1. Borra TODAS las tablas y sus datos, también las que ya no usa la aplicación (por
   ejemplo post_post y post_image del antiguo módulo de publicaciones) y el historial de
   migraciones aplicadas.
2. Vuelve a crear las tablas con las migraciones del repositorio (`migrate`): usuarios,
   clubes, equipos, jugadores, partidos, convocatorias, fotos revisadas y eliminadas,
   emails bloqueados, back-office... todo vacío.
3. Borra las fotos subidas (carpetas teams/ y players/ del almacenamiento de fotos, por
   defecto media/), que ya no son de nadie. Las fotos de ejemplo de populate/photos no se tocan.

Funciona con la base de datos configurada en zyra.settings (SQLite, o PostgreSQL con las
tablas en el esquema public) y con el almacenamiento de fotos configurado (disco o bucket
S3). No se puede deshacer: haz antes una copia (en SQLite basta con copiar db.sqlite3, y
la carpeta media/).

Con DJANGO_DEBUG=False (producción) se niega a borrar nada, salvo que se defina a propósito
ZYRA_PERMITIR_BORRAR_PRODUCCION=si. La imagen Docker de producción tampoco lo incluye.

Opciones:
    --yes             no pide confirmación.
    --conservar-fotos no borra las fotos subidas.
"""
import os
import sys
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zyra.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402

from core.images import PHOTO_DIRS  # noqa: E402


def refuse_in_production():
    """Sale con un error si DEBUG está apagado (producción), salvo permiso explícito por variable de entorno."""
    if not settings.DEBUG and os.environ.get("ZYRA_PERMITIR_BORRAR_PRODUCCION") != "si":
        sys.exit("Negado: con DJANGO_DEBUG=False esto borraría la base de datos de producción. "
                 "Solo se usa en desarrollo.")


def drop_all_tables():
    """
    Borra todas las tablas sin construir SQL con sus nombres: en SQLite se borra el
    fichero de la base de datos y en PostgreSQL se vuelve a crear el esquema public.
    """
    tables = connection.introspection.table_names()
    vendor = connection.vendor
    if vendor == "sqlite":
        path = Path(connection.settings_dict["NAME"])
        connection.close()
        path.unlink(missing_ok=True)
    elif vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
        connection.close()
    else:
        sys.exit(f"Base de datos {vendor} no soportada: usa SQLite o PostgreSQL.")
    return tables


def _files(folder):
    """Rutas de todos los ficheros de ``folder`` en el almacenamiento de fotos, recorriendo subcarpetas."""
    try:
        dirs, files = default_storage.listdir(folder)
    except FileNotFoundError:
        return []
    found = [f"{folder}/{name}" for name in files]
    for sub in dirs:
        found += _files(f"{folder}/{sub}")
    return found


def delete_uploaded_photos():
    """Borra las fotos subidas (carpetas de PHOTO_DIRS) y devuelve cuántas se han borrado."""
    deleted = 0
    for folder in PHOTO_DIRS:
        for name in _files(folder):
            default_storage.delete(name)
            deleted += 1
    return deleted


if __name__ == "__main__":
    args = set(sys.argv[1:])
    refuse_in_production()
    keep_photos = "--conservar-fotos" in args
    db = connection.settings_dict["NAME"]
    tables = connection.introspection.table_names()
    print(f"Base de datos: {db} ({connection.vendor}), {len(tables)} tablas.")
    if not keep_photos:
        print(f"Fotos subidas: {', '.join(f'{d}/' for d in PHOTO_DIRS)} en {getattr(default_storage, 'location', 'el bucket')}.")
    if "--yes" not in args:
        what = "TODAS las tablas y sus datos" + ("" if keep_photos else " y las fotos subidas")
        if input(f'Se borrarán {what}. Escribe "BORRAR" para seguir: ').strip() != "BORRAR":
            sys.exit("Cancelado: no se ha borrado nada.")

    print(f"Borradas {len(drop_all_tables())} tablas.")
    call_command("migrate", interactive=False, verbosity=0)
    print(f"Creadas de nuevo {len(connection.introspection.table_names())} tablas con las migraciones (vacías).")
    if not keep_photos:
        print(f"Borradas {delete_uploaded_photos()} fotos subidas.")
    print("Listo. Para cargar los datos de partida: python populate_db.py")
