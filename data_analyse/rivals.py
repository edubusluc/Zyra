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
# Por % de victorias: el mejor primero y «peor primero» (el rival contra el que peor nos va).
SORT_PCT, SORT_WORST = "pct", "worst"
SORTS = (SORT_RIVAL, SORT_PCT, SORT_WORST, SORT_BALANCE, SORT_LAST)


def rival_key(match):
    """Clave del rival de un enfrentamiento: ``('team', pk)`` o ``('name', nombre en minúsculas)``."""
    team = match.visiting if match.own_is_local else match.local
    if team:
        return ("team", team.pk)
    return ("name", (match.rival_name or "").strip().casefold())


def own_points(match):
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


# Nombre público para otros módulos (p. ej. team_card).
outcome = _outcome


def closed_matches(club, season=None, match_type=None):
    """Enfrentamientos cerrados del club en los que juega el equipo propio, con los equipos ya cargados."""
    qs = Match.objects.filter(club=club, draft_mode=False).select_related("local", "visiting", "club")
    if season:
        qs = qs.filter(season=season)
    qs = qs.filter(**match_type_lookup(match_type)).order_by("start_date", "pk")
    return [m for m in qs if m.own_is_local or m.own_is_visiting]


def _entry(match):
    """Una línea del historial de un rival."""
    own, other = own_points(match)
    return {
        "match": match,
        "date": match.start_date,
        "season": match.season,
        "outcome": _outcome(match),
        "own": own,
        "other": other,
        "local": match.own_is_local,
        "friendly": match.is_friendly,
        "type_label": match.type_label,
        "round": match.round_number,
        "league_points": match.league_points,
        "rival_no_show": match.no_show == Match.NO_SHOW_RIVAL,
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
        "league_points": sum(e["league_points"] or 0 for e in entries),
        "last": entries[-1] if entries else None,
        "streak": "".join(e["outcome"] for e in entries[-3:]),
        "form": [e["outcome"] for e in entries[-5:]],
    }


def rival_summary(club, season=None, match_type=None, sort=SORT_RIVAL):
    """
    Una fila por rival con su balance: ``{'key', 'label', 'team', 'friendly_only', 'played', 'won',
    'drawn', 'lost', 'pct', 'points_for', 'points_against', 'league_points', 'last', 'streak', 'form'}``
    (``pct``: % de enfrentamientos ganados; ``league_points``: puntos de liga contra él, solo con liga).
    ``sort``: por nombre, por % de victorias (mejor o peor primero), por balance (victorias netas) o por el
    último enfrentamiento.
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
        rows[-1]["pct"] = round(100 * rows[-1]["won"] / rows[-1]["played"])
    if sort == SORT_PCT:
        rows.sort(key=lambda r: (-r["pct"], -r["played"], r["label"].casefold()))
    elif sort == SORT_WORST:
        rows.sort(key=lambda r: (r["pct"], -r["played"], r["label"].casefold()))
    elif sort == SORT_BALANCE:
        rows.sort(key=lambda r: (-(r["won"] - r["lost"]), -r["played"], r["label"].casefold()))
    elif sort == SORT_LAST:
        rows.sort(key=lambda r: (r["last"]["date"], r["label"].casefold()), reverse=True)
    else:
        rows.sort(key=lambda r: r["label"].casefold())
    return rows


def _best_pairs(club, match_ids, players, min_games=MIN_GAMES_PAIR, only_winning=True):
    """
    Parejas del club que jugaron contra el rival (de más a menos % de victorias, con al menos
    ``min_games`` partidos y, salvo con ``only_winning=False``, alguna victoria): ``[{'p1', 'p2', 'played', 'wins'}]``.
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
        if a_id in by_id and b_id in by_id and played >= min_games and (wins or not only_winning):
            rows.append({"p1": by_id[a_id], "p2": by_id[b_id], "played": played, "wins": wins})
    rows.sort(key=lambda r: (-r["wins"] / r["played"], -r["played"], r["p1"].short_name))
    return rows


def pairs_against(club, match_ids, players, min_games=MIN_GAMES_PAIR, n=3):
    """
    Parejas del club contra los enfrentamientos ``match_ids``, las que tienen al menos ``min_games`` partidos:
    ``(mejores, peores)`` con ``{'p1', 'p2', 'played', 'wins', 'losses', 'pct'}``, hasta ``n`` de cada una. Las
    mejores son las de más % (con alguna victoria) y las peores, las de menos % entre las que no están en las
    mejores: ninguna pareja sale en las dos listas.
    """
    rows = []
    for r in _best_pairs(club, match_ids, players, min_games=min_games, only_winning=False):
        rows.append({**r, "losses": r["played"] - r["wins"], "pct": round(100 * r["wins"] / r["played"])})
    best = [r for r in rows if r["wins"]][:n]
    worst = sorted((r for r in rows if r not in best), key=lambda r: (r["pct"], -r["played"], r["p1"].short_name))[:n]
    return best, worst


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
    ids = {m.pk for m in matches}
    best, worst = pairs_against(club, ids, players)
    tally = _tally(entries)
    return {
        "label": matches[-1].rival_label,
        "team": team,
        **tally,
        "pct": round(100 * tally["won"] / tally["played"]),
        "history": list(reversed(entries)),
        "best_pairs": _best_pairs(club, ids, players),
        "pairs_best": best,
        "pairs_worst": worst,
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
