"""
Vistas del back-office para el seguimiento de clientes y la operación diaria: auditoría, registro de
correos, buscador global, CRM de clubes (etapa, contacto, notas, tareas, correo al capitán), acciones sobre
cuentas y clubes y «Entrar como» un usuario (solo lectura).
"""
import datetime
import re

from allauth.account.forms import ResetPasswordForm
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core import services
from core.emails import build_email, club_admins
from core.models import Club, Membership
from players.models import Player
from team.models import Team

from . import impersonation
from .audit import ACTIONS, audit
from .decorators import staff_required, superuser_required
from .models import AuditLog, ClubCrm, ClubNote, EmailLog, FollowUpTask

User = get_user_model()
PAGE_SIZE = 25


def _page(request, qs):
    """Página pedida en ``?page=`` de ``qs``."""
    return Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))


def _extra(request, *keys):
    """Filtros de la petición para conservarlos en los enlaces de paginación."""
    from urllib.parse import urlencode
    params = {k: request.GET[k] for k in keys if request.GET.get(k)}
    return "&" + urlencode(params) if params else ""


# ---------- Auditoría y registro de correos ----------

@staff_required
def audit_list(request):
    """Auditoría de las acciones del personal (solo personal), filtrable por ``q`` (persona u objeto) y ``action``."""
    q = request.GET.get("q", "").strip()
    action = request.GET.get("action", "")
    logs = AuditLog.objects.all()
    if q:
        logs = logs.filter(Q(username__icontains=q) | Q(object_label__icontains=q) | Q(object_id__icontains=q))
    if action in ACTIONS:
        logs = logs.filter(action=action)
    return render(request, "backoffice/audit_list.html", {
        "section": "audit", "page": _page(request, logs), "q": q, "action": action,
        "actions": sorted((k, _(v)) for k, v in ACTIONS.items()), "labels": {k: _(v) for k, v in ACTIONS.items()},
        "extra": _extra(request, "q", "action"),
    })


@staff_required
def email_log(request):
    """Registro de correos enviados por la web (solo personal), filtrable por ``status`` y ``q`` (destinatario o asunto)."""
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    emails = EmailLog.objects.all()
    if q:
        emails = emails.filter(Q(to__icontains=q) | Q(subject__icontains=q))
    if status in dict(EmailLog.STATUSES):
        emails = emails.filter(status=status)
    return render(request, "backoffice/email_log.html", {
        "section": "emails", "page": _page(request, emails), "q": q, "status": status,
        "statuses": EmailLog.STATUSES, "extra": _extra(request, "q", "status"),
    })


# ---------- Buscador global ----------

PUBLIC_ID = re.compile(r"[A-Za-z]{3}[A-Za-z0-9]{12}")


@staff_required
def search(request):
    """
    Buscador global (solo personal). Un id público exacto (club, equipo, jugador, ejecución…) lleva
    directo a su ficha; cualquier otro texto busca en clubes, usuarios, equipos y jugadores.
    """
    q = request.GET.get("q", "").strip()
    results = {"clubs": [], "users": [], "teams": [], "players": []}
    if len(q) >= 2:
        if PUBLIC_ID.fullmatch(q):
            target = _by_public_id(q)
            if target:
                return redirect(target)
        results["clubs"] = list(Club.objects.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(public_id__iexact=q))[:15])
        results["users"] = list(User.objects.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))[:15])
        results["teams"] = list(Team.objects.filter(Q(name__icontains=q) | Q(public_id__iexact=q)).select_related("club")[:15])
        results["players"] = list(Player.objects.filter(
            Q(name__icontains=q) | Q(last_name__icontains=q) | Q(public_id__iexact=q)).select_related("club")[:15])
    return render(request, "backoffice/search.html", {
        "section": "search", "q": q, "results": results, "total": sum(len(v) for v in results.values()),
    })


def _by_public_id(value):
    """URL de la ficha del back-office de un objeto a partir de su id público (club, equipo, jugador, ejecución), o None."""
    from .models import JobRun
    prefix = value[:3].upper()
    if prefix == "CLB":
        club = Club.objects.filter(public_id=value).first()
        return reverse("backoffice:club_detail", args=[club.public_id]) if club else None
    if prefix == "TEA":
        team = Team.objects.filter(public_id=value).select_related("club").first()
        return reverse("backoffice:club_detail", args=[team.club.public_id]) if team and team.club else None
    if prefix == "PLY":
        player = Player.objects.filter(public_id=value).select_related("club").first()
        return reverse("backoffice:club_detail", args=[player.club.public_id]) if player and player.club else None
    if prefix == "RUN":
        run = JobRun.objects.filter(public_id=value).first()
        return reverse("backoffice:run_detail", args=[run.public_id]) if run else None
    return None


# ---------- Entrar como ----------

@staff_required
@require_POST
def impersonate_start(request, user_id):
    """
    Empieza «Entrar como» (solo personal, POST): se usa Zyra con la cuenta de otro usuario, pudiendo editar (cada cambio queda auditado),
    30 minutos como máximo. Hace falta un motivo; no vale para el personal ni para uno mismo.
    """
    target = get_object_or_404(User, pk=user_id)
    reason = request.POST.get("reason", "").strip()
    if getattr(request, "impersonator", None):
        messages.error(request, _("Ya estás dentro de «Entrar como»."))
    elif target.is_staff or target.is_superuser or target == request.user or not target.is_active:
        messages.error(request, _("No se puede entrar como esta cuenta."))
    elif len(reason) < 5:
        messages.error(request, _("Escribe el motivo (para la auditoría)."))
    else:
        impersonation.start(request, target, reason[:300])
        return redirect("home")
    return redirect("backoffice:user_detail", user_id=target.pk)


@require_POST
def impersonate_stop(request):
    """Termina «Entrar como» y vuelve a la ficha del usuario visto. Solo cuenta si hay modo activo."""
    if not (request.user.is_authenticated and request.user.is_staff):
        return redirect("home")
    username = impersonation.stop(request)
    target = User.objects.filter(username=username).first() if username else None
    if target:
        return redirect("backoffice:user_detail", user_id=target.pk)
    return redirect("backoffice:dashboard")


# ---------- Tareas de seguimiento ----------

@staff_required
def task_list(request):
    """
    Tareas de seguimiento (solo personal). Por defecto las pendientes asignadas a quien mira;
    ``?who=all`` las de todos y ``?done=1`` las hechas.
    """
    done = request.GET.get("done") == "1"
    who = request.GET.get("who", "me")
    tasks = FollowUpTask.objects.select_related("club", "assigned_to")
    tasks = tasks.filter(done_at__isnull=False) if done else tasks.filter(done_at__isnull=True)
    if who != "all":
        tasks = tasks.filter(assigned_to=request.user)
    today = timezone.localdate()
    page = _page(request, tasks.order_by("-done_at" if done else "due_date", "id"))
    for t in page:
        t.overdue = not t.done_at and t.due_date < today
    return render(request, "backoffice/task_list.html", {
        "section": "tasks", "page": page, "done": done, "who": who, "today": today,
        "clubs": Club.objects.order_by("name"), "staff": User.objects.filter(is_staff=True, is_active=True).order_by("username"),
        "extra": _extra(request, "who", "done"),
    })


@staff_required
@require_POST
def task_add(request):
    """Crea una tarea de seguimiento (solo personal, POST) con título, fecha y, si se quiere, club y responsable."""
    title = request.POST.get("title", "").strip()[:200]
    try:
        due = datetime.date.fromisoformat(request.POST.get("due_date", ""))
    except ValueError:
        due = None
    club = Club.objects.filter(public_id=request.POST.get("club", "")).first()
    assigned = User.objects.filter(pk=request.POST.get("assigned_to"), is_staff=True).first() if request.POST.get("assigned_to", "").isdigit() else request.user
    if not title or due is None:
        messages.error(request, _("Escribe la tarea y su fecha."))
    else:
        task = FollowUpTask.objects.create(title=title, due_date=due, club=club, assigned_to=assigned or request.user, created_by=request.user)
        audit(request, "task.create", label=task.title, club=club.name if club else "", due=due.isoformat())
        messages.success(request, _("Tarea creada."))
    return _back(request, "backoffice:task_list")


@staff_required
@require_POST
def task_toggle(request, task_id):
    """Marca una tarea como hecha (o la reabre) (solo personal, POST)."""
    task = get_object_or_404(FollowUpTask, pk=task_id)
    task.done_at = None if task.done_at else timezone.now()
    task.save(update_fields=["done_at"])
    return _back(request, "backoffice:task_list")


@staff_required
@require_POST
def task_delete(request, task_id):
    """Borra una tarea (solo personal, POST)."""
    get_object_or_404(FollowUpTask, pk=task_id).delete()
    return _back(request, "backoffice:task_list")


def _back(request, default):
    """Vuelve a ``next`` si es una ruta de este sitio; si no, a la vista ``default``."""
    from django.utils.http import url_has_allowed_host_and_scheme
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(default)


# ---------- CRM del club ----------

def _club(club_id):
    """Club por su id público o 404."""
    return get_object_or_404(Club, public_id=club_id)


@staff_required
@require_POST
def club_crm_update(request, club_id):
    """Guarda la etapa del ciclo y los datos de contacto del club (solo personal, POST)."""
    club = _club(club_id)
    crm, _created = ClubCrm.objects.get_or_create(club=club)
    lifecycle = request.POST.get("lifecycle", crm.lifecycle)
    email = request.POST.get("contact_email", "").strip()
    try:
        if email:
            validate_email(email)
    except ValidationError:
        messages.error(request, _("El email de contacto no es válido."))
        return redirect("backoffice:club_detail", club_id=club.public_id)
    before = {"lifecycle": crm.lifecycle, "contact_email": crm.contact_email}
    if lifecycle in dict(ClubCrm.LIFECYCLES):
        crm.lifecycle = lifecycle
    crm.contact_name = request.POST.get("contact_name", "").strip()[:120]
    crm.contact_email = email
    crm.contact_phone = request.POST.get("contact_phone", "").strip()[:40]
    crm.save()
    audit(request, "club.crm", club, before=before, lifecycle=crm.lifecycle)
    messages.success(request, _("Ficha del club guardada."))
    return redirect("backoffice:club_detail", club_id=club.public_id)


@staff_required
@require_POST
def club_note_add(request, club_id):
    """Añade una nota interna al club (solo personal, POST)."""
    club = _club(club_id)
    text = request.POST.get("text", "").strip()[:2000]
    if text:
        ClubNote.objects.create(club=club, author=request.user, author_name=request.user.get_username(), text=text)
        audit(request, "note.create", club, label=club.name)
    return redirect("backoffice:club_detail", club_id=club.public_id)


@staff_required
@require_POST
def club_note_delete(request, note_id):
    """Borra una nota (solo su autora o un superusuario, POST)."""
    note = get_object_or_404(ClubNote.objects.select_related("club"), pk=note_id)
    if note.author_id == request.user.pk or request.user.is_superuser:
        note.delete()
    return redirect("backoffice:club_detail", club_id=note.club.public_id)


def contact_templates(club):
    """Plantillas de correo al capitán (clave -> (asunto, texto)) con el nombre del club ya puesto."""
    name = club.name
    return {
        "welcome": (
            _("Te damos la bienvenida a Zyra"),
            _("Hola,\n\nGracias por crear %(club)s en Zyra. Si necesitas ayuda para añadir jugadores, "
              "crear el primer partido o enviar la convocatoria, respóndeme a este correo y lo vemos juntos.\n\nUn saludo.") % {"club": name}),
        "inactive": (
            _("¿Te echamos una mano con Zyra?"),
            _("Hola,\n\nHe visto que %(club)s lleva un tiempo sin actividad en Zyra. ¿Hay algo que no te haya funcionado "
              "o que eches de menos? Cuéntamelo y lo arreglamos.\n\nUn saludo.") % {"club": name}),
        "feedback": (
            _("¿Qué tal va Zyra?"),
            _("Hola,\n\nQuería saber qué tal os va con Zyra en %(club)s y qué mejoraríais. Cualquier comentario me sirve.\n\nUn saludo.") % {"club": name}),
        "blank": ("", ""),
    }


@staff_required
@require_POST
def club_contact(request, club_id):
    """
    Escribe a los capitanes del club (y al contacto de la ficha) desde el back-office (solo personal, POST).
    El correo queda en el registro de correos, en la auditoría y como nota del club.
    """
    club = _club(club_id)
    subject = request.POST.get("subject", "").strip()[:200]
    body = request.POST.get("body", "").strip()[:5000]
    recipients = [u.email for u in club_admins(club) if u.email]
    crm = getattr(club, "crm", None)
    if crm and crm.contact_email and crm.contact_email not in recipients:
        recipients.append(crm.contact_email)
    if not subject or not body:
        messages.error(request, _("Escribe el asunto y el mensaje."))
    elif not recipients:
        messages.error(request, _("El club no tiene ningún email al que escribir."))
    else:
        html = "".join(f"<p>{line}</p>" if line else "" for line in _escape(body).split("\n"))
        email = build_email(subject, body, html, to=recipients, reply_to=[request.user.email] if request.user.email else None)
        email.extra_headers["X-Zyra-Kind"] = "crm"
        try:
            email.send(fail_silently=False)
        except Exception:
            messages.error(request, _("No se ha podido enviar el correo; queda anotado en el registro de correos."))
        else:
            ClubNote.objects.create(club=club, author=request.user, author_name=request.user.get_username(),
                                    text=_("Correo enviado a %(to)s: %(subject)s") % {"to": ", ".join(recipients), "subject": subject})
            audit(request, "club.contact", club, subject=subject, to=", ".join(recipients))
            messages.success(request, _("Correo enviado a %(to)s.") % {"to": ", ".join(recipients)})
    return redirect("backoffice:club_detail", club_id=club.public_id)


def _escape(text):
    """Texto seguro para meterlo en HTML."""
    from django.utils.html import escape
    return escape(text)


# ---------- Acciones sobre clubes y cuentas ----------

@staff_required
@require_POST
def club_edit(request, club_id):
    """Cambia el nombre del club (solo personal, POST)."""
    club = _club(club_id)
    name = request.POST.get("name", "").strip()[:100]
    if not name:
        messages.error(request, _("Escribe el nombre del club."))
    elif name != club.name:
        old = club.name
        club.name = name
        club.save(update_fields=["name"])
        audit(request, "club.edit", club, before=old, after=name)
        messages.success(request, _("Nombre del club cambiado."))
    return redirect("backoffice:club_detail", club_id=club.public_id)


@superuser_required
@require_POST
def club_delete(request, club_id):
    """Elimina el club y todo lo suyo (solo superusuarios, POST) tras escribir su nombre; queda anotado en la auditoría."""
    club = _club(club_id)
    if not services.club_name_matches(club, request.POST.get("confirm", "")):
        messages.error(request, _("Escribe el nombre del club para confirmar."))
        return redirect("backoffice:club_detail", club_id=club.public_id)
    audit(request, "club.delete", club, label=club.name, members=club.memberships.count())
    services.delete_club(club)
    messages.success(request, _("Club eliminado."))
    return redirect("backoffice:club_list")


@staff_required
@require_POST
def club_transfer_captain(request, club_id):
    """Traspasa la capitanía del club a otro miembro enlazado a un jugador (solo personal, POST)."""
    club = _club(club_id)
    current = club.memberships.filter(role=Membership.ADMIN).first()
    target = club.memberships.filter(public_id=request.POST.get("membership", "")).first()
    try:
        if current is None or target is None:
            raise services.CaptaincyError(_("Elige a otro miembro del club."))
        services.transfer_captaincy(club, current, target)
    except services.CaptaincyError as error:
        messages.error(request, str(error))
    else:
        audit(request, "club.captain_transfer", club, before=current.user.get_username(), after=target.user.get_username())
        messages.success(request, _("Capitanía traspasada a %(user)s.") % {"user": target.user.get_username()})
    return redirect("backoffice:club_detail", club_id=club.public_id)


@staff_required
@require_POST
def user_password_reset(request, user_id):
    """Envía al usuario el correo para restablecer su contraseña (solo personal, POST)."""
    member = get_object_or_404(User, pk=user_id)
    if not member.email:
        messages.error(request, _("La cuenta no tiene email."))
    else:
        form = ResetPasswordForm({"email": member.email})
        if form.is_valid():
            form.save(request)
            audit(request, "user.reset_link", member, label=member.get_username())
            messages.success(request, _("Correo de restablecimiento enviado a %(email)s.") % {"email": member.email})
        else:
            messages.error(request, _("No se ha podido preparar el correo de restablecimiento."))
    return redirect("backoffice:user_detail", user_id=member.pk)
