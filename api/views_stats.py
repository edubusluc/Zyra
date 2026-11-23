"""``GET /api/v1/teams/<id>/stats/team``: «Estadísticas · Equipo» para la pantalla nativa (solo lectura).

No calcula nada: junta lo que ya calculan las funciones de ``data_analyse`` (las mismas que la web) y lo entrega como JSON.
La web guarda la temporada elegida en la sesión; aquí la temporada y el tipo van siempre en la petición (``season``,
``match_type``) y, sin ``season``, vale la temporada actual si el equipo tiene partidos en ella y, si no, «todas».
"""
from django.utils.translation import gettext as _, ngettext

from core.season_choice import ALL_SEASONS
from data_analyse import comparison, pairs as pair_stats, records, roster_table, team_card
from data_analyse.attendance import signup_attendance
from data_analyse.sets import by_game_number, set_stats
from core.spaces import player_history
from data_analyse.views import (ALL_TYPES, COMPETITIVE, build_game_log, calculate_match_statistics, calculate_tiebreak_stats,
                                calls_by_season, column_chart, format_for_chart, get_total_season, players_charts,
                                signup_summary, summarize)
from match.models import Match
from players.models import Player, current_season

from .errors import ApiError
from .responses import json_ok
from .teams import active_memberships, membership_for_team
from .views_base import ApiView


def _filters(request, seasons):
    """(temporada elegida o None para «todas», tipo de partido o None para «todos») según los parámetros de la petición."""
    asked = request.GET.get("season")
    if asked == ALL_SEASONS:
        season = None
    elif asked in seasons:
        season = asked
    elif asked:
        raise ApiError("invalid", _("Temporada no válida."), 400)
    else:
        season = current_season() if current_season() in seasons else None
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
    return {"side": side, "sort": sort, "has_snp": has_snp,
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
