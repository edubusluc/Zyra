"""``GET /api/v1/teams/<id>/stats/team``: «Estadísticas · Equipo» para la pantalla nativa (solo lectura).

No calcula nada: junta lo que ya calculan las funciones de ``data_analyse`` (las mismas que la web) y lo entrega como JSON.
La web guarda la temporada elegida en la sesión; aquí la temporada y el tipo van siempre en la petición (``season``,
``match_type``) y, sin ``season``, vale la temporada actual si el equipo tiene partidos en ella y, si no, «todas».
"""
from collections import Counter
from types import SimpleNamespace

from django.http import Http404
from django.utils.translation import gettext as _, ngettext

from core.season_choice import ALL_SEASONS
from data_analyse import comparison, pairs as pair_stats, player_card, records, rivals as rival_stats, roster_table, team_card
from data_analyse.attendance import signup_attendance
from data_analyse.sets import by_game_number, set_stats
from core.spaces import player_history
from data_analyse.views import (ALL_TYPES, COMPETITIVE, _squad_compare, aligned_by_season, build_game_log, degree_of_affinity,
                                lineup_summary, PAIR_LAST_GAMES, pair_last_games, season_games, summarize_by_season, calculate_match_statistics, calculate_tiebreak_stats,
                                calls_by_season, column_chart, format_for_chart, get_total_season, players_charts,
                                signup_summary, summarize)
from match.models import Match
from players.models import Player, current_season, joined_by
from team.models import Team

from .errors import ApiError
from .responses import json_ok
from .teams import active_memberships, membership_for_team
from .views_base import ApiView


def _filters(request, seasons, default_all=False):
    """(temporada elegida o None para «todas», tipo de partido o None para «todos») según los parámetros de la petición.

    Sin ``season``, vale la actual si hay partidos en ella y, si no, «todas» (o siempre «todas» con ``default_all``)."""
    asked = request.GET.get("season")
    if asked == ALL_SEASONS:
        season = None
    elif asked in seasons:
        season = asked
    elif asked:
        raise ApiError("invalid", _("Temporada no válida."), 400)
    else:
        season = None if default_all else (current_season() if current_season() in seasons else None)
    kind = request.GET.get("match_type", COMPETITIVE)
    if kind == ALL_TYPES:
        kind = None
    elif kind not in pair_stats.FILTER_VALUES:
        raise ApiError("invalid", _("Tipo de partido no válido."), 400)
    return season, kind


def _player(p):
    """Jugador resumido: identificador público y nombre corto."""
    return {"id": str(p.public_id), "name": p.short_name}


def _snp(ranking):
    """Ranking SNP del equipo sin modelos: filas con su jugador, media, fecha de actualización y gráfico."""
    rows = [{**{k: v for k, v in r.items() if k != "player"}, "player": _player(r["player"])} for r in ranking["rows"]]
    riser = ranking["riser"]
    return {"rows": rows, "average": ranking["average"], "updated": ranking["updated"], "stale": ranking["stale"],
            "chart": ranking["chart"], "riser": {**{k: v for k, v in riser.items() if k != "player"},
                                                 "player": _player(riser["player"])} if riser else None}


def _roster(club, log, season, kind, params, snp):
    """Tabla de plantilla con los mismos criterios que la web (``lado`` y ``orden``); sin paginar, cabe una plantilla."""
    has_snp = club.rules.has_snp
    side, sort = roster_table.parse_options(params, has_snp)
    squad = list(Player.objects.filter(club=club, in_team=True))
    signup = roster_table.signup_by_player(club, squad, season, kind, side)
    snp_rows = {r["player"].id: r for r in (snp or {}).get("rows", [])}
    rows = roster_table.roster_rows(squad, log, signup, side, sort, snp_rows)
    return {"side": side, "sort": sort, "has_snp": has_snp, "min_games": roster_table.MIN_RANKED_GAMES,
            "rows": [{**{k: v for k, v in r.items() if k != "player"}, "player": _player(r["player"])} for r in rows]}


class TeamStatsView(ApiView):
    """Estadísticas del equipo de la cuenta: balance, puntos, sets, récords, plantilla y puntos SNP. Lleva ``ETag``."""
    etag = True

    def get(self, request, team_id):
        """Responde ``filters`` (opciones y elegidas), ``has_matches`` y, si hay partidos cerrados, las tarjetas."""
        membership = membership_for_team(request.user, team_id)
        club = membership.club
        team = club.own_team
        matches = Match.objects.filter(club=club, draft_mode=False)
        seasons = sorted(get_total_season(matches), key=lambda s: int(s.split("-")[0]), reverse=True)
        season, kind = _filters(request, seasons)
        data = {
            "filters": {"seasons": seasons, "season": season or ALL_SEASONS, "match_type": kind or ALL_TYPES,
                        "match_types": [ALL_TYPES, COMPETITIVE, Match.AMISTOSO]},
            "has_matches": bool(seasons),
        }
        if not seasons or team is None:
            return json_ok(data)

        total, won, drawn, lost, pct, _d, _l = calculate_match_statistics(season, team, kind)
        log = pair_stats.club_game_log(club, season, kind)
        sets = set_stats(log)
        snp = records.snp_ranking(club, season or current_season())
        data.update({
            "balance": {"total": total, "won": won, "drawn": drawn, "lost": lost, "won_pct": pct},
            "tiebreaks": calculate_tiebreak_stats(season, team, kind),
            "pairs_chart": format_for_chart(column_chart(club, season, kind)) if club.rules.ordered_pairs else [],
            "game_numbers": by_game_number(log),
            "sets": sets,
            "set_rows": [{"label": str(label), "hint": str(hint), **situation}
                         for label, hint, situation in comparison.set_situation_rows(sets)],
            "records": records.team_records(club, season, kind, log),
            "form": team_card.form_and_streak(club, season, kind),
            "league": team_card.league_summary(club, season or current_season()),
            # Como la web: la elegibilidad es de la temporada en curso (solo sin temporada elegida o con la actual).
            "finals": team_card.finals_roster(club, current_season()) if season in (None, current_season()) else None,
            "points": team_card.points_series(club, season, kind),
            "venue": team_card.venue_matches(club, season, kind),
            "walkovers": team_card.walkovers(club, season, kind),
            "attendance": signup_attendance(club, season, kind),
            "snp": _snp(snp),
            "roster": _roster(club, log, season, kind, request.GET, snp),
        })
        return json_ok(data)


class MyStatsView(ApiView):
    """
    ``GET /api/v1/me/stats``: «Yo» (Mis estadísticas): lo de la persona en todas sus fichas, las de sus equipos actuales y las
    de equipos en los que ya no está. ``state`` es ``no_player`` sin ninguna ficha enlazada. Filtros ``season`` y ``match_type``
    como en Equipo. Lleva ``ETag``.
    """
    etag = True

    def get(self, request):
        """``filters``, ``state``, ``headline``, ``me`` (cifras de todas las fichas), ``players`` (una fila por ficha) y ``charts``."""
        active, suspended = active_memberships(request.user)
        players = player_history(request.user, {m.club_id for m in active}, {c.id for c in suspended})
        clubs = [p.club for p in players]
        seasons = sorted(get_total_season(Match.objects.filter(club__in=clubs, draft_mode=False)),
                         key=lambda s: int(s.split("-")[0]), reverse=True)
        season, kind = _filters(request, seasons)
        data = {"filters": {"seasons": seasons, "season": season or ALL_SEASONS, "match_type": kind or ALL_TYPES,
                            "match_types": [ALL_TYPES, COMPETITIVE, Match.AMISTOSO]},
                "state": "ok" if players else "no_player"}
        if not players:
            return json_ok(data)

        rows, logs, all_log = [], [], []
        for player in players:
            log = [g for g in build_game_log(player, kind) if not season or g["season"] == season]
            logs.append(log)
            all_log += log
            summary = summarize(log)
            present, total = calls_by_season(player, kind)
            if season:
                present, total = {season: present.get(season, 0)}, {season: total.get(season, 0)}
            rows.append({"player_id": str(player.public_id), "team_id": str(player.club.public_id), "club": player.club.name,
                         "competition": player.club.competition, "competition_name": str(player.club.rules.name),
                         "former": player.is_former, "kind": player.history_kind, "played": summary["played"],
                         "wins": summary["wins"], "losses": summary["losses"], "pct": round(summary["pct"]),
                         "calls": signup_summary(present, total)})
        me = summarize(all_log)
        teams = len({p.club_id for p in players if not p.is_former})
        data.update({
            "headline": ngettext("Llevas %(wins)s de %(played)s partido ganado.", "Llevas %(wins)s de %(played)s partidos ganados.",
                                 me["played"]) % {"wins": me["wins"], "played": me["played"]} if me["played"] else None,
            "teams": teams,
            "single_player": rows[0]["player_id"] if len(rows) == 1 else None,
            "me": {key: me[key] for key in ("played", "wins", "losses", "pct", "form", "streak_type", "streak_len",
                                            "best_win_streak")},
            "players": rows,
            "charts": players_charts(players, logs, season, kind),
        })
        return json_ok(data)


class PlayerStatsView(ApiView):
    """
    ``GET /api/v1/teams/<id>/stats/players/<player_id>``: la ficha de un jugador de la plantilla (la de «Yo» cuando es el propio
    jugador). Filtros ``season`` y ``match_type`` como en Equipo; sin ``season`` vale «todas» (la ficha enseña la evolución).
    Junta lo que calcula ``_player_page`` en la web: cabecera, cifras, temporadas, sets, reparto por partido, convocatorias,
    compañeros, «Frente a la plantilla», puntos SNP y los partidos jugados. Lleva ``ETag``.
    """
    etag = True

    def get(self, request, team_id, player_id):
        """``filters``, ``hero``, ``summary``, ``seasons``, ``trend``, ``set_rows``, ``game_numbers``, ``signup``, ``lineup``, ``partners``, ``squad``, ``snp`` y ``games``."""
        membership = membership_for_team(request.user, team_id)
        club = membership.club
        player = Player.objects.filter(public_id=player_id, club=club).first()
        if player is None:
            raise Http404("Jugador no encontrado")
        squad = list(Player.objects.filter(club=club, in_team=True).order_by("name", "last_name"))
        seasons_all = sorted(get_total_season(Match.objects.filter(club=club, draft_mode=False)),
                             key=lambda s: int(s.split("-")[0]), reverse=True)
        played = {g["season"] for g in build_game_log(player)}
        seasons = [s for s in seasons_all if s in played or joined_by(player.joined_season, s)]
        asked = request.GET.get("season")
        if asked and asked != ALL_SEASONS and asked not in seasons_all:
            raise ApiError("invalid", _("Temporada no válida."), 400)
        # Una temporada del club en la que el jugador aún no estaba equivale a «todas» (la app comparte filtros con «Yo»).
        season = asked if asked in seasons else None
        _s, kind = _filters(request, seasons or [None])
        log = build_game_log(player, kind)
        season_log = [g for g in log if g["season"] == season] if season else log
        present, total = calls_by_season(player, kind)
        rows = summarize_by_season(log, present, total)
        aligned = aligned_by_season(player, kind)
        for r in rows:
            r["aligned"] = aligned.get(r["season"], 0)
        only = (lambda d: {k: v for k, v in d.items() if k == season}) if season else (lambda d: d)
        affinity = degree_of_affinity(player, kind, season)
        snp_updated = player.snp_history.order_by("-date").values_list("date", flat=True).first()
        is_me = request.user.id in (player.user_id, player.past_user_id)
        summary = summarize(season_log)
        clutch = set_stats(season_log)
        games = season_games(player, season, kind)
        data = {
            "filters": {"seasons": seasons, "season": season or ALL_SEASONS, "match_type": kind or ALL_TYPES,
                        "match_types": [ALL_TYPES, COMPETITIVE, Match.AMISTOSO]},
            "hero": {"id": str(player.public_id), "name": player.full_name, "role": str(player_card.role_label(player)),
                     "position": player.get_position_display(), "hand": player.get_skillfull_hand_display(),
                     "joined_season": player.joined_season, "partner": player_card.usual_partner(affinity),
                     "competition": club.competition, "has_snp": club.rules.has_snp, "snp_score": player.snp_score,
                     "snp_rank": player_card.snp_rank(player), "snp_updated": snp_updated,
                     "snp_stale": records.snp_is_stale(snp_updated), "is_me": bool(is_me)},
            "summary": {k: summary[k] for k in ("played", "wins", "losses", "pct", "points", "points_possible", "streak_type",
                                                "streak_len", "best_win_streak", "worst_loss_streak", "local_played",
                                                "local_wins", "local_losses", "visiting_played", "visiting_wins",
                                                "visiting_losses")},
            "form": [g["won"] for g in season_log][-5:],
            "league": player_card.league_rounds(player, season),
            "finals": player_card.league_rounds(player, current_season()),
            "seasons": rows,
            "trend": comparison.trend(rows),
            "snp_seasons": player_card.snp_by_season(player),
            "signup": signup_summary(only(present), only(total)),
            "lineup": lineup_summary(only(present), only(aligned)),
            "game_numbers": by_game_number(season_log),
            "set_rows": [{"label": str(label), "hint": str(hint), **situation}
                         for label, hint, situation in comparison.set_situation_rows(clutch)],
            "partners": [{"id": a.get("public_id") and str(a["public_id"]), "name": a["name"], "games": a["games"],
                          "wins": a["wins"], "losses": a["losses"], "pct": a["pct"]}
                         for a in comparison.partner_rows(affinity)],
            "squad": _squad_compare(SimpleNamespace(club=club), player, squad, season, kind, bool(is_me))
            if player in squad else None,
            "games": [{"match_id": str(g["match_public_id"]), "n_game": g["n_game"], "date": g["date"], "rival": g["rival"],
                       "local": g["local"], "neutral": g["neutral"], "partner": g["partner"].short_name if g["partner"] else None,
                       "sets": g["sets"], "won": g["won"], "points": g["points"]} for g in games],
        }
        return json_ok(data)


def _pair_row(row):
    """Fila de ``pairs.all_pairs`` sin modelos: los dos jugadores resumidos y el balance."""
    return {"p1": _player(row["p1"]), "p2": _player(row["p2"]), **{k: row[k] for k in ("played", "wins", "losses", "pct")}}


def _club_filters(club, request, default_all=False):
    """(``filters``, temporada, tipo) de las pantallas de parejas, con las temporadas con enfrentamientos cerrados del club."""
    seasons = sorted(get_total_season(Match.objects.filter(club=club, draft_mode=False)),
                     key=lambda s: int(s.split("-")[0]), reverse=True)
    season, kind = _filters(request, seasons, default_all)
    return {"seasons": seasons, "season": season or ALL_SEASONS, "match_type": kind or ALL_TYPES,
            "match_types": [ALL_TYPES, COMPETITIVE, Match.AMISTOSO]}, season, kind


class PairsStatsView(ApiView):
    """
    ``GET /api/v1/teams/<id>/stats/pairs``: «Estadísticas · Parejas», todas las parejas que han jugado juntas. Filtros
    ``season`` y ``match_type`` como en Equipo y ``sort`` (``comparison.PAIR_SORTS``; por defecto, más partidos). Sin
    paginar: la búsqueda por nombre la hace la app. ``best`` y ``worst`` son las destacadas de la web. Lleva ``ETag``.
    """
    etag = True

    def get(self, request, team_id):
        """``filters``, ``has_matches``, ``sort``, ``min_games``, ``best``, ``worst`` y ``rows``."""
        club = membership_for_team(request.user, team_id).club
        filters, season, kind = _club_filters(club, request)
        sort = request.GET.get("sort")
        sort = sort if sort in comparison.PAIR_SORTS else comparison.PAIR_SORT_PLAYED
        data = {"filters": filters, "has_matches": bool(filters["seasons"]), "sort": sort,
                "sorts": list(comparison.PAIR_SORTS)}
        if not filters["seasons"]:
            return json_ok(data)
        players = list(Player.objects.filter(club=club).order_by("name", "last_name"))
        pairs = pair_stats.all_pairs(pair_stats.club_game_log(club, season, kind), players)
        min_games = pair_stats.min_games_pair(kind)
        best, worst = pair_stats.best_and_worst_pairs(pairs, min_games=min_games)
        data.update({"min_games": min_games, "best": [_pair_row(r) for r in best], "worst": [_pair_row(r) for r in worst],
                     "rows": [_pair_row(r) for r in comparison.sort_pairs(pairs, sort)]})
        return json_ok(data)


class PairStatsView(ApiView):
    """
    ``GET /api/v1/teams/<id>/stats/pairs/<p1_id>/<p2_id>``: la ficha de una pareja (lo que la web enseña con ``?p1=&p2=``).
    Filtros ``season`` y ``match_type``; sin ``season`` vale «todas». Dos jugadores iguales dan 400 y uno que no es del club, 404.
    Con una temporada elegida ``games`` lista todos los partidos de la pareja en ella y, si no, los últimos. Lleva ``ETag``.
    """
    etag = True

    def get(self, request, team_id, p1_id, p2_id):
        """``filters``, ``p1``, ``p2``, ``compact``, ``usual_number``, ``summary``, ``form``, ``seasons``, ``trend``, ``set_rows``, ``venue`` y ``games``."""
        club = membership_for_team(request.user, team_id).club
        by_public_id = {str(p.public_id): p for p in Player.objects.filter(club=club)}
        p1, p2 = by_public_id.get(p1_id), by_public_id.get(p2_id)
        if p1 is None or p2 is None:
            raise Http404("Jugador no encontrado")
        if p1 == p2:
            raise ApiError("invalid", _("Elige dos jugadores distintos."), 400)
        filters, season, kind = _club_filters(club, request, default_all=True)
        log = pair_stats.club_game_log(club, season, kind)
        summary = pair_stats.pair_summary(log, p1.id, p2.id)
        pair_log = [g for g in log if g["pair"] == pair_stats.pair_key(p1.id, p2.id)]
        numbers = Counter(g["n_game"] for g in pair_log)
        games = pair_last_games(club, p1, p2, n=None if season else PAIR_LAST_GAMES, match_type=kind, season=season)
        data = {
            "filters": filters,
            "p1": _player(p1), "p2": _player(p2),
            "compact": summary["played"] < comparison.MIN_PAIR_SHEET_GAMES,
            "min_trend_games": comparison.MIN_TREND_GAMES,
            "usual_number": numbers.most_common(1)[0][0] if numbers else None,
            "summary": {k: summary[k] for k in ("played", "wins", "losses", "pct", "points", "matches", "local_played",
                                                "local_wins", "local_losses", "visiting_played", "visiting_wins",
                                                "visiting_losses", "streak_type", "streak_len", "best_win_streak",
                                                "worst_loss_streak")},
            "form": summary["form"],
            "seasons": summary["seasons"],
            "trend": comparison.trend(summary["seasons"]),
            "set_rows": [{"label": str(label), "hint": str(hint), **situation}
                         for label, hint, situation in comparison.set_situation_rows(set_stats(pair_log))],
            "venue": comparison.venue_split({"won": summary["local_wins"], "lost": summary["local_losses"]},
                                            {"won": summary["visiting_wins"], "lost": summary["visiting_losses"]}, "games"),
            "games": [{"match_id": str(g["match_public_id"]), "n_game": g["n_game"], "date": g["date"], "season": g["season"],
                       "rival": g["rival"], "local": g["local"], "neutral": g["neutral"], "sets": g["sets"],
                       "won": g["won"], "points": g["points"]} for g in games],
        }
        return json_ok(data)


def _rival_ref(row):
    """Datos que identifican a un rival (equipo del grupo o nombre escrito a mano) sin modelos."""
    team = row["team"]
    return {"team_id": str(team.public_id) if team else None, "name": row["label"]}


def _rival_entry(e):
    """Una línea del historial de un rival sin el modelo ``Match``."""
    return {"match_id": str(e["match"].public_id), "date": e["date"], "season": e["season"], "outcome": e["outcome"],
            "own": e["own"], "other": e["other"], "local": e["local"], "neutral": e["neutral"], "friendly": e["friendly"],
            "type_label": str(e["type_label"]), "round": e["round"], "league_points": e["league_points"],
            "rival_no_show": e["rival_no_show"]}


def _rival_tally(row):
    """Balance de un rival (lista y ficha): enfrentamientos, puntos, forma y último resultado."""
    last = row["last"]
    return {**{k: row[k] for k in ("played", "won", "drawn", "lost", "pct", "points_for", "points_against", "league_points",
                                   "form")},
            "last": {k: last[k] for k in ("date", "outcome", "own", "other", "local")} if last else None}


class RivalsStatsView(ApiView):
    """
    ``GET /api/v1/teams/<id>/stats/rivals``: «Estadísticas · Rivales», el balance contra cada rival (lo mismo que la lista de
    la web). Filtros ``season`` y ``match_type`` como en Equipo y ``sort`` (``rival``, ``pct``, ``worst``, ``balance`` o ``last``).
    Sin paginar: la búsqueda por nombre la hace la app. Lleva ``ETag``.
    """
    etag = True

    def get(self, request, team_id):
        """``filters``, ``has_matches``, ``sort``, ``sorts`` y ``rows`` (cada rival con ``team_id`` o solo ``name``)."""
        club = membership_for_team(request.user, team_id).club
        filters, season, kind = _club_filters(club, request)
        sort = request.GET.get("sort")
        sort = sort if sort in rival_stats.SORTS else rival_stats.SORT_RIVAL
        data = {"filters": filters, "has_matches": bool(filters["seasons"]), "sort": sort, "sorts": list(rival_stats.SORTS)}
        if filters["seasons"]:
            data["rows"] = [{**_rival_ref(r), "friendly_only": r["friendly_only"], **_rival_tally(r)}
                            for r in rival_stats.rival_summary(club, season, kind, sort)]
        return json_ok(data)


class RivalStatsView(ApiView):
    """
    ``GET /api/v1/teams/<id>/stats/rival?team=<id público>`` (o ``?name=`` en un amistoso con rival escrito a mano): la ficha
    de un rival, con balance, historial y las mejores y peores parejas contra él (lo que enseña la web). Filtros ``season`` y
    ``match_type``. Un equipo que no es del club, 404; un rival sin enfrentamientos con esos filtros, ``detail`` nulo. Lleva ``ETag``.
    """
    etag = True

    def get(self, request, team_id):
        """``filters``, ``name``, ``team_id``, ``detail`` (balance, ``history``, ``pairs_best``, ``pairs_worst``) y ``min_games_pair``."""
        club = membership_for_team(request.user, team_id).club
        team, name = None, (request.GET.get("name") or "").strip()
        if request.GET.get("team"):
            team = Team.objects.filter(public_id=request.GET["team"], club=club).first()
            if team is None:
                raise Http404("Rival no encontrado")
        elif not name:
            raise ApiError("invalid", _("Falta el rival."), 400)
        filters, season, kind = _club_filters(club, request)
        detail = rival_stats.rival_detail(club, list(Player.objects.filter(club=club)), team, name, season, kind)
        data = {"filters": filters, "team_id": str(team.public_id) if team else None, "name": detail["label"] if detail else (team.name if team else name),
                "min_games_pair": pair_stats.MIN_GAMES_PAIR, "detail": None}
        if detail:
            pair = lambda r: {"p1": _player(r["p1"]), "p2": _player(r["p2"]), **{k: r[k] for k in ("played", "wins", "losses", "pct")}}  # noqa: E731
            data["detail"] = {**_rival_tally(detail), "history": [_rival_entry(e) for e in detail["history"]],
                              "pairs_best": [pair(r) for r in detail["pairs_best"]],
                              "pairs_worst": [pair(r) for r in detail["pairs_worst"]]}
        return json_ok(data)
