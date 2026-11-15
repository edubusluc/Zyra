"""
Tarjeta «Frente a la plantilla» de la ficha del jugador: cada cifra del jugador comparada con la de
los jugadores de la plantilla actual (media, rango y puesto). Solo lógica, sin vistas.

Medidas: % de victorias, % de convocatorias a las que se apunta, % de sets ganados y, según la competición,
puntos SNP o jornadas de liga jugadas (LAPI). La media, el rango y el puesto cuentan solo a quienes
tienen al menos ``MIN_SAMPLE`` partidos (o convocatorias en «Se apunta»), o los que lleve el que más ha jugado
si aún son menos (principio de temporada, o una liga con pocas jornadas); si el jugador no llega, esa medida
no sale, y si menos de ``MIN_SAMPLE`` jugadores tienen datos no hay con quién compararse.
"""
from django.utils.formats import number_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from match.models import Game, Match

# Partidos (o convocatorias) mínimos para entrar en la comparación.
MIN_SAMPLE = 3
# Diferencia por debajo de la cual se dice «En la media», según la unidad de la medida.
NEAR = {"pct": 1, "points": 5, "rounds": 0.5}
SLOTS = ("player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting")

PCT, SIGNUP, SETS, SNP, LEAGUE = "pct", "signup", "sets", "snp", "league"
LABELS = {
    PCT: gettext_lazy("% de victorias"),
    SIGNUP: gettext_lazy("Se apunta"),
    SETS: gettext_lazy("% de sets ganados"),
    SNP: gettext_lazy("Puntos SNP"),
    LEAGUE: gettext_lazy("Jornadas de liga jugadas"),
}
TIPS = {
    PCT: gettext_lazy("Partidos ganados sobre los jugados."),
    SIGNUP: gettext_lazy("Convocatorias cerradas a las que se apuntó, desde que se incorporó al equipo."),
    SETS: gettext_lazy("Sets ganados sobre los jugados."),
    SNP: gettext_lazy("Puntos SNP de la última actualización de la temporada."),
    LEAGUE: gettext_lazy("Jornadas de liga en las que ha jugado, sobre las disputadas."),
}
CARD_TIP = gettext_lazy(
    "Se compara con los jugadores de la plantilla que tienen al menos 3 partidos en el periodo elegido, "
    "o los que lleve el que más ha jugado si son menos. La media es la de esos jugadores y el rango va del menor al mayor."
)


def league_played(club, season, players):
    """
    Jornadas de liga cerradas en las que ha jugado cada jugador de ``players``: ``({id: n}, total)`` con
    ``total`` las jornadas de la competición (``season`` None = todas). ``(None, 0)`` sin liga. Una sola consulta.
    """
    rules = club.rules
    if not rules.league_type:
        return None, 0
    matches = Match.objects.filter(club=club, draft_mode=False, match_type=rules.league_type)
    if season:
        matches = matches.filter(season=season)
    total = matches.count()
    seen = {p.id: set() for p in players}
    for row in Game.objects.filter(match__in=matches, draft_mode=False).values("match_id", *(f"{s}_id" for s in SLOTS)):
        for slot in SLOTS:
            if row[f"{slot}_id"] in seen:
                seen[row[f"{slot}_id"]].add(row["match_id"])
    return {pid: len(m) for pid, m in seen.items()}, total


def _tally(players, log):
    """``{id: {'played', 'wins', 'sets_won', 'sets_played'}}`` de cada jugador a partir del log del club."""
    tally = {p.id: {"played": 0, "wins": 0, "sets_won": 0, "sets_played": 0} for p in players}
    for g in log:
        won_sets = sum(1 for own, rival in g["sets"] if own > rival)
        for pid in g["pair"]:
            t = tally.get(pid)
            if t is None:
                continue
            t["played"] += 1
            t["wins"] += bool(g["won"])
            t["sets_won"] += won_sets
            t["sets_played"] += len(g["sets"])
    return tally


def _rate(part, total):
    """Porcentaje (con decimales) de ``part`` sobre ``total``; None si ``total`` es 0."""
    return 100 * part / total if total else None


def _pct_text(value):
    """«68 %» para un porcentaje."""
    return _("%(n)s %%") % {"n": round(value)}


def _points_text(value):
    """«1.840 pts» para unos puntos SNP, con el separador del idioma."""
    return _("%(n)s pts") % {"n": number_format(round(value), use_l10n=True, force_grouping=True)}


def _rounds_text(value):
    """Jornadas como texto: entero, o con un decimal si lo tiene (la media)."""
    return number_format(int(value) if float(value).is_integer() else round(value, 1), use_l10n=True)


def compare_to_squad(player, squad, log, signup, snp_rows=None, league=None):
    """
    La comparación de ``player`` con ``squad`` (jugadores de la plantilla actual). ``log`` es ``club_game_log``
    (ya filtrado por temporada y tipo), ``signup`` sale de ``roster_table.signup_by_player``, ``snp_rows`` es
    ``{id: fila de records.snp_ranking}`` (None sin SNP) y ``league`` es ``(jugadas por jugador, total)`` de
    ``league_played`` (None sin liga).

    Devuelve None si no hay comparación que enseñar, o ``{'rows', 'above', 'count'}``: cada fila trae
    ``key``, ``label``, ``tip``, ``value`` (texto), ``base`` (texto), ``rank``, ``of``, ``top``, ``tone``
    (up/down/eq), ``arrow``, ``delta``, ``mean``, ``low``, ``high`` (textos), las cuatro posiciones de la barra
    en tanto por ciento entero (``pos_low``, ``pos_high``, ``pos_mean``, ``pos_me``, más ``range_width``) y ``reader`` (texto para
    lectores de pantalla). ``above`` son las medidas por encima de la media.
    """
    if player.id not in {p.id for p in squad}:
        return None
    tally = _tally(squad, log)
    def base_pct(p):
        """«15 de 22 partidos» de ``p``."""
        x = tally[p.id]
        return _("%(w)s de %(n)s partidos") % {"w": x["wins"], "n": x["played"]}

    def base_sets(p):
        """«33 de 52 sets» de ``p``."""
        x = tally[p.id]
        return _("%(w)s de %(n)s sets") % {"w": x["sets_won"], "n": x["sets_played"]}

    def base_signup(p):
        """«17 de 20 convocatorias» de ``p``."""
        s = signup.get(p.id) or {}
        return _("%(w)s de %(n)s convocatorias") % {"w": s.get("signed", 0), "n": s.get("total", 0)}

    # Muestra mínima: 3, o lo que lleve el que más ha jugado si aún son menos (así una liga con 2 jornadas compara).
    need_games = max(1, min(MIN_SAMPLE, max(x["played"] for x in tally.values())))
    need_calls = max(1, min(MIN_SAMPLE, max((signup.get(p.id) or {}).get("total", 0) for p in squad)))
    table = [
        # clave, ¿cuenta?, valor, formato, base, unidad, eje fijo
        (PCT, lambda p: tally[p.id]["played"] >= need_games,
         lambda p: _rate(tally[p.id]["wins"], tally[p.id]["played"]), _pct_text, base_pct, "pct", (0, 100)),
        (SIGNUP, lambda p: (signup.get(p.id) or {}).get("total", 0) >= need_calls,
         lambda p: signup[p.id]["pct"], _pct_text, base_signup, "pct", (0, 100)),
        (SETS, lambda p: tally[p.id]["played"] >= need_games and tally[p.id]["sets_played"] > 0,
         lambda p: _rate(tally[p.id]["sets_won"], tally[p.id]["sets_played"]), _pct_text, base_sets, "pct", (0, 100)),
    ]
    if snp_rows is not None:
        table.append((SNP, lambda p: p.id in snp_rows and snp_rows[p.id]["score"],
                      lambda p: snp_rows[p.id]["score"], _points_text,
                      lambda p: _("última actualización"), "points", None))
    elif league is not None and league[0] is not None:
        played, total = league
        table.append((LEAGUE, lambda p: p.id in played, lambda p: played[p.id], _rounds_text,
                      lambda p: _("de %(n)s jornadas") % {"n": total}, "rounds", None))

    rows, above = [], 0
    for key, counts, value, fmt, base, unit, axis in table:
        if not counts(player):
            continue
        values = [value(p) for p in squad if counts(p)]
        if len(values) < MIN_SAMPLE:
            continue
        mine = value(player)
        mean, low, high = sum(values) / len(values), min(values), max(values)
        rank = 1 + sum(1 for v in values if v > mine + 1e-9)
        # Puntos SNP y jornadas: la barra va exactamente del menor al mayor, así el máximo queda al final (con todos iguales, se centra).
        lo_axis, hi_axis = axis or ((low, high) if high > low else (low - 1, high + 1))

        def pos(x):
            """Posición de ``x`` en la barra, en tanto por ciento entero y sin salirse de los bordes."""
            return round(max(2, min(98, 100 * (x - lo_axis) / (hi_axis - lo_axis))))

        diff = mine - mean
        near = abs(diff) < NEAR[unit]
        if near:
            tone, arrow, delta = "eq", "=", _("En la media")
        else:
            tone, arrow = ("up", "▲") if diff > 0 else ("down", "▼")
            size = abs(diff)
            amount = (_("%(n)s pts") % {"n": number_format(round(size), use_l10n=True, force_grouping=True)}
                      if unit != "rounds" else _plural_rounds(size))
            delta = (_("%(a)s sobre la media") if diff > 0 else _("%(a)s bajo la media")) % {"a": amount}
            above += diff > 0
        rows.append({
            "key": key, "label": LABELS[key], "tip": TIPS[key], "value": fmt(mine), "base": base(player),
            "rank": rank, "of": len(values), "top": rank == 1, "tone": tone, "arrow": arrow, "delta": delta,
            "mean": fmt(mean), "low": fmt(low), "high": fmt(high),
            "pos_low": pos(low), "pos_high": pos(high), "range_width": pos(high) - pos(low), "pos_mean": pos(mean), "pos_me": pos(mine),
            "reader": _("%(label)s: %(value)s, puesto %(rank)s de %(of)s, media %(mean)s") % {
                "label": LABELS[key], "value": fmt(mine), "rank": rank, "of": len(values), "mean": fmt(mean)},
        })
    if not rows:
        return None
    return {"rows": rows, "above": above, "count": len(rows), "all_above": above == len(rows),
            "none_above": above == 0, "tip": CARD_TIP}


def _plural_rounds(size):
    """«2 jornadas» / «0,5 jornadas» para la diferencia de jornadas con la media."""
    shown = number_format(round(size, 1), use_l10n=True)
    return _("%(n)s jornadas") % {"n": shown}
