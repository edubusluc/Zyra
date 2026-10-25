"""
Calendario mensual de los enfrentamientos del club (pestaña «Calendario» de Enfrentamientos).

Solo lectura: arma las semanas de un mes y coloca en cada día los enfrentamientos que tiene, sin enviar
nada ni crear tareas. La vista (``match.views.calendar_match``) pinta la cuadrícula en pantallas anchas y
una agenda por días en las estrechas.
"""
import calendar
import datetime
import re

from .models import Match

MONTH_PARAM = "month"
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def parse_month(value, today):
    """Primer día del mes de ``value`` ('AAAA-MM'); el mes de ``today`` si falta o no es válido."""
    found = _MONTH_RE.match(value or "")
    if found:
        year, month = int(found.group(1)), int(found.group(2))
        if 1 <= month <= 12 and 1900 <= year <= 2200:
            return datetime.date(year, month, 1)
    return today.replace(day=1)


def shift_month(first, delta):
    """Primer día del mes ``delta`` meses antes (negativo) o después de ``first``."""
    index = first.year * 12 + first.month - 1 + delta
    return datetime.date(index // 12, index % 12 + 1, 1)


def month_key(first):
    """'AAAA-MM' de un primer día de mes, para la URL."""
    return f"{first.year}-{first.month:02d}"


def month_weeks(first):
    """Semanas del mes de ``first`` (de lunes a domingo): listas de siete fechas, con los días de los meses vecinos."""
    return calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)


def month_events(club, weeks):
    """
    Enfrentamientos del club entre el primer y el último día de ``weeks``, agrupados por fecha:
    ``{fecha: [enfrentamiento, ...]}`` ordenados por hora y, sin ella, al final del día.
    """
    first, last = weeks[0][0], weeks[-1][-1]
    matches = (Match.objects.filter(club=club, start_date__range=(first, last))
               .select_related("local", "visiting")
               .order_by("start_date", "start_time", "id"))
    by_day = {}
    for match in matches:
        by_day.setdefault(match.start_date, []).append(match)
    return by_day
