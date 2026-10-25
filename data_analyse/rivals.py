"""
Cara a cara por rival: balance contra cada rival, su ficha y la «Previa» de un enfrentamiento.

Solo lógica, sin vistas. Un rival es el equipo del grupo contra el que se jugó (se agrupa por equipo,
no por nombre: el mismo nombre en dos divisiones son dos rivales) o, en los amistosos con rival escrito
a mano, su nombre sin distinguir mayúsculas. Solo cuentan los enfrentamientos con el acta cerrada.
"""
from match import outcomes
from match.models import Match

from .pairs import MIN_GAMES_PAIR, club_game_log, match_type_lookup

WIN, DRAW, LOSS = "V", "E", "D"
# Orden de la lista de rivales (?sort=).
SORT_RIVAL, SORT_BALANCE, SORT_LAST = "rival", "balance", "last"
SORTS = (SORT_RIVAL, SORT_BALANCE, SORT_LAST)


def rival_key(match):
    """Clave del rival de un enfrentamiento: ``('team', pk)`` o ``('name', nombre en minúsculas)``."""
    team = match.visiting if match.own_is_local else match.local
    if team:
        return ("team", team.pk)
    return ("name", (match.rival_name or "").strip().casefold())


def _own_points(match):
    """(puntos propios, puntos del rival) de un enfrentamiento cerrado, o (None, None) si no constan."""
    try:
        local, visiting = (int(n) for n in match.result_points.split("/"))
    except (AttributeError, ValueError):
        return None, None
    return (local, visiting) if match.own_is_local else (visiting, local)


def _outcome(match):
    """'V', 'E' o 'D' desde el punto de vista del club."""
    if match.result == outcomes.DRAW:
        return DRAW
    own_won = (match.result == outcomes.LOCAL_WIN) == match.own_is_local
    return WIN if own_won else LOSS


def closed_matches(club, season=None, match_type=None):
    """Enfrentamientos cerrados del club en los que juega el equipo propio, con los equipos ya cargados."""
    qs = Match.objects.filter(club=club, draft_mode=False).select_related("local", "visiting")
    if season:
        qs = qs.filter(season=season)
    qs = qs.filter(**match_type_lookup(match_type)).order_by("start_date", "pk")
    return [m for m in qs if m.own_is_local or m.own_is_visiting]


def _entry(match):
    """Una línea del historial de un rival."""
    own, other = _own_points(match)
    return {
        "match": match,
        "date": match.start_date,
        "season": match.season,
        "outcome": _outcome(match),
        "own": own,
        "other": other,
        "local": match.own_is_local,
        "friendly": match.is_friendly,
        "type_label": match.get_match_type_display(),
    }


def _tally(entries):
    """Balance de una lista de líneas del historial (de la más antigua a la más reciente)."""
    won = sum(e["outcome"] == WIN for e in entries)
    drawn = sum(e["outcome"] == DRAW for e in entries)
    return {
        "played": len(entries),
        "won": won,
        "drawn": drawn,
        "lost": len(entries) - won - drawn,
        "points_for": sum(e["own"] or 0 for e in entries),
        "points_against": sum(e["other"] or 0 for e in entries),
        "last": entries[-1] if entries else None,
        "streak": "".join(e["outcome"] for e in entries[-3:]),
    }


def rival_summary(club, season=None, match_type=None, sort=SORT_RIVAL):
    """
    Una fila por rival con su balance: ``{'key', 'label', 'team', 'friendly_only', 'played', 'won',
    'drawn', 'lost', 'points_for', 'points_against', 'last', 'streak'}``. ``sort``: por nombre,
    por balance (más victorias netas primero) o por el último enfrentamiento.
    """
    groups = {}
    for m in closed_matches(club, season, match_type):
        key = rival_key(m)
        if key[0] == "name" and not key[1]:
            continue
        group = groups.setdefault(key, {"label": m.rival_label, "team": m.visiting if m.own_is_local else m.local,
                                        "entries": []})
        group["entries"].append(_entry(m))
    rows = []
    for key, group in groups.items():
        rows.append({
            "key": key,
            "label": group["label"],
            "team": group["team"],
            "friendly_only": all(e["friendly"] for e in group["entries"]),
            **_tally(group["entries"]),
        })
    if sort == SORT_BALANCE:
        rows.sort(key=lambda r: (-(r["won"] - r["lost"]), -r["played"], r["label"].casefold()))
    elif sort == SORT_LAST:
        rows.sort(key=lambda r: (r["last"]["date"], r["label"].casefold()), reverse=True)
    else:
        rows.sort(key=lambda r: r["label"].casefold())
    return rows


def _best_pairs(club, match_ids, players, min_games=MIN_GAMES_PAIR):
    """
    Parejas del club que jugaron contra el rival (de más a menos % de victorias, con al menos
    ``min_games`` partidos y alguna victoria): ``[{'p1', 'p2', 'played', 'wins'}]``.
    """
    by_id = {p.id: p for p in players}
    acc = {}
    for g in club_game_log(club):
        if g["match_id"] not in match_ids:
            continue
        a = acc.setdefault(g["pair"], [0, 0])
        a[0] += 1
        a[1] += g["won"]
    rows = []
    for (a_id, b_id), (played, wins) in acc.items():
        if a_id in by_id and b_id in by_id and played >= min_games and wins:
            rows.append({"p1": by_id[a_id], "p2": by_id[b_id], "played": played, "wins": wins})
    rows.sort(key=lambda r: (-r["wins"] / r["played"], -r["played"], r["p1"].short_name))
    return rows


def rival_detail(club, players, team=None, name="", season=None, match_type=None):
    """
    Ficha de un rival: balance, historial (el más reciente primero) y sus mejores parejas contra él.
    ``team`` es un equipo del grupo o ``name`` el de un rival escrito a mano. None si no hay nada.
    """
    key = ("team", team.pk) if team else ("name", name.strip().casefold())
    matches = [m for m in closed_matches(club, season, match_type) if rival_key(m) == key]
    if not matches:
        return None
    entries = [_entry(m) for m in matches]
    return {
        "label": matches[-1].rival_label,
        "team": team,
        **_tally(entries),
        "history": list(reversed(entries)),
        "best_pairs": _best_pairs(club, {m.pk for m in matches}, players),
    }


def rival_preview(match):
    """
    «Previa» de un enfrentamiento: balance contra ese mismo rival en los enfrentamientos cerrados
    anteriores (de cualquier tipo) y su mejor pareja contra él. None si nunca se jugó contra él.
    """
    club = match.club
    if not club or not (match.own_is_local or match.own_is_visiting):
        return None
    team = match.visiting if match.own_is_local else match.local
    name = match.rival_name
    if not team and not name.strip():
        return None
    earlier = [m for m in closed_matches(club) if m.pk != match.pk and m.start_date <= match.start_date
               and rival_key(m) == rival_key(match)]
    if not earlier:
        return None
    from players.models import Player
    best = _best_pairs(club, {m.pk for m in earlier}, list(Player.objects.filter(club=club)))
    entries = [_entry(m) for m in earlier]
    return {**_tally(entries), "best_pair": best[0] if best else None}
