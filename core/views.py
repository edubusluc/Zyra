"""
Vistas generales de Zyra: portada, inicio de sesión, páginas de error, alta de club,
cambio de club activo, gestión de miembros e invitaciones.
"""
import datetime
from urllib.parse import urlencode

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.forms import Select
from django.forms.utils import ErrorDict
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.conf import settings
from django.contrib.staticfiles import finders
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from data_analyse import my_form as my_form_stats, pairs as pair_stats
from call.models import Call
from match.models import Match
from match.phase import phases_for, player_status
from players.models import Player, SnpAccount, current_season

from .adapters import GOOGLE_NEW_ACCOUNT_KEY
from .blocklist import is_user_blocked
from .decorators import club_admin_required, club_manager_required, club_required
from .emails import send_invitation_email, send_welcome_email
from . import guides, season_prep
from .forms import CaptainPlayerForm, CaptainSnpForm, ClubForm, EmailChangeForm, InviteMemberForm, SignUpForm
from .middleware import SESSION_KEY
from .models import REPORT_SCOPES, Invitation, Membership, UserPreference
from .onboarding import onboarding_for
from . import email_verification, ratelimit, seo
from players import snp_service
from .unsubscribe import user_from_result_token, user_from_token
from .services import (
    CaptaincyError, InvitationError, accept_invitation, account_delete_blocker, club_name_matches, club_of,
    create_club, delete_account, delete_club, eligible_successors, is_last_admin, is_only_member,
    ManagerError, remove_membership, set_manager, transfer_captaincy,
)

INVITATIONS_PER_PAGE = 10
# Filas del bloque «Pendiente» del inicio: el resto se ve en el listado de enfrentamientos.
HOME_PENDING_ROWS = 3

# Invitación pendiente de aceptar mientras el visitante inicia sesión con Google
PENDING_INVITE_KEY = "pending_invitation"
# Parámetro con el que el botón de Google del alta de club vuelve a register_club
FROM_GOOGLE_PARAM = "google"
# Hay varios backends de autenticación (usuario/email y Google): al iniciar sesión
# justo después de registrarse hay que indicar cuál se usa.
LOGIN_BACKEND = "django.contrib.auth.backends.ModelBackend"

User = get_user_model()

# Inicio de sesión: tras LOGIN_MAX_FAILURES contraseñas erróneas seguidas para el mismo
# usuario desde la misma IP, se bloquea durante LOGIN_LOCKOUT_SECONDS.
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

# Límites por IP (core/ratelimit.py): altas de club, altas de cuenta por invitación y
# comprobaciones de contraseña mientras se escribe.
REGISTER_LIMIT, REGISTER_WINDOW = 5, 60 * 60
INVITE_SIGNUP_LIMIT, INVITE_SIGNUP_WINDOW = 10, 60 * 60
PASSWORD_CHECK_LIMIT, PASSWORD_CHECK_WINDOW = 60, 60
RESEND_LIMIT, RESEND_WINDOW = 5, 60 * 60
DELETE_ACCOUNT_LIMIT, DELETE_ACCOUNT_WINDOW = 5, 60 * 60


def email_needs_confirmation(user):
    """True si la cuenta tiene email por confirmar (las de Google no tienen contraseña y nacen verificadas)."""
    return bool(user.email) and user.has_usable_password() and not email_verification.is_verified(user)


@require_safe
def home(request):
    """Portada del club: logo, próximo partido y jugador/pareja en racha."""
    if not request.user.is_authenticated:
        return render(request, 'landing.html', {
            'faq': seo.landing_faq(),
            'guides': [(g, g.title_for(guides.language_code())) for g in guides.GUIDES],
            'structured_data': seo.landing_structured_data(request),
        })
    if request.club is None:
        return redirect('no_club')

    club = request.club
    today = datetime.date.today()
    # Actas abiertas, las más antiguas primero: las pasadas son lo que se quedó a medias (H-02).
    open_matches = list(Match.objects.filter(club=club, draft_mode=True).select_related('local', 'visiting')
                        .order_by('start_date', 'id')[:30])
    phases = phases_for(open_matches)
    next_match = next((m for m in open_matches if m.start_date >= today), None)
    pending = []
    if request.membership.can_manage:
        pending = [{"match": m, "phase": phases[m.id], "overdue": m.start_date < today} for m in open_matches]
    my_status = None
    my_player = Player.objects.filter(club=club, user=request.user).first()
    if next_match and my_player:
        games = list(next_match.games.select_related('player_1_local', 'player_2_local',
                                                     'player_1_visiting', 'player_2_visiting'))
        call = Call.objects.filter(match=next_match).first()
        my_status = player_status(my_player, call, games)
    players = Player.objects.filter(club=club, in_team=True)
    hot_player, hot_pair = pair_stats.hot_streaks(pair_stats.club_game_log(club), players)

    my_form_hidden = bool(my_player) and UserPreference.my_form_is_hidden(request.user)
    my_form_data = my_form_stats.my_form(club, my_player) if my_player and not my_form_hidden else None

    onboarding = onboarding_for(request.membership)
    # «Prepara la temporada» (julio-octubre) lleva dentro el paso de SNP: no se repite la tarea suelta.
    prep = season_prep.season_prep_for(request.membership)
    snp_sync = None
    if request.membership.is_admin and prep is None:
        from players import snp_import
        snp_sync = snp_import.sync_task(club)
    return render(request, 'home.html', {
        'email_unverified': email_needs_confirmation(request.user),
        'snp_sync': snp_sync,
        'own_team': club.own_team,
        'season': current_season(),
        'next_match': next_match,
        'pending': pending[:HOME_PENDING_ROWS],
        'pending_total': len(pending),
        'my_player': my_player,
        'my_form': my_form_data,
        'my_form_hidden': my_form_hidden,
        'my_status': my_status,
        'days_left': (next_match.start_date - today).days if next_match else None,
        'hot_player': hot_player,
        'hot_pair': hot_pair,
        # Aviso al capitán mientras no haya registrado la cuenta SNP del club (si se muestran los
        # primeros pasos, la tarea de SNP ya va dentro de la lista).
        'season_prep': prep,
        'snp_missing': (request.membership.is_admin and onboarding is None and prep is None
                        and not SnpAccount.objects.filter(club=club).exists()),
        # Primeros pasos del capitán (core.onboarding): solo se ve el siguiente; el resto, plegado.
        'onboarding': onboarding,
        'manager_welcome': request.membership.is_manager and request.membership.manager_welcome_pending,
        # Aviso al capitán sobre el rol de gestor, hasta que lo cierre.
        'manager_tip': request.membership.is_admin and UserPreference.manager_tip_pending(request.user),
        'onboarding_done': sum(step["done"] for step in onboarding) if onboarding else 0,
        'onboarding_percent': round(100 * sum(step["done"] for step in onboarding) / len(onboarding)) if onboarding else 0,
        'onboarding_next': next((step for step in onboarding if not step["done"]), None) if onboarding else None,
    })


@club_required
@require_safe
def member_welcome(request):
    """
    Bienvenida de una pantalla tras aceptar una invitación: quién es su capitán, a qué equipo se ha
    unido y cuál es su próxima convocatoria; si su cuenta aún no está enlazada a una ficha de
    jugador, el botón principal lleva a elegirla («¿Quién eres en el equipo?»).
    """
    club = request.club
    captains = [m.user.get_full_name().strip() or m.user.username
                for m in club.memberships.filter(role=Membership.ADMIN).select_related("user")]
    today = datetime.date.today()
    next_match = (Match.objects.filter(club=club, draft_mode=True, start_date__gte=today)
                  .select_related("local", "visiting").order_by("start_date", "id").first())
    my_player = Player.objects.filter(club=club, user=request.user).first()
    my_status = None
    if next_match and my_player:
        games = list(next_match.games.select_related("player_1_local", "player_2_local",
                                                     "player_1_visiting", "player_2_visiting"))
        my_status = player_status(my_player, Call.objects.filter(match=next_match).first(), games)
    return render(request, "welcome_member.html", {
        "captains": captains, "own_team": club.own_team, "next_match": next_match,
        "my_player": my_player, "my_status": my_status,
    })


@club_admin_required
@require_POST
def dismiss_onboarding(request):
    """El capitán cierra la lista de primeros pasos de la portada (solo POST)."""
    request.club.onboarding_dismissed_at = timezone.now()
    request.club.save(update_fields=["onboarding_dismissed_at"])
    return redirect("home")


@club_required
@require_POST
def toggle_my_form(request):
    """Oculta o vuelve a mostrar la tarjeta «Mi forma» del Inicio a quien la pulsa (POST, ``hide`` = 1 o 0)."""
    UserPreference.objects.update_or_create(
        user=request.user, defaults={"my_form_hidden": request.POST.get("hide") == "1"})
    return redirect("home")


@club_admin_required
@require_POST
def dismiss_manager_tip(request):
    """El capitán cierra el aviso «Añade un gestor» de la portada para siempre (solo POST)."""
    UserPreference.objects.update_or_create(user=request.user, defaults={"manager_tip_dismissed_at": timezone.now()})
    return redirect("home")


@club_manager_required
@require_POST
def dismiss_manager_welcome(request):
    """El gestor cierra la bienvenida a sus nuevas funciones de la portada (solo POST)."""
    Membership.objects.filter(pk=request.membership.pk).update(manager_welcome_pending=False)
    return redirect("home")


class ThrottledLoginView(LoginView):
    """
    LoginView de Django con freno a los ataques de fuerza bruta: sin él se podían probar
    contraseñas sin límite. (El login de allauth, /accounts/login/, ya tiene el suyo.)
    """

    def _key(self):
        """Clave de caché del contador de fallos: IP y usuario escrito."""
        username = (self.request.POST.get("username") or "").strip().lower()
        return f"login-failures:{ratelimit.client_ip(self.request)}:{username}"

    def post(self, request, *args, **kwargs):
        """Con demasiados fallos seguidos responde 429 sin comprobar la contraseña."""
        if ratelimit.get_count(self._key()) >= LOGIN_MAX_FAILURES:
            # Sin validar el formulario: validarlo comprobaría la contraseña.
            form = self.get_form()
            form._errors, form.cleaned_data = ErrorDict(), {}
            form.add_error(None, _("Demasiados intentos fallidos. Espera 15 minutos y vuelve a intentarlo."))
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        """Suma un fallo al contador (caduca a los LOGIN_LOCKOUT_SECONDS)."""
        ratelimit.add_hit(self._key(), LOGIN_LOCKOUT_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        """Inicio de sesión correcto: pone a cero el contador de fallos."""
        ratelimit.clear(self._key())
        return super().form_valid(form)


def error_404_view(request, exception):
    """Página «No encontrado» (handler404)."""
    return render(request, '404.html', status=404)


def error_403_view(request, exception=None):
    """
    Página «Sin permiso»: el usuario ha iniciado sesión pero intenta abrir una página o
    hacer una acción reservada (por ejemplo, un miembro que entra por URL en una página
    de capitán). El motivo solo se muestra si lo da la propia aplicación.
    """
    reason = str(exception) if isinstance(exception, PermissionDenied) and exception.args else ""
    return render(request, '403.html', {'reason': reason}, status=403)


def csrf_failure(request, reason=""):
    """Formulario rechazado por la protección CSRF (caducado o enviado desde otra web)."""
    return render(request, '403.html', {
        'reason': _("No se ha podido comprobar el formulario: puede que haya caducado o que venga de otra web. "
                    "Vuelve a la página, recárgala e inténtalo de nuevo."),
        'csrf': True,
    }, status=403)


def _site_url(request):
    """URL absoluta de la raíz de la web, para los enlaces de los correos."""
    return request.build_absolute_uri("/")


def _style(*forms):
    """Añade las clases de Bootstrap (form-control / form-select) a los campos de los formularios."""
    for form in filter(None, forms):
        for field in form:
            css = 'form-select' if isinstance(field.field.widget, Select) else 'form-control'
            field.field.widget.attrs.update({'class': css})


def register_club(request):
    """
    Alta de un club nuevo. Si el visitante no tiene cuenta, se le crea una. Quien ya
    pertenece a un club (como miembro o capitán) no puede registrar otro.

    El jugador del capitán se crea con su nombre y apellidos o, si elige conectar su cuenta
    de SNP (CaptainSnpForm), se guarda la cuenta y se trae el equipo de SNP con sus puntos
    («Completar equipo» confirmado solo); al terminar elige cuál de esos jugadores es él.
    """
    anonymous = not request.user.is_authenticated

    # Vuelve de "Crear mi cuenta con Google". Si el email ya tenía cuenta, Google ha
    # iniciado sesión en ella: no es un alta nueva, así que va a su portada.
    if not anonymous and request.GET.get(FROM_GOOGLE_PARAM):
        if request.session.pop(GOOGLE_NEW_ACCOUNT_KEY, False):
            return redirect("register_club")
        messages.info(request, _("Ya tenías una cuenta con este email. Has iniciado sesión con ella."))
        return redirect("home")

    # Una cuenta solo puede pertenecer a un club.
    current = None if anonymous else club_of(request.user)
    if current is not None:
        messages.error(request, _("Ya perteneces a %(club)s y solo se puede pertenecer a un club. "
                                  "Abandona ese club antes de registrar otro.") % {"club": current.name})
        return redirect("home")

    # Nombre y apellidos para el jugador del capitán. Con Google vienen de su perfil si
    # los tiene; si falta alguno, se avisa de que hay que escribirlos.
    known = {} if anonymous else {"name": request.user.first_name.strip(), "last_name": request.user.last_name.strip()}
    google_missing_name = (
        not anonymous and not all(known.values())
        and SocialAccount.objects.filter(user=request.user, provider="google").exists()
    )

    if request.method == "POST":
        if ratelimit.too_many(request, "register", REGISTER_LIMIT, REGISTER_WINDOW):
            return render(request, "429.html", status=429)
        club_form = ClubForm(request.POST)
        player_form = CaptainPlayerForm(request.POST, prefix="player")
        snp_form = CaptainSnpForm(request.POST, prefix="snp")
        user_form = SignUpForm(request.POST) if anonymous else None
        # Con SNP no hace falta escribir el nombre: el jugador se elige después de entre los de SNP.
        valid = all([club_form.is_valid(), snp_form.is_valid(), snp_form.uses_snp or player_form.is_valid(),
                     user_form is None or user_form.is_valid()])
        # Un email bloqueado por el personal (p. ej. de un club suspendido) no puede crear clubes.
        if valid and not anonymous and is_user_blocked(request.user):
            club_form.add_error(None, _("Tu email está bloqueado en Zyra y no puede crear clubes."))
            valid = False
        if valid:
            use_snp = snp_form.uses_snp
            try:
                with transaction.atomic():
                    user = user_form.save() if anonymous else request.user
                    data = club_form.cleaned_data
                    player = {} if use_snp else player_form.cleaned_data
                    club = create_club(data["name"], data["location"], user, gender=data["gender"], country=data["country"],
                                       division=data["division"], player_name=player.get("name", ""),
                                       player_last_name=player.get("last_name", ""))
                    # La cuenta se queda con el nombre del jugador si no tenía uno.
                    if player and not (user.first_name or user.last_name):
                        user.first_name, user.last_name = player["name"], player["last_name"]
                        user.save(update_fields=["first_name", "last_name"])
                    if use_snp:
                        account = SnpAccount(club=club, updated_by=user)
                        account.username = snp_form.cleaned_data["username"].strip()
                        account.password = snp_form.cleaned_data["password"]
                        account.save()
            except IntegrityError:
                # Doble envío o dos registros a la vez: otro proceso creó ese usuario o email entre la validación y el guardado.
                if not anonymous or not user_form.report_taken():
                    raise
                valid = False
            if valid:
                if anonymous:
                    login(request, user, backend=LOGIN_BACKEND)
                    email_verification.start_verification(request, user)
                request.session[SESSION_KEY] = club.id
                send_welcome_email(user, club, created=True, site_url=_site_url(request))
                messages.success(request, _("Club %(club)s creado correctamente.") % {"club": club.name})
                if use_snp and snp_service.is_enabled():
                    from players import snp_import
                    team_import = snp_import.start_search(club, user, auto_confirm=True)
                    return redirect("complete_team_welcome", import_id=team_import.public_id)
                if use_snp:
                    messages.warning(request, snp_service.UNAVAILABLE_MESSAGE)
                    return redirect("my_player")
                return redirect("home")
    else:
        club_form = ClubForm()
        player_form = CaptainPlayerForm(initial=known, prefix="player")
        snp_form = CaptainSnpForm(prefix="snp")
        user_form = SignUpForm() if anonymous else None

    _style(club_form, user_form, player_form)
    for name in ("username", "password"):
        snp_form.fields[name].widget.attrs["class"] = "form-control"
    return render(request, "register_club.html", {
        "club_form": club_form, "user_form": user_form, "player_form": player_form, "snp_form": snp_form,
        "google_missing_name": google_missing_name, "snp_service_off": not snp_service.is_enabled(),
        "google_next": f"{reverse('register_club')}?{FROM_GOOGLE_PARAM}=1",
    })


@require_safe
def register(request):
    """
    Primera pantalla del registro: elegir entre unirse como jugador (cuenta sin club,
    ``register_account``) o registrarse como capitán (crear el club, ``register_club``).
    Quien ya tiene sesión no la necesita y va a su portada.
    """
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "register_choose.html")


@require_http_methods(["GET", "POST"])
def register_account(request):
    """
    Alta de una cuenta sin club, para quien espera a que un capitán lo invite (enlace
    compartido o email). Quien ya tiene sesión no se registra de nuevo: va a su portada
    o, si no tiene club, a la página de espera. Más tarde puede registrar un club
    (``register_club``) o aceptar una invitación.
    """
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        if ratelimit.too_many(request, "register-account", REGISTER_LIMIT, REGISTER_WINDOW):
            return render(request, "429.html", status=429)
        form = SignUpForm(request.POST)
        user = None
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
            except IntegrityError:
                if not form.report_taken():
                    raise
        if user is not None:
            login(request, user, backend=LOGIN_BACKEND)
            email_verification.start_verification(request, user)
            messages.success(request, _("Cuenta creada. Ya puedes unirte a un club cuando te inviten."))
            return redirect("no_club")
    else:
        form = SignUpForm()
    _style(form)
    return render(request, "register_account.html", {"form": form, "google_next": reverse("no_club")})


@login_required
@require_safe
def no_club(request):
    """
    Página para quien ha iniciado sesión pero no tiene club activo (requiere sesión).

    Explica cómo unirse o registrar un club y lista sus clubes suspendidos. Si ya tiene
    club, redirige a la portada.
    """
    if request.club is not None:
        return redirect("home")
    return render(request, "no_club.html", {"suspended_clubs": request.suspended_clubs})


@login_required
@require_POST
def switch_club(request):
    """
    Cambia el club activo del usuario (requiere sesión; solo POST con ``club_id``).

    Solo admite clubes de los que es miembro (si no, 404) y redirige a la portada.
    """
    club_id = request.POST.get("club_id", "")
    if not club_id.isdigit():
        raise Http404
    membership = get_object_or_404(Membership, user=request.user, club_id=club_id)
    request.session[SESSION_KEY] = membership.club_id
    return redirect("home")


@club_required
@require_safe
def club_home(request):
    """
    «Club»: acceso único a lo que se configura una vez y no cada semana (H-14, H-38): miembros
    e invitaciones y cuenta SNP (solo capitanes), el equipo propio y los rivales. Los miembros
    ven el equipo propio y los rivales; los capitanes, además, los dos enlaces de gestión.
    """
    club = request.club
    return render(request, "club.html", {
        "own_team": club.own_team,
        "rivals_count": club.teams.filter(is_own=False, in_group=True).count(),
        "members_count": club.memberships.count(),
        "snp_account": SnpAccount.objects.filter(club=club).first() if request.membership.is_admin else None,
    })


@club_admin_required
def club_members(request, invite_form=None):
    """
    Página de miembros del club (solo capitanes, club_admin_required).

    Muestra los miembros con su rol, el formulario de invitación y las invitaciones
    pendientes, paginadas y filtrables por email (parámetro ``q``). create_invitation
    la reutiliza con ``invite_form`` para mostrar los errores del formulario.
    """
    club = request.club
    invite_form = invite_form or InviteMemberForm(club=club)
    _style(invite_form)
    memberships = club.memberships.select_related("user").order_by("user__username")
    pending = club.invitations.pending()
    has_invitations = pending.exists()
    search = request.GET.get("q", "").strip()
    if search:
        pending = pending.filter(email__icontains=search)
    page = Paginator(pending.order_by("-created_at", "-id"), INVITATIONS_PER_PAGE).get_page(request.GET.get("page"))
    # (invitación, enlace, texto para compartir por WhatsApp). El texto se monta aquí, sin HTML,
    # y la plantilla solo lo codifica para la URL.
    invitations = []
    for inv in page:
        url = request.build_absolute_uri(reverse("invitation", args=[inv.token]))
        invitations.append((inv, url, _("Únete a %(club)s en Zyra: %(url)s") % {"club": club.name, "url": url}))
    extra = ("&" + urlencode({"q": search}) if search else "") + "#invitaciones"
    return render(request, "club_members.html", {
        "invite_form": invite_form, "memberships": memberships, "invitations": invitations,
        "successor_ids": set(eligible_successors(club).values_list("pk", flat=True)),
        "managers_full": club.memberships.filter(role=Membership.MANAGER).count() >= Membership.MAX_MANAGERS,
        "invitations_page": page, "has_invitations": has_invitations, "search": search, "extra": extra,
    })


@club_admin_required
@require_POST
def create_invitation(request):
    """
    El capitán invita a un jugador por email. Las cuentas las crea cada jugador
    desde el enlace; el capitán ya no puede crear usuarios. Volver a invitar al
    mismo email sustituye la invitación pendiente por una nueva.
    """
    club = request.club
    form = InviteMemberForm(request.POST, club=club)
    if not form.is_valid():
        return club_members(request, invite_form=form)

    email = form.cleaned_data["email"]
    club.invitations.filter(email__iexact=email, used_at__isnull=True).delete()
    invitation = Invitation.objects.create(club=club, created_by=request.user, email=email)
    url = request.build_absolute_uri(reverse("invitation", args=[invitation.token]))
    if send_invitation_email(invitation, url):
        messages.success(request, _("Invitación enviada a %(email)s. El enlace caduca en 24 horas.") % {"email": email})
    else:
        invitation.delete()
        messages.error(request, _("No se pudo enviar el correo a %(email)s. Inténtalo de nuevo más tarde.") % {"email": email})
    return redirect(reverse("club_members") + "#invitaciones")


@club_admin_required
@require_POST
def create_invitation_link(request):
    """
    Invitación sin email: el capitán copia el enlace y lo comparte (por WhatsApp, por
    ejemplo). Sirve para todas las personas que lo usen hasta que caduque o se anule.
    Solo vale el último enlace: al generar uno nuevo, el anterior deja de funcionar (se
    marca como caducado, así se conserva quién se unió con él).
    """
    with transaction.atomic():
        replaced = request.club.invitations.pending().filter(reusable=True).update(expires_at=timezone.now())
        Invitation.objects.create(club=request.club, created_by=request.user, reusable=True)
    if replaced:
        messages.success(request, _("Enlace nuevo creado: el anterior ya no funciona. Cópialo y compártelo. "
                                    "Lo pueden usar varias personas y caduca en 24 horas."))
    else:
        messages.success(request, _("Enlace creado: cópialo y compártelo. Lo pueden usar varias personas y caduca en 24 horas."))
    return redirect(reverse("club_members") + "#invitaciones")


@club_admin_required
@require_POST
def revoke_invitation(request, invitation_id):
    """
    Anula una invitación pendiente del club (solo capitanes, solo POST).

    Redirige a la lista de invitaciones de la página de miembros.
    """
    get_object_or_404(Invitation.objects.pending(), public_id=invitation_id, club=request.club).delete()
    messages.success(request, _("Invitación anulada."))
    return redirect(reverse("club_members") + "#invitaciones")


@require_POST
def password_check(request):
    """
    Comprueba, mientras se escribe, las reglas de contraseña que solo conoce el
    servidor (parecido al usuario/email y contraseñas comunes) para la lista de
    requisitos de los formularios de registro. Solo responde sí/no por regla.
    """
    if ratelimit.too_many(request, "password-check", PASSWORD_CHECK_LIMIT, PASSWORD_CHECK_WINDOW):
        return JsonResponse({"error": "rate_limited"}, status=429)
    user = User(username=request.POST.get("username", ""), email=request.POST.get("email", ""))
    codes = set()
    try:
        validate_password(request.POST.get("password", ""), user)
    except ValidationError as exc:
        codes = {error.code for error in exc.error_list}
    return JsonResponse({
        "similar": "password_too_similar" not in codes,
        "common": "password_too_common" not in codes,
    })


def _join(request, invitation, user):
    """Acepta la invitación para ``user``; devuelve True si ha entrado en el club."""
    try:
        membership = accept_invitation(invitation, user)
    except InvitationError as exc:
        messages.error(request, str(exc))
        return False
    request.session[SESSION_KEY] = membership.club_id
    send_welcome_email(user, membership.club, site_url=_site_url(request))
    messages.success(request, _("¡Bienvenido a %(club)s!") % {"club": membership.club.name})
    return True


def invitation(request, token):
    """
    Enlace de invitación. Un visitante sin cuenta se registra con usuario, email y
    contraseña (o con Google); quien ya tiene sesión iniciada se une con un clic.
    """
    invitation = Invitation.objects.select_related("club").filter(token=token).first()
    if invitation is None or not invitation.is_valid:
        request.session.pop(PENDING_INVITE_KEY, None)
        return render(request, "invitation_invalid.html", {"invitation": invitation}, status=410)
    club = invitation.club

    if request.user.is_authenticated:
        if Membership.objects.filter(user=request.user, club=club).exists():
            request.session.pop(PENDING_INVITE_KEY, None)
            request.session[SESSION_KEY] = club.id
            messages.info(request, _("Ya eres miembro de %(club)s.") % {"club": club.name})
            return redirect("home")
        # Solo se puede pertenecer a un club: explica por qué no puede unirse a este.
        current = club_of(request.user)
        if current is not None:
            request.session.pop(PENDING_INVITE_KEY, None)
            return render(request, "invitation.html", {"invitation": invitation, "club": club, "current_club_name": current.name})
        # Vuelve de iniciar sesión con Google desde esta misma invitación: se une directamente.
        from_google = request.session.pop(PENDING_INVITE_KEY, None) == token
        if request.method == "POST" or from_google:
            # Tras unirse, elige su jugador en la plantilla o lo crea (players.views.my_player).
            return redirect("member_welcome" if _join(request, invitation, request.user) else "home")
        return render(request, "invitation.html", {"invitation": invitation, "club": club})

    request.session[PENDING_INVITE_KEY] = token
    if request.method == "POST":
        if ratelimit.too_many(request, "invite-signup", INVITE_SIGNUP_LIMIT, INVITE_SIGNUP_WINDOW):
            return render(request, "429.html", status=429)
        form = SignUpForm(request.POST)
        user = None
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    try:
                        accept_invitation(invitation, user)
                    except InvitationError as exc:
                        transaction.set_rollback(True)
                        messages.error(request, str(exc))
                        return redirect("invitation", token=token)
            except IntegrityError:
                # Doble envío o dos registros a la vez: ese usuario o email se creó entre la validación y el guardado.
                if not form.report_taken():
                    raise
                user = None
        if user is not None:
            request.session.pop(PENDING_INVITE_KEY, None)
            login(request, user, backend=LOGIN_BACKEND)
            # El enlace llegó a ese email: quien lo abre y se registra con él lo ha demostrado.
            email_verification.start_verification(
                request, user, verified=bool(invitation.email) and invitation.email.lower() == user.email.lower(),
            )
            request.session[SESSION_KEY] = club.id
            send_welcome_email(user, club, site_url=_site_url(request))
            messages.success(request, _("¡Bienvenido a %(club)s!") % {"club": club.name})
            return redirect("member_welcome")
    else:
        form = SignUpForm(initial={"email": invitation.email})

    _style(form)
    return render(request, "invitation.html", {"invitation": invitation, "club": club, "form": form})


@club_admin_required
@require_POST
def update_member(request, membership_id):
    """
    Antes guardaba el email propio desde la página de miembros; ya no cambia nada (solo POST).

    El email solo se cambia en «Mi perfil», que pide la contraseña actual. Esta URL se
    conserva para no romper enlaces y redirige allí. Un capitán nunca puede cambiar el email
    de otro miembro, ni el rol: la capitanía se traspasa con ``transfer_captaincy``.
    """
    get_object_or_404(Membership, public_id=membership_id, club=request.club)
    return redirect(f"{reverse('my_profile')}?edit=email")


@club_manager_required
@require_POST
def season_prep_step(request, key):
    """
    Marca un paso de «Prepara la temporada» como hecho (solo POST): la plantilla y los rivales los marca
    el capitán o un gestor; omitir el paso de SNP (``snp_skipped``), solo el capitán.
    """
    if key not in (*season_prep.MANUAL_STEPS, season_prep.SNP_SKIPPED):
        raise Http404
    if key == season_prep.SNP_SKIPPED and not request.membership.is_admin:
        raise PermissionDenied(_("Solo el capitán del club puede omitir el paso de SNP."))
    if season_prep.mark_step(request.club, key):
        messages.success(request, _("Temporada %(label)s lista. ¡A competir!")
                         % {"label": season_prep.season_label(season_prep.prep_year())})
    return redirect("home")


@club_admin_required
@require_POST
def season_prep_dismiss(request):
    """El capitán oculta «Prepara la temporada» hasta la próxima temporada (solo POST)."""
    season_prep.close(request.club)
    return redirect("home")


@club_admin_required
@require_POST
def set_manager_view(request, membership_id):
    """
    Hace gestor a un miembro (``enable=1``) o lo devuelve a miembro (``enable=0``). Solo el capitán,
    solo POST. Un club tiene como mucho dos gestores.
    """
    target = get_object_or_404(Membership.objects.select_related("user"), public_id=membership_id, club=request.club)
    enable = request.POST.get("enable") == "1"
    try:
        set_manager(request.club, request.membership, target, enable)
    except ManagerError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, (_("%(username)s es ahora gestor del club.") if enable
                                   else _("%(username)s vuelve a ser miembro.")) % {"username": target.user.username})
    return redirect("club_members")


@club_admin_required
@require_POST
def transfer_captaincy_view(request, membership_id):
    """
    Traspasa la capitanía del club al miembro elegido (solo el capitán, solo POST). El nuevo
    capitán tiene que estar enlazado a un jugador del club; el actual pasa a ser miembro.
    """
    target = get_object_or_404(Membership.objects.select_related("user"), public_id=membership_id, club=request.club)
    try:
        transfer_captaincy(request.club, request.membership, target)
    except CaptaincyError as exc:
        messages.error(request, str(exc))
        return redirect("club_members")
    messages.success(request, _("%(username)s es ahora el capitán de %(club)s. Tú sigues en el club como miembro.")
                     % {"username": target.user.username, "club": request.club.name})
    return redirect("home")


def _change_own_email(request, user, email):
    """
    Cambia el email del propio usuario y le manda el enlace para confirmarlo; devuelve el
    mensaje de error o None.
    """
    email = email.lower()
    if email == (user.email or "").lower():
        return None
    if not email:
        return _("El email es obligatorio: lo necesitas para recuperar tu contraseña y recibir los informes.")
    try:
        validate_email(email)
    except ValidationError:
        return _("'%(email)s' no es un email válido.") % {"email": email}
    if email and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
        return _("Ese email ya lo usa otra cuenta.")
    user.email = email
    user.save(update_fields=["email"])
    # El email verificado (Google) era el anterior: allauth no debe seguir dándolo por bueno.
    EmailAddress.objects.filter(user=user).exclude(email__iexact=email).delete()
    email_verification.start_verification(request, user)
    return None


@login_required
def my_profile(request):
    """
    «Mi perfil»: email y contraseña de la cuenta y, con club activo, su jugador.

    El email se cambia aquí (``?edit=email``) pidiendo la contraseña actual; la contraseña,
    en la página de allauth. Las cuentas creadas con Google y sin contraseña ven su email
    sin poder cambiarlo: lo gestiona Google. Con jugador enlazado se muestra para ir a
    editarlo; sin él, se ofrece enlazarse a uno (players.views.my_player).
    """
    user = request.user
    google_only = not user.has_usable_password()
    email_form = None
    is_captain = bool(request.membership and request.membership.is_admin)
    if request.method == "POST" and ("report_scope" in request.POST or "monthly_form" in request.POST
                                  or "results_form" in request.POST):
        defaults = {}
        scope = request.POST.get("report_scope")
        # El informe de la convocatoria es del capitán: un miembro no lo ve ni puede cambiarlo.
        if is_captain and scope in dict(REPORT_SCOPES):
            defaults["report_scope"] = scope
        if "results_form" in request.POST:
            defaults["match_result_email"] = request.POST.get("match_result_email") == "on"
        if "monthly_form" in request.POST:
            defaults["monthly_report"] = request.POST.get("monthly_report") == "on"
            if request.POST.get("monthly_scope") in dict(REPORT_SCOPES):
                defaults["monthly_scope"] = request.POST["monthly_scope"]
        if defaults:
            UserPreference.objects.update_or_create(user=user, defaults=defaults)
            messages.success(request, _("Preferencias guardadas."))
        return redirect("my_profile")
    if not google_only and (request.method == "POST" or request.GET.get("edit") == "email"):
        email_form = EmailChangeForm(request.POST or None, user=user)
        if email_form.is_valid():
            _change_own_email(request, user, email_form.cleaned_data["email"])
            messages.success(request, _("Email actualizado."))
            return redirect("my_profile")
    elif request.method == "POST":
        return redirect("my_profile")
    return render(request, "my_profile.html", {
        "google_only": google_only,
        "uses_google": SocialAccount.objects.filter(user=user, provider="google").exists(),
        "email_form": email_form,
        "is_captain": is_captain,
        "report_scopes": REPORT_SCOPES,
        "report_scope": UserPreference.report_scope_for(user),
        "monthly_report": UserPreference.monthly_for(user)[0],
        "monthly_scope": UserPreference.monthly_for(user)[1],
        "match_result_email": UserPreference.match_result_for(user),
        "player": Player.objects.filter(club=request.club, user=user).first() if request.club else None,
        "email_unverified": email_needs_confirmation(user),
    })


@login_required
@require_POST
def resend_verification(request):
    """Vuelve a enviar el enlace para confirmar el email de la cuenta (solo POST, con límite por IP)."""
    if ratelimit.too_many(request, "resend-verification", RESEND_LIMIT, RESEND_WINDOW):
        return render(request, "429.html", status=429)
    if request.user.email and not email_verification.is_verified(request.user):
        if email_verification.start_verification(request, request.user):
            messages.success(request, _("Te hemos enviado un enlace para confirmar tu email."))
        else:
            messages.error(request, _("No se pudo enviar el correo. Inténtalo de nuevo más tarde."))
    # El aviso de la portada reenvía desde allí y vuelve a ella; «Mi perfil» es el destino por defecto.
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("my_profile")


@login_required
@require_http_methods(["GET", "POST"])
def delete_account_view(request):
    """
    «Eliminar mi cuenta» (desde «Mi perfil»). Un capitán no puede hasta traspasar la capitanía a otro
    jugador enlazado (``core.services.account_delete_blocker``). Para confirmar hay que escribir la
    contraseña o, en las cuentas de Google sin contraseña, el nombre de usuario. Opcionalmente se
    elimina también su ficha de jugador; si no, la ficha se queda en el club sin cuenta ni foto.
    Después se cierra la sesión.
    """
    user = request.user
    blocker = account_delete_blocker(user)
    needs_password = user.has_usable_password()
    player = Player.objects.filter(user=user).select_related("club").first()
    error = ""
    if request.method == "POST" and not blocker:
        if ratelimit.too_many(request, "delete-account", DELETE_ACCOUNT_LIMIT, DELETE_ACCOUNT_WINDOW):
            return render(request, "429.html", status=429)
        typed = request.POST.get("confirm", "")
        confirmed = user.check_password(typed) if needs_password else typed.strip().lower() == user.username.lower()
        if not confirmed:
            error = _("La contraseña no es correcta.") if needs_password else _("Escribe tu nombre de usuario tal cual para confirmar.")
        else:
            delete_player = request.POST.get("delete_player") == "on"
            # Se cierra la sesión antes de borrar: las señales de logout necesitan al usuario guardado.
            logout(request)
            with transaction.atomic():
                delete_account(user, delete_player=delete_player)
            messages.success(request, _("Tu cuenta se ha eliminado. Gracias por haber usado Zyra."))
            return redirect("home")
    return render(request, "delete_account.html", {
        "blocker": blocker, "needs_password": needs_password, "player": player, "error": error,
    })


@require_http_methods(["GET", "POST"])
def monthly_unsubscribe(request, token):
    """
    Baja de los correos mensuales desde el enlace del email, sin iniciar sesión.

    El GET solo pide confirmación (los antivirus y clientes de correo abren los enlaces
    solos); el POST, con el token CSRF de esa página, desactiva el correo. El token firmado de
    la URL identifica a la cuenta.
    """
    user = user_from_token(token)
    if user is None:
        return render(request, "monthly_unsubscribe.html", {"invalid": True}, status=404)
    if request.method == "POST":
        UserPreference.objects.update_or_create(user=user, defaults={"monthly_report": False})
        return render(request, "monthly_unsubscribe.html", {"done": True})
    return render(request, "monthly_unsubscribe.html")


@require_http_methods(["GET", "POST"])
def result_unsubscribe(request, token):
    """
    Baja del aviso de resultado de los enfrentamientos desde el enlace del email, sin iniciar sesión.

    Igual que ``monthly_unsubscribe``: el GET solo pide confirmación y el POST, con el token CSRF de
    esa página, desactiva el aviso de la cuenta que identifica el token firmado de la URL.
    """
    user = user_from_result_token(token)
    if user is None:
        return render(request, "result_unsubscribe.html", {"invalid": True}, status=404)
    if request.method == "POST":
        UserPreference.objects.update_or_create(user=user, defaults={"match_result_email": False})
        return render(request, "result_unsubscribe.html", {"done": True})
    return render(request, "result_unsubscribe.html")


@club_admin_required
@require_POST
def remove_member(request, membership_id):
    """
    Da de baja a un miembro del club (solo capitanes, solo POST) y desenlaza su cuenta de
    su jugador, así si vuelve a entrar no sigue enlazado al de antes.

    No permite quitar al último capitán. Redirige a la página de miembros.
    """
    membership = get_object_or_404(Membership.objects.select_related("user"), public_id=membership_id, club=request.club)
    if is_last_admin(membership) and membership.user_id != request.user.id:
        messages.error(request, _("No puedes quitar al capitán: traspasa antes la capitanía."))
    elif membership.user_id == request.user.id:
        # Quitarse a uno mismo es abandonar el club: se hace desde el menú, con su aviso.
        return leave_club(request)
    else:
        remove_membership(membership)
        messages.success(request, _("%(username)s ya no es miembro del club.") % {"username": membership.user.username})
    return redirect("club_members")


@login_required
@require_POST
def leave_club(request):
    """
    El usuario abandona el club activo (solo POST; el menú pide confirmación antes).

    Se desenlaza su cuenta del jugador que tuviera en el club. El último capitán no puede
    irse si quedan otros miembros: antes tiene que nombrar a otro capitán. Si es el único
    miembro, al irse se elimina el club con todos sus datos, siempre que confirme
    escribiendo el nombre del club (campo ``confirm_name``). Después pasa a otro de sus
    clubes o, si no tiene más, a la página «sin club».
    """
    membership = request.membership
    if membership is None:
        return redirect("home")
    if is_last_admin(membership) and is_only_member(membership):
        club = membership.club
        if not club_name_matches(club, request.POST.get("confirm_name")):
            messages.error(request, _("Para eliminar el club escribe su nombre exactamente: %(club)s.") % {"club": club.name})
            return redirect("home")
        club_name = club.name
        delete_club(club)
        request.session.pop(SESSION_KEY, None)
        messages.success(request, _("Has abandonado %(club)s y el club se ha eliminado con todos sus datos.") % {"club": club_name})
        return redirect("home")
    if is_last_admin(membership):
        messages.error(request, _("Eres el capitán de %(club)s: traspasa la capitanía a otro jugador enlazado antes de "
                                  "abandonar el club. Para eliminar el club, quita antes a todos los miembros.")
                       % {"club": membership.club.name})
        return redirect("club_members")
    club_name = membership.club.name
    remove_membership(membership)
    request.session.pop(SESSION_KEY, None)
    messages.success(request, _("Has abandonado %(club)s.") % {"club": club_name})
    return redirect("home")


# Fecha de la última revisión de las páginas legales (cámbiala al editar sus textos).
LEGAL_UPDATED = datetime.date(2026, 10, 12)

TEXT_PLAIN = "text/plain"


@require_safe
def legal_page(request, template):
    """Página legal pública (privacidad, términos o cookies) con los datos del responsable."""
    return render(request, template, {
        "legal": {
            "owner_name": settings.LEGAL_OWNER_NAME,
            "owner_id": settings.LEGAL_OWNER_ID,
            "owner_address": settings.LEGAL_OWNER_ADDRESS,
        },
        "legal_updated": LEGAL_UPDATED,
    })


@require_safe
def robots_txt(request):
    """robots.txt: qué secciones no deben rastrear los buscadores y dónde está el sitemap."""
    return render(request, "robots.txt", content_type=TEXT_PLAIN)


@require_safe
def favicon_ico(request):
    """/favicon.ico en la raíz (200, sin redirección): es donde los buscadores lo piden por defecto."""
    path = finders.find("zyra/favicon.ico")
    with open(path, "rb") as f:
        response = HttpResponse(f.read(), content_type="image/x-icon")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_safe
def bing_site_auth(request):
    """BingSiteAuth.xml: archivo de verificación de Bing Webmaster Tools (el código es público)."""
    return render(request, "BingSiteAuth.xml", content_type="application/xml")


@require_safe
def healthz(request):
    """
    Comprobación para el servicio que vigila si la web está caída (UptimeRobot, Better
    Stack...): 200 si la aplicación y la base de datos responden, 503 si no.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return HttpResponse("db error", status=503, content_type=TEXT_PLAIN)
    return HttpResponse("ok", content_type=TEXT_PLAIN)
