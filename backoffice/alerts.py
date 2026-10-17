"""
Alertas por correo al personal: se avisa cuando un problema empieza, un recordatorio si sigue
pasado un día, y otra vez cuando se resuelve (no en cada pasada). Lo ejecuta ``send_staff_alerts``.
"""
import datetime

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from django.utils.html import format_html

from core.emails import build_email

from .metrics import attention_counts
from .models import AlertState, RequestMetric, ScheduledJob

REMIND_EVERY = datetime.timedelta(hours=24)
FAILING_JOB_RUNS = 3
SNP_FAILING_CLUBS = 3
ERRORS_PER_HOUR = 10


def current_problems(now=None):
    """Problemas de ahora mismo: dict {clave: texto}. Una clave que no aparece está resuelta."""
    now = now or timezone.now()
    counts = attention_counts()
    problems = {}
    if counts["scheduler_late"]:
        problems["scheduler"] = _("El lanzador de procesos no está en marcha.")
    if counts["reports_failed"]:
        problems["reports"] = _("Hay %(n)s informes de convocatoria fallidos en los últimos 7 días.") % {"n": counts["reports_failed"]}
    if counts["snp_failing"] >= SNP_FAILING_CLUBS:
        problems["snp"] = _("%(n)s clubes tienen la sincronización de SNP fallando.") % {"n": counts["snp_failing"]}
    errors = RequestMetric.objects.filter(minute__gte=now - datetime.timedelta(hours=1)).aggregate(n=Sum("errors"))["n"] or 0
    if errors >= ERRORS_PER_HOUR:
        problems["web_errors"] = _("%(n)s errores 500 en la última hora.") % {"n": errors}
    failing = list(ScheduledJob.objects.filter(consecutive_failures__gte=FAILING_JOB_RUNS).values_list("name", flat=True))
    if failing:
        problems["jobs"] = _("Procesos fallando varias veces seguidas: %(jobs)s.") % {"jobs": ", ".join(failing)}
    return problems


def staff_emails():
    """Emails del personal activo."""
    return list(get_user_model().objects.filter(is_staff=True, is_active=True).exclude(email="").values_list("email", flat=True))


def _send(subject, text):
    """Envía un correo corto al personal; devuelve si salió."""
    recipients = staff_emails()
    if not recipients:
        return False
    try:
        build_email(subject, text, format_html("<p>{}</p>", text), to=recipients).send(fail_silently=False)
    except Exception:
        return False
    return True


def evaluate(now=None):
    """
    Compara los problemas actuales con su estado guardado y envía los avisos que toquen (inicio,
    recordatorio y resolución). Devuelve la lista de avisos enviados como textos.
    """
    now = now or timezone.now()
    problems = current_problems(now)
    sent = []
    for name, text in problems.items():
        state, _created = AlertState.objects.get_or_create(name=name)
        if not state.active or state.notified_at is None or now - state.notified_at >= REMIND_EVERY:
            if _send(_("Zyra · Alerta: %(text)s") % {"text": text}, text):
                sent.append(text)
                state.notified_at = now
        if not state.active:
            state.since = now
        state.active = True
        state.save()
    for state in AlertState.objects.filter(active=True).exclude(name__in=problems):
        text = _("Resuelto: %(name)s ya no da problemas.") % {"name": state.name}
        if _send(_("Zyra · %(text)s") % {"text": text}, text):
            sent.append(text)
        state.active, state.since, state.notified_at = False, None, None
        state.save()
    return sent
