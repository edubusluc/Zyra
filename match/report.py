"""
Datos del informe que se envía al cerrar una convocatoria.

Las estadísticas se calculan para el escenario del partido: si el club juega
como visitante, el rendimiento "en la sede" es el de sus partidos fuera (y
viceversa).
"""
from django.db.models import Q
from django.utils.translation import gettext as _, pgettext

from data_analyse.pairs import COMPETITIVE, club_game_log, match_type_lookup

from core.competitions import competition_for

from . import advisor, outcomes
from call.models import Call

from .models import Match

MAX_PAIRS_TABLE = 6
MAX_PRECEDENTS = 4


def _outcome(match):
    """'V', 'D' o 'E' de un partido cerrado desde el punto de vista del club."""
    if match.result == outcomes.LOCAL_WIN:
        return "V" if match.own_is_local else "D"
    if match.result == outcomes.VISITING_WIN:
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
    precedentes contra el rival, partidos jugados y convocatorias de cada convocado y las dos alineaciones
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
    competitive_only = match.report_competitive_only
    log = [g for g in club_game_log(club, match_type=COMPETITIVE if competitive_only else None)
           if g['date'] < match.start_date]
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

    # Con «solo competitivos», los amistosos tampoco cuentan en balances, precedentes ni convocatorias
    scope_filter = match_type_lookup(COMPETITIVE) if competitive_only else {}
    call_scope_filter = match_type_lookup(COMPETITIVE, "match__") if competitive_only else {}

    # Balance de la temporada (general y en la sede)
    season_matches = list(
        Match.objects.filter(club=club, season=match.season, draft_mode=False, start_date__lt=match.start_date)
        .filter(**scope_filter)
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
        .filter(**scope_filter).filter(same_rival)
        .select_related("local", "visiting")
        .order_by("-start_date")[:MAX_PRECEDENTS]
    ]

    # Uso de cada convocado: partidos jugados y convocatorias en las que se apuntó esta
    # temporada, y fecha del último partido que disputó (de cualquier temporada)
    usage = {p.id: {"games": 0, "calls": 0, "last": None} for p in called}
    for g in log:
        for pid in g["pair"]:
            if pid in usage:
                if g["season"] == match.season:
                    usage[pid]["games"] += 1
                usage[pid]["last"] = max(filter(None, (usage[pid]["last"], g["date"])))
    calls = (Call.objects.filter(match__club=club, match__season=match.season, match__draft_mode=False, draft_mode=False,
                                 match__start_date__lt=match.start_date)
             .filter(**call_scope_filter).exclude(pk=call.pk).values_list("players", flat=True))
    for pid in calls:
        if pid in usage:
            usage[pid]["calls"] += 1

    comp = competition_for(club)
    lineup_a, lineup_b = advisor.recommend(forms, pairs, [p.id for p in called], comp)
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
        "usage": usage,  # por id de convocado: {'games', 'calls', 'last'}
        "competitive_only": competitive_only,
        "enough_players": len(called) >= comp.players_per_lineup,
        "other_competitions": other_competitions(called, match) if match.report_other_competitions else [],
        "competition": comp,
    }


def other_competitions(called, match):
    """
    Partidos de la temporada del enfrentamiento que los convocados con cuenta enlazada han jugado
    en sus otros espacios (otras competiciones): una fila por jugador y competición con
    {'player', 'club', 'played', 'wins'}. Solo informativo: no entra en las alineaciones.
    """
    from data_analyse.views import build_game_log
    from players.models import Player

    by_user = {p.user_id: p for p in called if p.user_id}
    rows = []
    others = (Player.objects.filter(user_id__in=by_user).exclude(club=match.club)
              .select_related("club").order_by("club__competition"))
    for other in others:
        log = [g for g in build_game_log(other) if g["season"] == match.season]
        rows.append({"player": by_user[other.user_id], "club": other.club, "played": len(log),
                     "wins": sum(g["won"] for g in log)})
    rows.sort(key=lambda r: (r["player"].name, r["player"].last_name))
    return rows


def suggested_lineups(call):
    """
    Alineaciones recomendadas (A y, si la hay, B) para rellenar el formulario de parejas.

    Usa el mismo recomendador que el informe de la convocatoria, con la historia anterior
    al enfrentamiento y la ficha de su competición. Devuelve una lista (vacía si no hay
    convocados para llenar todas las parejas) de
    {'key', 'title', 'win', 'expected', 'explanation', 'pairs': [[id, id], ...]} con las
    parejas en orden de juego (partido 1 primero) si la competición lo fija.
    """
    match = call.match
    comp = competition_for(match.club)
    called = list(call.players.all())
    if len(called) < comp.players_per_lineup:
        return []
    own_local = match.own_is_local
    venue_label = pgettext("sede, en minúscula", "local") if own_local else pgettext("sede, en minúscula", "visitante")
    log = [g for g in club_game_log(match.club, match_type=COMPETITIVE if match.report_competitive_only else None)
           if g['date'] < match.start_date]
    forms, pairs = advisor.build_forms(log, called, own_local)
    lineup_a, lineup_b = advisor.recommend(forms, pairs, [p.id for p in called], comp)
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
