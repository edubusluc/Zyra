"""``GET /api/v1/matches``: la lista de Partidos de la app nativa (mismas reglas que ``match.views.list_match``)."""
import datetime

from django.core.paginator import EmptyPage, Paginator
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import gettext as _

from call.models import Call
from core.season_choice import ALL_SEASONS
from data_analyse.pairs import COMPETITIVE, FILTER_VALUES, match_type_lookup
from match import month_view, phase as match_phase
from match.models import Game, Match
from match.views import (LIST_HORIZON_DAYS, MATCHES_PER_PAGE, club_score, filter_by_rival, match_outcome, rival_names,
                         search_matches)
from players.models import current_season

from .responses import json_ok
from .teams import active_memberships, membership_for_team
from .views_home import _kind_label, _side, _team


def _match_types():
    """Opciones del filtro de tipo, como los chips de la web: todos, competitivos, amistosos y cada tipo."""
    options = [{"value": "", "label": _("Todos")}, {"value": COMPETITIVE, "label": _("Competitivos")}]
    options += [{"value": value, "label": str(label)} for value, label in Match.MATCH_TYPES]
    return options


def _row(match, *, today, managed, dual_role, called, pending_close, phase):
    """Una fila de la lista: lados, fecha, estado, marcador propio/rival y el grupo en el que va."""
    outcome = match_outcome(match)
    own, rival = club_score(match) if outcome else (None, None)
    can_manage = match.club_id in managed
    group = ("played" if not match.draft_mode else
             "action" if can_manage and (dual_role or match.start_date < today) else "upcoming")
    return {
        "id": str(match.public_id),
        "team_id": str(match.club.public_id),
        "competition": match.club.competition,
        "competition_name": match.club.rules.name,
        "kind_label": _kind_label(match),
        "match_type": match.match_type,
        "date": match.start_date.isoformat(),
        "time": match.start_time.strftime("%H:%M") if match.start_time else None,
        "location": match.location or None,
        "local": _side(match.local, match.local_name),
        "visiting": _side(match.visiting, match.visiting_name),
        "own_is_local": bool(match.own_is_local),
        "outcome": outcome,
        "own_points": own,
        "rival_points": rival,
        "called": called,
        "status_label": str(phase.label) if match.draft_mode else None,
        "pending_close": pending_close,
        "can_manage": can_manage,
        "group": group,
    }


def _rows(matches, *, today, managed, dual_role):
    """Las filas de ``matches`` (con convocados, acta por cerrar y fase de cada una: unas pocas consultas en total)."""
    called = dict(Call.objects.filter(match__in=matches).annotate(n=Count("players")).values_list("match_id", "n"))
    open_ids = [m.id for m in matches if m.draft_mode]
    games_count = dict(Game.objects.filter(match_id__in=open_ids).values("match_id").annotate(n=Count("id"))
                       .values_list("match_id", "n"))
    with_result = dict(Game.objects.filter(match_id__in=open_ids, results__isnull=False).values("match_id")
                       .annotate(n=Count("id", distinct=True)).values_list("match_id", "n"))
    phases = match_phase.phases_for(matches)
    rows = []
    for m in matches:
        n = games_count.get(m.id, 0)
        pending_close = bool(m.draft_mode and n >= m.club.rules.games and with_result.get(m.id, 0) == n)
        rows.append(_row(m, today=today, managed=managed, dual_role=dual_role, called=called.get(m.id),
                         pending_close=pending_close, phase=phases[m.id]))
    return rows


def _scope(request):
    """Equipos a mirar (``team`` o todos los de la cuenta): ``(todas las membresías, las elegidas, gestionados, doble rol)``."""
    all_active, _suspended = active_memberships(request.user)
    team_id = request.GET.get("team")
    active = [membership_for_team(request.user, team_id)] if team_id else all_active
    managed = {m.club_id for m in active if m.can_manage}
    dual_role = 0 < len({m.club_id for m in all_active if m.can_manage}) < len(all_active)
    return all_active, active, managed, dual_role


def calendar_matches(request):
    """
    ``GET /api/v1/matches/calendar``: los enfrentamientos de un mes, agrupados por día (como el calendario de la web).
    ``month`` (``AAAA-MM``; por defecto el actual) y ``team`` (opcional). Responde ``month``, ``prev``, ``next``,
    ``is_current``, ``today``, ``teams`` y ``days`` (solo los días con enfrentamientos: ``date`` y ``matches``, con la
    misma forma que en la lista), ordenados por hora.
    """
    today = timezone.localdate()
    first = month_view.parse_month(request.GET.get(month_view.MONTH_PARAM), today)
    all_active, active, managed, dual_role = _scope(request)
    by_day = month_view.month_events([m.club for m in active], month_view.month_weeks(first))
    flat = [m for d in sorted(by_day) if d.month == first.month for m in by_day[d]]
    rows = iter(_rows(flat, today=today, managed=managed, dual_role=dual_role))
    days = [{"date": d.isoformat(), "matches": [next(rows) for _ in by_day[d]]}
            for d in sorted(by_day) if d.month == first.month]
    return json_ok({
        "month": month_view.month_key(first),
        "prev": month_view.month_key(month_view.shift_month(first, -1)),
        "next": month_view.month_key(month_view.shift_month(first, 1)),
        "is_current": first == today.replace(day=1),
        "today": today.isoformat(),
        "teams": [_team(m) for m in all_active],
        "days": days,
    })


def list_matches(request):
    """
    ``GET /api/v1/matches``: enfrentamientos de los equipos de la cuenta (o de ``team``), ordenados como la web: primero lo
    que requiere acción, luego lo próximo y al final lo jugado. Parámetros: ``team`` (id; 404 si no es de la cuenta),
    ``season`` (``AAAA-AAAA`` o ``all``; por defecto la actual, ``all`` si se busca o se filtra por rival), ``match_type``
    (``competitivo`` o un tipo), ``rival`` (nombre exacto), ``q`` (equipo o lugar), ``all=1`` (también los abiertos a más de
    14 días; al buscar o filtrar por rival se ven siempre) y ``page`` (de 12 en 12).

    Responde ``teams``, ``seasons``, ``season``, ``rivals``, ``match_types``, ``summary`` (jugados, V, E, D, pendientes de
    lo filtrado), ``matches`` (cada uno con ``group``: ``action``, ``upcoming`` o ``played``), ``hidden_far`` (abiertos
    lejanos ocultos) y ``page``/``pages``.
    """
    all_active, active, managed, dual_role = _scope(request)
    clubs = [m.club for m in active]

    club_matches = Match.objects.filter(club__in=clubs).select_related("local", "visiting", "club")
    seasons = set(club_matches.values_list("season", flat=True)) | {current_season()}
    seasons = sorted((s for s in seasons if s and s != "NONE"), reverse=True)
    rivals = rival_names(club_matches)

    search = request.GET.get("q", "").strip()[:100]
    rival = request.GET.get("rival", "").strip()
    if rival not in rivals:
        rival = ""
    asked = request.GET.get("season")
    if asked == ALL_SEASONS or asked in seasons:
        season = asked
    elif search or rival:
        season = ALL_SEASONS
    else:
        season = current_season() if current_season() in seasons else ALL_SEASONS
    match_type = request.GET.get("match_type")
    match_type = match_type if match_type in FILTER_VALUES else None

    matches = club_matches
    if season != ALL_SEASONS:
        matches = matches.filter(season=season)
    matches = matches.filter(**match_type_lookup(match_type))
    if rival:
        matches = filter_by_rival(matches, rival)
    if search:
        matches = search_matches(matches, search)

    outcomes = [match_outcome(m) for m in matches]
    summary = {"played": sum(o is not None for o in outcomes), "won": outcomes.count("V"),
               "drawn": outcomes.count("E"), "lost": outcomes.count("D"), "pending": outcomes.count(None)}

    today = timezone.localdate()
    open_matches = matches.filter(draft_mode=True)
    show_all = request.GET.get("all") == "1" or bool(search or rival)
    upcoming_open = open_matches.filter(start_date__gte=today)
    hidden_far = 0
    if not show_all:
        horizon = today + datetime.timedelta(days=LIST_HORIZON_DAYS)
        hidden_far = upcoming_open.filter(start_date__gt=horizon).count()
        upcoming_open = upcoming_open.filter(start_date__lte=horizon)
    ordered = [*open_matches.filter(start_date__lt=today).order_by("start_date", "id"),
               *upcoming_open.order_by("start_date", "id"),
               *matches.filter(draft_mode=False).order_by("-start_date", "-id")]

    def rank(m):
        """0 acción, 1 próximos, 2 jugados (orden estable)."""
        return 2 if not m.draft_mode else 0 if m.club_id in managed and (dual_role or m.start_date < today) else 1

    ordered.sort(key=rank)
    paginator = Paginator(ordered, MATCHES_PER_PAGE)
    try:
        page = paginator.page(request.GET.get("page") or 1)
    except (EmptyPage, ValueError):
        page = paginator.page(paginator.num_pages if request.GET.get("page", "").isdigit() else 1)
    page_matches = list(page)

    rows = _rows(page_matches, today=today, managed=managed, dual_role=dual_role)
    return json_ok({
        "teams": [_team(m) for m in all_active],
        "seasons": seasons,
        "season": season,
        "rivals": rivals,
        "match_types": _match_types(),
        "match_type": match_type or "",
        "summary": summary,
        "matches": rows,
        "hidden_far": hidden_far,
        "page": page.number,
        "pages": paginator.num_pages,
        "can_create": bool(managed),
    })
