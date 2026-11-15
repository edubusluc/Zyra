"""
Datos del selector de competición del alta de un equipo (``register_club``).

Cada competición se ofrece como una tarjeta con su escudo 3D. Las que la cuenta aún no tiene se pueden
elegir; en las que ya pertenece (como capitán, gestor o jugador) la tarjeta sale bloqueada y dice a qué
equipo pertenece. Qué se muestra de cada una (color, países, partidos, puntos…) sale de su ficha
(``core.competitions``); añadir una competición nueva no exige tocar el selector.
"""
from team.models import Team


def picker_entries(free, memberships):
    """
    Una entrada por competición, en el orden del registro: ``free`` son las fichas que se pueden
    elegir y ``memberships`` las membresías de la cuenta (club y rol), que bloquean la suya.
    """
    from .competitions import COMPETITIONS

    taken = {m.club.competition: m for m in memberships}
    free_codes = {c.code for c in free}
    entries = []
    for rules in COMPETITIONS.values():
        membership = taken.get(rules.code)
        hex_color = rules.color.lstrip("#")
        entries.append({
            "code": rules.code,
            "name": str(rules.name),
            "full_name": str(rules.full_name),
            "color": rules.color,
            "rgb": ", ".join(str(int(hex_color[i:i + 2], 16)) for i in (0, 2, 4)),
            "monogram": rules.code.upper(),
            "countries": list(rules.countries),
            "games": rules.games,
            "points": rules.total_points,
            "min_call": rules.min_call_players,
            "types": [str(label) for _value, label, _plural in rules.match_types],
            "divisions": list(rules.divisions),
            "snp": rules.has_snp,
            "free": rules.code in free_codes,
            "club": membership.club.name if membership else "",
            "role": str(membership.get_role_display()) if membership else "",
        })
    return entries


def country_names():
    """Nombre de cada país del alta (código de ``Team.COUNTRIES`` → nombre), para el aviso de las tarjetas."""
    return {code: str(label) for code, label in Team.COUNTRIES}
