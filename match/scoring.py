"""
Reglas de puntuación de un partido de pádel (al mejor de 3 sets).

- Un set se gana 6-0, 6-1, 6-2, 6-3, 6-4, 7-5 o 7-6 (tie-break).
- Si una pareja gana los dos primeros sets, no se juega el tercero.
- Si se reparten los dos primeros, el tercero es obligatorio y puede ser un
  set normal o, si ALLOW_SUPER_TIEBREAK está activo, un super tie-break a 10
  puntos con 2 de diferencia (10-8, 11-9, 12-10...).
"""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _, gettext_lazy

ALLOW_SUPER_TIEBREAK = True
SUPER_TIEBREAK_POINTS = 10

VALID_SET_SCORES = sorted(
    {(6, n) for n in range(5)} | {(7, 5), (7, 6)}
)
SET_RULE = gettext_lazy("Un set se gana 6-0, 6-1, 6-2, 6-3, 6-4, 7-5 o 7-6.")


def to_int(value):
    """'6' -> 6; '' o None -> None. Lanza ValidationError si no es un número >= 0."""
    if value in (None, ""):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(_("'%(value)s' no es un número.") % {"value": value})
    if n < 0:
        raise ValidationError(_("Los juegos no pueden ser negativos."))
    return n


def is_valid_set(a, b):
    """True si el marcador es un set válido (6-0 ... 6-4, 7-5 o 7-6), en cualquier orden."""
    return (max(a, b), min(a, b)) in VALID_SET_SCORES


def is_valid_super_tiebreak(a, b):
    """True si el marcador es un super tie-break válido (a 10 puntos con 2 de diferencia)."""
    high, low = max(a, b), min(a, b)
    if high < SUPER_TIEBREAK_POINTS:
        return False
    # A 10 se gana con 2 de ventaja; si se pasa de 10, la diferencia es exactamente 2
    return high - low >= 2 if high == SUPER_TIEBREAK_POINTS else high - low == 2


def set_winner(a, b):
    """'local' o 'visiting' según quién ganó el set (a juegos del local, b del visitante)."""
    return "local" if a > b else "visiting"


def validate_padel_result(set1, set2, set3):
    """
    Valida un resultado (cada set es una tupla (local, visitante) de enteros o None).
    Devuelve (sets_normalizados, ganador) con ganador 'local' o 'visiting'.
    Lanza ValidationError con un mensaje por cada problema encontrado.
    """
    errors = []
    sets = [set1, set2, set3]

    for n, (a, b) in enumerate(sets[:2], start=1):
        if a is None or b is None:
            errors.append(_("Set %(n)s: falta el resultado.") % {"n": n})
        elif not is_valid_set(a, b):
            errors.append(_("Set %(n)s: %(score)s no es un resultado válido. %(rule)s")
                          % {"n": n, "score": f"{a}-{b}", "rule": SET_RULE})
    if errors:
        raise ValidationError(errors)

    w1, w2 = set_winner(*set1), set_winner(*set2)
    a3, b3 = set3
    third_played = not (a3 in (None, 0) and b3 in (None, 0))

    if w1 == w2:
        if third_played:
            raise ValidationError(
                _("Set 3: no se juega si la misma pareja ha ganado los dos primeros sets. Déjalo vacío.")
            )
        return [set1, set2, (None, None)], w1

    if not third_played or a3 is None or b3 is None:
        raise ValidationError(_("Set 3: con un set para cada pareja, el tercero es obligatorio."))
    if is_valid_set(a3, b3):
        return sets, set_winner(a3, b3)
    if ALLOW_SUPER_TIEBREAK and is_valid_super_tiebreak(a3, b3):
        return sets, set_winner(a3, b3)

    rule = str(SET_RULE)
    if ALLOW_SUPER_TIEBREAK:
        rule += " " + _("También vale un super tie-break a %(points)s puntos con 2 de diferencia (10-8, 11-9...).") % {
            "points": SUPER_TIEBREAK_POINTS}
    raise ValidationError(_("Set %(n)s: %(score)s no es un resultado válido. %(rule)s")
                          % {"n": 3, "score": f"{a3}-{b3}", "rule": rule})


def validate_retired_result(set1, set2, set3):
    """
    Valida un resultado de un partido que acabó por lesión (puede estar incompleto).

    Los sets se rellenan en orden y todos menos el último introducido deben ser sets
    completos; el último puede quedarse a medias (7-5 / 3-0). Gana quien va ganando: más
    sets (el set a medias cuenta para quien lo domina), después más juegos en total.
    Devuelve (sets_normalizados, ganador) con los sets no jugados como (None, None);
    lanza ValidationError si no hay ningún juego, si faltan sets intermedios, si se sigue
    jugando con el partido decidido o si no se puede saber quién va ganando.
    """
    sets = [(None, None) if (a in (None, 0) and b in (None, 0)) else (a, b) for a, b in (set1, set2, set3)]
    errors = []
    played = [i for i, (a, b) in enumerate(sets) if a is not None or b is not None]
    if not played:
        raise ValidationError(_("Introduce los juegos que se llegaron a jugar."))
    last = played[-1]
    for i in range(last + 1):
        a, b = sets[i]
        if a is None or b is None:
            errors.append(_("Set %(n)s: falta el resultado.") % {"n": i + 1})
        elif i < last and not is_valid_set(a, b):
            errors.append(_("Set %(n)s: %(score)s no es un resultado válido. %(rule)s")
                          % {"n": i + 1, "score": f"{a}-{b}", "rule": SET_RULE})
    if not errors and last == 2 and set_winner(*sets[0]) == set_winner(*sets[1]):
        errors.append(_("Set 3: no se juega si la misma pareja ha ganado los dos primeros sets. Déjalo vacío."))
    if errors:
        raise ValidationError(errors)

    entered = sets[:last + 1]
    local_sets = sum(a > b for a, b in entered)
    visiting_sets = sum(b > a for a, b in entered)
    if local_sets == visiting_sets:
        local_sets = sum(a for a, _b in entered)
        visiting_sets = sum(b for _a, b in entered)
    if local_sets == visiting_sets:
        raise ValidationError(_("No se puede saber quién iba ganando: el resultado está empatado."))
    return sets, "local" if local_sets > visiting_sets else "visiting"
