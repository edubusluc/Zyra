"""
Tabla de plantilla de «Estadísticas · Equipo» y de la entrada de «Jugadores»: una fila por jugador del
equipo con sus partidos, balance, % de victorias, % de convocatorias a las que se apunta y, en SNP, sus puntos.

Sustituye a los dos Top 5 (local y visitante) y a las tarjetas «Más victorias» y «Más partidos jugados», que
eran el mismo ranking en listas distintas. Se ordena por columna y se filtra por local o visitante. Sin
mínimo de partidos: cuenta el % de todo el que ha jugado. Solo lógica, sin vistas.
"""
from call.models import Call
from players.models import joined_by

from .pairs import match_type_lookup


SIDE_ALL, SIDE_LOCAL, SIDE_VISITING = "todos", "local", "visitante"
SIDES = (SIDE_ALL, SIDE_LOCAL, SIDE_VISITING)
# Columnas por las que se ordena (``?orden=``): % de victorias por defecto.
SORTS = ("pct", "played", "signup", "snp", "name")
DEFAULT_SORT = "pct"


def parse_options(params, has_snp):
    """
    Opciones de la tabla a partir de ``params`` (``request.GET``): ``(side, sort)``. Un valor que no existe
    vuelve al de por defecto (todos, por %); sin puntos SNP no se ordena por puntos.
    """
    side = params.get("lado")
    side = side if side in SIDES else SIDE_ALL
    sort = params.get("orden")
    sort = sort if sort in SORTS and (sort != "snp" or has_snp) else DEFAULT_SORT
    return side, sort


def signup_by_player(club, players, season=None, match_type=None, side=SIDE_ALL):
    """
    Convocatorias cerradas a las que se apuntó cada jugador de ``players``: ``{id: {'signed', 'total',
    'pct'}}``. Como en la ficha del jugador, solo cuentan las de su temporada de incorporación en adelante
    (``Player.joined_season``). Con ``side`` local o visitante, solo las de los enfrentamientos en los que el
    equipo juega en ese lado. Una sola consulta para toda la plantilla. ``pct`` es None sin convocatorias.
    """
    calls = Call.objects.filter(match__club=club, match__draft_mode=False, draft_mode=False, match__no_show="",
                                **match_type_lookup(match_type, "match__"))
    if season:
        calls = calls.filter(match__season=season)
    calls = list(calls.select_related("match", "match__local", "match__visiting").prefetch_related("players"))
    if side != SIDE_ALL:
        calls = [c for c in calls if (c.match.own_is_local if side == SIDE_LOCAL else c.match.own_is_visiting)]
    signed_ids = [(c.match.season, {p.id for p in c.players.all()}) for c in calls]
    out = {}
    for p in players:
        total = signed = 0
        for call_season, ids in signed_ids:
            if joined_by(p.joined_season, call_season):
                total += 1
                signed += p.id in ids
        out[p.id] = {"signed": signed, "total": total, "pct": round(100 * signed / total) if total else None}
    return out


def roster_rows(players, log, signup, side=SIDE_ALL, sort=DEFAULT_SORT, snp=None):
    """
    Filas de la tabla de plantilla. ``log`` es ``club_game_log`` (ya filtrado por temporada y tipo), ``signup``
    sale de ``signup_by_player`` y ``snp`` es ``{id jugador: fila de records.snp_ranking}`` (None sin SNP).

    Cada fila: ``player``, ``played``, ``wins``, ``losses``, ``pct`` (None sin partidos), ``enough`` (ha
    jugado alguno), ``signed``, ``calls``, ``signup`` y, con SNP, ``snp``, ``delta`` (puntos), ``rank_delta``
    (puestos), ``rank_moved`` y ``spark``. No hay mínimo de partidos: cuenta el % de todo el que ha jugado. Quien
    no ha jugado ninguno va al final del orden por %; el resto, por la columna elegida.
    """
    counts = {}
    for g in log:
        if side != SIDE_ALL and g["local"] != (side == SIDE_LOCAL):
            continue
        for pid in g["pair"]:
            wins, played = counts.get(pid, (0, 0))
            counts[pid] = (wins + g["won"], played + 1)
    rows = []
    for p in players:
        wins, played = counts.get(p.id, (0, 0))
        sign = signup.get(p.id) or {"signed": 0, "total": 0, "pct": None}
        row = {
            "player": p, "played": played, "wins": wins, "losses": played - wins,
            "pct": round(100 * wins / played) if played else None, "enough": played > 0,
            "signed": sign["signed"], "calls": sign["total"], "signup": sign["pct"],
            "snp": None, "delta": None, "rank_delta": None, "spark": None,
        }
        if snp and p.id in snp:
            row["snp"], row["delta"] = snp[p.id]["score"], snp[p.id]["delta"]
            row["rank_delta"], row["spark"] = snp[p.id]["rank_delta"], snp[p.id]["spark"]
            row["rank_moved"] = abs(row["rank_delta"] or 0)
        rows.append(row)

    def key(r):
        """Orden descendente por la columna elegida; los vacíos al final y el nombre desempata."""
        value = {"pct": r["pct"], "played": r["played"], "signup": r["signup"], "snp": r["snp"]}.get(sort)
        return (value is None, -(value or 0), -r["played"], r["player"].name, r["player"].last_name)

    if sort == "name":
        return sorted(rows, key=lambda r: (r["player"].name.casefold(), r["player"].last_name.casefold()))
    # Por %, quien no ha jugado ninguno va detrás.
    return sorted(rows, key=lambda r: (sort == "pct" and not r["enough"], *key(r)))
