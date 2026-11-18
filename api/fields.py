"""Lectura y validación de los campos del cuerpo JSON de la API: un único sitio y un único error (``invalid_field``)."""
import re

from django.utils.translation import gettext as _

from .errors import ApiError


def invalid(name):
    """``ApiError`` 400 (``invalid_field``) que nombra el campo."""
    return ApiError("invalid_field", _("Campo no válido: %(name)s.") % {"name": name}, 400)


def text_field(body, name, required=True, max_length=254, pattern=None):
    """
    Campo de texto del cuerpo. Obligatorio: no vacío. Opcional: ``""`` si falta. ``pattern`` (expresión regular
    completa) limita los caracteres. Lanza ``invalid_field`` si no es texto, es muy largo o no cumple el patrón.
    """
    value = body.get(name)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > max_length:
        raise invalid(name)
    if pattern is not None and not re.fullmatch(pattern, value):
        raise invalid(name)
    return value


def choice_field(body, name, choices, default):
    """Campo que debe ser uno de ``choices`` (``default`` si falta). Lanza ``invalid_field`` si no."""
    value = body.get(name, default)
    if value not in choices:
        raise invalid(name)
    return value
