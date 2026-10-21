"""
Cifras del dashboard del back-office. Todas se calculan al vuelo sobre los datos
de todos los clubes; cuando haya muchos datos se guardará un resumen diario.
"""
import datetime

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.db.models import Count, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import TruncHour, TruncWeek
from django.utils import timezone
from django.utils.translation import gettext as _

from call.models import Call, ReportDelivery
from core import email_verification
from core.models import Club, Invitation, Membership, PhotoCheck
from match.models import Game, Match, MatchResultDelivery, Result
from players.models import Player, SnpAccount

from .models import (
    AccountNoticeLog, DailyActivity, DailyMetric, ErrorEvent, FollowUpTask, JobRun, RequestMetric, ScheduledJob,
    UserActivity,
)
from .scheduler import scheduler_status

User = get_user_model()

# Un club está "activo" si ha jugado (o tiene programado) un partido en esta ventana.
ACTIVE_CLUB_DAYS = 30
# Un club lleva "sin actividad" si no tiene partidos en esta ventana.
AT_RISK_DAYS = 60


def _subquery_count(model, fk, **filters):
    """
    Subconsulta que cuenta las filas de `model` cuyo campo `fk` apunta al objeto de la
    consulta exterior (con los filtros extra que se pasen). Evita los JOIN que multiplican filas.
    """
    qs = (
        model.objects.filter(**{fk: OuterRef("pk")}, **filters)
        .order_by().values(fk).annotate(n=Count("pk")).values("n")
    )
    return Subquery(qs)


def annotate_clubs(qs):
    """Añade a cada club sus contadores (miembros, jugadores, partidos) y la fecha del último partido."""
    today = timezone.localdate()
    last_match = (
        Match.objects.filter(club=OuterRef("pk"), start_date__lte=today)
        .order_by("-start_date").values("start_date")[:1]
    )
    return qs.annotate(
        n_members=_subquery_count(Membership, "club"),
        n_admins=_subquery_count(Membership, "club", role=Membership.ADMIN),
        n_players=_subquery_count(Player, "club", in_team=True),
        n_matches=_subquery_count(Match, "club"),
        last_match=Subquery(last_match),
    )


def google_user_ids():
    """Ids de los usuarios que tienen cuenta de Google enlazada (subconsulta para filtrar)."""
    return SocialAccount.objects.filter(provider="google").values("user_id")


def dashboard_kpis():
    """
    Cifras del dashboard: clubes, usuarios, actividad, invitaciones, altas por semana y
    listas cortas de clubes y usuarios recientes y de clubes sin actividad.
    """
    now = timezone.now()
    today = timezone.localdate()
    active_from = today - datetime.timedelta(days=ACTIVE_CLUB_DAYS)
    at_risk_from = today - datetime.timedelta(days=AT_RISK_DAYS)

    users = User.objects.all()
    clubs = Club.objects.all()
    active_clubs = clubs.filter(
        matches__start_date__gte=active_from, matches__start_date__lte=today + datetime.timedelta(days=ACTIVE_CLUB_DAYS),
    ).distinct()

    invitations = Invitation.objects.all()
    inv_used_30 = invitations.filter(used_at__gte=now - datetime.timedelta(days=30)).count()
    inv_created_30 = invitations.filter(created_at__gte=now - datetime.timedelta(days=30)).count()

    waiting = accounts_without_club(users)

    return {
        "clubs": {
            "total": clubs.count(),
            "new_30": clubs.filter(created_at__gte=now - datetime.timedelta(days=30)).count(),
            "active": active_clubs.count(),
        },
        "users": {
            "total": users.count(),
            "new_7": users.filter(date_joined__gte=now - datetime.timedelta(days=7)).count(),
            "new_30": users.filter(date_joined__gte=now - datetime.timedelta(days=30)).count(),
            "online": online_users().count(),
            # Usuarios distintos con actividad real (DailyActivity), no solo con inicio de sesión.
            "active_24h": active_users(1),
            "active_7": active_users(7),
            "active_30": active_users(30),
            "google": users.filter(pk__in=google_user_ids()).count(),
            "without_club": users.filter(memberships__isnull=True).count(),
            # Cuentas que esperan una invitación: sin club, ni personal ni desactivadas.
            "waiting": waiting.count(),
            "waiting_7": waiting.filter(date_joined__lt=now - datetime.timedelta(days=7)).count(),
            "waiting_new_7": waiting.filter(date_joined__gte=now - datetime.timedelta(days=7)).count(),
            "waiting_oldest": waiting.order_by("date_joined").values_list("date_joined", flat=True).first(),
        },
        "activity": {
            "players": Player.objects.filter(in_team=True).count(),
            "matches_30": Match.objects.filter(start_date__gte=active_from, start_date__lte=today).count(),
            "matches_upcoming": Match.objects.filter(start_date__gt=today, start_date__lte=today + datetime.timedelta(days=30)).count(),
            "calls_open": Call.objects.filter(draft_mode=True, match__start_date__gte=today).count(),
        },
        "invitations": {
            "pending": invitations.pending().count(),
            "created_30": inv_created_30,
            "used_30": inv_used_30,
            "conversion_30": round(100 * inv_used_30 / inv_created_30) if inv_created_30 else None,
        },
        "signups_by_week": signups_by_week(weeks=8),
        "recent_clubs": annotate_clubs(clubs.order_by("-created_at"))[:5],
        "recent_users": users.order_by("-date_joined")[:5],
        "inactive_clubs": annotate_clubs(
            clubs.filter(created_at__lt=now - datetime.timedelta(days=AT_RISK_DAYS))
            .exclude(matches__start_date__gte=at_risk_from)
        ).order_by("name")[:10],
    }


def accounts_without_club(users=None):
    """Cuentas activas, que no son del personal, sin ningún club: esperan a que las inviten."""
    users = User.objects.all() if users is None else users
    return users.filter(memberships__isnull=True, is_staff=False, is_active=True)


def active_users(days, today=None):
    """Usuarios distintos con alguna petición en los últimos ``days`` días (hoy incluido)."""
    today = today or timezone.localdate()
    since = today - datetime.timedelta(days=days - 1)
    return DailyActivity.objects.filter(date__gte=since, date__lte=today).values("user").distinct().count()


def signups_by_week(weeks=8):
    """Altas de usuarios por semana (lunes), las últimas `weeks` semanas, incluidas las de cero altas."""
    today = timezone.localdate()
    this_monday = today - datetime.timedelta(days=today.weekday())
    mondays = [this_monday - datetime.timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    start = timezone.make_aware(datetime.datetime.combine(mondays[0], datetime.time.min))

    rows = (
        User.objects.filter(date_joined__gte=start)
        .annotate(week=TruncWeek("date_joined")).values("week").annotate(n=Count("pk"))
    )
    counts = {}
    for row in rows:
        week = row["week"]
        week = week.date() if isinstance(week, datetime.datetime) else week
        counts[week] = counts.get(week, 0) + row["n"]

    peak = max(counts.values(), default=0) or 1
    return [
        {"week": monday, "n": counts.get(monday, 0), "pct": round(100 * counts.get(monday, 0) / peak)}
        for monday in mondays
    ]


# ---------- Carga y usuarios conectados ----------

# Un usuario cuenta como "conectado" si ha hecho alguna petición en estos minutos.
ONLINE_MINUTES = 5


def online_users():
    """Actividad de los usuarios conectados (con alguna petición en los últimos ONLINE_MINUTES)."""
    since = timezone.now() - datetime.timedelta(minutes=ONLINE_MINUTES)
    return UserActivity.objects.filter(last_seen__gte=since).select_related("user", "club").order_by("-last_seen")


def _bars(rows, peak_key="requests"):
    """
    Añade a cada fila el porcentaje de su barra respecto a la mayor (`pct`) y la parte de
    la barra que son errores (`err_pct`). Modifica las filas y las devuelve.
    """
    peak = max((r[peak_key] for r in rows), default=0) or 1
    for r in rows:
        r["pct"] = round(100 * r[peak_key] / peak)
        # Parte de la barra que son errores 500 (se pinta en rojo).
        r["err_pct"] = round(100 * r.get("errors", 0) / r[peak_key]) if r[peak_key] else 0
    return rows


def _summary(qs):
    """Totales de un conjunto de RequestMetric: peticiones, errores, lentas, media y máximo en ms."""
    agg = qs.aggregate(requests=Sum("requests"), errors=Sum("errors"), slow=Sum("slow"),
                       total_ms=Sum("total_ms"), max_ms=Max("max_ms"))
    requests = agg["requests"] or 0
    return {
        "requests": requests,
        "errors": agg["errors"] or 0,
        "slow": agg["slow"] or 0,
        "avg_ms": round(agg["total_ms"] / requests) if requests else 0,
        "max_ms": agg["max_ms"] or 0,
    }


def load_metrics():
    """Peticiones de la última hora (por minuto) y de las últimas 24 h (por hora)."""
    now = timezone.now()
    this_minute = now.replace(second=0, microsecond=0)
    this_hour = now.replace(minute=0, second=0, microsecond=0)

    first_minute = this_minute - datetime.timedelta(minutes=59)
    by_minute = {m.minute: m for m in RequestMetric.objects.filter(minute__gte=first_minute)}
    minutes = []
    for i in range(60):
        minute = first_minute + datetime.timedelta(minutes=i)
        m = by_minute.get(minute)
        minutes.append({"at": minute, "requests": m.requests if m else 0, "errors": m.errors if m else 0,
                        "avg_ms": m.avg_ms if m else 0})

    first_hour = this_hour - datetime.timedelta(hours=23)
    hourly = (
        RequestMetric.objects.filter(minute__gte=first_hour)
        .annotate(hour=TruncHour("minute")).values("hour")
        .annotate(requests=Sum("requests"), errors=Sum("errors"), total_ms=Sum("total_ms"))
    )
    by_hour = {row["hour"]: row for row in hourly}
    hours = []
    for i in range(24):
        hour = first_hour + datetime.timedelta(hours=i)
        row = by_hour.get(hour, {})
        requests = row.get("requests") or 0
        hours.append({"at": hour, "requests": requests, "errors": row.get("errors") or 0,
                      "avg_ms": round(row["total_ms"] / requests) if requests else 0})

    last_hour = RequestMetric.objects.filter(minute__gte=now - datetime.timedelta(hours=1))
    last_day = RequestMetric.objects.filter(minute__gte=now - datetime.timedelta(hours=24))
    peak = max(minutes, key=lambda m: m["requests"])
    return {
        "minutes": _bars(minutes),
        "hours": _bars(hours),
        "last_hour": _summary(last_hour),
        "last_day": _summary(last_day),
        "peak_minute": peak if peak["requests"] else None,
    }


# ---------- Uso de la plataforma ----------

USAGE_WEEKS = 12


def _weekly(dates, mondays):
    """Cuenta de fechas por semana (lunes) para las semanas dadas, con la barra relativa a la mayor."""
    counts = {}
    for d in dates:
        monday = d - datetime.timedelta(days=d.weekday())
        counts[monday] = counts.get(monday, 0) + 1
    peak = max((counts.get(m, 0) for m in mondays), default=0) or 1
    return [{"week": m, "n": counts.get(m, 0), "pct": round(100 * counts.get(m, 0) / peak)} for m in mondays]


def usage_metrics(weeks=USAGE_WEEKS):
    """
    Uso de la plataforma: enfrentamientos jugados, convocatorias cerradas y resultados
    metidos por semana (por fecha del enfrentamiento), cuántos clubes usan cada parte de
    la web y los clubes con más partidos en los últimos 30 días.
    """
    today = timezone.localdate()
    this_monday = today - datetime.timedelta(days=today.weekday())
    mondays = [this_monday - datetime.timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    start, end = mondays[0], this_monday + datetime.timedelta(days=6)
    in_range = {"start_date__gte": start, "start_date__lte": min(end, today)}

    matches = Match.objects.filter(**in_range).values_list("start_date", flat=True)
    calls = Call.objects.filter(draft_mode=False, **{f"match__{k}": v for k, v in in_range.items()}) \
        .values_list("match__start_date", flat=True)
    results = Result.objects.filter(**{f"game__match__{k}": v for k, v in in_range.items()}) \
        .values_list("game__match__start_date", flat=True)

    clubs = Club.objects.all()
    total = clubs.count()

    def adoption(label, qs):
        """{'label', 'n', 'pct'}: clubes de ``qs`` (distintos) sobre el total."""
        n = qs.values("pk").distinct().count()
        return {"label": label, "n": n, "pct": round(100 * n / total) if total else 0}

    features = [
        adoption(_("Han creado algún enfrentamiento"), clubs.filter(matches__isnull=False)),
        adoption(_("Han cerrado una convocatoria"), clubs.filter(pk__in=Call.objects.filter(draft_mode=False).values("match__club"))),
        adoption(_("Han hecho una alineación"), clubs.filter(pk__in=Game.objects.values("match__club"))),
        adoption(_("Han metido resultados"), clubs.filter(pk__in=Result.objects.values("game__match__club"))),
        adoption(_("Tienen cuenta SNP"), clubs.filter(pk__in=SnpAccount.objects.values("club"))),
        adoption(_("Tienen jugadores con cuenta"), clubs.filter(players__user__isnull=False)),
        adoption(_("Tienen más de un miembro"), clubs.annotate(n=Count("memberships")).filter(n__gt=1)),
    ]

    month_ago = today - datetime.timedelta(days=30)
    top_clubs = (
        annotate_clubs(clubs)
        .annotate(recent=Count("matches", filter=Q(matches__start_date__gte=month_ago, matches__start_date__lte=today)))
        .filter(recent__gt=0).order_by("-recent", "name")[:10]
    )
    return {
        "weeks": weeks,
        "matches": _weekly(matches, mondays),
        "calls": _weekly(calls, mondays),
        "results": _weekly(results, mondays),
        "totals": {
            "matches": len(matches), "calls": len(calls), "results": len(results),
            "all_matches": Match.objects.count(), "all_results": Result.objects.count(),
        },
        "clubs_total": total,
        "features": features,
        "top_clubs": top_clubs,
    }


# ---------- Salud de los servicios ----------

# Una cuenta SNP sin sincronizar en estos días está "atrasada" (hay dos ciclos por semana; el hueco
# más largo, de miércoles a lunes, es de 5 días, más un día de margen).
SNP_STALE_DAYS = 6
HEALTH_DAYS = 30


def _delivery_summary(model, since, club_path):
    """Cifras de una cola de envíos (``status``, ``attempts``) desde ``since``: enviados, fallidos, pendientes,
    enviados tras reintentar, % de éxito, último envío correcto y los 10 últimos sin enviar (con su club)."""
    rows = model.objects.filter(created_at__gte=since)
    by_status = dict(rows.order_by().values_list("status").annotate(n=Count("pk")))
    sent, failed, pending = (by_status.get(k, 0) for k in (model.SENT, model.FAILED, model.PENDING))
    finished = sent + failed
    last = model.objects.filter(status=model.SENT).order_by("-sent_at").values_list("sent_at", flat=True).first()
    return {
        "sent": sent, "failed": failed, "pending": pending,
        "retried": rows.filter(status=model.SENT, attempts__gt=1).count(),
        "ok_pct": round(100 * sent / finished) if finished else None,
        "last_sent": last,
        "problems": model.objects.exclude(status=model.SENT).select_related(club_path).order_by("-created_at")[:10],
    }


def health_metrics():
    """
    Salud de los servicios: envío de informes por email (ReportDelivery), sincronización
    de puntos SNP por club, procesos programados y errores 500 de la web en 24 h.
    """
    now = timezone.now()
    since = now - datetime.timedelta(days=HEALTH_DAYS)

    deliveries = ReportDelivery.objects.filter(created_at__gte=since)
    by_status = dict(deliveries.order_by().values_list("status").annotate(n=Count("pk")))
    sent = by_status.get(ReportDelivery.SENT, 0)
    failed = by_status.get(ReportDelivery.FAILED, 0)
    pending = by_status.get(ReportDelivery.PENDING, 0)
    finished = sent + failed
    retried = deliveries.filter(status=ReportDelivery.SENT, attempts__gt=1).count()
    problems = (
        ReportDelivery.objects.exclude(status=ReportDelivery.SENT)
        .select_related("call__match__club").order_by("-created_at")[:10]
    )

    results = _delivery_summary(MatchResultDelivery, since, "match__club")

    accounts = SnpAccount.objects.select_related("club")
    stale_before = now - datetime.timedelta(days=SNP_STALE_DAYS)
    snp_failing = list(accounts.filter(last_sync_ok=False).order_by("-last_sync_at")[:10])
    snp = {
        "total": accounts.count(),
        "ok": accounts.filter(last_sync_ok=True).count(),
        "failed": accounts.filter(last_sync_ok=False).count(),
        "never": accounts.filter(last_sync_at__isnull=True).count(),
        "stale": accounts.filter(last_sync_at__lt=stale_before).count(),
        "failing": snp_failing,
    }

    week_ago = now - datetime.timedelta(days=7)
    runs = JobRun.objects.filter(started_at__gte=week_ago)
    jobs = []
    for job in ScheduledJob.objects.all():
        job_runs = runs.filter(job=job)
        total_runs = job_runs.count()
        errors = job_runs.filter(status=JobRun.ERROR).count()
        last = job.runs.order_by("-started_at").first()
        jobs.append({
            "job": job, "runs": total_runs, "errors": errors, "last": last,
            "ok_pct": round(100 * (total_runs - errors) / total_runs) if total_runs else None,
        })

    web = _summary(RequestMetric.objects.filter(minute__gte=now - datetime.timedelta(hours=24)))
    web["error_pct"] = round(100 * web["errors"] / web["requests"], 2) if web["requests"] else 0

    return {
        "days": HEALTH_DAYS,
        "reports": {
            "sent": sent, "failed": failed, "pending": pending, "retried": retried,
            "ok_pct": round(100 * sent / finished) if finished else None,
            "problems": problems,
        },
        "results": results,
        "snp": snp,
        "snp_stale_days": SNP_STALE_DAYS,
        "jobs": jobs,
        "scheduler": scheduler_status(),
        "scheduler_late": scheduler_status()["late"],
        "web": web,
    }


# ---------- Que atender, contadores del menú y tendencias ----------

def attention_counts():
    """
    Cuántas cosas esperan al personal: fotos sin validar, cuentas sin confirmar con el plazo
    vencido, procesos con error en 24 h, tareas de hoy o atrasadas, clubes con SNP fallando,
    informes fallidos y avisos de resultado fallidos en 7 días y si el lanzador está parado.
    """
    now = timezone.now()
    last_notice = AccountNoticeLog.objects.filter(action=AccountNoticeLog.WARNING, user=OuterRef("pk")).order_by("-created_at")
    overdue = (
        email_verification.unverified_users().annotate(deadline=Subquery(last_notice.values("deadline_at")[:1]))
        .filter(deadline__lte=now).count()
    )
    return {
        "photos": PhotoCheck.objects.filter(status=PhotoCheck.UNCHECKED).exclude(photo="").count(),
        "unverified_overdue": overdue,
        "jobs_failed": JobRun.objects.filter(status=JobRun.ERROR, started_at__gte=now - datetime.timedelta(hours=24)).count(),
        "tasks_due": FollowUpTask.objects.filter(done_at__isnull=True, due_date__lte=timezone.localdate()).count(),
        "snp_failing": SnpAccount.objects.filter(last_sync_ok=False).count(),
        "reports_failed": ReportDelivery.objects.filter(
            status=ReportDelivery.FAILED, created_at__gte=now - datetime.timedelta(days=7)).count(),
        "results_failed": MatchResultDelivery.objects.filter(
            status=MatchResultDelivery.FAILED, created_at__gte=now - datetime.timedelta(days=7)).count(),
        "scheduler_late": scheduler_status()["late"],
    }


def attention_items(counts=None):
    """
    Bandeja de atención del dashboard: una línea por asunto pendiente (``text`` ya traducido,
    ``url`` del back-office, ``level`` danger o warning). Vacía si no hay nada.
    """
    from django.urls import reverse
    c = counts or attention_counts()
    items = []

    def add(level, text, url):
        """Añade una línea a la bandeja."""
        items.append({"level": level, "text": text, "url": url})

    if c["jobs_failed"]:
        add("danger", _("%(n)s ejecuciones de procesos con error en 24 h.") % {"n": c["jobs_failed"]}, reverse("backoffice:run_list") + "?status=error")
    if c["results_failed"]:
        add("danger", _("%(n)s avisos de resultado fallidos en 7 días.") % {"n": c["results_failed"]}, reverse("backoffice:health"))
    if c["reports_failed"]:
        add("danger", _("%(n)s informes de convocatoria fallidos en 7 días.") % {"n": c["reports_failed"]}, reverse("backoffice:health"))
    if c["snp_failing"]:
        add("warning", _("%(n)s clubes con la sincronización de SNP fallando.") % {"n": c["snp_failing"]}, reverse("backoffice:health"))
    if c["photos"]:
        add("warning", _("%(n)s fotos por validar.") % {"n": c["photos"]}, reverse("backoffice:photo_list"))
    if c["unverified_overdue"]:
        add("warning", _("%(n)s cuentas sin confirmar con el plazo vencido.") % {"n": c["unverified_overdue"]}, reverse("backoffice:unverified_list") + "?state=overdue")
    if c["tasks_due"]:
        add("warning", _("%(n)s tareas de seguimiento para hoy o atrasadas.") % {"n": c["tasks_due"]}, reverse("backoffice:task_list"))
    return items


def daily_trend(days=30):
    """Resúmenes diarios (DailyMetric) de los últimos ``days`` días, del más antiguo al más reciente, con barras relativas."""
    rows = list(DailyMetric.objects.filter(date__gte=timezone.localdate() - datetime.timedelta(days=days)).order_by("date"))
    peak = max((r.dau for r in rows), default=0) or 1
    return [{"date": r.date, "dau": r.dau, "wau": r.wau, "mau": r.mau, "users": r.users, "without_club": r.users_without_club, "clubs": r.clubs,
             "errors": r.errors_5xx, "pct": round(100 * r.dau / peak)} for r in rows]


def snapshot_daily_metrics(day=None):
    """Calcula y guarda (o actualiza) el resumen de un día; por defecto, hoy. Devuelve el DailyMetric."""
    day = day or timezone.localdate()
    active_from = day - datetime.timedelta(days=ACTIVE_CLUB_DAYS)
    metrics = RequestMetric.objects.filter(minute__date=day)
    agg = metrics.aggregate(requests=Sum("requests"), errors=Sum("errors"))
    values = {
        "clubs": Club.objects.filter(created_at__date__lte=day).count(),
        "users": User.objects.filter(date_joined__date__lte=day).count(),
        # Aproximación: las cuentas sin club de hoy entre las que ya existían ese día.
        "users_without_club": accounts_without_club().filter(date_joined__date__lte=day).count(),
        "dau": active_users(1, day),
        "wau": active_users(7, day),
        "mau": active_users(30, day),
        "active_clubs": Club.objects.filter(
            matches__start_date__gte=active_from, matches__start_date__lte=day).distinct().count(),
        "matches": Match.objects.filter(start_date=day).count(),
        "calls": Call.objects.filter(draft_mode=False, match__start_date=day).count(),
        "reports_sent": ReportDelivery.objects.filter(status=ReportDelivery.SENT, sent_at__date=day).count(),
        "requests": agg["requests"] or 0,
        "errors_5xx": agg["errors"] or 0,
    }
    metric, _created = DailyMetric.objects.update_or_create(date=day, defaults=values)
    return metric


def funnel(days=90):
    """
    Embudo de captación de los clubes creados en los últimos ``days`` días: club creado, con al menos
    3 jugadores, con un enfrentamiento, con una convocatoria cerrada y con resultados. Cada paso
    lleva su cifra, el porcentaje sobre el paso anterior y el ancho de su barra.
    """
    since = timezone.now() - datetime.timedelta(days=days)
    clubs = set(Club.objects.filter(created_at__gte=since).values_list("pk", flat=True))
    players = {
        c for c, n in Player.objects.filter(club__in=clubs, in_team=True).values_list("club").annotate(n=Count("pk")) if n >= 3
    }
    matches = set(Match.objects.filter(club__in=clubs).values_list("club", flat=True))
    calls = set(Call.objects.filter(draft_mode=False, match__club__in=clubs).values_list("match__club", flat=True))
    results = set(Result.objects.filter(game__match__club__in=clubs).values_list("game__match__club", flat=True))
    steps = [
        (_("Club creado"), clubs), (_("Con 3 jugadores o más"), players), (_("Con un enfrentamiento"), matches),
        (_("Con una convocatoria cerrada"), calls), (_("Con resultados"), results),
    ]
    out, previous, total = [], None, len(clubs)
    for label, ids in steps:
        n = len(ids & clubs)
        out.append({
            "label": label, "n": n, "pct_prev": round(100 * n / previous) if previous else None,
            "pct": round(100 * n / total) if total else 0,
        })
        previous = n
    # Cuentas nuevas del mismo periodo: cuántas ya están en un club y cuántas esperan invitación.
    new_accounts = User.objects.filter(date_joined__gte=since, is_staff=False)
    accounts = {
        "total": new_accounts.count(),
        "with_club": new_accounts.filter(memberships__isnull=False).distinct().count(),
        "waiting": accounts_without_club(new_accounts).count(),
    }
    return {"days": days, "steps": out, "accounts": accounts}


def error_summary(days=7):
    """Errores y peticiones lentas de los últimos ``days`` días: rutas más afectadas y los últimos eventos."""
    since = timezone.now() - datetime.timedelta(days=days)
    events = ErrorEvent.objects.filter(created_at__gte=since)
    paths = (
        events.values("path").annotate(n=Count("pk"), errors=Count("pk", filter=Q(status__gte=500)), worst=Max("duration_ms"))
        .order_by("-n")[:8]
    )
    return {"days": days, "paths": list(paths), "recent": list(events.select_related("user")[:15])}
