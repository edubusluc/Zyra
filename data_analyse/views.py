"""
Estadísticas del club: del equipo, por jugador, por parejas y advertencias.

Todas se calculan sobre los partidos cerrados del club y admiten filtro por temporada
y por tipo de partido.
"""
from collections import Counter

from match import outcomes
from django.shortcuts import render
from match.models import Match, Game
from players.models import Player, proper_name
from team.models import Team
from call.models import Call
from django.db.models import Q, Count
from django.views.decorators.http import require_GET
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.http import Http404
from django.core.paginator import Paginator
from urllib.parse import urlencode
from django.utils.translation import gettext as _, gettext_lazy
from core.decorators import club_required, club_manager_required
from core import spaces
from core.competitions import competition_for
from penalty.models import KINDS as PENALTY_KINDS, Penalty
from core.season_choice import ALL_SEASONS, choose_season
from players.models import current_season, joined_by
from . import pairs as pair_stats
from . import rivals as rival_stats
from . import records
from . import player_card, team_card
from .attendance import signup_attendance
from .sets import by_game_number, own_sets, set_stats

def _zero_state(request, title):
    """
    Con el club sin ningún enfrentamiento cerrado no hay nada que filtrar ni comparar: en vez de
    las pestañas y los filtros vacíos se muestra una sola tarjeta que explica qué se verá y cómo
    llegar (``stats_empty.html``). None si ya hay enfrentamientos cerrados.
    """
    club = request.club
    if Match.objects.filter(club=club, draft_mode=False).exists():
        return None
    return render(request, 'stats_empty.html', {
        'zero_title': title,
        'has_open_matches': Match.objects.filter(club=club, draft_mode=True).exists(),
    })


# ---------------------------------------------------------------
# ESTADÍSTICAS EQUIPO
# ---------------------------------------------------------------
from match.outcomes import DRAW, LOCAL_WIN, VISITING_WIN
# DRAW: empate a puntos en la eliminatoria (p. ej. 6-6), ni victoria ni derrota.


def get_total_season(matchs):
    """Temporadas distintas de los partidos de ``matchs``."""
    return set(matchs.values_list('season', flat=True).distinct())


# ---------------------------------------------------------------
# FILTRO POR TIPO DE PARTIDO: Todos / Competitivos (enfrentamiento, reto, play off) / Amistosos
# ---------------------------------------------------------------
MATCH_TYPE_PARAM = "match_type"
COMPETITIVE = pair_stats.COMPETITIVE


def selected_match_type(request):
    """Filtro elegido en la URL (?match_type=competitivo, reto, amistoso...); None = todos."""
    value = request.GET.get(MATCH_TYPE_PARAM)
    return value if value in pair_stats.FILTER_VALUES else None


ALL_TYPES = "todos"


def stats_match_type(request):
    """
    Filtro de tipo de las pantallas de Estadísticas: sin nada en la URL, ``competitivo`` (lo que cuenta
    para la clasificación; los amistosos no se mezclan por defecto, igual que en «Mi forma»);
    ``?match_type=todos`` los incluye (devuelve None) y cualquier otro valor válido filtra por él.
    """
    value = request.GET.get(MATCH_TYPE_PARAM)
    if value == ALL_TYPES:
        return None
    return value if value in pair_stats.FILTER_VALUES else COMPETITIVE


# ---------------------------------------------------------------
# SELECTOR DE TEMPORADAS: Todas + las tres últimas + buscador para el resto
# ---------------------------------------------------------------
SEASON_PARAM = "season"
PAGE_PARAM = "page"
RECENT_SEASONS = 3


def season_filter_context(request, seasons, selected_season, all_value=ALL_SEASONS, anchor=""):
    """
    Chips "Todas" y las ``RECENT_SEASONS`` temporadas más recientes (``seasons`` de más nueva a
    más antigua); si la elegida es más antigua, aparece también como chip activo. Con más temporadas
    de las que caben en los chips, ``season_search`` lista todas para el buscador. Cada enlace conserva
    el resto de la URL (jugador, tipo de partido) salvo la página, que vuelve a la primera.
    ``all_value`` es el valor de "Todas" en la URL (advertencias y el listado de partidos usan
    ?season=all porque sin parámetro muestran la temporada actual).
    """
    def url(value):
        """URL de la página actual con la temporada ``value`` (sin ella para «Todas»)."""
        params = request.GET.copy()
        params.pop(PAGE_PARAM, None)
        if value:
            params[SEASON_PARAM] = value
        else:
            params.pop(SEASON_PARAM, None)
        query = params.urlencode()
        return f"{request.path}?{query}{anchor}" if query else f"{request.path}{anchor}"

    all_active = selected_season in (None, "", all_value)
    chips = list(seasons[:RECENT_SEASONS])
    if not all_active and selected_season not in chips:
        chips.append(selected_season)
    return {
        'season_all': {'url': url(all_value), 'active': all_active},
        'season_chips': [{'label': s, 'url': url(s), 'active': s == selected_season} for s in chips],
        'season_search': list(seasons) if len(seasons) > RECENT_SEASONS else [],
        # Resto de la URL para el formulario del buscador.
        'season_keep': [(key, value) for key, values in request.GET.lists() if key not in (SEASON_PARAM, PAGE_PARAM)
                        for value in values],
        'season_anchor': anchor,
    }


def match_type_context(request, match_type, by_type=False, stats=False):
    """
    Filtro por tipo de partido: chips Todos / Competitivos / Amistosos (``match_types``) y, dentro
    de Competitivos, un selector con todos los partidos competitivos o un tipo (``competitive_types``).
    Cada enlace conserva el resto de la URL (jugador, pareja, temporada); ``match_type_qs`` sirve
    para añadir el filtro a los enlaces que ya existían (temporadas). Con ``by_type`` (pantallas de una sola
    competición) los chips son Todos, un chip por tipo de la competición y Amistosos, sin «Competitivos».
    Con ``stats`` (Estadísticas) el tipo por defecto es Competitivos y «Todos» va explícito
    (``?match_type=todos``, ver ``stats_match_type``); ``match_type_param`` es el valor a conservar en los
    enlaces y formularios y ``match_type_changed`` dice si el filtro se aparta del defecto (se marca en lima).
    """
    def url(value):
        """URL de la página actual con el tipo de partido ``value`` (sin él para «Todos»)."""
        params = request.GET.copy()
        if stats:
            params[MATCH_TYPE_PARAM] = value or ALL_TYPES
        elif value:
            params[MATCH_TYPE_PARAM] = value
        else:
            params.pop(MATCH_TYPE_PARAM, None)
        query = params.urlencode()
        return f"{request.path}?{query}" if query else request.path

    competitive = match_type == COMPETITIVE or match_type in dict(Match.COMPETITIVE_TYPES)
    options = [
        {'label': _("Todos"), 'url': url(None), 'active': match_type is None},
        {'label': _("Competitivos"), 'url': url(COMPETITIVE), 'active': competitive},
        {'label': _("Amistosos"), 'url': url(Match.AMISTOSO), 'active': match_type == Match.AMISTOSO},
    ]
    # Tipos de la competición del espacio activo (Enfrentamientos, Retos, Play offs en SNP; Liga,
    # Playoffs, Fase final en LAPI).
    rules = request.club.rules if getattr(request, "club", None) is not None else competition_for(None)
    competitive_labels = [(COMPETITIVE, _("Todos los enfrentamientos"))] + [
        (value, plural) for value, _label, plural in rules.match_types]
    labels = dict(competitive_labels, **{COMPETITIVE: _("Competitivos"), Match.AMISTOSO: _("Amistosos")})
    if by_type:
        # Con el defecto de Estadísticas (Competitivos) el desplegable tiene que poder mostrarlo como elegido.
        options = ([options[0]] + ([options[1]] if stats else [])
                   + [{'label': plural, 'url': url(value), 'active': value == match_type} for value, _label, plural in rules.match_types]
                   + [options[2]])
        competitive = False
    return {
        'match_types': options,
        'competitive_types': [{'label': label, 'value': value, 'url': url(value), 'active': value == match_type}
                              for value, label in competitive_labels] if competitive else [],
        # Resto de la URL (jugador, pareja, temporada) para el formulario del selector de Competitivos.
        'match_type_keep': [(key, value) for key, values in request.GET.lists() if key != MATCH_TYPE_PARAM
                            for value in values],
        'selected_match_type': match_type,
        'selected_match_type_label': labels.get(match_type),
        'match_type_param': (match_type or ALL_TYPES) if stats else (match_type or ""),
        'match_type_changed': (match_type != COMPETITIVE) if stats else bool(match_type),
        'match_type_qs': f"&{MATCH_TYPE_PARAM}={(match_type or ALL_TYPES) if stats else match_type}" if (stats or match_type) else "",
    }


def _by_type(matches, match_type, prefix=""):
    """Filtra un queryset por el filtro de tipo; ``prefix`` es la ruta hasta Match ('match__')."""
    return matches.filter(**pair_stats.match_type_lookup(match_type, prefix))


def calculate_match_statistics(season, team, match_type=None):
    """
    Enfrentamientos cerrados del club (de la temporada si se indica): (total, ganados,
    empatados, perdidos, % ganados, % empatados, % perdidos). Una eliminatoria empatada a
    puntos cuenta como empate, no como derrota.
    """
    matches = _by_type(Match.objects.filter(club=team.club, draft_mode=False), match_type)
    if season is not None:
        matches = matches.filter(season=season)
    total_matches = matches.count()
    won_local = matches.filter(local=team, result=LOCAL_WIN).count()
    won_visiting = matches.filter(visiting=team, result=VISITING_WIN).count()

    total_won = won_local + won_visiting
    drawn_matches = matches.filter(result=DRAW).count()
    lost_matches = total_matches - total_won - drawn_matches

    def pct(n):
        """``n`` como porcentaje del total, con dos decimales."""
        return round(n / total_matches * 100, 2) if total_matches > 0 else 0

    return (total_matches, total_won, drawn_matches, lost_matches,
            pct(total_won), pct(drawn_matches), pct(lost_matches))


def calculate_tiebreak_stats(season, team, match_type=None):
    """
    Eliminatorias de Reto y Play Off que quedaron 6-6 y decidió el partido 3:
    ``{'total', 'for', 'against', 'for_pct', 'against_pct'}`` según si el equipo ganó o perdió ese
    partido (porcentajes sobre el total, que suman 100).
    """
    matches = _by_type(Match.objects.filter(club=team.club, draft_mode=False, match_type__in=Match.NO_DRAW_TYPES,
                                            result_points="6/6"), match_type)
    if season is not None:
        matches = matches.filter(season=season)
    in_favor = (matches.filter(local=team, result=LOCAL_WIN).count()
                + matches.filter(visiting=team, result=VISITING_WIN).count())
    against = (matches.filter(local=team, result=VISITING_WIN).count()
               + matches.filter(visiting=team, result=LOCAL_WIN).count())
    total = in_favor + against
    for_pct = round(in_favor / total * 100) if total else 0
    return {'total': total, 'for': in_favor, 'against': against,
            'for_pct': for_pct, 'against_pct': 100 - for_pct if total else 0}


def column_chart(club, season, match_type=None):
    """Partidos de 2 y 3 puntos ganados/perdidos por jugador actual (una sola consulta)."""
    players = Player.objects.filter(club=club, in_team=True)
    names = {p.id: p.full_name for p in players}
    dicc = {
        name: {
            'Partidos de 2 puntos ganados': 0,
            'Partidos de 2 puntos perdidos': 0,
            'Partidos de 3 puntos ganados': 0,
            'Partidos de 3 puntos perdidos': 0,
        } for name in names.values()
    }

    games = Game.objects.filter(match__club=club, match__draft_mode=False, draft_mode=False,
                                winner__in=outcomes.WINNERS, n_game__in=[1, 2, 3, 4, 5])
    if season:
        games = games.filter(match__season=season)
    games = _by_type(games, match_type, "match__")
    rows = games.values_list('n_game', 'winner', 'player_1_local', 'player_2_local', 'player_1_visiting', 'player_2_visiting')
    for n_game, winner, l1, l2, v1, v2 in rows:
        kind = '3' if n_game in (1, 2) else '2'
        for pid, side in ((l1, "Local"), (l2, "Local"), (v1, "Visitante"), (v2, "Visitante")):
            if pid in names:
                outcome = 'ganados' if winner == side else 'perdidos'
                dicc[names[pid]][f'Partidos de {kind} puntos {outcome}'] += 1

    return dicc


def format_for_chart(dic):
    """Datos de ``column_chart`` como lista de {'player', 'data'} para el gráfico de columnas."""
    players = []
    for player_name, stats in dic.items():
        players.append({
            'player': player_name,
            'data': [
                stats['Partidos de 2 puntos ganados'],
                stats['Partidos de 2 puntos perdidos'],
                stats['Partidos de 3 puntos ganados'],
                stats['Partidos de 3 puntos perdidos'],
            ]
        })
    return players


@spaces.consult_view
@club_required
@require_GET
def team_statistics(request):
    """
    Estadísticas del equipo propio: balance de enfrentamientos y juegos, puntos de liga o de cada
    enfrentamiento, sets, récords y mejores jugadores como local, y puntos SNP del equipo.
    Requiere pertenecer al club y solo GET. Filtra por temporada (``?season=``) y tipo de partido.

    Como el resto de pantallas de Estadísticas, es del equipo activo (``?en=`` lo cambia, ``spaces.consult_view``)
    y con varios espacios lleva el selector de competición: los equipos de cada competición no se mezclan
    (lo global de la persona está en «Mis estadísticas»).
    """
    zero = _zero_state(request, _("Estadísticas del equipo"))
    if zero:
        return zero
    seasons = get_total_season(Match.objects.filter(club=request.club))
    team = request.club.own_team
    match_type = stats_match_type(request)
    seasons = sorted(seasons, key=lambda s: int(s.split('-')[0]), reverse=True)
    selected_season = choose_season(request, seasons)
    if selected_season == ALL_SEASONS:
        selected_season = None

    dicc = column_chart(request.club, selected_season, match_type) if request.club.rules.ordered_pairs else {}
    column_chart_data = format_for_chart(dicc)

    if not team:
        return render(request, 'team_statistics.html', {"seasons": seasons, **match_type_context(request, match_type, stats=True),
                                                        **season_filter_context(request, seasons, selected_season)})

    (total_matches, total_won, drawn_matches, lost_matches,
     percentage_won, _percentage_drawn, _percentage_lost) = calculate_match_statistics(selected_season or None, team, match_type)

    tiebreaks = calculate_tiebreak_stats(selected_season or None, team, match_type)

    # Top 5 (jugadores actuales del equipo), respetando la temporada y el tipo de partido elegidos
    squad = list(Player.objects.filter(club=request.club, in_team=True))
    log = pair_stats.club_game_log(request.club, selected_season or None, match_type)

    context = {
        **match_type_context(request, match_type, stats=True, by_type=True),
        **season_filter_context(request, seasons, selected_season),
        'team': team,
        'total_matches': total_matches,
        'won_matches': total_won,
        'drawn_matches': drawn_matches,
        'tiebreaks': tiebreaks,
        'lost_matches': lost_matches,
        'percentage_won': percentage_won,
        "seasons": seasons,
        "selected_season": selected_season,
        "top_local_players": pair_stats.top_players(log, squad, local=True),
        "top_visiting_players": pair_stats.top_players(log, squad, local=False),
        "column_chart_data": column_chart_data,
        "min_games_player": pair_stats.MIN_GAMES_PLAYER,
    }
    context.update(team_extra_context(request.club, selected_season, match_type, log))
    context['attendance'] = signup_attendance(request.club, selected_season, match_type)
    context.update(team_card_context(request.club, selected_season, match_type, context))

    return render(request, 'team_statistics.html', context)


@club_required
@require_GET
def my_statistics(request):
    """
    «Mis estadísticas»: lo de la persona en todas sus competiciones, para quien tiene jugador en
    varias (``spaces.linked_players``). «Todas» junta sus partidos y pone cada competición al lado de
    la otra en los gráficos, sin sumar puntos; ``?espacio=snp`` (o lapi) lleva a su ficha de jugador
    en esa competición. Con un solo jugador enlazado va directo a su ficha; con ninguno (y varios
    equipos) explica cómo enlazar la ficha (stats_mine_link.html). Filtra por temporada y
    tipo de partido. Renderiza stats_mine.html.
    """
    players = spaces.linked_players(request)
    if len(players) < 2:
        if players:
            return redirect(f"{reverse('player_statistics')}?en={players[0].club.competition}&player={players[0].public_id}")
        if len(spaces.user_clubs(request)) > 1:
            return render(request, 'stats_mine_link.html')
        return redirect('team_statistics')
    wanted = request.GET.get(spaces.SPACE_PARAM)
    chosen = next((p for p in players if p.club.competition == wanted), None)
    if chosen:
        params = request.GET.copy()
        params.pop(spaces.SPACE_PARAM, None)
        params[spaces.SWITCH_PARAM] = chosen.club.competition
        params['player'] = chosen.public_id
        return redirect(f"{reverse('player_statistics')}?{params.urlencode()}")

    match_type = stats_match_type(request)
    clubs = [p.club for p in players]
    seasons = sorted(get_total_season(Match.objects.filter(club__in=clubs)),
                     key=lambda s: int(s.split('-')[0]), reverse=True)
    selected_season = choose_season(request, seasons)
    if selected_season == ALL_SEASONS:
        selected_season = None

    rows, all_log, logs = [], [], []
    for player in players:
        log = [g for g in build_game_log(player, match_type) if not selected_season or g['season'] == selected_season]
        logs.append(log)
        all_log += log
        summary = summarize(log)
        present, total = calls_by_season(player, match_type)
        if selected_season:
            present, total = {selected_season: present.get(selected_season, 0)}, {selected_season: total.get(selected_season, 0)}
        rows.append({"club": player.club, "player": player, "played": summary['played'], "wins": summary['wins'],
                     "losses": summary['losses'], "pct": round(summary['pct']),
                     "calls": signup_summary(present, total)})
    me = summarize(all_log)

    return render(request, 'stats_mine.html', {
        **match_type_context(request, match_type, stats=True),
        **season_filter_context(request, seasons, selected_season),
        **mine_chips(request, players, None),
        **players_charts(players, logs, selected_season, match_type),
        'selected_season': selected_season,
        'rows': rows,
        'me': me,
    })


def mine_chips(request, players, active):
    """
    Chips de «Mis estadísticas» (Todas y una por competición con jugador enlazado) para
    ``includes/stats_tabs.html``; ``active``: código de la competición abierta o None para «Todas».
    """
    base = reverse('my_statistics')
    chips = [{"code": spaces.ALL_SPACES, "label": _("Todas"), "url": base, "active": active is None}]
    chips += [{"code": p.club.competition, "label": str(p.club.rules.name), "club": p.club, "name": p.club.rules.name,
               "url": f"{base}?{spaces.SPACE_PARAM}={p.club.competition}", "active": active == p.club.competition}
              for p in players]
    return {"mine_chips": chips}


# Situaciones de la tarjeta «Sets» que se comparan entre competiciones: (clave de set_stats, título, explicación).
SET_SITUATIONS = (
    ('third', gettext_lazy("Set decisivo"), gettext_lazy("Tercer set, a set normal o a super tie-break.")),
    ('tiebreak', gettext_lazy("Tie-breaks"), gettext_lazy("Sets que llegan a 6-6 y acaban 7-6.")),
    ('comeback', gettext_lazy("Remontadas"), gettext_lazy("Partidos ganados tras perder el primer set.")),
    ('first_set', gettext_lazy("Cerrar el partido"), gettext_lazy("Partidos ganados tras ganar el primer set.")),
    ('close', gettext_lazy("Sets ajustados"), gettext_lazy("Sets que acaban 7-5 o 7-6.")),
)


# Situaciones de sets que muestra «Mis estadísticas · Todas», en el orden del diseño.
MINE_SET_KEYS = ('tiebreak', 'first_set', 'comeback')


def players_charts(players, logs, season, match_type):
    """
    Gráficos de «Mis estadísticas · Todas» con cada competición al lado de la otra, nunca sumadas en
    una cifra (los puntos de un partido no valen lo mismo en SNP que en LAPI). ``logs``: partidos de
    cada jugador de ``players`` (build_game_log, ya filtrados por temporada).

    Devuelve ``set_rows`` (cada situación de sets con el % de cada competición), ``set_panels`` (lo mismo
    agrupado por competición, para los paneles de stats_mine.html) y ``spaces_chart``
    para stats_spaces.js: competiciones, % de victorias como local y como visitante,
    partidos ganados por temporada (sin temporada elegida) y % de convocatorias en las que se apuntó
    por temporada (con una temporada elegida, solo esa: se dibuja con barras).
    """
    comps, sets_by_comp, local, visiting, years, attendance = [], [], [], [], [], []
    for player, log in zip(players, logs):
        club = player.club
        comps.append({"code": club.competition, "name": str(club.rules.name), "club": club.name})
        sets_by_comp.append(set_stats(log))
        local.append({"won": sum(g["won"] for g in log if g["local"]),
                      "lost": sum(not g["won"] for g in log if g["local"])})
        visiting.append({"won": sum(g["won"] for g in log if not g["local"]),
                         "lost": sum(not g["won"] for g in log if not g["local"])})
        per_year = {}
        for g in log:
            per_year[g["season"]] = per_year.get(g["season"], 0) + g["won"]
        years.append(per_year if not season else {})
        present, total = calls_by_season(player, match_type)
        if season:
            present, total = {season: present.get(season, 0)}, {season: total.get(season, 0)}
        attendance.append({s: round(present.get(s, 0) / n * 100) for s, n in total.items() if n})

    set_rows = [{
        "key": key, "label": label, "hint": hint,
        "comps": [{"code": c["code"], "name": c["name"], "r": st[key]} for c, st in zip(comps, sets_by_comp)],
    } for key, label, hint in SET_SITUATIONS]

    # Lo mismo agrupado por competición: un panel por competición con todas sus situaciones (idea «marco y dato»).
    set_panels = [{
        "code": c["code"], "name": c["name"], "club": c["club"],
        "rows": [{"label": label, "hint": hint, "r": st[key]} for key, label, hint in SET_SITUATIONS],
    } for c, st in zip(comps, sets_by_comp)]

    # Tarjeta «Sets» de «Mis estadísticas»: solo las tres situaciones del diseño, con el % de cada competición.
    set_compare = [row for key in MINE_SET_KEYS for row in set_rows if row["key"] == key]

    # % de victorias en casa y fuera de cada competición (None sin partidos), para «Local y visitante».
    pct = lambda r: round(100 * r["won"] / (r["won"] + r["lost"])) if r["won"] + r["lost"] else None
    totals = [{"won": a["won"] + b["won"], "lost": a["lost"] + b["lost"], "local": a, "visiting": b,
               "pct_local": pct(a), "pct_visiting": pct(b)}
              for a, b in zip(local, visiting)]

    by_start = lambda s: int(s.split('-')[0])
    labels = sorted({y for per in years for y in per}, key=by_start)
    att_labels = sorted({s for per in attendance for s in per}, key=by_start)
    return {
        "set_rows": set_rows,
        "set_panels": set_panels,
        "set_compare": set_compare,
        "sets_played": any(st["played"] for st in sets_by_comp),
        "has_local": any(r["won"] or r["lost"] for r in local),
        "has_visiting": any(r["won"] or r["lost"] for r in visiting),
        "spaces_chart": {
            "comps": comps,
            "local": local,
            "visiting": visiting,
            "totals": totals,
            "years": {"labels": labels, "won": [[per.get(y, 0) for y in labels] for per in years]},
            "attendance": {"labels": att_labels, "series": [[per.get(s) for s in att_labels] for per in attendance]},
            "currentSeason": current_season(),
        },
    }


def team_card_context(club, season, match_type, context):
    """
    Datos de las tarjetas de «Equipo» del diseño: puntos de liga o de cada enfrentamiento, plantilla y
    fases finales, no presentados y lesiones, filas de sets con su texto, y tarjetas y puntos SNP del equipo.
    ``context`` es lo ya calculado (sets, ranking SNP).
    """
    rules = club.rules
    sets = context['set_stats']
    sets_total = sets['sets_won'] + sets['sets_lost']
    bagels = {'pct': round(100 * sets['bagels_for'] / sets_total) if sets_total else None}
    by_key = {key: (label, desc) for key, label, desc in SET_SITUATIONS}
    set_rows = [(*by_key[key], sets[key]) for key in ('tiebreak', 'first_set', 'comeback')]
    set_rows.append((_("Roscos a favor"), _("Sets ganados por 6-0."), bagels))
    snp = context['snp']
    extra = {
        'points_card': team_card.points_series(club, season, match_type),
        'finals': team_card.finals_roster(club, current_season()) if season in (None, current_season()) else None,
        'walkovers': team_card.walkovers(club, season, match_type),
        'set_rows': set_rows,
        'venue': team_card.venue_matches(club, season, match_type),
    }
    if rules.has_snp:
        extra['snp_total'] = {'average': snp['average']}
    return extra


def team_extra_context(club, season, match_type, log):
    """
    Tarjetas de la página de equipo que salen del log de partidos: balance por número de
    partido, sets, récords y ranking SNP de la plantilla (de la temporada elegida o la actual).
    """
    numbers = by_game_number(log)
    snp_season = season or current_season()
    snp = records.snp_ranking(club, snp_season)
    return {
        'game_numbers': numbers,
        'set_stats': set_stats(log),
        'records': records.team_records(club, season, match_type, log),
        'snp': snp,
        'snp_season': snp_season,
        'snp_chart': snp['chart'],
    }


# ---------------------------------------------------------------
# ESTADÍSTICAS JUGADORES
# ---------------------------------------------------------------

# Orden cronológico de los partidos del jugador (por fecha, como pairs.club_game_log).
# De esto dependen las rachas.
ORDER = ('match__start_date', 'match_id', 'n_game')

# Peso del "punto de partida" neutro (50 %) en la afinidad, medido en puntos en juego.
PRIOR_POINTS = 6


def degree_of_affinity(player, match_type=None, season=None):
    """
    Afinidad (0-100) con cada compañero con el que ha jugado en pareja.
    % de puntos ganados en pareja (cada partido pesa game.score), suavizado
    hacia el 50 % cuando hay pocos partidos.
    Incluye a los compañeros que ya no están en el equipo (in_team=False) y a los
    eliminados (por el nombre guardado en el partido); 'in_team' los distingue.
    Con ``season`` solo cuenta los partidos de esa temporada.
    Devuelve: [{'name', 'affinity', 'games', 'wins', 'losses', 'in_team'}, ...] de mayor a menor.
    """
    games = Game.objects.filter(
        Q(player_1_local=player) | Q(player_2_local=player) |
        Q(player_1_visiting=player) | Q(player_2_visiting=player),
        draft_mode=False,
        match__draft_mode=False,
        winner__in=outcomes.WINNERS,
    )
    if season:
        games = games.filter(match__season=season)
    games = _by_type(games, match_type, "match__")

    people = {p.id: p for p in Player.objects.filter(club=player.club).exclude(id=player.id)}
    acc = {}

    for g in games:
        if player.id in (g.player_1_local_id, g.player_2_local_id):
            side, slots = 'Local', ('player_1_local', 'player_2_local')
        else:
            side, slots = 'Visitante', ('player_1_visiting', 'player_2_visiting')

        partner_slot = slots[1] if getattr(g, slots[0] + '_id') == player.id else slots[0]
        partner_id = getattr(g, partner_slot + '_id')
        if partner_id in people:
            partner = people[partner_id]
            key, name, in_team = partner_id, partner.full_name, partner.in_team
        elif partner_id is None and g.removed_player_names.get(partner_slot):
            # Jugador eliminado: se agrupa por el nombre guardado en el partido
            name = proper_name(g.removed_player_names[partner_slot])
            key, in_team = ('removed', name), False
        else:
            continue

        won = g.winner == side
        weight = g.score or 1
        a = acc.setdefault(key, {'name': name, 'in_team': in_team, 'games': 0, 'wins': 0, 'stake': 0, 'won_pts': 0})
        a['games'] += 1
        a['wins'] += won
        a['stake'] += weight
        a['won_pts'] += weight if won else 0

    results = []
    for a in acc.values():
        rate = (a['won_pts'] + PRIOR_POINTS * 0.5) / (a['stake'] + PRIOR_POINTS)
        results.append({
            'name': a['name'],
            'affinity': round(rate * 100),
            'games': a['games'],
            'wins': a['wins'],
            'losses': a['games'] - a['wins'],
            'in_team': a['in_team'],
        })

    results.sort(key=lambda r: (r['affinity'], r['games']), reverse=True)
    return results


def build_game_log(player, match_type=None):
    """
    Una sola consulta (+1 prefetch): lista cronológica de los partidos (Game) del jugador.
    Cada elemento: {'season', 'match_id', 'n_game', 'local', 'won', 'points', 'sets_won', 'sets_lost', 'sets'}
    'sets_*' son los "juegos" que suma el jugador y su rival dentro del partido; 'sets', los
    sets jugados desde su lado (ver data_analyse.sets).
    """
    games = (
        Game.objects
        .filter(
            Q(player_1_local=player) | Q(player_2_local=player) |
            Q(player_1_visiting=player) | Q(player_2_visiting=player),
            draft_mode=False,
            match__draft_mode=False,
        )
        .select_related('match')
        .prefetch_related('results')
        .order_by(*ORDER)
    )
    games = _by_type(games, match_type, "match__")

    log = []
    for g in games:
        if g.winner not in outcomes.WINNERS:
            continue  # partido sin cerrar
        is_local = player.id in (g.player_1_local_id, g.player_2_local_id)
        won = (g.winner == outcomes.WINNER_LOCAL) == is_local

        sets_won = sets_lost = 0
        for r in g.results.all():
            loc = sum(filter(None, [r.set1_local, r.set2_local, r.set3_local]))
            vis = sum(filter(None, [r.set1_visiting, r.set2_visiting, r.set3_visiting]))
            mine, theirs = (loc, vis) if is_local else (vis, loc)
            sets_won += mine
            sets_lost += theirs

        log.append({
            'season': g.match.season,
            'match_id': g.match_id,
            'n_game': g.n_game,
            'local': is_local,
            'won': won,
            'points': g.score if won else 0,
            'possible': g.score,
            'sets_won': sets_won,
            'sets_lost': sets_lost,
            'sets': own_sets(next(iter(g.results.all()), None), is_local),
        })
    return log


def _sets_text(game, is_local):
    """Sets desde el punto de vista del club ("6-3 4-6 10-8"). Usa game.results prefetched."""
    result = next(iter(game.results.all()), None)
    if not result:
        return ""
    return " ".join(
        f"{loc}-{vis}" if is_local else f"{vis}-{loc}"
        for loc, vis in result.sets() if loc is not None and vis is not None
    )


def season_games(player, season, match_type=None):
    """
    Partidos (Game) cerrados del jugador en una temporada (``season`` None = todas), del más reciente al más antiguo.
    Solo partidos de enfrentamientos de su club: los enlaces llevan a call_for_match,
    que también exige que el enfrentamiento sea del club activo.
    Cada elemento: {'match_id', 'match_public_id', 'n_game', 'date', 'rival', 'local', 'partner', 'sets', 'won', 'points'}
    """
    games = (
        Game.objects
        .filter(
            Q(player_1_local=player) | Q(player_2_local=player) |
            Q(player_1_visiting=player) | Q(player_2_visiting=player),
            draft_mode=False,
            match__draft_mode=False,
            winner__in=outcomes.WINNERS,
            match__club=player.club,
        )
        .select_related('match__local', 'match__visiting',
                        'player_1_local', 'player_2_local', 'player_1_visiting', 'player_2_visiting')
        .prefetch_related('results')
        .order_by('-match__start_date', '-match_id', 'n_game')
    )
    if season:
        games = games.filter(match__season=season)
    games = _by_type(games, match_type, "match__")

    rows = []
    for g in games:
        is_local = player.id in (g.player_1_local_id, g.player_2_local_id)
        pair = (g.player_1_local, g.player_2_local) if is_local else (g.player_1_visiting, g.player_2_visiting)
        partner = next((p for p in pair if p and p.id != player.id), None)
        won = (g.winner == outcomes.WINNER_LOCAL) == is_local

        rows.append({
            'match_id': g.match_id,
            'match_public_id': g.match.public_id,
            'n_game': g.n_game,
            'date': g.match.start_date,
            'rival': g.match.visiting_name if is_local else g.match.local_name,
            'local': is_local,
            'partner': partner,
            'sets': _sets_text(g, is_local),
            'type_label': g.match.type_label,
            'round': g.match.round_number,
            'won': won,
            'points': g.score if won else 0,
            'possible': g.score,
        })
    return rows


def calls_by_season(player, match_type=None):
    """
    Convocatorias por temporada: ({temporada: a las que se apuntó}, {temporada: total}). Solo cuentan
    las de su temporada de incorporación en adelante (``Player.joined_season``): antes no estaba en el equipo.
    """
    base = _by_type(Call.objects.filter(match__club=player.club, match__draft_mode=False, draft_mode=False,
                                        match__no_show=""), match_type, "match__")
    total = dict(base.order_by().values_list('match__season').annotate(n=Count('id', distinct=True)))
    present = dict(
        base.filter(players__id=player.id)
        .order_by().values_list('match__season').annotate(n=Count('id', distinct=True))
    )
    keep = lambda d: {k: v for k, v in d.items() if joined_by(player.joined_season, k)}
    return keep(present), keep(total)


def aligned_by_season(player, match_type=None):
    """
    {temporada: convocatorias cerradas a las que se apuntó y en las que además jugó algún
    partido}. Junto con calls_by_season da el "apuntado y alineado".
    """
    signed = _by_type(
        Call.objects.filter(match__club=player.club, match__draft_mode=False, draft_mode=False, match__no_show="",
                            players__id=player.id), match_type, "match__"
    ).values_list('match_id', 'match__season')
    seasons = dict(signed)
    played = set(
        Game.objects.filter(
            Q(player_1_local=player) | Q(player_2_local=player) |
            Q(player_1_visiting=player) | Q(player_2_visiting=player),
            match_id__in=list(seasons),
        ).values_list('match_id', flat=True)
    )
    result = {}
    for match_id in played:
        if joined_by(player.joined_season, seasons[match_id]):
            result[seasons[match_id]] = result.get(seasons[match_id], 0) + 1
    return result


def lineup_summary(calls_present, aligned):
    """Totales de "apuntado y alineado": {'signed', 'aligned', 'benched', 'pct'} (pct None sin convocatorias)."""
    signed = sum(calls_present.values())
    played = sum(aligned.values())
    return {
        'signed': signed,
        'aligned': played,
        'benched': signed - played,
        'pct': round(played / signed * 100) if signed else None,
    }


def signup_summary(calls_present, calls_total):
    """Totales de convocatorias cerradas: {'total', 'signed', 'missed', 'pct'} (pct None sin convocatorias)."""
    total = sum(calls_total.values())
    signed = sum(calls_present.values())
    return {
        'total': total,
        'signed': signed,
        'missed': total - signed,
        'pct': round(signed / total * 100) if total else None,
    }


def _pct(wins, total):
    """Porcentaje con un decimal; 0 si no hay partidos."""
    return round(wins / total * 100, 1) if total else 0


def _longest_run(results, target):
    """Racha más larga de resultados iguales a ``target`` (True: victorias, False: derrotas)."""
    best = run = 0
    for r in results:
        run = run + 1 if r == target else 0
        best = max(best, run)
    return best


def _current_run(results):
    """Devuelve ('V', 4) o ('D', 2). Sin partidos: (None, 0)."""
    if not results:
        return None, 0
    last, n = results[-1], 0
    for r in reversed(results):
        if r != last:
            break
        n += 1
    return ('V' if last else 'D'), n


def summarize(log):
    """Todas las métricas a partir de un log (global o de una temporada)."""
    results = [g['won'] for g in log]
    local_games = [g for g in log if g['local']]
    visiting_games = [g for g in log if not g['local']]
    local = [g['won'] for g in local_games]
    visiting = [g['won'] for g in visiting_games]

    total, wins = len(results), sum(results)
    streak_type, streak_len = _current_run(results)

    local_sets_won = sum(g['sets_won'] for g in local_games)
    local_sets_lost = sum(g['sets_lost'] for g in local_games)
    visiting_sets_won = sum(g['sets_won'] for g in visiting_games)
    visiting_sets_lost = sum(g['sets_lost'] for g in visiting_games)

    return {
        'played': total,
        'wins': wins,
        'losses': total - wins,
        'pct': _pct(wins, total),
        'points': sum(g['points'] for g in log),
        'points_possible': sum(g.get('possible', 0) for g in log),

        'local_played': len(local),
        'local_wins': sum(local),
        'local_losses': len(local) - sum(local),
        'local_pct': _pct(sum(local), len(local)),
        'local_sets_won': local_sets_won,
        'local_sets_lost': local_sets_lost,
        'local_sets_total': local_sets_won + local_sets_lost,

        'visiting_played': len(visiting),
        'visiting_wins': sum(visiting),
        'visiting_losses': len(visiting) - sum(visiting),
        'visiting_pct': _pct(sum(visiting), len(visiting)),
        'visiting_sets_won': visiting_sets_won,
        'visiting_sets_lost': visiting_sets_lost,
        'visiting_sets_total': visiting_sets_won + visiting_sets_lost,

        'streak_type': streak_type,
        'streak_len': streak_len,
        'best_win_streak': _longest_run(results, True),
        'worst_loss_streak': _longest_run(results, False),
        'best_local_streak': _longest_run(local, True),
        'best_visiting_streak': _longest_run(visiting, True),

        # últimos 5, el más reciente a la derecha
        'form': results[-5:],
    }


def summarize_by_season(log, calls_present, calls_total):
    """Temporadas (ascendente) con métricas, convocatorias y variación de % vs. la anterior."""
    by_season = {}
    for g in log:
        by_season.setdefault(g['season'], []).append(g)

    rows, previous = [], None
    for season in sorted(by_season, key=lambda s: int(s.split('-')[0])):
        games = by_season[season]
        wins = sum(g['won'] for g in games)
        pct = _pct(wins, len(games))
        rows.append({
            'season': season,
            'played': len(games),
            'wins': wins,
            'losses': len(games) - wins,
            'pct': pct,
            'points': sum(g['points'] for g in games),
            'calls_present': calls_present.get(season, 0),
            'calls_total': calls_total.get(season, 0),
            'delta': round(pct - previous, 1) if previous is not None else None,
        })
        previous = pct
    return rows


@spaces.consult_view
@club_required
@require_GET
def statistics_per_player(request):
    """
    Estadísticas de un jugador del club (``?player=``): balance, rachas, evolución por
    temporada, afinidad con sus compañeros, puntos SNP y, con ``?season=``, el resumen, la afinidad
    y el detalle de esa temporada (combinable con ``?match_type=``). Sin jugador muestra solo el selector. Requiere pertenecer al club y solo GET.
    Quien es jugador en todos sus equipos (``spaces.plays_only``) no ve la pestaña «Resumen» de la
    ficha (la de Plantilla).
    """
    # Con un jugador elegido se sigue viendo su historial de puntos SNP aunque no haya enfrentamientos cerrados.
    zero = None if request.GET.get('player') else _zero_state(request, _("Estadísticas de jugadores"))
    if zero:
        return zero
    players = Player.objects.filter(club=request.club, in_team=True).order_by('name', 'last_name')
    player_id = request.GET.get('player')
    match_type = stats_match_type(request)

    if not player_id:
        return render(request, 'player_statistics.html', {'players': players, **match_type_context(request, match_type, stats=True, by_type=True)})

    # Solo jugadores del club activo: los de otros clubes dan 404
    player = get_object_or_404(Player, public_id=player_id, club=request.club)

    # Chips de temporada: todas las del club
    all_seasons = sorted(get_total_season(Match.objects.filter(club=request.club)),
                         key=lambda s: int(s.split('-')[0]), reverse=True)
    log = build_game_log(player, match_type)
    # Sin las temporadas anteriores a su incorporación (salvo que haya jugado en ellas)
    played_seasons = {g['season'] for g in build_game_log(player)}
    all_seasons = [s for s in all_seasons if joined_by(player.joined_season, s) or s in played_seasons]
    selected_season = choose_season(request, all_seasons)
    if selected_season == ALL_SEASONS:
        selected_season = None

    # Resumen y afinidad siguen la temporada elegida; la evolución por temporadas usa siempre el registro completo.
    season_log = [g for g in log if g['season'] == selected_season] if selected_season else log
    summary = summarize(season_log)
    player_numbers = by_game_number(season_log)
    calls_present, calls_total = calls_by_season(player, match_type)
    rows = summarize_by_season(log, calls_present, calls_total)
    aligned = aligned_by_season(player, match_type)
    for r in rows:
        r['aligned'] = aligned.get(r['season'], 0)
    only = (lambda d: {k: v for k, v in d.items() if k == selected_season}) if selected_season else (lambda d: d)
    lineup_rate = lineup_summary(only(calls_present), only(aligned))
    signup_rate = signup_summary(only(calls_present), only(calls_total))

    # Detalle de la temporada elegida
    detail = None
    if selected_season:
        detail = summarize(season_log)
        present = calls_present.get(selected_season, 0)
        total = calls_total.get(selected_season, 0)
        detail.update({
            'calls_present': present,
            'calls_total': total,
            'calls_absent': total - present,
            'aligned': aligned.get(selected_season, 0),
        })

    # Puntos SNP de la temporada elegida (o de la actual), uno por actualización semanal
    snp_season = selected_season or current_season()
    snp_history = list(player.snp_history.filter(season=snp_season))

    clutch = set_stats(season_log)
    affinity = degree_of_affinity(player, match_type, selected_season)
    is_me = bool(player.user_id and player.user_id == request.user.id)
    context = {
        'hero': {
            'role': player_card.role_label(player),
            'partner': player_card.usual_partner(affinity),
            'snp_score': player.snp_score,
            'snp_rank': player_card.snp_rank(player),
            'is_me': is_me,
            # Advertencias: solo las ve quien gestiona el equipo.
            'warnings': player.penalties.count() if request.membership.can_manage else 0,
        },
        'league': player_card.league_rounds(player, selected_season),
        'snp_seasons': player_card.snp_by_season(player),
        'affinity_top': [a for a in affinity if a['in_team']][:5],
        **match_type_context(request, match_type, stats=True, by_type=True),
        **season_filter_context(request, all_seasons, selected_season),
        'players': players,
        'selected_player': player.public_id,
        'player': player,
        'seasons': all_seasons,
        'selected_season': selected_season,
        's': summary,
        'd': detail,
        'games': season_games(player, selected_season, match_type),
        'seasons_asc': rows,
        'seasons_desc': list(reversed(rows)),
        'chart_seasons': {
            'labels': [r['season'] for r in rows],
            'wins': [r['wins'] for r in rows],
            'losses': [r['losses'] for r in rows],
            'pct': [r['pct'] for r in rows],
        },
        # enteros para anchos de barra (evita comas decimales en style="")
        'pct_w': round(summary['pct']),
        'local_pct_w': round(summary['local_pct']),
        'visiting_pct_w': round(summary['visiting_pct']),
        'chart_affinity': affinity,
        'lineup_rate': lineup_rate,
        'signup_rate': signup_rate,
        'game_numbers': player_numbers,
        'clutch': clutch,
        'clutch_rows': [(label, desc, clutch[key]) for key, label, desc in SET_SITUATIONS],
        'snp_season': snp_season,
        'chart_snp': {
            'labels': [h.date.strftime('%d/%m') for h in snp_history],
            'scores': [h.score for h in snp_history],
            # variación de cada punto respecto al anterior (None en el primero)
            'changes': [None] + [round(b.score - a.score, 1) for a, b in zip(snp_history, snp_history[1:])],
        },
    }
    # Su propio jugador, con jugador en varias competiciones: es «Mis estadísticas» de esta competición.
    if is_me:
        mine = spaces.linked_players(request)
        if len(mine) > 1:
            context.update(mine_chips(request, mine, request.club.competition))
    return render(request, 'player_statistics.html', context)


# ---------------------------------------------------------------
# ESTADÍSTICAS POR PAREJAS
# ---------------------------------------------------------------

@spaces.consult_view
@club_required
@require_GET
def statistics_per_pair(request):
    """
    Estadísticas por parejas: mejores y peores parejas del club y, con ``?p1=`` y ``?p2=``,
    el detalle de esa pareja y sus últimos partidos. Filtra por temporada (``?season=``) y tipo de
    partido. Un jugador de otro club da 404. Requiere pertenecer al club y solo GET.
    """
    # Con una pareja elegida (?p1=&p2=) se sigue validando que sean del club (404 si no).
    zero = None if request.GET.get('p1') or request.GET.get('p2') else _zero_state(request, _("Estadísticas por parejas"))
    if zero:
        return zero
    club_players = list(Player.objects.filter(club=request.club).order_by('name', 'last_name'))
    by_public_id = {p.public_id: p for p in club_players}
    match_type = stats_match_type(request)
    seasons = sorted(get_total_season(Match.objects.filter(club=request.club)),
                     key=lambda s: int(s.split('-')[0]), reverse=True)
    selected_season = choose_season(request, seasons)
    if selected_season == ALL_SEASONS:
        selected_season = None
    min_games_pair = pair_stats.min_games_pair(match_type)
    log = pair_stats.club_game_log(request.club, selected_season, match_type)
    best_pairs, worst_pairs = pair_stats.best_and_worst_pairs(pair_stats.all_pairs(log, club_players), min_games=min_games_pair)

    p1_id, p2_id = request.GET.get('p1', ''), request.GET.get('p2', '')
    context = {
        **match_type_context(request, match_type, stats=True),
        **season_filter_context(request, seasons, selected_season),
        'selected_season': selected_season,
        'players': club_players,
        'best_pairs': best_pairs,
        'worst_pairs': worst_pairs,
        'min_games_pair': min_games_pair,
        'worst_min_games': pair_stats.IMPROVE_MIN_GAMES_PAIR,
        'selected_p1': p1_id or None,
        'selected_p2': p2_id or None,
    }

    if context['selected_p1'] and context['selected_p2']:
        # Solo jugadores del club activo: los de otros clubes dan 404
        p1, p2 = by_public_id.get(context['selected_p1']), by_public_id.get(context['selected_p2'])
        if p1 is None or p2 is None:
            raise Http404("Jugador no encontrado")
        if p1 == p2:
            context['error'] = _("Elige dos jugadores distintos.")
        else:
            summary = pair_stats.pair_summary(log, p1.id, p2.id)
            pair_log = [g for g in log if g['pair'] == pair_stats.pair_key(p1.id, p2.id)]
            pair_sets = set_stats(pair_log)
            numbers = Counter(g['n_game'] for g in pair_log)
            context.update({
                'usual_number': numbers.most_common(1)[0][0] if numbers else None,
                'set_rows': [(label, desc, pair_sets[key]) for key, label, desc in SET_SITUATIONS],
                'p1': p1,
                'p2': p2,
                's': summary,
                'last_games': pair_last_games(request.club, p1, p2, match_type=match_type, season=selected_season),
                # Con una temporada elegida, «Detalle por temporada» lista todos los partidos de la pareja en ella.
                'season_games': (pair_last_games(request.club, p1, p2, n=None, match_type=match_type, season=selected_season)
                                 if selected_season else None),
                'pair_sets': pair_sets,
                'pct_w': round(summary['pct']),
                'local_pct_w': round(summary['local_pct']),
                'visiting_pct_w': round(summary['visiting_pct']),
                'chart_seasons': {
                    'labels': [r['season'] for r in summary['seasons']],
                    'wins': [r['wins'] for r in summary['seasons']],
                    'losses': [r['losses'] for r in summary['seasons']],
                    'pct': [r['pct'] for r in summary['seasons']],
                },
            })

    return render(request, 'pair_statistics.html', context)


PAIR_LAST_GAMES = 5


def pair_last_games(club, p1, p2, n=PAIR_LAST_GAMES, match_type=None, season=None):
    """
    Últimos `n` partidos (Game) cerrados de la pareja en el club (de una temporada si se indica), del más reciente al más antiguo.
    Cada elemento: {'match_id', 'match_public_id', 'n_game', 'date', 'season', 'rival', 'local', 'sets', 'type_label', 'round', 'won', 'points'}
    """
    together = (
        Q(player_1_local=p1, player_2_local=p2) | Q(player_1_local=p2, player_2_local=p1) |
        Q(player_1_visiting=p1, player_2_visiting=p2) | Q(player_1_visiting=p2, player_2_visiting=p1)
    )
    games = (
        Game.objects
        .filter(together, draft_mode=False, match__draft_mode=False, winner__in=outcomes.WINNERS, match__club=club,
                **pair_stats.match_type_lookup(match_type, prefix='match__'))
        .select_related('match__local', 'match__visiting', 'match__club')
        .prefetch_related('results')
        .order_by('-match__start_date', '-match_id', '-n_game')
    )
    if season:
        games = games.filter(match__season=season)
    games = games[:n] if n else games
    rows = []
    for g in games:
        is_local = p1.id in (g.player_1_local_id, g.player_2_local_id)
        won = (g.winner == outcomes.WINNER_LOCAL) == is_local
        rows.append({
            'match_id': g.match_id,
            'match_public_id': g.match.public_id,
            'n_game': g.n_game,
            'date': g.match.start_date,
            'season': g.match.season,
            'rival': g.match.visiting_name if is_local else g.match.local_name,
            'local': is_local,
            'sets': _sets_text(g, is_local),
            'won': won,
            'points': (g.score or 0) if won else 0,
        })
    return rows


# ---------------------------------------------------------------
# ADVERTENCIAS (solo capitanes)
# ---------------------------------------------------------------



@spaces.managed_consult_view
@club_manager_required
@require_GET
def warnings_statistics(request):
    """
    Advertencias del club por jugador y su ranking. Solo capitán y gestores, y solo de los equipos que
    gestionan (``spaces.managed_consult_view``: con rol mixto se abre el equipo que gestiona y el
    selector de competición solo ofrece esos). Solo GET. Sin
    ``?season=`` muestra la temporada actual; ``?season=all``, todas.
    """
    penalties = (
        Penalty.objects
        .filter(player__club=request.club, call__match__club=request.club)
        .select_related('player', 'call__match__local', 'call__match__visiting')
        .order_by('-call__match__start_date', '-id')
    )

    seasons = set(penalties.values_list('call__match__season', flat=True)) | {current_season()}
    seasons = sorted((x for x in seasons if x and x != "NONE"), reverse=True)
    selected_season = choose_season(request, seasons)
    if selected_season != ALL_SEASONS:
        penalties = penalties.filter(call__match__season=selected_season)
    penalties = list(penalties)

    by_player = {}
    for pen in penalties:
        row = by_player.setdefault(pen.player_id, {'player': pen.player, 'count': 0, 'items': []})
        row['count'] += 1
        row['items'].append(pen)
    ranking = sorted(by_player.values(), key=lambda r: (-r['count'], r['player'].name, r['player'].last_name))
    kinds = Counter(pen.kind for pen in penalties)
    top_kind = max(kinds.values(), default=0)
    by_kind = [{'label': label, 'count': kinds.get(code, 0),
                'pct': round(100 * kinds.get(code, 0) / top_kind) if top_kind else 0}
               for code, label in PENALTY_KINDS]

    return render(request, 'warnings_statistics.html', {
        'by_kind': by_kind,
        **season_filter_context(request, seasons, selected_season, all_value=ALL_SEASONS),
        'seasons': seasons,
        'selected_season': selected_season,
        'all_seasons': ALL_SEASONS,
        'penalties': penalties,
        'ranking': ranking,
        'total': len(penalties),
        'players_warned': len(by_player),
        'matches_warned': len({p.call.match_id for p in penalties}),
    })


# ---------------------------------------------------------------
# RIVALES: cara a cara por rival
# ---------------------------------------------------------------
RIVALS_PER_PAGE = 15
HISTORY_PER_PAGE = 10


def _rival_query(row):
    """Parte de la URL (``team=…`` o ``name=…``) que identifica a un rival en su ficha."""
    team = row["team"]
    return urlencode({"team": team.public_id}) if team else urlencode({"name": row["label"]})


def _season_and_type(request, with_type):
    """
    (temporadas, temporada elegida o None para «Todas», filtro de tipo de partido) de la URL, con los
    mismos valores por defecto que el resto de Estadísticas: la temporada común (``choose_season``) y
    Competitivos; ``with_type`` False ignora el filtro de tipo.
    """
    seasons = sorted(get_total_season(Match.objects.filter(club=request.club)),
                     key=lambda s: int(s.split('-')[0]), reverse=True)
    selected = choose_season(request, seasons)
    return seasons, (None if selected == ALL_SEASONS else selected), (stats_match_type(request) if with_type else None)


@spaces.consult_view
@club_required
@require_GET
def rival_statistics(request):
    """
    Balance contra cada rival (enfrentamientos jugados, ganados, empatados y perdidos, puntos y último
    resultado), con la temporada y el tipo por defecto del resto de Estadísticas (temporada común y
    Competitivos: los amistosos no se mezclan salvo ``?match_type=todos``). Se ordena con ``?sort=`` (rival,
    balance o último), se busca por nombre con ``?q=`` y se pagina de 15 en 15. Requiere pertenecer al club y
    solo GET.
    """
    zero = _zero_state(request, _("Estadísticas por rival"))
    if zero:
        return zero
    seasons, selected_season, match_type = _season_and_type(request, with_type=True)
    sort = request.GET.get("sort")
    sort = sort if sort in rival_stats.SORTS else rival_stats.SORT_RIVAL
    search = (request.GET.get("q") or "").strip()
    rows = rival_stats.rival_summary(request.club, selected_season, match_type, sort)
    if search:
        rows = [r for r in rows if search.casefold() in r["label"].casefold()]
    for row in rows:
        row["query"] = _rival_query(row)
        row["balance"] = row["won"] - row["lost"]
    page = Paginator(rows, RIVALS_PER_PAGE).get_page(request.GET.get(PAGE_PARAM))
    keep = request.GET.copy()
    keep.pop(PAGE_PARAM, None)
    sort_links = []
    for value, label in ((rival_stats.SORT_RIVAL, _("Rival")), (rival_stats.SORT_BALANCE, _("Balance")),
                         (rival_stats.SORT_LAST, _("Último enfrentamiento"))):
        params = keep.copy()
        params["sort"] = value
        sort_links.append({"label": label, "url": f"{request.path}?{params.urlencode()}", "active": value == sort})
    return render(request, "rival_statistics.html", {
        **match_type_context(request, match_type, stats=True),
        **season_filter_context(request, seasons, selected_season),
        "selected_season": selected_season,
        "rivals": page,
        "sort_links": sort_links,
        "page_extra": ("&" + keep.urlencode()) if keep else "",
        "total_rivals": len(rows),
        "search": search,
        "season_keep_fields": [(k, v) for k, v in keep.items() if k in ("season", "sort", MATCH_TYPE_PARAM)],
    })


@spaces.consult_view
@club_required
@require_GET
def rival_detail(request):
    """
    Ficha de un rival: balance, historial de enfrentamientos (con enlace a cada acta) y mejores parejas
    contra él. El rival es un equipo (``?team=<id público>``) o, en un amistoso con rival escrito a
    mano, su nombre (``?name=``). Un equipo de otro club da 404. Filtra por temporada y por tipo de partido
    (por defecto la temporada común y Competitivos, como Rivales) y pagina el historial de 10 en 10.
    """
    team = None
    name = (request.GET.get("name") or "").strip()
    if request.GET.get("team"):
        team = get_object_or_404(Team, public_id=request.GET["team"], club=request.club)
    elif not name:
        raise Http404("Rival no indicado")
    seasons, selected_season, match_type = _season_and_type(request, with_type=True)
    players = list(Player.objects.filter(club=request.club))
    detail = rival_stats.rival_detail(request.club, players, team, name, selected_season, match_type)
    keep = request.GET.copy()
    keep.pop(PAGE_PARAM, None)
    history = Paginator(detail["history"], HISTORY_PER_PAGE).get_page(request.GET.get(PAGE_PARAM)) if detail else None
    return render(request, "rival_detail.html", {
        **match_type_context(request, match_type, stats=True),
        **season_filter_context(request, seasons, selected_season),
        "selected_season": selected_season,
        "detail": detail,
        "history": history,
        "page_extra": ("&" + keep.urlencode()) if keep else "",
        "rival_label": detail["label"] if detail else (team.name if team else name),
        "team": team,
        "min_games_pair": pair_stats.MIN_GAMES_PAIR,
    })
