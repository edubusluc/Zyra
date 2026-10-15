"""Vistas de jugadores: alta, lista, ficha, plantilla, cuenta SNP, «Completar equipo» y perfil propio."""
from django.shortcuts import render, redirect, get_object_or_404
from core.decorators import club_required, club_admin_required
from .forms import NewOwnPlayerForm, OwnPlayerForm, PlayerEditForm, PlayerForm, SnpAccountForm, with_placeholder
from django.contrib import messages
from match.models import Game
from players.models import Player, SnpAccount, SnpTeamImport
from core.crypto import DecryptionError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.urls import reverse
from django.db import transaction
from django.db.models import BooleanField, ExpressionWrapper, Q
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy, ngettext
from . import snp_import, snp_service
from .scraper import SnpScrapeError
from core import similarity


# Create your views here.


@club_admin_required
def create_player(request):
    """
    Alta de un jugador en el equipo propio del club. Solo capitanes (``club_admin_required``).

    GET muestra el formulario. POST lo valida y, si hay jugadores con un nombre igual o
    parecido, vuelve a mostrarlo para que se confirme antes de crearlo. Las peticiones de
    comprobación (``similarity.is_check_request``) responden en JSON si es válido y los
    parecidos, sin crear nada. Al crearlo redirige a la lista de jugadores.
    """
    similar = []
    if request.method == "POST":
        form = PlayerForm(request.POST, request.FILES, club=request.club)
        form.uploader, form.check_only = request.user, similarity.is_check_request(request)
        if form.is_valid():
            # Jugadores con nombre y apellidos iguales o parecidos: se pregunta antes de crearlo.
            similar = similarity.similar_players(request.club, form.cleaned_data['name'], form.cleaned_data['last_name'])
            if similarity.is_check_request(request):
                return JsonResponse({"valid": True, "similar": [str(p) for p in similar]})
            if not similar or similarity.confirmed(request):
                player = form.save(commit=False)
                player.club = request.club
                player.team = request.club.own_team  # save() le copia la categoría del equipo
                player.save()
                return redirect("list_players")
        else:
            if similarity.is_check_request(request):
                return JsonResponse({"valid": False, "similar": []})
            messages.error(request, _("Error al crear el jugador. Por favor, verifica los datos."))
    else:
        form = PlayerForm(club=request.club)

    # Agregar clases a cada campo
    for field in form:
        field.field.widget.attrs.update({'class': 'form-control'})

    return render(request, "create_player.html", {
        "form": form,
        "similar": [str(p) for p in similar],
        "own_team": request.club.own_team,
    })


ORDER_FIELDS = {'name', '-name', 'last_name', '-last_name', 'position', '-position', 'snp_score', '-snp_score'}


@club_required
def list_players(request):
    """
    Lista de jugadores del club con orden (``order_by``). Se envían todos y la búsqueda en vivo y
    la paginación (9 por página) las hace ``static/js/player-selector.js``, igual que en las
    convocatorias. Requiere pertenecer al club (``club_required``). Por defecto solo se listan los del equipo; los
    capitanes pueden desmarcar «solo mi equipo» (``team=0``) para ver también a los que
    ya no están en el equipo (al final) y el estado del botón «Completar equipo».
    """
    order_by = request.GET.get('order_by', 'name')
    if order_by not in ORDER_FIELDS:
        order_by = 'name'

    # Interruptor «solo mi equipo»: marcado por defecto; el formulario envía team=0 al desmarcarlo.
    # Solo los capitanes pueden verlo desmarcado (el resto nunca ve a los que ya no están).
    only_team = request.GET.get('team', '1') != '0'
    players = Player.objects.filter(club=request.club)
    if request.membership.is_admin and not only_team:
        players = players.order_by('-in_team', order_by)
    else:
        players = players.filter(in_team=True).order_by(order_by)

    context = {
        'players': players,
        'order_by': order_by,
        'only_team': only_team,
    }
    if request.membership.is_admin:
        context.update(_complete_team_context(request.club))
    return render(request, 'list_players.html', context)


def _complete_team_context(club):
    """Estado del botón «Completar equipo» (solo con cuenta SNP; una sola vez y, tras varios fallos, oculto)."""
    if not SnpAccount.objects.filter(club=club).exists():
        return {}
    done = snp_import.web_import_done(club)
    active = snp_import.active_import(club)
    return {
        'snp_import_enabled': True,
        'snp_import': active,
        'snp_import_changes': bool(active) and snp_import.has_changes(active),
        'snp_import_done': done is not None,
        'snp_import_blocked': snp_import.web_blocked(club) and not active,
        'snp_import_wait': snp_import.search_limit(club),
        'snp_service_off': not snp_service.is_enabled(),
    }

@club_admin_required
def edit_player(request, player_id):
    """
    Edición de un jugador del club, foto incluida. Solo capitanes. GET muestra el
    formulario; POST lo guarda si es válido y redirige a la lista de jugadores.
    """
    player = get_object_or_404(Player, public_id=player_id, club=request.club)
    form = PlayerEditForm(request.POST or None, request.FILES or None, instance=player)
    form.uploader = request.user
    if request.method == "POST":
        if form.is_valid():
            form.save()
            return redirect('list_players')

    context = {
        'player': player,
        'form': form,
        'positions': with_placeholder(Player.POSITIONS),
        'hands': with_placeholder(Player.HAND),
    }
    return render(request, 'edit_player.html', context)


@club_admin_required
def delete_player(request, player_id):
    """Elimina un jugador tras avisar de que se borran sus estadísticas. Los partidos se conservan."""
    player = get_object_or_404(Player, public_id=player_id, club=request.club)
    if request.method == "POST":
        name = str(player)
        player.delete()
        messages.success(request, _("Jugador «%(name)s» eliminado.") % {"name": name})
        return redirect("list_players")

    played = Game.objects.filter(
        Q(player_1_local=player) | Q(player_2_local=player) |
        Q(player_1_visiting=player) | Q(player_2_visiting=player)
    ).count()
    return render(request, "confirm_delete.html", {
        "player": player,
        "games": played,
        "calls": player.calls.count(),
        "penalties": player.penalties.count(),
    })


@club_required
def show_player(request, player_id):
    """Ficha de un jugador del club con sus últimos 5 partidos cerrados. Requiere pertenecer al club."""
    player = get_object_or_404(Player, public_id=player_id, club=request.club)
    games = Game.objects.filter(
        (Q(player_1_local=player) | Q(player_2_local=player) |
        Q(player_1_visiting=player) | Q(player_2_visiting=player)) &
        Q(draft_mode=False)
    ).select_related(
        'match__local', 'match__visiting',
        'player_1_local', 'player_2_local', 'player_1_visiting', 'player_2_visiting',
    ).order_by('-match__start_date')[:5]
    games = list(games)
    form = ["w" if player_won(game, player) else "l" for game in games]
    return render(request, "player_detail.html", {"player": player, "games": games, "form": form})


def player_won(game, player):
    """True si ``player`` ganó el juego ``game`` (jugó en la pareja ganadora)."""
    if game.winner == 'Local':
        return player in (game.player_1_local, game.player_2_local)
    return player in (game.player_1_visiting, game.player_2_visiting)


@club_admin_required
def manage_roster(request):
    """Marca de una vez qué jugadores están en el equipo."""
    players = Player.objects.filter(club=request.club).order_by('name', 'last_name')

    if request.method == "POST":
        in_team_ids = {int(i) for i in request.POST.getlist('in_team') if i.isdigit()}
        joined = players.filter(id__in=in_team_ids, in_team=False).update(in_team=True)
        left = players.exclude(id__in=in_team_ids).filter(in_team=True).update(in_team=False)
        if joined or left:
            joined_text = ngettext("%(n)s alta", "%(n)s altas", joined) % {"n": joined}
            left_text = ngettext("%(n)s baja", "%(n)s bajas", left) % {"n": left}
            messages.success(request, _("Plantilla actualizada: %(joined)s y %(left)s.") % {"joined": joined_text, "left": left_text})
        else:
            messages.info(request, _("No había cambios que guardar."))
        return redirect('manage_roster')

    return render(request, 'manage_roster.html', {
        'players': players,
        'in_team_count': sum(p.in_team for p in players),
    })


@club_admin_required
def snp_account(request):
    """
    Cuenta SNP del capitán: con ella se descargan cada semana los puntos SNP de los jugadores.
    Con la cuenta guardada se muestra una tarjeta con el usuario y la contraseña oculta; el
    formulario solo aparece al pulsar «Editar» (``?edit=1``), si todavía no hay cuenta o si
    lo enviado no es válido.
    """
    account = SnpAccount.objects.filter(club=request.club).first()
    username = None
    if account:
        try:
            username = account.username
        except DecryptionError:
            if request.method != "POST":
                messages.error(request, _("No se ha podido leer la cuenta guardada (¿ha cambiado la clave de cifrado?). Vuelve a introducirla."))
    if request.method == "POST":
        form = SnpAccountForm(request.POST, has_password=account is not None)
        if form.is_valid():
            account = account or SnpAccount(club=request.club)
            account.username = form.cleaned_data["username"]
            if form.cleaned_data["password"]:
                account.password = form.cleaned_data["password"]
            # El equipo ya no se pide: si la cuenta tiene varios, se elige por el nombre del equipo del club.
            account.team_id = ""
            account.updated_by = request.user
            account.save()
            messages.success(request, _("Cuenta SNP guardada. Los puntos se actualizarán cada lunes por la noche."))
            return redirect("snp_account")
    else:
        initial = {"username": username} if account else {}
        form = SnpAccountForm(initial=initial, has_password=account is not None)
    editing = account is None or username is None or request.method == "POST" or request.GET.get("edit") == "1"
    return render(request, "snp_account.html", {
        "form": form, "account": account, "username": username, "editing": editing,
    })


@club_admin_required
@require_POST
def snp_account_password(request):
    """
    Contraseña de SNP guardada, en JSON, para enseñarla en la tarjeta de la cuenta al pulsar
    el ojo. Solo capitanes y por POST: así no queda escrita en la página ni en el historial.
    """
    account = get_object_or_404(SnpAccount, club=request.club)
    try:
        return JsonResponse({"password": account.password})
    except DecryptionError:
        return JsonResponse({"error": _("No se ha podido leer la contraseña guardada.")}, status=409)


@club_admin_required
@require_POST
def snp_account_delete(request):
    """Borra la cuenta SNP del club. Solo capitanes y por POST; vuelve a la página de la cuenta SNP."""
    SnpAccount.objects.filter(club=request.club).delete()
    messages.success(request, _("Cuenta SNP borrada."))
    return redirect("snp_account")


# ---------- «Completar equipo» con los jugadores de SNP ----------

# Aviso tras traer jugadores de SNP: llegan sin posición en pista.
POSITION_NOTICE = gettext_lazy(
    "¡Ya tienes a tus jugadores! SNP no dice en qué lado juega cada uno, así que su posición en pista "
    "ha quedado vacía. Cuando puedas, edita cada jugador y elige su posición: así las parejas y las "
    "alineaciones te saldrán mucho mejor."
)

# Tras varios fallos seguidos de «Completar equipo»: la opción se oculta y el personal revisa el proceso.
BLOCKED_NOTICE = gettext_lazy(
    "«Completar equipo» ha fallado varias veces, así que ya no se ofrece. Hemos avisado al administrador "
    "de Zyra para que revise el proceso; no hace falta que hagas nada más."
)


def _web_import_closed(request):
    """
    True (y deja un mensaje) si la web ya no ofrece «Completar equipo» al club: porque ya se hizo
    una vez o porque ha fallado varias veces y se avisó al personal.
    """
    if snp_import.web_import_done(request.club):
        messages.error(request, _("El equipo ya se completó desde SNP. A partir de ahora se actualiza solo."))
        return True
    if snp_import.web_blocked(request.club):
        messages.error(request, BLOCKED_NOTICE)
        return True
    return False


@club_admin_required
@require_POST
def complete_team_start(request):
    """
    Lanza en segundo plano la búsqueda de «Completar equipo». Solo capitanes y por POST.
    Hace falta cuenta SNP; no se lanza si ya se completó una vez, está bloqueado por fallos, hay otra en curso o se
    han hecho demasiadas búsquedas seguidas (snp_import.search_limit).

    Desde la portada (``from=home``, botón «Reintentar» tras un fallo en el alta del club) se comporta como en
    el alta: confirma sola lo encontrado y lleva a la espera de «Trayendo tu equipo». Si no, redirige a la
    lista de jugadores, que va preguntando el estado.
    """
    from_home = request.POST.get("from") == "home"
    back = "home" if from_home else "list_players"
    if not SnpAccount.objects.filter(club=request.club).exists():
        messages.error(request, _("Primero registra la cuenta SNP del capitán."))
        return redirect("snp_account")
    if not snp_service.is_enabled():
        messages.error(request, snp_service.UNAVAILABLE_MESSAGE)
        return redirect(back)
    if _web_import_closed(request) or snp_import.active_import(request.club):
        return redirect(back)
    wait = snp_import.search_limit(request.club)
    if wait:
        messages.error(request, _("Has buscado tu equipo en SNP varias veces seguidas. Para no saturar SNP, "
                                  "podrás volver a intentarlo a partir del %(date)s.")
                       % {"date": f"{timezone.localtime(wait):%d/%m/%Y %H:%M}"})
        return redirect(back)
    team_import = snp_import.start_search(request.club, request.user, auto_confirm=from_home)
    if from_home:
        return redirect("complete_team_welcome", import_id=team_import.public_id)
    return redirect("list_players")


@club_admin_required
def complete_team_status(request, import_id):
    """Estado en JSON de una búsqueda de «Completar equipo» (lo consulta la lista). Solo capitanes."""
    team_import = get_object_or_404(SnpTeamImport, public_id=import_id, club=request.club)
    data = {"status": team_import.status, "message": team_import.message, "redirect": ""}
    if team_import.status == SnpTeamImport.ERROR and team_import.error_kind in (SnpScrapeError.ACCOUNT, SnpScrapeError.TEAM):
        data["redirect"] = reverse("complete_team_failed", args=[team_import.public_id])
    return JsonResponse(data)


@club_admin_required
@require_GET
def complete_team_failed(request, import_id):
    """
    Lleva al capitán a donde puede arreglar el fallo de «Completar equipo», con el motivo:
    a la cuenta SNP si SNP no acepta la cuenta, o a la edición de su equipo si no se
    encuentran jugadores. Solo capitanes.
    """
    team_import = get_object_or_404(SnpTeamImport, public_id=import_id, club=request.club, status=SnpTeamImport.ERROR)
    reason = _("No se ha podido leer el equipo de SNP: %(message)s") % {"message": team_import.message}
    own = request.club.own_team
    if team_import.error_kind == SnpScrapeError.TEAM and own:
        hint = _("Comprueba que la configuración de tu equipo es correcta, sobre todo la nacionalidad: decide en qué país de SNP se buscan tus jugadores.")
        destination = reverse("edit_team", args=[own.public_id])
    elif team_import.error_kind == SnpScrapeError.ACCOUNT:
        hint = _("Revisa el usuario, la contraseña y el equipo de tu cuenta SNP.")
        destination = reverse("snp_account") + "?edit=1"
    else:
        hint = _("Comprueba que la configuración de tu equipo es correcta.")
        destination = reverse("list_players")
    messages.error(request, f"{reason} {hint}")
    if snp_import.web_blocked(request.club):
        messages.warning(request, BLOCKED_NOTICE)
    return redirect(destination)


@club_admin_required
@require_POST
def complete_team_confirm(request, import_id):
    """
    Confirma una búsqueda de «Completar equipo» lista para confirmar: crea los jugadores
    nuevos y actualiza los puntos SNP de los que ya estaban. Solo capitanes y por POST;
    solo si no se completó ya desde la web. Redirige a la lista de jugadores.
    """
    team_import = get_object_or_404(SnpTeamImport, public_id=import_id, club=request.club, source=SnpTeamImport.WEB)
    if team_import.status != SnpTeamImport.READY or not snp_import.has_changes(team_import) or _web_import_closed(request):
        return redirect("list_players")
    team_import = snp_import.confirm(team_import)
    messages.success(request, _("Equipo completado: %(message)s") % {"message": team_import.message})
    if team_import.created_players:
        messages.info(request, POSITION_NOTICE)
    return redirect("list_players")


@club_admin_required
@require_POST
def complete_team_cancel(request, import_id):
    """Cancela la búsqueda de «Completar equipo» en curso o pendiente. Solo capitanes y por POST."""
    SnpTeamImport.objects.filter(
        public_id=import_id, club=request.club, source=SnpTeamImport.WEB, status__in=[SnpTeamImport.RUNNING, SnpTeamImport.READY],
    ).update(status=SnpTeamImport.CANCELLED)
    return redirect("list_players")


@club_admin_required
@require_GET
def complete_team_welcome(request, import_id):
    """
    Equipo traído de SNP al registrar el club. Mientras se busca, muestra una espera que va
    preguntando el estado; al terminar lleva al capitán a «¿Quién eres en el equipo?» para
    que enlace su cuenta a su jugador; si falla, explica el motivo y cómo seguir. Solo capitanes.
    """
    team_import = get_object_or_404(SnpTeamImport, public_id=import_id, club=request.club, source=SnpTeamImport.WEB)
    if team_import.status == SnpTeamImport.DONE:
        messages.success(request, _("¡Tu equipo ya está en Zyra! %(message)s") % {"message": team_import.message})
        if own_player(request):
            return redirect("list_players")
        return redirect(reverse("my_player") + f"?{WELCOME_PARAM}=1")
    return render(request, "complete_team_welcome.html", {"team_import": team_import})


# ---------- Perfil del propio jugador ----------

# «¿Quién eres en el equipo?» recién traído el equipo de SNP al registrar el club.
WELCOME_PARAM = "bienvenida"

def own_player(request):
    """Jugador enlazado a la cuenta del usuario en el club activo (o None)."""
    return Player.objects.filter(club=request.club, user=request.user).first()


@club_required
def my_player(request):
    """
    «Mi jugador». Sin jugador enlazado: lista de jugadores del club para elegir «Soy yo»
    (los que ya tienen cuenta aparecen apagados y no se pueden elegir), con confirmación,
    o formulario para crear el suyo si no está. Con jugador enlazado: edita su posición,
    mano hábil y foto (el nombre y la temporada los cambia el capitán).
    """
    player = own_player(request)
    if player:
        form = OwnPlayerForm(request.POST or None, request.FILES or None, instance=player)
        form.uploader = request.user
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, _("Perfil actualizado."))
            return redirect("show_player", player_id=player.public_id)
        return render(request, "my_player.html", {"player": player, "form": form})

    new_form = NewOwnPlayerForm(request.POST or None, request.FILES or None, club=request.club)
    new_form.uploader = request.user
    if request.method == "POST" and new_form.is_valid():
        with transaction.atomic():
            if own_player(request):  # se ha enlazado en otra pestaña mientras tanto
                return redirect("my_player")
            player = new_form.save(commit=False)
            player.club = request.club
            player.team = request.club.own_team
            player.user = request.user
            player.save()
        messages.success(request, _("Jugador creado y enlazado a tu cuenta."))
        return redirect("show_player", player_id=player.public_id)

    # Todos los jugadores del club: primero los que se pueden elegir (sin cuenta, se ven en
    # lima) y después los ya enlazados (apagados). El buscador filtra la lista mientras se
    # escribe; ``q`` queda para quien navega sin JavaScript.
    search = request.GET.get("q", "").strip()
    candidates = (
        Player.objects.filter(club=request.club)
        .annotate(linked=ExpressionWrapper(Q(user__isnull=False), output_field=BooleanField()))
        .order_by("linked", "-in_team", "name", "last_name")
    )
    if search:
        candidates = candidates.filter(Q(name__icontains=search) | Q(last_name__icontains=search))
    return render(request, "link_player.html", {
        "candidates": candidates, "search": search, "new_form": new_form,
        "show_new": request.method == "POST",
        # Recién traído el equipo de SNP: se recuerda completar la posición de cada jugador.
        "position_notice": POSITION_NOTICE if request.GET.get(WELCOME_PARAM) else "",
    })


@club_required
@require_POST
def link_player(request, player_id):
    """«Soy yo»: enlaza la cuenta con un jugador del club que aún no tiene cuenta."""
    with transaction.atomic():
        player = get_object_or_404(Player.objects.select_for_update(), public_id=player_id, club=request.club)
        if own_player(request):
            messages.info(request, _("Tu cuenta ya está enlazada a un jugador."))
        elif player.user_id:
            messages.error(request, _("Ese jugador ya está enlazado a otra cuenta. Si eres tú, habla con tu capitán."))
            return redirect("my_player")
        else:
            player.user = request.user
            player.save(update_fields=["user"])
            # Quien se registró con SNP no escribió su nombre: la cuenta toma el del jugador.
            if not (request.user.first_name or request.user.last_name):
                request.user.first_name, request.user.last_name = player.name, player.last_name
                request.user.save(update_fields=["first_name", "last_name"])
            messages.success(request, _("Tu cuenta está enlazada a %(player)s.") % {"player": player.short_name})
    return redirect("my_player")


@club_admin_required
@require_POST
def unlink_player(request, player_id):
    """El capitán quita el enlace entre un jugador y su cuenta (por si alguien se equivocó)."""
    player = get_object_or_404(Player, public_id=player_id, club=request.club)
    player.user = None
    player.save(update_fields=["user"])
    messages.success(request, _("%(player)s ya no está enlazado a ninguna cuenta.") % {"player": player.short_name})
    return redirect("edit_player", player_id=player.public_id)
