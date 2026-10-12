"""
Envío del informe de convocatoria a los capitanes del club.

Cada envío es una fila de ReportDelivery (una por destinatario), que hace de cola: al
cerrar la convocatoria se intenta enviar al momento y, si el correo falla (SMTP caído,
límite del proveedor…), el proceso ``send_call_reports`` lo reintenta con esperas
crecientes. Tras MAX_ATTEMPTS intentos se da por fallido y se avisa al personal.
"""
import datetime
import logging
import re

from django.core.mail import get_connection
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from call.models import ReportDelivery

from core.emails import build_email
from core.models import Membership

from .report import build_report
from .report_pdf import render_report

logger = logging.getLogger(__name__)


def report_filename(match):
    """Nombre del PDF del informe, p. ej. 'convocatoria-20250301-Local-vs-Visitante.pdf'.

    Solo deja letras, números, - y _: los nombres de los equipos los escribe el capitán y unas
    comillas o un punto y coma romperían la cabecera Content-Disposition de la descarga.
    """
    name = f"convocatoria-{match.start_date:%Y%m%d}-{match.local_name}-vs-{match.visiting_name}".replace(" ", "_")
    return re.sub(r"[^\w-]", "", name) + ".pdf"


def admin_emails(club):
    """Emails (sin repetir y ordenados) de los capitanes activos del club."""
    return sorted({
        m.user.email for m in Membership.objects.filter(club=club, role=Membership.ADMIN).select_related("user")
        if m.user.email and m.user.is_active
    })


def _bodies(match):
    """Texto plano y HTML del correo. Un cuerpo con algo de contexto y versión HTML
    se parece más a un correo escrito por una persona y ayuda a no caer en spam."""
    rival = match.rival_label
    date = f"{match.start_date:%d/%m/%Y}"
    club = match.club.name
    greeting = _("Hola,")
    closed = _("Se ha cerrado la convocatoria de %(club)s para el partido contra %(rival)s del %(date)s "
               "(%(local)s vs %(visiting)s).")
    attached = _("Te adjuntamos el informe en PDF con el estado del equipo, las rachas, los precedentes "
                 "contra este rival y dos alineaciones recomendadas según el formato de la SNP.")
    questions = _("Si tienes cualquier duda, responde a este correo y le llegará a quien cerró la convocatoria.")
    regards = _("Un saludo,")
    values = {"club": club, "rival": rival, "date": date, "local": match.local_name, "visiting": match.visiting_name}
    text = (
        f"{greeting}\n\n"
        f"{closed % values}\n\n"
        f"{attached}\n\n"
        f"{questions}\n\n"
        f"{regards}\nZyra · {club}"
    )
    strong = {k: format_html("<strong>{}</strong>", values[k]) for k in ("club", "rival", "date")}
    html_values = {**{k: escape(v) for k, v in values.items()}, **strong}
    html = mark_safe(
        format_html("<p>{}</p>", greeting)
        + "<p>" + escape(closed) % html_values + "</p>"
        + format_html("<p>{}</p><p>{}</p><p>{}<br>Zyra · {}</p>", attached, questions, regards, club)
    )
    return text, html


# Espera tras cada intento fallido (en minutos): 2, 10, 30 y 120. El quinto fallo es el último.
RETRY_DELAYS = (2, 10, 30, 120)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
# Mientras se envía, el envío queda reservado este tiempo para que nadie más lo coja.
LEASE = datetime.timedelta(minutes=10)


def queue_call_report(call, sender=None):
    """
    Deja en la cola un envío del informe para cada capitán del club con email
    (si ya existía, vuelve a enviarse). Las respuestas le llegan a quien cerró la
    convocatoria (``sender``), si tiene email. Devuelve los envíos.
    """
    reply_to = sender.email if sender is not None and sender.email else ""
    now = timezone.now()
    return [
        ReportDelivery.objects.update_or_create(call=call, email=email, defaults={
            "reply_to": reply_to, "status": ReportDelivery.PENDING, "attempts": 0,
            "next_attempt_at": now, "last_error": "", "sent_at": None,
        })[0]
        for email in admin_emails(call.match.club)
    ]


def send_call_report(call, sender=None):
    """
    Encola el informe para los capitanes del club y lo intenta enviar al momento.
    Se manda un correo individual a cada uno (nadie ve las direcciones de los demás).
    Devuelve los envíos: los que no han salido se reintentan solos.
    """
    deliveries = queue_call_report(call, sender)
    deliver(deliveries)
    return deliveries


def due_deliveries(now=None, limit=None):
    """Envíos pendientes cuyo próximo intento ya ha llegado, más antiguos primero (como mucho ``limit``)."""
    now = now or timezone.now()
    due = (ReportDelivery.objects.filter(status=ReportDelivery.PENDING, next_attempt_at__lte=now)
           .select_related("call__match__club", "call__match__local", "call__match__visiting")
           .order_by("next_attempt_at", "pk"))
    return list(due[:limit] if limit else due)


def _claim(delivery, now):
    """Reserva el envío de forma atómica: si otra pasada ya lo tiene, devuelve False."""
    return ReportDelivery.objects.filter(
        pk=delivery.pk, status=ReportDelivery.PENDING, next_attempt_at__lte=now,
    ).update(next_attempt_at=now + LEASE) == 1


def _failed(delivery, error, now):
    """Anota un intento fallido y programa el siguiente; tras MAX_ATTEMPTS lo da por fallido."""
    delivery.attempts += 1
    delivery.last_error = str(error)[:2000] or error.__class__.__name__
    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = ReportDelivery.FAILED
        delivery.next_attempt_at = None
    else:
        delivery.next_attempt_at = now + datetime.timedelta(minutes=RETRY_DELAYS[delivery.attempts - 1])
    delivery.save(update_fields=["attempts", "last_error", "status", "next_attempt_at"])
    logger.warning("No se pudo enviar el informe %s a %s (intento %s): %s",
                   delivery.call_id, delivery.email, delivery.attempts, error)


def _sent(delivery, now):
    """Marca el envío como enviado."""
    delivery.attempts += 1
    delivery.status = ReportDelivery.SENT
    delivery.sent_at = now
    delivery.next_attempt_at = None
    delivery.last_error = ""
    delivery.save(update_fields=["attempts", "status", "sent_at", "next_attempt_at", "last_error"])


def deliver(deliveries, now=None):
    """
    Envía los envíos pendientes que se le pasen (los que otra pasada no tenga ya
    reservados). El PDF se genera una vez por convocatoria y cada correo se envía por
    separado: si falla uno, los demás siguen. Devuelve los envíos intentados.
    """
    now = now or timezone.now()
    claimed = [d for d in deliveries if d.status == ReportDelivery.PENDING and _claim(d, now)]
    by_call = {}
    for delivery in claimed:
        by_call.setdefault(delivery.call_id, []).append(delivery)

    connection = None
    try:
        for group in by_call.values():
            call = group[0].call
            match = call.match
            try:
                pdf = render_report(build_report(call))
            except Exception as exc:
                logger.exception("No se pudo generar el informe de la convocatoria %s", call.pk)
                for delivery in group:
                    _failed(delivery, f"No se pudo generar el PDF: {exc}", now)
                continue
            subject = _("Convocatoria cerrada · %(local)s vs %(visiting)s (%(date)s)") % {
                "local": match.local_name, "visiting": match.visiting_name, "date": f"{match.start_date:%d/%m/%Y}"}
            text, html = _bodies(match)
            for delivery in group:
                email = build_email(subject, text, html, to=[delivery.email],
                                    reply_to=[delivery.reply_to] if delivery.reply_to else None)
                email.attach(report_filename(match), pdf, "application/pdf")
                try:
                    if connection is None:
                        connection = get_connection(fail_silently=False)
                        connection.open()
                    connection.send_messages([email])
                except Exception as exc:
                    _failed(delivery, exc, now)
                    # Tras un error la conexión puede quedar inservible: se abre otra.
                    _close(connection)
                    connection = None
                else:
                    _sent(delivery, now)
                    logger.info("Informe de convocatoria %s enviado a %s", call.pk, delivery.email)
    finally:
        _close(connection)
    return claimed


def _close(connection):
    """Cierra la conexión SMTP si existe, ignorando errores."""
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass
