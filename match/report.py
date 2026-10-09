"""
Datos del informe que se envía al cerrar una convocatoria.

Las estadísticas se calculan para el escenario del partido: si el club juega
como visitante, el rendimiento "en la sede" es el de sus partidos fuera (y
viceversa).
"""
from django.db.models import Q
from django.utils.translation import gettext as _, pgettext

from data_analyse.pairs import club_game_log

from . import advisor
from call.models import Call
from players.models import Player

from .models import Match

MAX_PAIRS_TABLE = 6
MAX_PRECEDENTS = 4
MAX_USAGE_ROWS = 5


def _outcome(match):
    """'V', 'D' o 'E' de un partido cerrado desde el punto de vista del club."""
    if match.result == "Victoria Local":
        return "V" if match.own_is_local else "D"
    if match.result == "Victoria Visitante":
        return "V" if match.own_is_visiting else "D"
    return "E"


def _own_score(match):
    """'3/9' (local/visitante) -> '9-3' desde el punto de vista del club."""
    try:
        local, visiting = match.result_points.split("/")
    except (AttributeError, ValueError):
        return "-"
    return f"{local}-{visiting}" if match.own_is_local else f"{visiting}-{local}"


def build_report(call):
    """Reúne todos los datos del informe de la convocatoria ``call`` en un diccionario.

    Incluye la forma de los convocados y sus parejas, rachas, balance de la temporada,
    precedentes contra el rival, reparto de partidos de la plantilla y las dos alineaciones
    recomendadas. Solo usa partidos anteriores a la fecha del enfrentamiento.
    """
    match = call.match
    club = match.club
    own_local = match.own_is_local
    venue_label = pgettext("sede, en minúscula", "local") if own_local else pgettext("sede, en minúscula", "visitante")
    rival_team = match.visiting if own_local else match.local
    rival = match.rival_label

    called = list(call.players.order_by("name", "last_name"))
    # Solo la historia anterior a este partido (el informe de un partido antiguo no ve el futuro)
    log = [g for g in club_game_log(club) if g['date'] < match.start_date]
    forms, pairs = advisor.build_forms(log, called, own_local)
    player_rows = sorted(forms.values(), key=lambda f: (f.strength, f.snp), reverse=True)

    # Rachas destacadas
    hot = sorted((f for f in player_rows if f.streak[0] == 'V' and f.streak[1] >= 2), key=lambda f: -f.streak[1])
    cold = sorted((f for f in player_rows if f.streak[0] == 'D' and f.streak[1] >= 2), key=lambda f: -f.streak[1])

    # Parejas entre los convocados con historial, mejores en la sede del partido
    pair_rows = sorted(
        (p for p in pairs.values() if p.played),
        key=lambda p: (advisor._smooth(p.venue_wins, p.venue_played), p.played),
        reverse=True,
    )[:MAX_PAIRS_TABLE]

    # Balance de la temporada (general y en la sede)
    season_matches = list(
        Match.objects.filter(club=club, season=match.season, draft_mode=False, start_date__lt=match.start_date)
        .exclude(pk=match.pk).select_related("local", "visiting")
    )
    season = {"played": 0, "won": 0, "venue_played": 0, "venue_won": 0}
    for m in season_matches:
        won = _outcome(m) == "V"
        season["played"] += 1
        season["won"] += won
        if m.own_is_local == own_local:
            season["venue_played"] += 1
            season["venue_won"] += won

    # Precedentes contra el mismo rival: el equipo del grupo o, si se escribió a mano,
    # los partidos con ese mismo nombre de rival.
    if rival_team:
        same_rival = Q(local=rival_team) | Q(visiting=rival_team)
    else:
        same_rival = Q(rival_name__iexact=rival) & (Q(local__isnull=True) | Q(visiting__isnull=True))
    precedents = [
        {
            "date": m.start_date,
            "season": m.season,
            "venue": _("Local") if m.own_is_local else _("Visitante"),
            "score": _own_score(m),
            "outcome": _outcome(m),
        }
        for m in Match.objects.filter(club=club, draft_mode=False, start_date__lt=match.start_date)
        .filter(same_rival)
        .select_related("local", "visiting")
        .order_by("-start_date")[:MAX_PRECEDENTS]
    ]

    # Reparto de partidos en la temporada: toda la plantilla actual (no solo los convocados)
    squad = list(Player.objects.filter(club=club, in_team=True).order_by("name", "last_name"))
    season_log = [g for g in log if g["season"] == match.season]
    usage = {p.id: {"player": p, "games": 0, "last": None, "calls": 0,
                     "called_now": False} for p in squad}
    for g in season_log:
        for pid in g["pair"]:
            if pid in usage:
                usage[pid]["games"] += 1
                usage[pid]["last"] = max(filter(None, (usage[pid]["last"], g["date"])))
    calls = (Call.objects.filter(match__club=club, match__season=match.season, draft_mode=False,
                                 match__start_date__lt=match.start_date)
             .values_list("players", flat=True))
    for pid in calls:
        if pid in usage:
            usage[pid]["calls"] += 1
    for p in called:
        if p.id in usage:
            usage[p.id]["called_now"] = True
    usage_rows = list(usage.values())
    most_games = sorted(usage_rows, key=lambda u: (-u["games"], u["player"].name))[:MAX_USAGE_ROWS]
    least_games = sorted(usage_rows, key=lambda u: (u["games"], -u["calls"], u["player"].name))[:MAX_USAGE_ROWS]
    never_played = sum(1 for u in usage_rows if not u["games"])

    lineup_a, lineup_b = advisor.recommend(forms, pairs, [p.id for p in called])
    lineups = []
    for letter, lineup, compare_to in (("A", lineup_a, None), ("B", lineup_b, lineup_a)):
        if lineup:
            lineups.append({
                "title": _("Alineación %(letter)s · %(title)s") % {"letter": letter, "title": lineup.title},
                "lineup": lineup,
                "explanation": advisor.explain(lineup, venue_label, compare_to=compare_to),
            })

    return {
        "club": club,
        "match": match,
        "rival": rival,
        "venue_label": venue_label,
        "called": called,
        "players": player_rows,  # todos; el PDF decide cuántos caben
        "hot": hot[:4],
        "cold": cold[:3],
        "pairs": pair_rows,
        "season": season,
        "precedents": precedents,
        "lineups": lineups,
        "most_games": most_games,
        "least_games": least_games,
        "never_played": never_played,
        "squad_size": len(squad),
        "enough_players": len(called) >= advisor.PLAYERS_PER_LINEUP,
    }


def suggested_lineups(call):
    """
    Alineaciones recomendadas (A y, si la hay, B) para rellenar el formulario de parejas.

    Usa el mismo recomendador que el informe de la convocatoria, con la historia anterior
    al enfrentamiento. Devuelve una lista (vacía con menos de 10 convocados) de
    {'key', 'title', 'win', 'expected', 'explanation', 'pairs': [[id, id], ...]} con las
    parejas en orden de juego (partido 1 primero).
    """
    match = call.match
    called = list(call.players.all())
    if len(called) < advisor.PLAYERS_PER_LINEUP:
        return []
    own_local = match.own_is_local
    venue_label = pgettext("sede, en minúscula", "local") if own_local else pgettext("sede, en minúscula", "visitante")
    log = [g for g in club_game_log(match.club) if g['date'] < match.start_date]
    forms, pairs = advisor.build_forms(log, called, own_local)
    lineup_a, lineup_b = advisor.recommend(forms, pairs, [p.id for p in called])
    result = []
    for key, lineup, compare_to in (("A", lineup_a, None), ("B", lineup_b, lineup_a)):
        if not lineup:
            continue
        result.append({
            "key": key,
            "title": _("Alineación %(letter)s · %(title)s") % {"letter": key, "title": lineup.title},
            "win": round(lineup.win * 100),
            "expected": round(lineup.expected, 1),
            "explanation": advisor.explain(lineup, venue_label, compare_to=compare_to),
            "pairs": [[p.a.id, p.b.id] for p in lineup.pairs],
        })
    return result
