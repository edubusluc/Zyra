"""Almacenamiento de estáticos de producción tolerante con referencias rotas de terceros."""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class TolerantManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Igual que el almacenamiento con manifiesto, pero sin abortar por referencias que no existen.

    Las librerías de ``static/vendor/`` (Font Awesome, Chart.js...) traen referencias a ficheros que
    no se incluyen (fuentes ``.ttf`` de respaldo, ``sourceMappingURL``). ``collectstatic`` las trata
    como error con el almacenamiento estándar; aquí se dejan tal cual, porque el navegador solo pide
    lo que necesita (``.woff2``) y los mapas son opcionales.
    """

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        """Devuelve el nombre con hash, o el original si el fichero referenciado no existe."""
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            return name
