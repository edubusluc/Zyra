"""Configuración de la app core."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuración de la app core."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        """Las etiquetas de los formularios no llevan dos puntos (UX-050): ``label_suffix`` vacío por defecto."""
        from django.forms import BaseForm
        original = BaseForm.__init__

        def init(form, *args, **kwargs):
            """Igual que ``BaseForm.__init__``, pero quita los dos puntos que Django pone por defecto."""
            original(form, *args, **kwargs)
            if str(form.label_suffix) == ':':
                form.label_suffix = ''

        BaseForm.__init__ = init
