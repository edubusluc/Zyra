"""Resumen semanal por correo para el dueño de Zyra (``send_staff_digest``)."""
import datetime

from django.utils import timezone
from django.utils.translation import gettext as _

from call.models import ReportDelivery
from match.models import MatchResultDelivery
from django.utils.html import format_html

from core.emails import build_email
from core.models import Club
from django.contrib.auth import get_user_model

from .alerts import staff_emails
from .metrics import active_users, dashboard_kpis
from .models import FollowUpTask, RequestMetric
from django.db.models import Sum


def build_digest(days=7):
    """Cifras de los últimos ``days`` días como lista de líneas de texto."""
    now = timezone.now()
    since = now - datetime.timedelta(days=days)
    kpis = dashboard_kpis()
    reports = ReportDelivery.objects.filter(created_at__gte=since)
    results = MatchResultDelivery.objects.filter(created_at__gte=since)
    errors = RequestMetric.objects.filter(minute__gte=since).aggregate(n=Sum("errors"))["n"] or 0
    new_clubs = Club.objects.filter(created_at__gte=since).count()
    new_users = get_user_model().objects.filter(date_joined__gte=since).count()
    tasks = FollowUpTask.objects.filter(done_at__isnull=True, due_date__lte=timezone.localdate()).count()
    lines = [
        _("Clubes nuevos: %(n)s (total %(total)s)") % {"n": new_clubs, "total": kpis["clubs"]["total"]},
        _("Usuarios nuevos: %(n)s (total %(total)s)") % {"n": new_users, "total": kpis["users"]["total"]},
        _("Usuarios activos en %(days)s días: %(n)s") % {"days": days, "n": active_users(days)},
        _("Clubes activos (partido en 30 días): %(n)s") % {"n": kpis["clubs"]["active"]},
        _("Informes enviados: %(sent)s · fallidos: %(failed)s") % {
            "sent": reports.filter(status=ReportDelivery.SENT).count(), "failed": reports.filter(status=ReportDelivery.FAILED).count()},
        _("Avisos de resultado enviados: %(sent)s · fallidos: %(failed)s") % {
            "sent": results.filter(status=MatchResultDelivery.SENT).count(),
            "failed": results.filter(status=MatchResultDelivery.FAILED).count()},
        _("Errores 500: %(n)s") % {"n": errors},
        _("Clubes sin actividad (más de 60 días): %(n)s") % {"n": len(kpis["inactive_clubs"])},
        _("Tareas de seguimiento para hoy o atrasadas: %(n)s") % {"n": tasks},
    ]
    return lines


def send_digest(days=7):
    """Envía el resumen al personal; devuelve a cuántas personas."""
    recipients = staff_emails()
    if not recipients:
        return 0
    lines = build_digest(days)
    text = "\n".join("- " + line for line in lines)
    html = "<ul>" + "".join(format_html("<li>{}</li>", line) for line in lines) + "</ul>"
    build_email(_("Zyra · Resumen de la semana"), text, html, to=recipients).send(fail_silently=False)
    return len(recipients)
