"""
Vistas del back-office del personal de Zyra.

Dashboard y carga, clubes, usuarios, procesos programados, fotos subidas y emails
bloqueados son para el personal (staff_required); la consola SQL y la importación de
datos, solo para superusuarios (superuser_required).
"""
import csv
import datetime
import re
from urllib.parse import urlencode

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.utils.translation import gettext as _, ngettext
from django.views.decorators.http import require_POST

from core import blocklist, moderation
from core.emails import send_photo_removed_email
from core.models import BlockedEmail, Club, Invitation, Membership, PhotoCheck, PhotoRemoval
from match.models import Match
from players.models import Player

from . import importer, sql
from .decorators import staff_required, superuser_required
from .metrics import (
    AT_RISK_DAYS, ONLINE_MINUTES, annotate_clubs, dashboard_kpis, google_user_ids, health_metrics, load_metrics,
    online_users, usage_metrics,
)
from .middleware import SLOW_MS, flush_metrics
from .models import ImportJob, JobRun, QueryLog, SavedQuery, ScheduledJob
from .scheduler import SCHEDULER_TIME_ZONE, scheduler_is_late, start_manual_run, sync_jobs
from .templatetags.backoffice_tags import duration as duration_filter

User = get_user_model()

PAGE_SIZE = 25


def _page(request, qs):
    """Página pedida en ?page= de `qs`, de PAGE_SIZE en PAGE_SIZE."""
    return Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))


def _extra(request, *keys):
    """Parámetros de filtro para mantenerlos en los enlaces de paginación."""
    params = {k: request.GET[k] for k in keys if request.GET.get(k)}
    return "&" + urlencode(params) if params else ""


@staff_required
def dashboard(request):
    """
    Portada del back-office (solo personal). Vuelca antes las métricas pendientes y
    muestra las cifras generales, los procesos fallidos en 24 h y si el lanzador va con retraso.
    """
    flush_metrics()
    day_ago = timezone.now() - datetime.timedelta(hours=24)
    return render(request, "backoffice/dashboard.html", {
        "section": "dashboard", "kpis": dashboard_kpis(), "at_risk_days": AT_RISK_DAYS,
        "jobs_failed_24h": JobRun.objects.filter(status=JobRun.ERROR, started_at__gte=day_ago).count(),
        "scheduler_late": scheduler_is_late(),
    })


@staff_required
def load(request):
    """Carga de la web y usuarios conectados (solo personal), con las métricas recién volcadas."""
    flush_metrics()
    return render(request, "backoffice/load.html", {
        "section": "load", "online": online_users(), "online_minutes": ONLINE_MINUTES,
        "load": load_metrics(), "slow_ms": SLOW_MS,
    })


@staff_required
def usage(request):
    """Uso de la plataforma (solo personal): actividad por semana, adopción por club y clubes más activos."""
    return render(request, "backoffice/usage.html", {"section": "usage", "usage": usage_metrics()})


@staff_required
def health(request):
    """Salud de los servicios (solo personal): informes por email, sincronización SNP, procesos y errores."""
    flush_metrics()
    return render(request, "backoffice/health.html", {"section": "health", "health": health_metrics()})


CLUB_ORDERINGS = {
    "recent": F("created_at").desc(),
    "name": F("name").asc(),
    "members": F("n_members").desc(nulls_last=True),
    "activity": F("last_match").desc(nulls_last=True),
}


@staff_required
def club_list(request):
    """
    Lista de clubes (solo personal) con sus contadores. Filtros por GET: ``q`` (nombre o
    slug), ``activity`` (active/inactive según AT_RISK_DAYS) y ``order`` (CLUB_ORDERINGS).
    """
    q = request.GET.get("q", "").strip()
    activity = request.GET.get("activity", "")
    order = request.GET.get("order", "recent")

    clubs = annotate_clubs(Club.objects.all())
    if q:
        clubs = clubs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
    today = timezone.localdate()
    recent = today - datetime.timedelta(days=AT_RISK_DAYS)
    if activity == "active":
        clubs = clubs.filter(last_match__gte=recent)
    elif activity == "inactive":
        clubs = clubs.filter(Q(last_match__lt=recent) | Q(last_match__isnull=True))

    if order not in CLUB_ORDERINGS:
        order = "recent"
    clubs = clubs.order_by(CLUB_ORDERINGS[order], "name")

    return render(request, "backoffice/club_list.html", {
        "section": "clubs", "page": _page(request, clubs), "q": q, "activity": activity, "order": order,
        "extra": _extra(request, "q", "activity", "order"), "at_risk_days": AT_RISK_DAYS,
    })


@staff_required
def club_detail(request, club_id):
    """Ficha de un club (solo personal): miembros, jugadores, partidos, invitaciones y emails bloqueados."""
    club = get_object_or_404(annotate_clubs(Club.objects.all()), public_id=club_id)
    today = timezone.localdate()
    matches = Match.objects.filter(club=club).select_related("local", "visiting")
    players = Player.objects.filter(club=club)

    return render(request, "backoffice/club_detail.html", {
        "section": "clubs",
        "club": club,
        "memberships": club.memberships.select_related("user").order_by("role", "user__username"),
        "players_total": players.count(),
        "players_active": players.filter(in_team=True).count(),
        "rivals": club.teams.filter(is_own=False).count(),
        "past_matches": matches.filter(start_date__lte=today).order_by("-start_date")[:10],
        "upcoming_matches": matches.filter(start_date__gt=today).order_by("start_date")[:5],
        "invitations": club.invitations.select_related("created_by", "used_by")[:10],
        "blocked_emails": club.blocked_emails.all(),
        "now": timezone.now(),
    })


@staff_required
@require_POST
def club_toggle_suspended(request, club_id):
    """Suspende (o reactiva) un club: sus miembros no pueden entrar en él. No se borra nada."""
    club = get_object_or_404(Club, public_id=club_id)
    # La acción va en el formulario: un doble envío o una pestaña antigua no deshacen la anterior.
    suspend = request.POST.get("action") == "suspend"
    if suspend == club.is_suspended:
        messages.info(request, _("El club ya estaba suspendido.") if suspend else _("El club ya estaba activo."))
        return redirect("backoffice:club_detail", club_id=club.public_id)
    if not suspend:
        club.suspended_at, club.suspension_reason = None, ""
        # Se desbloquean los emails que se bloquearon al suspenderlo.
        unblocked = blocklist.unblock_club(club)
        messages.success(request, _("Club reactivado.") + (" " + ngettext(
            "%(n)s email desbloqueado.", "%(n)s emails desbloqueados.", unblocked) % {"n": unblocked} if unblocked else ""))
    else:
        club.suspended_at = timezone.now()
        club.suspension_reason = request.POST.get("reason", "").strip()[:500]
        # Emails de los miembros marcados (por defecto, los capitanes): no podrán crear
        # otro club ni unirse a ninguno.
        member_ids = [i for i in request.POST.getlist("block") if i.isdigit()]
        blocked = 0
        for m in club.memberships.filter(user_id__in=member_ids).select_related("user"):
            if m.user.email:
                blocked += blocklist.block(
                    m.user.email, user=m.user, club=club, blocked_by=request.user,
                    reason=club.suspension_reason or _("Club %(club)s suspendido") % {"club": club.name},
                )
        messages.success(request, _("Club suspendido: sus miembros ya no pueden entrar.") + (" " + ngettext(
            "%(n)s email bloqueado.", "%(n)s emails bloqueados.", blocked) % {"n": blocked} if blocked else ""))
    club.save(update_fields=["suspended_at", "suspension_reason"])
    return redirect("backoffice:club_detail", club_id=club.public_id)


@staff_required
def user_list(request):
    """
    Lista de usuarios (solo personal). Filtros por GET: ``q`` (usuario, email o nombre) y
    ``kind`` (staff, google, no_club o inactive: sin entrar en 30 días).
    """
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "")

    users = User.objects.annotate(n_clubs=Count("memberships")).order_by("-date_joined")
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    month_ago = timezone.now() - datetime.timedelta(days=30)
    if kind == "staff":
        users = users.filter(is_staff=True)
    elif kind == "google":
        users = users.filter(pk__in=google_user_ids())
    elif kind == "no_club":
        users = users.filter(n_clubs=0)
    elif kind == "inactive":
        users = users.filter(Q(last_login__lt=month_ago) | Q(last_login__isnull=True))

    page = _page(request, users)
    google_ids = set(
        SocialAccount.objects.filter(provider="google", user__in=[u.pk for u in page]).values_list("user_id", flat=True)
    )
    for u in page:
        u.uses_google = u.pk in google_ids

    return render(request, "backoffice/user_list.html", {
        "section": "users", "page": page, "q": q, "kind": kind, "extra": _extra(request, "q", "kind"),
    })


@staff_required
def user_detail(request, user_id):
    """
    Ficha de un usuario (solo personal): clubes, formas de entrar, invitaciones, fotos en uso
    y fotos que se le han eliminado.
    """
    member = get_object_or_404(User, pk=user_id)
    providers = SocialAccount.objects.filter(user=member).values_list("provider", flat=True)
    login_methods = ([_("Contraseña")] if member.has_usable_password() else []) + [p.capitalize() for p in providers]
    return render(request, "backoffice/user_detail.html", {
        "section": "users",
        "member": member,
        "memberships": Membership.objects.filter(user=member).select_related("club").order_by("club__name"),
        "login_methods": login_methods,
        "invitation_used": Invitation.objects.filter(used_by=member).select_related("club", "created_by").first(),
        "invitations_sent": Invitation.objects.filter(created_by=member).count(),
        "photo_checks": [
            c for c in PhotoCheck.objects.for_user(member).select_related("team", "player", "club") if c.in_use
        ],
        "photo_removals": PhotoRemoval.objects.filter(user=member).select_related("club", "removed_by"),
    })


# ---------- Procesos programados ----------

def _last_runs(jobs):
    """Última ejecución de cada proceso, indexada por el id del proceso."""
    last = {}
    for run in JobRun.objects.filter(job__in=jobs).order_by("job_id", "-started_at").select_related("job"):
        last.setdefault(run.job_id, run)
    return last


def _back(request):
    """Vuelve a la página desde la que se pulsó el botón (solo rutas de este sitio)."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("backoffice:job_list")


@staff_required
def job_list(request):
    """Lista de procesos programados con su última ejecución y las ejecuciones recientes (solo personal)."""
    jobs = list(sync_jobs())
    last = _last_runs(jobs)
    day_ago = timezone.now() - datetime.timedelta(hours=24)
    for job in jobs:
        job.last_run = last.get(job.pk)
    return render(request, "backoffice/job_list.html", {
        "section": "jobs", "jobs": jobs, "late": scheduler_is_late(), "time_zone": SCHEDULER_TIME_ZONE,
        "failed_24h": JobRun.objects.filter(status=JobRun.ERROR, started_at__gte=day_ago).count(),
        "recent_runs": JobRun.objects.select_related("job")[:10],
    })


@staff_required
def job_detail(request, name):
    """Ficha de un proceso con sus ejecuciones paginadas (solo personal)."""
    sync_jobs()
    job = get_object_or_404(ScheduledJob, name=name)
    runs = job.runs.select_related("triggered_by")
    return render(request, "backoffice/job_detail.html", {
        "section": "jobs", "job": job, "page": _page(request, runs), "time_zone": SCHEDULER_TIME_ZONE,
        "ok_count": runs.filter(status=JobRun.OK).count(), "error_count": runs.filter(status=JobRun.ERROR).count(),
    })


@staff_required
def run_list(request):
    """Log de ejecuciones de todos los procesos (solo personal), filtrable por ``status`` y ``job``."""
    status = request.GET.get("status", "")
    job_name = request.GET.get("job", "")
    runs = JobRun.objects.select_related("job", "triggered_by")
    if status in dict(JobRun.STATUSES):
        runs = runs.filter(status=status)
    if job_name:
        runs = runs.filter(job__name=job_name)
    return render(request, "backoffice/run_list.html", {
        "section": "jobs", "page": _page(request, runs), "status": status, "job_name": job_name,
        "statuses": JobRun.STATUSES, "jobs": sync_jobs(), "extra": _extra(request, "status", "job"),
    })


@staff_required
def run_detail(request, run_id):
    """Detalle de una ejecución (solo personal); la salida en directo la pide la página a run_live."""
    run = get_object_or_404(JobRun.objects.select_related("job", "triggered_by"), public_id=run_id)
    return render(request, "backoffice/run_detail.html", {"section": "jobs", "run": run})


@staff_required
@require_POST
def job_toggle(request, name):
    """Activa o pone en pausa un proceso (solo personal, POST) y vuelve a la página de origen."""
    job = get_object_or_404(ScheduledJob, name=name)
    job.enabled = not job.enabled
    job.save(update_fields=["enabled"])
    if job.enabled:
        messages.success(request, _("%(job)s: activado.") % {"job": job.name})
    else:
        messages.success(request, _("%(job)s: en pausa.") % {"job": job.name})
    return _back(request)


@staff_required
@require_POST
def job_run_now(request, name):
    """
    "Ejecutar ahora" (solo personal, POST). Valida los datos (``params``) y opciones del
    proceso que llegan en el formulario y lo lanza en segundo plano. Redirige a la página
    de la ejecución, o de vuelta con un error si algún dato no es válido o ya estaba en marcha.
    """
    job = get_object_or_404(ScheduledJob, name=name)
    args = []
    for param in job.spec.params if job.spec else ():
        value = request.POST.get(param.name, "").strip()
        if not re.fullmatch(param.pattern, value):
            messages.error(request, _("Indica un valor válido para «%(field)s».") % {"field": param.label})
            return redirect("backoffice:job_detail", name=job.name)
        args.append(value)
    for option in job.spec.options if job.spec else ():
        value = request.POST.get(option.name, "").strip()
        if not option.pattern:
            if value:
                args.append(option.flag)
        elif value:
            if not re.fullmatch(option.pattern, value):
                messages.error(request, _("Indica un valor válido para «%(field)s».") % {"field": option.label})
                return redirect("backoffice:job_detail", name=job.name)
            args += [option.flag, value]
    run = start_manual_run(job, request.user, args)
    if run is None:
        messages.error(request, _("%(job)s ya se está ejecutando.") % {"job": job.name})
        return _back(request)
    return redirect("backoffice:run_detail", run_id=run.public_id)


@staff_required
def run_live(request, run_id):
    """Salida de una ejecución a partir de `offset`, para la consola en directo."""
    run = get_object_or_404(JobRun, public_id=run_id)
    try:
        offset = max(int(request.GET.get("offset", 0)), 0)
    except ValueError:
        offset = 0
    output = run.output or ""
    return JsonResponse({
        "status": run.status,
        "status_label": run.get_status_display(),
        "finished": run.status != JobRun.RUNNING,
        "output": output[offset:],
        "offset": len(output),
        "error": run.error if run.status == JobRun.ERROR else "",
        "duration": duration_filter(run.duration) if run.finished_at else "",
    })


# ---------- Consola SQL ----------

def _csv_response(result, filename):
    """CSV que Excel abre bien en español: UTF-8 con BOM y separador punto y coma."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(result.columns)
    for row in result.rows:
        writer.writerow(["" if v is None else v for v in row])
    return response


def _export_name(saved):
    """Nombre del CSV exportado: el de la consulta guardada (o 'consulta') con la fecha y hora."""
    base = slugify(saved.name) if saved else "consulta"
    return f"zyra-{base}-{timezone.localtime():%Y%m%d-%H%M}.csv"


@superuser_required
def sql_console(request):
    """
    Consola SQL de solo lectura (solo superusuarios).

    GET muestra la consola (con la consulta guardada de ``?saved=`` si se indica). POST
    según ``action``: ``run`` ejecuta la consulta y ``export`` la descarga en CSV (ambas
    quedan en QueryLog); ``save`` la valida y la guarda o actualiza por nombre, y redirige
    a la consola con ella cargada.
    """
    saved = None
    if request.GET.get("saved"):
        saved = SavedQuery.objects.filter(public_id=request.GET["saved"]).first()
    query = request.POST.get("sql") if request.method == "POST" else (saved.sql if saved else "")
    action = request.POST.get("action", "")
    result = error = None

    if request.method == "POST" and action in ("run", "export"):
        export = action == "export"
        log = QueryLog(user=request.user, sql=query or "", exported=export)
        try:
            result = sql.run(query, limit=sql.EXPORT_LIMIT if export else sql.DISPLAY_LIMIT)
            log.row_count, log.duration_ms = result.row_count, result.duration_ms
        except sql.QueryError as exc:
            error = log.error = str(exc)
        log.save()
        if export and result:
            return _csv_response(result, _export_name(saved))

    elif request.method == "POST" and action == "save":
        name = request.POST.get("name", "").strip()
        try:
            sql.validate(query)
        except sql.QueryError as exc:
            error = str(exc)
        else:
            if not name:
                error = _("Ponle un nombre a la consulta para guardarla.")
            else:
                saved, created = SavedQuery.objects.update_or_create(
                    name=name, defaults={"sql": sql.clean(query), "description": request.POST.get("description", "").strip()[:255],
                                         "created_by": request.user},
                )
                if created:
                    messages.success(request, _("Consulta «%(name)s» guardada.") % {"name": saved.name})
                else:
                    messages.success(request, _("Consulta «%(name)s» actualizada.") % {"name": saved.name})
                return redirect(f"{request.path}?saved={saved.public_id}")

    return render(request, "backoffice/sql_console.html", {
        "section": "sql", "query": query or "", "result": result, "error": error, "saved": saved,
        "saved_queries": SavedQuery.objects.all(), "schema": sql.schema(),
        "history": QueryLog.objects.filter(user=request.user)[:15],
        "display_limit": sql.DISPLAY_LIMIT, "export_limit": sql.EXPORT_LIMIT, "timeout": sql.TIMEOUT_SECONDS,
    })


@superuser_required
@require_POST
def sql_delete_saved(request, query_id):
    """Borra una consulta guardada (solo superusuarios, POST) y vuelve a la consola."""
    saved = get_object_or_404(SavedQuery, public_id=query_id)
    saved.delete()
    messages.success(request, _("Consulta «%(name)s» borrada.") % {"name": saved.name})
    return redirect("backoffice:sql_console")


@superuser_required
def sql_log(request):
    """Auditoría de las consultas lanzadas o exportadas desde la consola (solo superusuarios)."""
    return render(request, "backoffice/sql_log.html", {
        "section": "sql", "page": _page(request, QueryLog.objects.select_related("user")),
    })


# ---------- Importación de datos ----------

PREVIEW_ROWS = 100


@superuser_required
def import_list(request):
    """
    Importación de datos, primer paso (solo superusuarios).

    GET muestra el formulario y las importaciones anteriores. POST recibe objeto, modo,
    club y fichero CSV, comprueba que se puede leer, crea el ImportJob en borrador con un
    emparejamiento de columnas propuesto y redirige a import_map.
    """
    if request.method == "POST":
        entity_key, mode = request.POST.get("entity"), request.POST.get("mode")
        club_id = request.POST.get("club", "")
        club = Club.objects.filter(pk=club_id).first() if club_id.isdigit() else None
        upload = request.FILES.get("file")
        error = None
        if entity_key not in importer.ENTITIES or mode not in dict(importer.MODES) or club is None:
            error = _("Elige qué importar, a qué club y cómo.")
        elif upload is None:
            error = _("Sube un fichero CSV.")
        else:
            try:
                text = importer.decode(upload.read())
                headers, _rows = importer.read_csv(text)
            except importer.ImportFileError as exc:
                error = str(exc)
        if error:
            messages.error(request, error)
            return redirect("backoffice:import_list")
        job = ImportJob.objects.create(
            user=request.user, club=club, entity=entity_key, mode=mode, filename=upload.name[:255], content=text,
            mapping=importer.guess_mapping(importer.ENTITIES[entity_key], headers),
        )
        return redirect("backoffice:import_map", job_id=job.public_id)

    return render(request, "backoffice/import_list.html", {
        "section": "import", "entities": importer.ENTITIES.values(), "modes": importer.MODES,
        "clubs": Club.objects.order_by("name"), "page": _page(request, ImportJob.objects.select_related("club", "user")),
        "max_rows": importer.MAX_ROWS,
    })


def _draft(job_id):
    """ImportJob en borrador con ese id público, o 404 (ya confirmada o deshecha)."""
    return get_object_or_404(ImportJob.objects.select_related("club"), public_id=job_id, status=ImportJob.DRAFT)


@superuser_required
def import_map(request, job_id):
    """
    Emparejamiento de columnas del fichero con los campos (solo superusuarios). GET muestra
    las columnas y unas filas de muestra; POST guarda el emparejamiento y redirige a la
    previsualización.
    """
    job = _draft(job_id)
    entity = job.entity_spec
    headers, rows = importer.read_csv(job.content)
    if request.method == "POST":
        mapping = {}
        for f in entity.all_fields():
            value = request.POST.get(f"map_{f.name}", "")
            if value.isdigit() and int(value) < len(headers):
                mapping[f.name] = int(value)
        job.mapping = mapping
        job.save(update_fields=["mapping"])
        return redirect("backoffice:import_preview", job_id=job.public_id)
    return render(request, "backoffice/import_map.html", {
        "section": "import", "job": job, "entity": entity, "headers": list(enumerate(headers)),
        "sample": rows[:3], "fields": [(f, job.mapping.get(f.name)) for f in entity.all_fields()],
    })


def _show(value):
    """Valor para mostrar en la previsualización (sí/no en lugar de True/False)."""
    if isinstance(value, bool):
        return _("sí") if value else _("no")
    return value


def _validate(job):
    """Valida todas las filas del fichero de la importación sin guardar nada."""
    headers, rows = importer.read_csv(job.content)
    return importer.process(job.entity_spec, job.club, job.mode, headers, rows, job.mapping)


@superuser_required
def import_preview(request, job_id):
    """
    Previsualización de una importación (solo superusuarios): valida todas las filas y
    muestra las que tienen errores (o, si no hay, las primeras PREVIEW_ROWS). Con
    ``?errors=csv`` descarga los errores en CSV. Si falla el fichero entero, vuelve a import_map.
    """
    job = _draft(job_id)
    try:
        results = _validate(job)
    except importer.ImportFileError as exc:
        messages.error(request, str(exc))
        return redirect("backoffice:import_map", job_id=job.public_id)

    if request.GET.get("errors") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="errores-{slugify(job.filename)}.csv"'
        response.write("﻿")
        writer = csv.writer(response, delimiter=";")
        writer.writerow([_("Línea"), _("Errores")])
        for r in results:
            if not r.ok:
                writer.writerow([r.line, " | ".join(r.errors)])
        return response

    errors = [r for r in results if not r.ok]
    entity = job.entity_spec
    fields = [f for f in entity.all_fields() if f.name in job.mapping]
    return render(request, "backoffice/import_preview.html", {
        "section": "import", "job": job, "entity": entity, "fields": fields,
        "rows": [(r, [_show(r.values.get(f.name, "")) for f in fields]) for r in (errors or results)[:PREVIEW_ROWS]],
        "total": len(results), "errors": len(errors),
        "creates": sum(r.action == importer.CREATE for r in results if r.ok),
        "updates": sum(r.action == importer.UPDATE for r in results if r.ok),
        "preview_rows": PREVIEW_ROWS,
    })


@superuser_required
@require_POST
def import_confirm(request, job_id):
    """
    Confirma una importación (solo superusuarios, POST). Si alguna fila falla no se guarda
    nada y vuelve a la previsualización; si va bien, marca la importación como hecha.
    """
    job = _draft(job_id)
    try:
        results = importer.run_import(job)
    except importer.ImportFileError as exc:
        messages.error(request, str(exc))
        return redirect("backoffice:import_map", job_id=job.public_id)
    if any(not r.ok for r in results):
        messages.error(request, _("Hay filas con errores: no se ha importado nada."))
        return redirect("backoffice:import_preview", job_id=job.public_id)
    job.status, job.finished_at = ImportJob.DONE, timezone.now()
    job.created_count = len(job.result["created"])
    job.updated_count = len(job.result["updated"])
    job.save()
    messages.success(request, _("Importación hecha: %(created)s creados y %(updated)s actualizados.") % {
        "created": job.created_count, "updated": job.updated_count,
    })
    return redirect("backoffice:import_list")


@superuser_required
@require_POST
def import_undo(request, job_id):
    """Deshace una importación (solo superusuarios, POST): borra lo creado y restaura lo cambiado."""
    job = get_object_or_404(ImportJob, public_id=job_id, status=ImportJob.DONE)
    deleted, restored = importer.undo_import(job)
    job.status, job.undone_at = ImportJob.UNDONE, timezone.now()
    job.save(update_fields=["status", "undone_at"])
    messages.success(request, _("Importación deshecha: %(deleted)s borrados y %(restored)s restaurados.") % {
        "deleted": deleted, "restored": restored,
    })
    return redirect("backoffice:import_list")


@superuser_required
def import_template(request, entity):
    """Descarga la plantilla CSV de un objeto importable (solo superusuarios); 404 si no existe."""
    spec = importer.ENTITIES.get(entity)
    if spec is None:
        raise Http404
    response = HttpResponse(importer.template_csv(spec), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="plantilla-{entity}.csv"'
    return response


# ---------- Fotos subidas ----------
# El personal revisa las fotos que suben los usuarios (escudos y fotos de jugador) y
# elimina las que no cumplen los términos y condiciones: se avisa por email al jugador
# (o a quien subió el escudo) y queda registrado (PhotoRemoval). Las veces que le ha
# pasado a cada usuario se ven aquí y en su ficha. Rekognition (core/moderation.py) es
# opcional y está desactivado por defecto: sin él todas las fotos llegan «Sin validar».

PHOTO_FILTERS = [PhotoCheck.UNCHECKED, PhotoCheck.REJECTED, PhotoCheck.APPROVED]


def _remove_photo(check):
    """Quita la foto del equipo o jugador (el fichero se borra al guardar, core/images.py)."""
    subject = check.subject
    if check.in_use:
        subject.photo = None
        subject.save(update_fields=["photo"])
        return True
    return False


def _remove_and_notify(request, checks, reason=""):
    """
    Elimina las fotos en uso de ``checks``, registra cada una (PhotoRemoval) y manda un
    solo correo a cada afectado. Devuelve (fotos eliminadas, avisados, sin poder avisar).
    """
    by_owner = {}
    removed_photos = set()
    for check in checks:
        subject, owner, club = check.subject_label, check.owner, check.club
        # Una misma foto puede tener más de un registro: se cuenta una sola vez.
        if check.photo not in removed_photos and _remove_photo(check):
            removed_photos.add(check.photo)
            by_owner.setdefault(owner, []).append((subject, club))
        check.delete()
    removed = notified = not_notified = 0
    for owner, items in by_owner.items():
        removals = [
            PhotoRemoval.objects.create(
                user=owner, club=club, subject=subject, reason=reason, removed_by=request.user,
            )
            for subject, club in items
        ]
        removed += len(removals)
        total = PhotoRemoval.objects.filter(user=owner).count() if owner else 0
        sent = send_photo_removed_email(
            owner, [subject for subject, _club in items], reason=reason, removals=total,
            site_url=request.build_absolute_uri("/"),
        )
        if sent:
            PhotoRemoval.objects.filter(pk__in=[r.pk for r in removals]).update(email_sent=True)
            notified += 1
        else:
            not_notified += 1
    return removed, notified, not_notified


def _report_removal(request, removed, notified, not_notified):
    """Mensajes para el personal con el resultado de eliminar fotos."""
    if not removed:
        messages.info(request, _("Esa foto ya no se usaba."))
        return
    messages.success(request, ngettext("%(n)s foto eliminada.", "%(n)s fotos eliminadas.", removed) % {"n": removed})
    if notified:
        messages.success(request, _("Se ha avisado por email al usuario."))
    if not_notified:
        messages.warning(request, _("No se ha podido avisar por email (el usuario no tiene email o falló el envío)."))


@staff_required
def photo_list(request):
    """
    Revisión de fotos subidas (solo personal), filtradas por estado (``status``, por
    defecto sin validar). Muestra cuántas fotos se le han eliminado ya a cada usuario y el
    estado de Rekognition.
    """
    status = request.GET.get("status", PhotoCheck.UNCHECKED)
    if status not in PHOTO_FILTERS:
        status = PhotoCheck.UNCHECKED
    checks = (
        PhotoCheck.objects.filter(status=status)
        .select_related("club", "uploaded_by", "team", "player__user")
        .order_by("-created_at")
    )
    if status != PhotoCheck.REJECTED:
        checks = checks.exclude(photo="")
    page = _page(request, checks)
    owners = {c.owner.pk for c in page if c.owner}
    strikes = dict(
        PhotoRemoval.objects.filter(user__in=owners).values_list("user").annotate(n=Count("id")).order_by()
    )
    for c in page:
        c.strikes = strikes.get(c.owner.pk, 0) if c.owner else 0
    # Las rechazadas no tienen foto guardada; del resto solo cuentan las que llegaron a guardarse.
    counts = dict(PhotoCheck.objects.exclude(photo="").values_list("status").annotate(n=Count("id")).order_by())
    counts[PhotoCheck.REJECTED] = PhotoCheck.objects.filter(status=PhotoCheck.REJECTED).count()
    return render(request, "backoffice/photo_list.html", {
        "section": "photos",
        "status": status,
        "filters": [(s, label, counts.get(s, 0)) for s, label in PhotoCheck.STATUSES],
        "page": page,
        "recent_removals": PhotoRemoval.objects.select_related("user", "club", "removed_by")[:10],
        "rekognition_enabled": settings.REKOGNITION_ENABLED,
        "calls_this_month": moderation.calls_this_month(),
        "monthly_limit": settings.REKOGNITION_MONTHLY_LIMIT,
        "free_until": settings.REKOGNITION_FREE_UNTIL,
        "not_validating": moderation.free_tier_status(),
    })


@staff_required
@require_POST
def photo_delete(request, check_id):
    """
    Elimina una foto (solo personal, POST) con el motivo indicado, avisa por email a su
    dueño y vuelve a la página de origen.
    """
    check = get_object_or_404(PhotoCheck.objects.select_related("team", "player__user", "uploaded_by", "club"), public_id=check_id)
    _report_removal(request, *_remove_and_notify(request, [check], request.POST.get("reason", "").strip()[:500]))
    return _back_to(request, "backoffice:photo_list")


@staff_required
@require_POST
def photo_approve(request, check_id):
    """El personal da por buena una foto pendiente: queda «Validada», como las que aprueba Rekognition."""
    check = get_object_or_404(PhotoCheck, public_id=check_id)
    check.status = PhotoCheck.APPROVED
    check.save(update_fields=["status"])
    messages.success(request, _("Foto marcada como validada."))
    return _back_to(request, "backoffice:photo_list")


@staff_required
@require_POST
def user_photos_delete(request, user_id):
    """Elimina todas las fotos que ha subido un usuario (o de su jugador) y siguen en uso."""
    member = get_object_or_404(User, pk=user_id)
    checks = (
        PhotoCheck.objects.for_user(member).select_related("team", "player__user", "uploaded_by", "club")
    )
    _report_removal(request, *_remove_and_notify(request, list(checks), request.POST.get("reason", "").strip()[:500]))
    return redirect("backoffice:user_detail", user_id=member.pk)


@staff_required
@require_POST
def user_toggle_active(request, user_id):
    """Suspende (o reactiva) la cuenta de un usuario: suspendida, no puede iniciar sesión."""
    member = get_object_or_404(User, pk=user_id)
    if member == request.user or member.is_superuser:
        messages.error(request, _("No puedes suspender esta cuenta."))
    elif (request.POST.get("action") == "activate") == member.is_active:
        messages.info(request, _("La cuenta ya estaba activa.") if member.is_active else _("La cuenta ya estaba suspendida."))
    else:
        member.is_active = not member.is_active
        member.save(update_fields=["is_active"])
        messages.success(request, _("Cuenta reactivada.") if member.is_active else _("Cuenta suspendida: ya no puede iniciar sesión."))
    return redirect("backoffice:user_detail", user_id=member.pk)


def _back_to(request, default):
    """Vuelve a la página de ``next`` si es de este sitio; si no, a la vista `default`."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(default)


# ---------- Emails bloqueados ----------

@staff_required
def blocked_email_list(request):
    """Lista de emails bloqueados (solo personal), con búsqueda por ``q``."""
    q = request.GET.get("q", "").strip()
    emails = BlockedEmail.objects.select_related("club", "blocked_by")
    if q:
        # Por el principio del email normalizado (usa el índice) o por cualquier parte del
        # email tal y como se escribió (p. ej. el dominio). Solo afecta a esta página: la
        # comprobación al registrarse o unirse es siempre una búsqueda exacta por índice.
        emails = emails.filter(Q(email__startswith=blocklist.normalize_email(q)) | Q(original_email__icontains=q))
    return render(request, "backoffice/blocked_email_list.html", {
        "section": "blocked", "page": _page(request, emails), "q": q,
        "extra": "&" + urlencode({"q": q}) if q else "",
    })


@staff_required
@require_POST
def blocked_email_add(request):
    """Bloquea un email a mano (solo personal, POST) y vuelve a la lista."""
    email = request.POST.get("email", "").strip()
    if "@" not in email:
        messages.error(request, _("Escribe un email válido."))
    elif blocklist.block(email, reason=request.POST.get("reason", "").strip(), blocked_by=request.user):
        messages.success(request, _("%(email)s bloqueado.") % {"email": email})
    else:
        messages.info(request, _("%(email)s ya estaba bloqueado.") % {"email": email})
    return redirect("backoffice:blocked_email_list")


@staff_required
@require_POST
def blocked_email_delete(request, blocked_id):
    """Desbloquea un email (solo personal, POST) y vuelve a la página de origen."""
    blocked = get_object_or_404(BlockedEmail, public_id=blocked_id)
    blocked.delete()
    messages.success(request, _("%(email)s desbloqueado.") % {"email": blocked.original_email})
    return _back_to(request, "backoffice:blocked_email_list")
