"""
Vistas generales de Zyra: portada, inicio de sesión, páginas de error, alta de club,
cambio de club activo, gestión de miembros e invitaciones.
"""
import datetime
from urllib.parse import urlencode

from allauth.account.models import EmailAddress
from django.forms import Select
from django.forms.utils import ErrorDict
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from data_analyse import pairs as pair_stats
from match.models import Match
from players.models import Player, SnpAccount, current_season

from .adapters import GOOGLE_NEW_ACCOUNT_KEY
from .blocklist import is_user_blocked
from .decorators import club_admin_required
from .emails import send_invitation_email, send_welcome_email
from .forms import ClubForm, InviteMemberForm, SignUpForm
from .middleware import SESSION_KEY
from .models import Invitation, Membership
from .services import InvitationError, accept_invitation, create_club, is_last_admin, remove_membership

INVITATIONS_PER_PAGE = 10

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


def home(request):
    """Portada del club: logo, próximo partido y jugador/pareja en racha."""
    if not request.user.is_authenticated:
        return render(request, 'landing.html')
    if request.club is None:
        return redirect('no_club')

    club = request.club
    today = datetime.date.today()
    next_match = (
        Match.objects.filter(club=club, start_date__gte=today)
        .select_related('local', 'visiting')
        .order_by('start_date', 'id')
        .first()
    )
    players = Player.objects.filter(club=club, in_team=True)
    hot_player, hot_pair = pair_stats.hot_streaks(pair_stats.club_game_log(club), players)

    return render(request, 'home.html', {
        'own_team': club.own_team,
        'season': current_season(),
        'next_match': next_match,
        'days_left': (next_match.start_date - today).days if next_match else None,
        'hot_player': hot_player,
        'hot_pair': hot_pair,
        # Aviso al capitán mientras no haya registrado la cuenta SNP del club.
        'snp_missing': request.membership.is_admin and not SnpAccount.objects.filter(club=club).exists(),
    })


class ThrottledLoginView(LoginView):
    """
    LoginView de Django con freno a los ataques de fuerza bruta: sin él se podían probar
    contraseñas sin límite. (El login de allauth, /accounts/login/, ya tiene el suyo.)
    """

    def _key(self):
        """Clave de caché del contador de fallos: IP y usuario escrito."""
        username = (self.request.POST.get("username") or "").strip().lower()
        return f"login-failures:{self.request.META.get('REMOTE_ADDR', '')}:{username}"

    def post(self, request, *args, **kwargs):
        """Con demasiados fallos seguidos responde 429 sin comprobar la contraseña."""
        if cache.get(self._key(), 0) >= LOGIN_MAX_FAILURES:
            # Sin validar el formulario: validarlo comprobaría la contraseña.
            form = self.get_form()
            form._errors, form.cleaned_data = ErrorDict(), {}
            form.add_error(None, _("Demasiados intentos fallidos. Espera 15 minutos y vuelve a intentarlo."))
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        """Suma un fallo al contador (caduca a los LOGIN_LOCKOUT_SECONDS)."""
        key = self._key()
        cache.add(key, 0, LOGIN_LOCKOUT_SECONDS)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, LOGIN_LOCKOUT_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        """Inicio de sesión correcto: pone a cero el contador de fallos."""
        cache.delete(self._key())
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
    """Alta de un club nuevo. Si el visitante no tiene cuenta, se le crea una."""
    anonymous = not request.user.is_authenticated

    # Vuelve de "Crear mi cuenta con Google". Si el email ya tenía cuenta, Google ha
    # iniciado sesión en ella: no es un alta nueva, así que va a su portada.
    if not anonymous and request.GET.get(FROM_GOOGLE_PARAM):
        if request.session.pop(GOOGLE_NEW_ACCOUNT_KEY, False):
            return redirect("register_club")
        messages.info(request, _("Ya tenías una cuenta con este email. Has iniciado sesión con ella."))
        return redirect("home")

    if request.method == "POST":
        club_form = ClubForm(request.POST)
        user_form = SignUpForm(request.POST) if anonymous else None
        valid = club_form.is_valid() and (user_form is None or user_form.is_valid())
        # Un email bloqueado por el personal (p. ej. de un club suspendido) no puede crear clubes.
        if valid and not anonymous and is_user_blocked(request.user):
            club_form.add_error(None, _("Tu email está bloqueado en Zyra y no puede crear clubes."))
            valid = False
        if valid:
            with transaction.atomic():
                user = user_form.save() if anonymous else request.user
                data = club_form.cleaned_data
                club = create_club(data["name"], data["location"], user, gender=data["gender"], country=data["country"],
                                   division=data["division"])
            if anonymous:
                login(request, user, backend=LOGIN_BACKEND)
            request.session[SESSION_KEY] = club.id
            send_welcome_email(user, club, created=True, site_url=_site_url(request))
            messages.success(request, _("Club %(club)s creado correctamente.") % {"club": club.name})
            return redirect("home")
    else:
        club_form = ClubForm()
        user_form = SignUpForm() if anonymous else None

    _style(club_form, user_form)
    return render(request, "register_club.html", {
        "club_form": club_form, "user_form": user_form,
        "google_next": f"{reverse('register_club')}?{FROM_GOOGLE_PARAM}=1",
    })


@login_required
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
    invitations = [
        (inv, request.build_absolute_uri(reverse("invitation", args=[inv.token])))
        for inv in page
    ]
    extra = ("&" + urlencode({"q": search}) if search else "") + "#invitaciones"
    return render(request, "club_members.html", {
        "invite_form": invite_form, "memberships": memberships, "roles": Membership.ROLES, "invitations": invitations,
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
    """
    Invitation.objects.create(club=request.club, created_by=request.user, reusable=True)
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
        # Vuelve de iniciar sesión con Google desde esta misma invitación: se une directamente.
        from_google = request.session.pop(PENDING_INVITE_KEY, None) == token
        if request.method == "POST" or from_google:
            # Tras unirse, elige su jugador en la plantilla o lo crea (players.views.my_player).
            return redirect("my_player" if _join(request, invitation, request.user) else "home")
        return render(request, "invitation.html", {"invitation": invitation, "club": club})

    request.session[PENDING_INVITE_KEY] = token
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                try:
                    accept_invitation(invitation, user)
                except InvitationError as exc:
                    transaction.set_rollback(True)
                    messages.error(request, str(exc))
                    return redirect("invitation", token=token)
            request.session.pop(PENDING_INVITE_KEY, None)
            login(request, user, backend=LOGIN_BACKEND)
            request.session[SESSION_KEY] = club.id
            send_welcome_email(user, club, site_url=_site_url(request))
            messages.success(request, _("¡Bienvenido a %(club)s!") % {"club": club.name})
            return redirect("my_player")
    else:
        form = SignUpForm(initial={"email": invitation.email})

    _style(form)
    return render(request, "invitation.html", {"invitation": invitation, "club": club, "form": form})


@club_admin_required
@require_POST
def update_member(request, membership_id):
    """
    Cambia el rol de un miembro (solo capitanes, solo POST).

    Si el capitán edita su propia fila también puede cambiar su email (el de los demás
    no). No deja el club sin capitanes. Redirige a la página de miembros.
    """
    membership = get_object_or_404(Membership, public_id=membership_id, club=request.club)
    role = request.POST.get("role")
    # Cada usuario solo puede cambiar su propio email. Antes un capitán podía cambiar el de
    # cualquier miembro y, con «Entrar con Google» (que entra en la cuenta cuyo email
    # coincide), quedarse con la cuenta de ese miembro.
    if membership.user_id == request.user.id and "email" in request.POST:
        error = _change_own_email(request.user, request.POST.get("email", "").strip())
        if error:
            messages.error(request, error)
            return redirect("club_members")
    if role not in dict(Membership.ROLES):
        messages.error(request, _("Rol no válido."))
    elif role != Membership.ADMIN and is_last_admin(membership):
        messages.error(request, _("El club debe tener al menos un capitán."))
    else:
        membership.role = role
        membership.save()
    return redirect("club_members")


def _change_own_email(user, email):
    """Cambia el email del propio usuario; devuelve el mensaje de error o None."""
    email = email.lower()
    if email == (user.email or "").lower():
        return None
    try:
        validate_email(email) if email else None
    except ValidationError:
        return _("'%(email)s' no es un email válido.") % {"email": email}
    if email and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
        return _("Ese email ya lo usa otra cuenta.")
    user.email = email
    user.save(update_fields=["email"])
    # El email verificado (Google) era el anterior: allauth no debe seguir dándolo por bueno.
    EmailAddress.objects.filter(user=user).exclude(email__iexact=email).delete()
    return None


@club_admin_required
@require_POST
def remove_member(request, membership_id):
    """
    Da de baja a un miembro del club (solo capitanes, solo POST) y desenlaza su cuenta de
    su jugador, así si vuelve a entrar no sigue enlazado al de antes.

    No permite quitar al último capitán. Redirige a la página de miembros.
    """
    membership = get_object_or_404(Membership.objects.select_related("user"), public_id=membership_id, club=request.club)
    if is_last_admin(membership):
        messages.error(request, _("El club debe tener al menos un capitán."))
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
    irse: antes tiene que nombrar a otro. Después pasa a otro de sus clubes o, si no
    tiene más, a la página «sin club».
    """
    membership = request.membership
    if membership is None:
        return redirect("home")
    if is_last_admin(membership):
        messages.error(request, _("Eres el único capitán de %(club)s: nombra a otro capitán antes de abandonar el club.")
                       % {"club": membership.club.name})
        return redirect("club_members")
    club_name = membership.club.name
    remove_membership(membership)
    request.session.pop(SESSION_KEY, None)
    messages.success(request, _("Has abandonado %(club)s.") % {"club": club_name})
    return redirect("home")
