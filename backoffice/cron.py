"""
Expresiones cron de 5 campos (minuto hora día-del-mes mes día-de-la-semana), sin
dependencias externas. Admite *, */n, listas (1,15), rangos (1-5) y rangos con paso
(0-30/10). Día de la semana: 0 o 7 = domingo, 1 = lunes... Como en cron, si se
restringen a la vez el día del mes y el de la semana, basta con que se cumpla uno.
"""
import datetime

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

FIELDS = [
    ("minuto", 0, 59),
    ("hora", 0, 23),
    ("día del mes", 1, 31),
    ("mes", 1, 12),
    ("día de la semana", 0, 7),
]

DAY_NAMES = [
    gettext_lazy("domingo"), gettext_lazy("lunes"), gettext_lazy("martes"), gettext_lazy("miércoles"),
    gettext_lazy("jueves"), gettext_lazy("viernes"), gettext_lazy("sábado"),
]


class CronError(ValueError):
    """Expresión cron mal escrita o que no se cumple nunca."""
    pass


def _parse_field(text, name, low, high):
    """
    Valores que admite un campo cron (`name` es solo para el mensaje de error y `low`-`high`
    el rango permitido). Como en cron, ``5/10`` equivale a ``5-high/10``.
    """
    values = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            if not step_text.isdigit() or int(step_text) < 1:
                raise CronError(f"Paso no válido en el {name}: {text}")
            step = int(step_text)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise CronError(f"Rango no válido en el {name}: {text}")
            start, end = int(a), int(b)
        elif part.isdigit():
            start = end = int(part)
            if step > 1:
                end = high
        else:
            raise CronError(f"Valor no válido en el {name}: {text}")
        if not (low <= start <= end <= high):
            raise CronError(f"Fuera de rango en el {name} ({low}-{high}): {text}")
        values.update(range(start, end + 1, step))
    return values


class Cron:
    """Expresión cron ya analizada, para calcular la siguiente ejecución y describirla."""
    def __init__(self, expression):
        """Analiza la expresión; lanza CronError si no tiene 5 campos o algún valor no es válido."""
        parts = expression.split()
        if len(parts) != 5:
            raise CronError("Una expresión cron tiene 5 campos: minuto hora día mes día-de-la-semana.")
        self.expression = " ".join(parts)
        parsed = [_parse_field(p, *field) for p, field in zip(parts, FIELDS)]
        self.minutes, self.hours, self.days, self.months, dows = parsed
        self.dows = {d % 7 for d in dows}
        self.days_restricted = parts[2] != "*"
        self.dows_restricted = parts[4] != "*"

    def _day_matches(self, day):
        """True si el día cumple el mes y el día del mes / día de la semana (regla del O de cron)."""
        if day.month not in self.months:
            return False
        dom = day.day in self.days
        dow = (day.weekday() + 1) % 7 in self.dows  # weekday(): lunes=0 → cron: lunes=1
        if self.days_restricted and self.dows_restricted:
            return dom or dow
        if self.days_restricted:
            return dom
        if self.dows_restricted:
            return dow
        return True

    def next_after(self, moment):
        """
        Primer instante estrictamente posterior a `moment` (aware) que cumple la expresión. Se compara en UTC y no
        con la hora de reloj: en el cambio de hora de octubre una hora ocurre dos veces (``fold``) y comparar el
        reloj daba instantes ya pasados, con lo que un proceso frecuente se lanzaba en cada pasada.
        """
        tz = moment.tzinfo
        utc = datetime.timezone.utc
        start = moment.astimezone(utc).replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        day = start.astimezone(tz).date()
        for _attempt in range(366 * 5):
            if self._day_matches(day):
                found = [
                    candidate for hour in self.hours for minute in self.minutes for fold in (0, 1)
                    if (candidate := datetime.datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz, fold=fold).astimezone(utc)) >= start
                ]
                if found:
                    return min(found).astimezone(tz)
            day += datetime.timedelta(days=1)
        raise CronError(f"La expresión {self.expression} no se cumple nunca.")

    def describe(self):
        """Descripción (en el idioma activo) de los casos habituales; si no, la propia expresión."""
        m, h, dom, mon, dow = self.expression.split()
        if dom == "*" and mon == "*" and dow == "*":
            if m == "*" and h == "*":
                return _("Cada minuto")
            if m.startswith("*/") and h == "*":
                return _("Cada %(n)s minutos") % {"n": m[2:]}
            if m.isdigit() and h == "*":
                return _("Cada hora, en el minuto %(minute)s") % {"minute": int(m)}
            if m.isdigit() and h.isdigit():
                return _("Cada día a las %(time)s") % {"time": f"{int(h):02d}:{int(m):02d}"}
        if dom == "*" and mon == "*" and dow.isdigit() and m.isdigit() and h.isdigit():
            return _("Cada %(day)s a las %(time)s") % {"day": DAY_NAMES[int(dow) % 7], "time": f"{int(h):02d}:{int(m):02d}"}
        if dom.isdigit() and mon == "*" and dow == "*" and m.isdigit() and h.isdigit():
            return _("El día %(day)s de cada mes a las %(time)s") % {"day": int(dom), "time": f"{int(h):02d}:{int(m):02d}"}
        return _("cron «%(expression)s»") % {"expression": self.expression}
