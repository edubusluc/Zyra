"""``GET /api/v1/home``: lo que necesita el Inicio nativo de la app."""
import datetime

from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext as _

from call import availability as availability_logic
from call.models import Call
from core.competitions import COMPETITIONS
from core.models import Membership, UserPreference
from core.templatetags.zyra_format import date_short
from data_analyse import my_form as my_form_stats
from match.models import Game, Match
from match.phase import CLOSE_MATCH, CREATE_CALL, CREATE_GAMES, ENTER_RESULTS, phases_for, player_status
from players.models import Player, current_season

from .fields import invalid
from .responses import json_ok
from .views_base import ApiView


def _display_name(user):
    """Nombre con el que se saluda: el de pila, y si no hay, el usuario."""
    return (user.first_name or "").strip() or user.get_username()


def _memberships(user):
    """Membresías de la cuenta: (activas, clubes suspendidos), con las activas en el orden de las competiciones.

    Mismo criterio que el middleware de la web: no cuentan los clubes suspendidos ni los archivados.
    """
    memberships = list(Membership.objects.filter(user=user).select_related("club").order_by("club__name"))
    suspended = [m.club for m in memberships if m.club.is_suspended]
    active = [m for m in memberships if not m.club.is_suspended and not m.club.is_archived]
    order = list(COMPETITIONS)
    active.sort(key=lambda m: order.index(m.club.competition) if m.club.competition in order else len(order))
    return active, suspended


def _team(membership):
    """Un equipo de la cuenta: nombre, escudo, competición, rol y categoría o división."""
    club = membership.club
    team = club.own_team
    rules = club.rules
    return {
        "id": str(club.public_id),
        "name": club.name,
        "crest": team.photo.url if team is not None and team.photo else None,
        "competition": club.competition,
        "competition_name": rules.name,
        "has_snp": bool(rules.has_snp),
        "role": membership.role,
        "role_label": str(membership.team_role_label),
        "can_manage": membership.can_manage,
        "division": team.division if team is not None else "",
        "division_label": str(team.get_division_display()) if team is not None and team.division else None,
    }


def _week_end(day):
    """Domingo de la semana natural que contiene ``day`` (el carrusel solo llega hasta ahí)."""
    return day + datetime.timedelta(days=6 - day.weekday())


def _kind_label(match):
    """«Jornada 6» en la liga regular; en el resto, el tipo («Play Off», «Amistoso»…)."""
    if match.round_number and match.is_league:
        return _("Jornada %(n)s") % {"n": match.round_number}
    return str(match.type_label)


def _side(team, name):
    """Un lado del enfrentamiento: nombre y si es el equipo propio (``team`` puede faltar si el rival se escribió a mano)."""
    return {"name": name, "is_own": bool(team and team.is_own)}


def _me(status, linked, can_manage):
    """
    Estado del jugador en un enfrentamiento: ``{"state", "game"?, "points"?, "partner"?}`` o None si no aplica.
    ``unlinked`` (cuenta sin ficha enlazada y sin gestionar), ``no_call``, ``applied_open``, ``called``,
    ``called_no_pair``, ``not_called`` o ``not_called_open``. Mismas reglas que la tarjeta de la web.
    """
    if not linked:
        return None if can_manage else {"state": "unlinked"}
    if not status["has_call"]:
        return {"state": "no_call"}
    if status["called"] and not status["closed"]:
        return {"state": "applied_open"}
    if status["called"]:
        game = status["game"]
        if game is None:
            return {"state": "called_no_pair"}
        partner = status["partner"]
        return {"state": "called", "game": game.n_game, "points": game.score,
                "partner": partner.full_name if partner else None}
    return {"state": "not_called" if status["closed"] else "not_called_open"}


def _upcoming(user, memberships, today):
    """
    Carrusel «Próximo enfrentamiento»: enfrentamientos abiertos de todos los equipos activos que caen en la semana
    natural del más cercano (como en la web), el más cercano primero.
    """
    clubs = [m.club for m in memberships]
    members = {m.club_id: m for m in memberships}
    matches = list(Match.objects.filter(club__in=clubs, draft_mode=True, start_date__gte=today)
                   .select_related("local", "visiting", "club").order_by("start_date", "id")[:200])
    if not matches:
        return []
    last = _week_end(matches[0].start_date)
    matches = [m for m in matches if m.start_date <= last]
    players = {p.club_id: p for p in Player.objects.filter(user=user, club__in=clubs)}
    calls = {c.match_id: c for c in Call.objects.filter(match__in=matches)}
    games = {}
    for game in Game.objects.filter(match__in=matches).select_related(
            "player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting"):
        games.setdefault(game.match_id, []).append(game)
    out = []
    for m in matches:
        player = players.get(m.club_id)
        status = player_status(player, calls.get(m.id), games.get(m.id, [])) if player else None
        can_manage = members[m.club_id].can_manage
        out.append({
            "id": str(m.public_id),
            "team_id": str(m.club.public_id),
            "competition": m.club.competition,
            "competition_name": m.club.rules.name,
            "kind_label": _kind_label(m),
            "date": m.start_date.isoformat(),
            "days_left": (m.start_date - today).days,
            "time": m.start_time.strftime("%H:%M") if m.start_time else None,
            "location": m.location or None,
            "maps_url": m.maps_url or None,
            "neutral_venue": bool(m.neutral_venue),
            "local": _side(m.local, m.local_name),
            "visiting": _side(m.visiting, m.visiting_name),
            "me": _me(status, player is not None, can_manage),
            "web_path": reverse("call_for_match", args=[m.public_id]),
        })
    return out


# Como la web (core.views): «Pendiente» solo enseña lo vencido y lo de los próximos 14 días; la app lo pagina de 3 en 3.
PENDING_DAYS = 14
PENDING_PAGE_SIZE = 3


def _pending_path(match, phase, can_manage):
    """Destino web de una fila de «Pendiente»: quien gestiona va directo al paso que toca; el resto, a la ficha."""
    if can_manage and phase.action == CREATE_CALL:
        return reverse("create_call", args=[match.public_id])
    if can_manage and phase.action == CREATE_GAMES:
        return reverse("create_game", args=[match.public_id])
    if can_manage and phase.action in (ENTER_RESULTS, CLOSE_MATCH):
        return reverse("enter_results", args=[match.public_id])
    return reverse("call_for_match", args=[match.public_id])


def _pending(memberships, today):
    """
    «Pendiente» de quien gestiona: enfrentamientos abiertos de los equipos que gestiona (vencidos primero, como
    ordena la fecha) y los de los próximos 14 días. Devuelve ``(filas, lejanos)``; ``lejanos`` cuenta los que caen
    más adelante y no se muestran.
    """
    managed = {m.club_id: m for m in memberships if m.can_manage}
    if not managed:
        return [], 0
    matches = list(Match.objects.filter(club__in=list(managed), draft_mode=True)
                   .select_related("local", "visiting", "club").order_by("start_date", "id")[:200])
    phases = phases_for(matches)
    limit = today + datetime.timedelta(days=PENDING_DAYS)
    rows = []
    for m in matches:
        if m.start_date > limit:
            continue
        phase = phases[m.id]
        rows.append({
            "match_id": str(m.public_id),
            "team_id": str(m.club.public_id),
            "competition": m.club.competition,
            "competition_name": m.club.rules.name,
            "rival": m.rival_label,
            "date": m.start_date.isoformat(),
            "overdue": m.start_date < today,
            "status_label": str(phase.label),
            "action": phase.action,
            "action_label": str(phase.pending_label),
            "web_path": _pending_path(m, phase, True),
        })
    return rows, len(matches) - len(rows)


def _todos(user, memberships, upcoming, today):
    """
    «Tus pendientes» del jugador: enlazar la ficha, subir la foto, la pareja del próximo enfrentamiento y las
    convocatorias sin responder de los próximos 14 días. Cada una: ``{"kind", "text", "team_id", "web_path"}``.
    """
    players = {p.club_id: p for p in Player.objects.filter(user=user, club__in=[m.club_id for m in memberships])}
    todos = []
    for membership in memberships:
        if membership.can_manage:
            continue
        club = membership.club
        player = players.get(club.id)
        if player is None:
            todos.append({"kind": "link", "text": _("Enlaza tu cuenta con tu ficha de jugador"),
                          "team_id": str(club.public_id), "web_path": reverse("my_player")})
        elif not player.photo:
            todos.append({"kind": "photo", "text": _("Sube tu foto"), "team_id": str(club.public_id),
                          "web_path": f"{reverse('my_player')}?en={club.competition}"})
    first = upcoming[0] if upcoming else None
    if first and first["me"] and first["me"].get("game") and first["me"].get("partner"):
        todos.append({"kind": "partner", "team_id": first["team_id"], "web_path": first["web_path"],
                      "text": _("Tu pareja el %(date)s: %(partner)s") % {
                          "date": date_short(datetime.date.fromisoformat(first["date"])),
                          "partner": first["me"]["partner"]}})
    horizon = today + datetime.timedelta(days=PENDING_DAYS)
    clubs = [m.club for m in memberships]
    open_matches = Match.objects.filter(club__in=clubs, draft_mode=True, start_date__gte=today,
                                        start_date__lte=horizon).select_related("local", "visiting", "club")
    for m, _player in availability_logic.unanswered(list(players.values()), list(open_matches.order_by("start_date", "id"))):
        todos.append({"kind": "availability", "team_id": str(m.club.public_id),
                      "web_path": reverse("call_for_match", args=[m.public_id]),
                      "text": _("Responde si puedes jugar: %(rival)s, %(date)s") % {
                          "rival": m.rival_label, "date": date_short(m.start_date)}})
    return todos


def _snp_card(snp):
    """Puntos SNP de «Mi forma»: puntuación, variación y gráfica escalonada (puntos en % del lienzo, ``y`` hacia abajo)."""
    if snp is None:
        return None
    chart = snp["chart"]
    out = {"score": snp["score"], "delta": snp["delta"], "chart": None}
    if chart:
        width, height = my_form_stats.CHART_WIDTH, my_form_stats.CHART_HEIGHT
        path = [[round(float(x) / width * 100, 1), round(float(y) / height * 100, 1)]
                for x, y in (pair.split(",") for pair in chart["line"].split())]
        out["chart"] = {
            "path": path,
            "low": chart["low"], "high": chart["high"], "start": chart["start"].isoformat(),
            "points": [{"x": p["x"], "y": p["y"], "score": p["score"], "date": p["date"].isoformat()}
                       for p in chart["points"]],
        }
    return out


def _my_form(user, memberships, today):
    """
    Tarjeta «Mi forma»: None si la cuenta no tiene ficha enlazada en ningún equipo activo; ``{"hidden": true}`` si
    la ocultó; si no, el resumen de ``data_analyse.my_form`` con las mismas reglas que la web (suma todas las
    competiciones de la cuenta, en el orden de las competiciones).
    """
    clubs = [m.club for m in memberships]
    players = sorted(Player.objects.filter(club__in=clubs, user=user).select_related("club"),
                     key=lambda p: clubs.index(p.club))
    if not players:
        return None
    if UserPreference.my_form_is_hidden(user):
        return {"hidden": True}
    main = players[0]
    data = my_form_stats.my_form(main.club, main, today=today, others=players[1:])
    run_kind, run_count = data["run"]
    return {
        "hidden": False,
        "season": current_season(),
        "stats_path": f"{reverse('player_statistics')}?en={main.club.competition}&player={main.public_id}",
        "empty": data["empty"],
        "has_snp": any(p.club.rules.has_snp for p in players),
        "wins": data["wins"], "losses": data["losses"],
        "by_competition": [{**c, "name": str(c["name"])} for c in data["by_competition"]],
        "last_games": data["last_games"],
        "run": {"kind": run_kind, "count": run_count},
        "called": data["called"], "played": data["played"], "played_pct": data["played_pct"],
        "snp": _snp_card(data["snp"]),
    }


class MyFormView(ApiView):
    """``POST /api/v1/home/my-form``: oculta o vuelve a mostrar «Mi forma» (la misma preferencia que la web)."""

    def post(self, request):
        """Cuerpo ``{"hide": true | false}``. Devuelve ``{"hidden": bool}``."""
        body = self.json_body(request)
        hide = body.get("hide")
        if not isinstance(hide, bool):
            raise invalid("hide")
        UserPreference.objects.update_or_create(user=request.user, defaults={"my_form_hidden": hide})
        return json_ok({"hidden": hide})


class HomeView(ApiView):
    """
    ``GET /api/v1/home``: base del Inicio nativo. Dice en qué situación está la cuenta (``state``: ``ok``,
    ``no_team`` o ``suspended``), sus equipos con el rol en cada uno, los datos para el saludo y ``upcoming``, el
    carrusel «Próximo enfrentamiento», ``pending`` («Pendiente» de quien gestiona: filas, lejanos y vencidos),
    ``todos`` («Tus pendientes» del jugador) y ``pending_count`` (el contador de la campana) y ``my_form`` («Mi forma»). Las demás tarjetas del Inicio (pendientes, «Mi forma», avisos…) se irán
    añadiendo a esta respuesta.
    """

    def get(self, request):
        """Resumen de la cuenta para pintar la cabecera del Inicio y decidir qué pantalla mostrar."""
        user = request.user
        active, suspended = _memberships(user)
        players = Player.objects.filter(Q(user=user) | Q(past_user=user))
        if active:
            state = "ok"
        elif suspended:
            state = "suspended"
        else:
            state = "no_team"
        today = datetime.date.today()
        upcoming = _upcoming(user, active, today)
        rows, far = _pending(active, today)
        todos = _todos(user, active, upcoming, today)
        return json_ok({
            "state": state,
            "user": {"username": user.get_username(), "display_name": _display_name(user)},
            "season": current_season(),
            "teams": [_team(m) for m in active],
            "suspended_clubs": [{"name": club.name} for club in suspended],
            "upcoming": upcoming,
            "pending": {"rows": rows, "far": far, "overdue": sum(1 for r in rows if r["overdue"]),
                        "page_size": PENDING_PAGE_SIZE},
            "todos": todos,
            "my_form": _my_form(user, active, today),
            "pending_count": len(rows) + len(todos),
            "has_player": players.filter(user=user, club__in=[m.club_id for m in active]).exists(),
            "has_history": players.exists(),
        })
