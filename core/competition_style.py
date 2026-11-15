"""
Color y escudo en imagen de cada competición, tal y como los deja el personal en el back-office
(``core.CompetitionStyle``). Lo que no ajuste el personal sale de la ficha (``core.competitions``).
"""
import re

from .models import CompetitionStyle

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def style_of(rules):
    """``(color, url del escudo o "")`` de la competición ``rules``: el ajustado por el personal o el de su ficha."""
    row = CompetitionStyle.objects.filter(code=rules.code).first()
    color = row.color if row and COLOR_RE.match(row.color) else rules.color
    crest = row.crest.url if row and row.crest else ""
    return color, crest
