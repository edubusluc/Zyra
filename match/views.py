"""Vistas de partidos: listado y alta de enfrentamientos, convocatorias, alineación de
los 5 partidos, resultados, cierre del acta e informe PDF de la convocatoria.

Todas las vistas trabajan solo con datos del club activo (``request.club``).
"""
from django.shortcuts import render, redirect, get_object_or_404
from core.decorators import club_required, club_admin_required
from django.contrib import messages
from .forms import MatchForm
from .models import Match, Game, Result
from . import lineup
from .notifications import send_call_report, report_filename
from call.models import ReportDelivery
from .report import build_report, suggested_lineups
from .report_pdf import render_report
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _, gettext_lazy
import logging

logger = logging.getLogger(__name__)
from players.models import Player, current_season
from call.models import Call
from team.models import Team
from datetime import datetime
from callLog.models import CallLog
from penalty.models import Penalty
import json
import re
from urllib.parse import urlencode
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils import timezone
from data_analyse.views import season_filter_context


CREATE_MATCH_HTML = "create_match.html"
# Create your views here.


def club_match(request, match_id):
    """Partido del club activo o 404: nunca se accede a partidos de otros clubes."""
    return get_object_or_404(Match, public_id=match_id, club=request.club)


def club_call(request, **filters):
    """Convocatoria del club activo que cumpla ``filters`` o 404."""
    return get_object_or_404(Call, match__club=request.club, **filters)


def club_players(request, ids):
    """Jugadores del club activo cuyos ids vienen del formulario (ignora ids ajenos)."""
    return Player.objects.filter(club=request.club, id__in=[i for i in ids if str(i).isdigit()])


MATCHES_PER_PAGE = 12
# Jugadores de cada posición que se ven en el detalle del partido antes de pulsar «Ver todos».
CALL_GROUP_PREVIEW = 8
ALL_SEASONS = "all"


def match_outcome(match):
    """'V', 'D' o 'E' desde el punto de vista del club; None si el acta sigue abierta."""
    if match.draft_mode or match.result in ("", "NONE", None):
        return None
    if match.result == "Victoria Local":
        return "V" if match.own_is_local else "D"
    if match.result == "Victoria Visitante":
        return "V" if match.own_is_visiting else "D"
    return "E"


def split_points(result_points):
    """Puntos de local y visitante a partir de ``result_points`` ('5/7'; los antiguos, '7-5').

    Devuelve dos cadenas, o (None, None) si no hay marcador legible.
    """
    parts = re.split(r"[/-]", result_points or "")
    if len(parts) != 2 or not all(x.strip().isdigit() for x in parts):
        return None, None
    return parts[0].strip(), parts[1].strip()


def rival_names(club_matches):
    """Rivales distintos de los partidos (equipos ajenos y rivales escritos a mano), por orden alfabético."""
    names = set()
    for m in club_matches:
        if m.local_id or m.visiting_id or m.rival_name:
            names.add(m.rival_label)
    return sorted((n for n in names if n), key=str.casefold)


def filter_by_rival(matches, rival):
    """Partidos contra ``rival``: un equipo ajeno con ese nombre o un rival escrito a mano."""
    return matches.filter(
        Q(local__name=rival, local__is_own=False) | Q(visiting__name=rival, visiting__is_own=False) | Q(rival_name=rival)
    )


def search_matches(matches, text):
    """Partidos cuyo equipo local, visitante, rival escrito a mano o ubicación contienen ``text``."""
    query = Q()
    for word in text.split():
        query &= (Q(local__name__icontains=word) | Q(visiting__name__icontains=word)
                  | Q(rival_name__icontains=word) | Q(location__icontains=word))
    return matches.filter(query)


@club_required
def list_match(request):
    """Listado paginado de los enfrentamientos del club, filtrable por temporada, rival y nombre.

    Requiere pertenecer al club (club_required). Por GET ``season`` elige la temporada
    (por defecto la actual; 'all' muestra todas) y ``page`` la página. El selector muestra
    «Todas», las tres temporadas más recientes y un buscador para las demás
    (data_analyse.views.season_filter_context). ``rival`` deja solo los partidos contra ese
    rival y ``q`` busca por coincidencia en los nombres de los equipos y la ubicación; al
    buscar o elegir rival sin indicar temporada se buscan en todas. Renderiza list_match.html
    con el resultado, la temporada de cada partido y un resumen de ganados, empatados,
    perdidos y pendientes de lo filtrado. Cada partido de la página lleva además los puntos
    de cada lado, cuántos convocados tiene y si es un partido próximo (sin resultado y con
    fecha de hoy en adelante) para pintar su tarjeta.
    """
    club_matches = Match.objects.filter(club=request.club).select_related('local', 'visiting')
    # Temporadas para el selector (desc), incluida la actual aunque aún no tenga partidos
    seasons = set(club_matches.values_list('season', flat=True)) | {current_season()}
    seasons = sorted((x for x in seasons if x and x != "NONE"), reverse=True)
    rivals = rival_names(club_matches)

    search = request.GET.get('q', '').strip()[:100]
    rival = request.GET.get('rival', '').strip()
    if rival not in rivals:
        rival = ''

    # Por defecto, la temporada actual; "all" muestra todas. Al buscar, todas.
    season = request.GET.get('season') or (ALL_SEASONS if search or rival else current_season())
    if season != ALL_SEASONS and season not in seasons:
        season = current_season()

    matches = club_matches.order_by('-start_date', '-id')
    if season != ALL_SEASONS:
        matches = matches.filter(season=season)
    if rival:
        matches = filter_by_rival(matches, rival)
    if search:
        matches = search_matches(matches, search)

    outcomes = [match_outcome(m) for m in matches]
    summary = {
        'played': sum(o is not None for o in outcomes),
        'won': outcomes.count('V'),
        'drawn': outcomes.count('E'),
        'lost': outcomes.count('D'),
        'pending': outcomes.count(None),
    }

    paginator = Paginator(matches, MATCHES_PER_PAGE)
    page = request.GET.get('page')
    try:
        matches = paginator.page(page)
    except PageNotAnInteger:
        matches = paginator.page(1)
    except EmptyPage:
        matches = paginator.page(paginator.num_pages)

    called = dict(Call.objects.filter(match__in=list(matches))
                  .annotate(n=Count('players')).values_list('match_id', 'n'))
    today = timezone.localdate()
    for m in matches:
        m.outcome = match_outcome(m)
        m.local_points, m.visiting_points = split_points(m.result_points) if m.outcome else (None, None)
        m.called = called.get(m.id)
        m.upcoming = m.outcome is None and m.start_date >= today

    # Resto de filtros para la paginación y para los formularios de búsqueda.
    keep = {'season': season, 'q': search, 'rival': rival}
    return render(request, "list_match.html", {
        'matches': matches,
        'seasons': seasons,
        'selected_season': season,
        'all_seasons': ALL_SEASONS,
        'summary': summary,
        'search': search,
        'rival': rival,
        'rivals': rivals,
        'filtering': bool(search or rival),
        'page_extra': '&' + urlencode({k: v for k, v in keep.items() if v}),
        **season_filter_context(request, seasons, season, all_value=ALL_SEASONS),
    })

@club_admin_required
def create_match(request):
    """Alta de un enfrentamiento.

    Solo para administradores del club (club_admin_required). En GET muestra el
    formulario; en POST lo valida (las reglas están en MatchForm), lo guarda y
    redirige al listado.
    """
    form = MatchForm(request.POST or None, club=request.club)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("list_match")
    return render(request, CREATE_MATCH_HTML, {"form": form})

@club_admin_required
def delete_match(request, match_id):
    """Borrado de un enfrentamiento que aún no está cerrado.

    Solo para administradores del club. En GET pide confirmación (delete_match.html);
    en POST lo borra. Si el acta ya está cerrada, avisa y vuelve al listado.
    """
    try:
        match = club_match(request, match_id)
        if match.draft_mode != False:

            if request.method == 'POST':
                # Eliminar el partido si el usuario confirma
                match.delete()
                return redirect('list_match')

            return render(request, 'delete_match.html', {'match': match})
        else:
            messages.error(request, _("No se puede eliminar un partido ya confirmado"))

            return redirect('list_match')
    except Match.DoesNotExist:
        messages.error(request, _("El partido no existe"))
        return redirect('list_match')


def selectable_players(club, include_ids=()):
    """
    Jugadores para el selector de convocatorias: los que están en el equipo
    (más los ya convocados aunque ya no estén), en orden alfabético y con sus
    sanciones en `penalty_reasons`.
    """
    players = list(
        Player.objects.filter(club=club)
        .filter(Q(in_team=True) | Q(id__in=list(include_ids)))
        .order_by('name', 'last_name')
    )
    reasons = {}
    for pid, reason in Penalty.objects.filter(player__in=players).values_list('player_id', 'reason'):
        reasons.setdefault(pid, []).append(reason)
    for p in players:
        p.penalty_reasons = reasons.get(p.id, [])
    return players


@club_admin_required
def create_call(request, match_id):
    """Crea la convocatoria de un enfrentamiento.

    Solo para administradores del club. Si ya existe convocatoria o el acta está
    cerrada, redirige a existing_call. En POST guarda los jugadores elegidos (al menos
    uno) y lleva a la página de la convocatoria; si no, muestra create_call.html.
    """
    match = club_match(request, match_id)
    if Call.objects.filter(match=match).exists() or match.draft_mode == False:
        return redirect('existing_call', match.public_id)

    selected_ids = []
    if request.method == 'POST':
        chosen = club_players(request, request.POST.getlist('players'))
        selected_ids = list(chosen.values_list('id', flat=True))
        if not selected_ids:
            messages.error(request, _("Debes seleccionar al menos un jugador."))
        else:
            call = Call.objects.create(match=match)
            call.players.set(selected_ids)
            CallLog.objects.create(call=call, text="")
            return redirect('call_for_match', match.public_id)

    return render(request, "create_call.html", {
        "players": selectable_players(request.club),
        "selected_players": selected_ids,
        "match": match,
    })


def validate_call(call):
    """Comprueba si la convocatoria se puede cerrar: (True, None) o (False, mensaje de error)."""
    if call.players.all().count() < 10:
        return False, _("Para cerrar una convocatoria al menos debes contar con 10 jugadores")
    if call.draft_mode == False:
        return False, _("Esta convocatoria ha sido cerrada")
    
    return True, None

@club_admin_required
def close_call(request, match_id):
    """Cierra la convocatoria de un enfrentamiento y envía el informe a los capitanes.

    Solo para administradores del club. Exige al menos 10 convocados y que siga
    abierta. Solo cierra en POST; siempre vuelve a la página de la convocatoria.
    """
    call = club_call(request, match__public_id=match_id)
    is_valid, error_message = validate_call(call)

    if not is_valid:
        messages.error(request, error_message)
        return redirect(call_for_match, match_id=match_id)

    if request.method == "POST":
        call.draft_mode = False
        call.save()
        _send_report(request, call, _("Convocatoria cerrada"))
        return redirect('call_for_match', call.match.public_id)

    return redirect('call_for_match', call.match.public_id)


def _send_report(request, call, done):
    """
    Informe PDF a los capitanes: se intenta al momento y lo que falle se reintenta
    solo (send_call_reports). Si falla el envío, la convocatoria queda cerrada igualmente.
    """
    try:
        deliveries = send_call_report(call, sender=request.user)
    except Exception:
        logger.exception("No se pudo enviar el informe de la convocatoria %s", call.pk)
        messages.warning(request, _("%(done)s, pero no se pudo enviar el informe por email. "
                                    "Puedes descargarlo desde esta página.") % {"done": done})
        return
    if not deliveries:
        messages.info(request, _("%(done)s. Ningún capitán tiene email: añádelo en "
                                 "Miembros para recibir el informe automáticamente.") % {"done": done})
        return
    sent = [d.email for d in deliveries if d.status == ReportDelivery.SENT]
    pending = [d.email for d in deliveries if d.status != ReportDelivery.SENT]
    if sent:
        messages.success(request, _("%(done)s. Informe enviado a %(emails)s.") % {"done": done, "emails": ", ".join(sent)})
    if pending:
        if sent:
            text = _("No se pudo enviar el informe a %(emails)s: se reintentará automáticamente. "
                     "Mientras, puedes descargarlo desde esta página.")
        else:
            text = _("%(done)s. No se pudo enviar el informe a %(emails)s: se reintentará automáticamente. "
                     "Mientras, puedes descargarlo desde esta página.")
        messages.warning(request, text % {"done": done, "emails": ", ".join(pending)})


@club_admin_required
def resend_call_report(request, match_id):
    """Vuelve a enviar el informe de una convocatoria cerrada a los capitanes."""
    call = club_call(request, match__public_id=match_id)
    if request.method == "POST" and not call.draft_mode:
        _send_report(request, call, _("Informe reenviado"))
    return redirect('call_for_match', call.match.public_id)


@club_admin_required
def call_report_pdf(request, match_id):
    """Descarga manual del informe de convocatoria."""
    call = club_call(request, match__public_id=match_id)
    pdf = render_report(build_report(call))
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{report_filename(call.match)}"'
    return response

@club_admin_required
def edit_call(request, call_id):
    """Edición de los jugadores de una convocatoria.

    Solo para administradores del club y mientras el acta del enfrentamiento esté
    abierta (si no, vuelve a la convocatoria). En POST guarda los jugadores y anota en
    el CallLog quién se ha añadido o quitado; en GET muestra edit_call.html.
    """
    call = club_call(request, public_id=call_id)
    selected_players = list(call.players.values_list('id', flat=True))
    all_players = selectable_players(request.club, include_ids=selected_players)
    call_log, _created = CallLog.objects.get_or_create(call=call, defaults={'text': ''})
    
    current_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    if call.match.draft_mode == False:
        return redirect('call_for_match', call.match.public_id)
    else:
        if request.method == "POST":
            selected_players_ids = list(club_players(request, request.POST.getlist("players")).values_list('id', flat=True))
            selected_set = set(selected_players_ids)
            call_set = set(selected_players)

            added_players = selected_set - call_set
            removed_players = call_set - selected_set

            # Definir si el mensaje es para convocatoria abierta o cerrada
            status_message = "convocatoria abierta" if call.draft_mode else "convocatoria cerrada"

            # Inicializar el log_text
            log_text = ""

            # Construir el mensaje para los jugadores añadidos
            if added_players:
                added_player_names = [Player.objects.get(id=player_id).name.upper() for player_id in added_players]
                log_text += f"Jugadores añadidos con la {status_message}: " + ", ".join(added_player_names) + f" el día {current_time};"

            # Construir el mensaje para los jugadores eliminados
            if removed_players:
                removed_player_names = [Player.objects.get(id=player_id).name.upper() for player_id in removed_players]
                log_text += f"Jugadores eliminados con la {status_message}: " + ", ".join(removed_player_names) + f" el día {current_time};"

            # Guardar el log si hay algún mensaje
            if log_text.strip():  # Verifica que log_text no esté vacío
                call_log.text += log_text
                call_log.save()

            # Actualizar la convocatoria con los jugadores seleccionados
            call.players.set(selected_players_ids)
            call.save()
            
            return redirect('call_for_match', call.match.public_id)



    context = {
        'call': call,
        'all_players': all_players,
        'selected_players': selected_players,
    }
    return render(request, 'edit_call.html', context)

@club_admin_required
def closed_call(request, call_id):
    """Aviso al intentar modificar una convocatoria ya cerrada (solo administradores del club)."""
    call = club_call(request, public_id=call_id)
    return render(request, 'closed_call.html', {'match': call})


@club_admin_required
def existing_call_view(request, match_id):
    """Aviso al intentar crear una convocatoria que ya existe (solo administradores del club)."""
    match = club_match(request, match_id)
    return render(request, 'existing_call.html', {'match': match})

POSITION_GROUPS = (("Derecha", gettext_lazy("Derecha")), ("Revés", gettext_lazy("Revés")), ("Mixto", gettext_lazy("Mixtos")))


@club_required
def call_for_match(request, match_id):
    """Página de un enfrentamiento: convocatoria, partidos y resultados.

    Requiere pertenecer al club (club_required). Agrupa a los convocados por posición
    (derecha, revés y mixtos), marca los que ya juegan algún partido y muestra el
    estado de los envíos del informe. Renderiza call_for_match.html.
    """
    match = club_match(request, match_id)
    call = Call.objects.filter(match=match).first()
    games = list(
        Game.objects.filter(match=match).order_by("n_game")
        .select_related("player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting")
        .prefetch_related("results")
    )
    for g in games:
        g.result = next(iter(g.results.all()), None)  # usa el prefetch: sin consulta extra por partido

    groups = []
    if call:
        players = list(call.players.order_by("name", "last_name"))
        playing = {pid for g in games for pid in (g.player_1_local_id, g.player_2_local_id,
                                                  g.player_1_visiting_id, g.player_2_visiting_id) if pid}
        for p in players:
            p.is_playing = p.id in playing
        known = {key for key, _label in POSITION_GROUPS}
        for key, label in POSITION_GROUPS:
            members = [p for p in players if p.position == key or (key == "Mixto" and p.position not in known)]
            # Primero los que juegan un partido: son los que se ven antes de desplegar el grupo
            members.sort(key=lambda p: not p.is_playing)
            groups.append({"label": label, "players": members, "hidden": max(len(members) - CALL_GROUP_PREVIEW, 0)})

    return render(request, "call_for_match.html", {
        "call_for_match": call,
        "match_id": match.public_id,
        "game_for_match": games,
        "games_count": len(games),
        "match": match,
        "groups": groups,
        "players_count": sum(len(g["players"]) for g in groups),
        "report_deliveries": list(call.report_deliveries.order_by("email")) if call else [],
    })


def validate_game_for_match(call):
    """Comprueba si se pueden crear los partidos: hace falta una convocatoria cerrada con
    al menos 10 jugadores. Devuelve (True, None) o (False, mensaje de error).
    """
    if not call:
        return False, _("No se pueden crear partidos, no existe ninguna convocatoria.")
    if call.players.all().count() < 10:
        return False, _("Para crear los partidos debes contar al menos con 10 jugadores")
    if call.draft_mode != False:
        return False, _("Para crear los partidos debes confirmar la convocatoria")

    
    return True, None

@club_admin_required
def create_game_for_match(request, match_id):
    """Crea los 5 partidos (parejas y orden) de un enfrentamiento.

    Solo para administradores del club, con la convocatoria cerrada. Si los partidos
    ya existen, redirige a su edición. En POST valida y guarda la alineación (ver
    match.lineup); en GET muestra create_game.html con los convocados.
    """
    match = club_match(request, match_id)
    call = Call.objects.filter(match=match).first()

    is_valid, error_message = validate_game_for_match(call)
    if not is_valid:
        messages.error(request, error_message)
        return redirect('call_for_match', match_id=match_id)

    if match.games.exists():
        messages.info(request, _("Los partidos ya están creados: puedes cambiar las parejas desde aquí."))
        return redirect('edit_games_match', match_id=match.public_id)

    if request.method == "POST":
        try:
            lineup.create_games(match, lineup.parse_lineup(request.POST.get("ordered_games"), call))
        except lineup.LineupError as e:
            messages.error(request, str(e))
            return redirect('create_game', match_id=match.public_id)
        messages.success(request, _("Partidos creados."))
        return redirect('call_for_match', match_id=match.public_id)

    return render(request, "create_game.html", {
        "call": call,
        "match": match,
        "players": call.players.order_by('name', 'last_name'),
        "games_per_match": lineup.GAMES_PER_MATCH,
    })


@club_admin_required
@require_GET
def suggested_lineup(request, match_id):
    """
    Alineaciones sugeridas (JSON) para rellenar las parejas del formulario de partidos.

    Solo administradores del club y con la convocatoria cerrada. Devuelve
    ``{"lineups": [...]}`` (ver match.report.suggested_lineups) o ``{"error": ...}``
    con estado 400 si no se puede sugerir.
    """
    match = club_match(request, match_id)
    call = Call.objects.filter(match=match).first()
    is_valid, error_message = validate_game_for_match(call)
    if not is_valid:
        return JsonResponse({"error": str(error_message)}, status=400)
    lineups = suggested_lineups(call)
    if not lineups:
        return JsonResponse({"error": _("Hacen falta al menos 10 convocados para sugerir una alineación.")}, status=400)
    return JsonResponse({"lineups": lineups})


SET_FIELDS = ('set1_local', 'set1_visiting', 'set2_local', 'set2_visiting', 'set3_local', 'set3_visiting')


def _save_result(request, game, result, template):
    """Valida y guarda el resultado de un partido; si hay errores, vuelve al formulario."""
    values = {f: request.POST.get(f, '').strip() for f in SET_FIELDS}
    for field, value in values.items():
        setattr(result, field, value)
    try:
        result.full_clean(exclude=['game', 'result'] + list(SET_FIELDS), validate_unique=False)
        result.result = result.determine_winner()
        result.save()
    except ValidationError as e:
        return render(request, template, {"game": game, "result": result, "values": values, "errors": e.messages})

    game.winner = "Local" if result.result == "Victoria Local" else "Visitante"
    game.save(update_fields=['winner'])
    return redirect('call_for_match', match_id=game.match.public_id)


@club_admin_required
def create_result(request, game_id):
    """Añade el resultado de un partido.

    Solo para administradores del club y con el acta abierta. Si el partido ya tiene
    resultado, redirige a su edición. En POST lo valida y guarda; en GET muestra
    create_result.html.
    """
    game = get_object_or_404(Game.objects.select_related('match__local', 'match__visiting'), public_id=game_id, match__club=request.club)
    if not game.match.draft_mode:
        messages.error(request, _("No se pueden añadir resultados a un partido ya confirmado"))
        return redirect('call_for_match', match_id=game.match.public_id)
    if game.results.exists():
        return redirect('edit_result', game_id=game.public_id)

    if request.method == "POST":
        return _save_result(request, game, Result(game=game), "create_result.html")
    return render(request, "create_result.html", {"game": game, "values": {}})


@club_admin_required
def edit_result(request, game_id):
    """Edita el resultado de un partido.

    Solo para administradores del club y con el acta abierta. En POST lo valida y
    guarda; en GET muestra edit_result.html con los sets actuales.
    """
    game = get_object_or_404(Game.objects.select_related('match__local', 'match__visiting'), public_id=game_id, match__club=request.club)
    match = game.match
    result = get_object_or_404(Result, game=game)

    if not match.draft_mode:
        messages.error(request, _("No se pueden editar los resultados de un partido ya confirmado"))
        return redirect('call_for_match', match_id=match.public_id)

    if request.method == "POST":
        return _save_result(request, game, result, "edit_result.html")
    values = {f: '' if getattr(result, f) is None else getattr(result, f) for f in SET_FIELDS}
    return render(request, "edit_result.html", {"game": game, "result": result, "values": values})



def calculate_points(games):
    """Suma los puntos de los partidos ganados por cada lado: (puntos_local, puntos_visitante)."""
    points_local = 0
    points_visiting = 0
    
    for g in games:
        if g.winner == "Visitante":
            points_visiting = points_visiting + g.score
        else:
            points_local = points_local + g.score
    
    return points_local, points_visiting

def determine_match_result(points_local, points_visiting):
    """'Victoria Local', 'Victoria Visitante' o 'EMPATE' (valor de Match.POSSIBLE_RESULT) según los puntos."""
    if points_local > points_visiting:
        return "Victoria Local"
    elif points_local < points_visiting:
        return "Victoria Visitante"
    else:
        return "EMPATE"
   
def valid_close_match(games,match):
    """Comprueba si se puede cerrar el acta: el enfrentamiento sigue abierto y tiene al menos
    5 partidos, todos con resultado. Devuelve (True, None) o (False, mensaje de error).
    """
    if match.draft_mode == False:
        return False, _("No se pueden cerrar actas, el partido ya ha sido cerrado")
    if len(games) < 5:
        return False, _("No se pueden cerrar actas, se requieren al menos 5 partidos.")
    
    for g in games:
        if g.results.first() is None:
            return False, _("No se pueden cerrar actas, algunos partidos no tienen resultado.")
    
    return True, None     

@club_admin_required
@require_POST
def close_match(request, match_id):
    """Cierra el acta de un enfrentamiento (solo POST, administradores del club).

    Si faltan partidos o resultados, avisa y vuelve a la convocatoria. Si no, cierra
    los partidos, calcula los puntos y el resultado final y redirige al listado.
    """
    match = club_match(request, match_id)
    games = match.games.all()

    # Validar si se pueden cerrar las actas
    is_valid, error_message = valid_close_match(games, match)
    if not is_valid:
        messages.error(request, error_message)
        return redirect(call_for_match, match_id=match_id)

    # Calcular puntos y actualizar ganadores
    points_local, points_visiting = calculate_points(games)

    # Dar por finalizado los juegos
    for game in games:
        game.draft_mode = False
        game.save()

    # Determinar el resultado del partido
    match.result = determine_match_result(points_local, points_visiting)
    match.result_points = f"{points_local}/{points_visiting}"
    match.draft_mode = False
    match.save()

    return redirect('list_match')


@club_admin_required
def edit_game_match(request, match_id):
    """Cambia las parejas y el orden de los partidos ya creados.

    Solo para administradores del club y con el acta abierta. Si aún no hay partidos,
    redirige a crearlos. En POST guarda la nueva alineación; en GET muestra
    edit_game_match.html con la alineación actual.
    """
    match = club_match(request, match_id)

    if not match.draft_mode:
        messages.error(request, _("No se pueden editar los partidos que se encuentran ya confirmados"))
        return redirect('call_for_match', match_id=match_id)

    games = list(Game.objects.filter(match=match).order_by('n_game'))
    if not games:
        return redirect('create_game', match_id=match.public_id)
    call = club_call(request, match__public_id=match_id)

    if request.method == "POST":
        try:
            lineup.update_games(match, lineup.parse_lineup(request.POST.get("ordered_games"), call, match_games=games))
        except lineup.LineupError as e:
            messages.error(request, str(e))
            return redirect('edit_games_match', match_id=match.public_id)
        messages.success(request, _("Parejas actualizadas."))
        return redirect('call_for_match', match_id=match.public_id)

    games_data = [
        {
            'gameId': game.id,
            'n_game': game.n_game,
            'player1Id': game.player_1_local_id or game.player_1_visiting_id,
            'player2Id': game.player_2_local_id or game.player_2_visiting_id,
        }
        for game in games
    ]

    return render(request, "edit_game_match.html", {
        "games": games_data,
        "match": match,
        "call": call,
        "players": call.players.order_by('name', 'last_name'),
    })








    

    



    





