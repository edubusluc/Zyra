"""Validadores de texto para los nombres que escriben los usuarios (clubes, equipos y jugadores)."""
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Caracteres de control (saltos de línea, tabuladores, nulos...) y los signos < > que
# no tienen sentido en un nombre y solo sirven para intentar colar HTML o romper el
# PDF de la convocatoria (reportlab interpreta < > como etiquetas).
FORBIDDEN_TEXT = re.compile(r"[\x00-\x1f\x7f<>]")


def validate_plain_text(value):
    """Nombres de clubes, equipos y jugadores: texto normal, sin HTML ni caracteres de control."""
    if FORBIDDEN_TEXT.search(value or ""):
        raise ValidationError(_("No se admiten los signos < > ni saltos de línea."), code="forbidden_characters")


def validate_has_letter(value):
    """Nombres de jugadores: tienen que llevar al menos una letra (no solo signos o números)."""
    if value and not any(c.isalpha() for c in value):
        raise ValidationError(_("Escribe al menos una letra."), code="no_letters")


def plain_text(form, *names):
    """Añade validate_plain_text a los campos ``names`` del formulario."""
    for name in names:
        form.fields[name].validators.append(validate_plain_text)


def player_name(form, *names):
    """Nombres y apellidos de jugadores: texto normal (``plain_text``) y con al menos una letra."""
    plain_text(form, *names)
    for name in names:
        form.fields[name].validators.append(validate_has_letter)
