"""
Envío del informe mensual: a cada cuenta enlazada a un jugador que jugó partidos el mes
anterior se le manda por email un PDF con sus estadísticas (``send_monthly_reports``). Si la
cuenta juega en varios equipos (SNP y LAPI), recibe un único correo con un PDF por equipo.

Es idempotente: ``MonthlyReportDelivery`` guarda una fila por cuenta y mes, reservada antes
de enviar. Si el correo falla se borra la reserva y la siguiente pasada lo reintenta; si ya
salió, no se vuelve a enviar aunque el comando se lance varias veces.
"""
import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.core.mail import get_connection
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from core.competitions import COMPETITIONS
from core.emails import build_email
from core.models import MonthlyReportDelivery, UserPreference
from core.unsubscribe import unsubscribe_path
from players.models import Player

from .monthly_pdf import month_label, render_monthly_report, report_filename
from .monthly_report import build_monthly_report

logger = logging.getLogger(__name__)


@dataclass
class Summary:
    """Resultado de una pasada: cuentas enviadas, saltadas (con el motivo) y fallidas."""
    sent: list = field(default_factory=list)
    skipped: dict = field(default_factory=dict)
    failed: list = field(default_factory=list)

    def skip(self, reason):
        """Cuenta un salto por ``reason``."""
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def recipient_players():
    """
    Fichas de cada cuenta activa enlazada, de clubes no suspendidos: ``[(user, [player, ...])]``,
    una entrada por cuenta con sus fichas en el orden de las competiciones (SNP, LAPI).
    """
    order = {code: i for i, code in enumerate(COMPETITIONS)}
    players = (Player.objects.filter(user__isnull=False, user__is_active=True, club__suspended_at__isnull=True)
               .select_related("user", "club").order_by("user_id", "pk"))
    grouped = {}
    for player in players:
        grouped.setdefault(player.user_id, (player.user, []))[1].append(player)
    for _user, sheets in grouped.values():
        sheets.sort(key=lambda p: (order.get(p.club.competition, len(order)), p.pk))
    return list(grouped.values())


def build_reports(players, month, scope):
    """Informe de ``month`` de cada ficha de ``players`` que jugó ese mes (puede quedar vacío)."""
    return [r for r in (build_monthly_report(p, month, scope) for p in players) if r["played"]]


def absolute_unsubscribe_url(user):
    """Enlace de baja con dominio (SITE_URL), para ponerlo en el correo."""
    return f"{settings.SITE_URL}{unsubscribe_path(user)}"


def _summary_line(report, several):
    """Resumen del mes de un informe; con varios equipos dice de cuál es."""
    values = {"month": month_label(report["month"]), "played": report["played"], "wins": report["wins"],
              "pct": report["pct"], "points": report["points"], "club": report["club"].name,
              "competition": report["club"].rules.name}
    if several:
        return _("%(club)s (%(competition)s): has jugado %(played)s partidos, ganado %(wins)s (%(pct)s%%) "
                 "y sumado %(points)s puntos.") % values
    return _("Este es tu resumen de %(month)s: has jugado %(played)s partidos, ganado %(wins)s (%(pct)s%%) "
             "y sumado %(points)s puntos.") % values


def _bodies(reports, unsubscribe_url):
    """Texto plano y HTML del correo, con el resumen del mes de cada equipo y el enlace de baja."""
    several = len(reports) > 1
    greeting = _("Hola %(name)s,") % {"name": reports[0]["player"].name.strip().title()}
    lines = [_summary_line(r, several) for r in reports]
    if several:
        lines.insert(0, _("Este es tu resumen de %(month)s en cada uno de tus equipos:")
                     % {"month": month_label(reports[0]["month"])})
        attached = _("Te adjuntamos un informe en PDF por equipo con tus parejas, tus sets y el detalle de cada partido.")
    else:
        attached = _("Te adjuntamos el informe en PDF con tus parejas, tus sets y el detalle de cada partido.")
    regards = _("¡Nos vemos en pista!")
    unsub = _("Si no quieres recibir más estos correos, puedes desactivarlos aquí:")
    text = "\n\n".join([greeting, *lines, attached, regards, f"{unsub}\n{unsubscribe_url}"])
    html = mark_safe(
        "".join(format_html("<p>{}</p>", part) for part in [greeting, *lines, attached, regards])
        + format_html('<p style="font-size:12px; color:#6B6B6B;">{} <a href="{}">{}</a></p>',
                      unsub, unsubscribe_url, _("Desactivar correos mensuales"))
    )
    return text, html


def build_message(reports, to, unsubscribe_url):
    """
    Correo con un PDF adjunto por equipo y la cabecera List-Unsubscribe (los clientes de correo
    muestran «Cancelar suscripción»). Con varios equipos, cada PDF lleva la competición en el nombre.
    """
    subject = _("Tu informe de %(month)s · Zyra") % {"month": month_label(reports[0]["month"])}
    text, html = _bodies(reports, unsubscribe_url)
    email = build_email(subject, text, html, to=[to])
    email.extra_headers = {"List-Unsubscribe": f"<{unsubscribe_url}>"}
    for report in reports:
        email.attach(report_filename(report, with_competition=len(reports) > 1),
                     render_monthly_report(report), "application/pdf")
    return email


def _claim(user, month, email):
    """Reserva el envío de ``user`` en ``month``; False si ya está enviado o reservado."""
    try:
        with transaction.atomic():
            MonthlyReportDelivery.objects.create(user=user, month=month, email=email)
    except IntegrityError:
        return False
    return True


def send_monthly_reports(month, dry_run=False, limit=None):
    """
    Envía el informe de ``month`` (primer día del mes) a todos los destinatarios que corresponda.

    Salta a quien lo desactivó, no tiene email, no jugó ese mes o ya lo recibió. Con
    ``dry_run`` no envía ni reserva nada y cuenta como «enviados» los que se enviarían;
    ``limit`` corta tras ese número de envíos (para respetar el límite diario del proveedor).
    Devuelve un ``Summary``.
    """
    summary = Summary()
    connection = None
    try:
        for user, players in recipient_players():
            enabled, scope = UserPreference.monthly_for(user)
            if not enabled:
                summary.skip("lo desactivó")
            elif not user.email:
                summary.skip("sin email")
            elif MonthlyReportDelivery.objects.filter(user=user, month=month).exists():
                summary.skip("ya enviado")
            else:
                reports = build_reports(players, month, scope)
                if not reports:
                    summary.skip("sin partidos")
                elif limit is not None and len(summary.sent) >= limit:
                    summary.skip("límite de la pasada")
                elif dry_run:
                    summary.sent.append(user.email)
                elif _claim(user, month, user.email):
                    try:
                        message = build_message(reports, user.email, absolute_unsubscribe_url(user))
                        if connection is None:
                            connection = get_connection(fail_silently=False)
                            connection.open()
                        connection.send_messages([message])
                    except Exception as exc:
                        logger.exception("No se pudo enviar el informe mensual a %s", user.email)
                        MonthlyReportDelivery.objects.filter(user=user, month=month).delete()
                        summary.failed.append((user.email, str(exc)))
                        _close(connection)
                        connection = None
                    else:
                        MonthlyReportDelivery.objects.filter(user=user, month=month).update(sent_at=timezone.now())
                        summary.sent.append(user.email)
                else:
                    summary.skip("ya enviado")
    finally:
        _close(connection)
    return summary


class ManualSendError(Exception):
    """El informe no se puede enviar a mano (sin cuenta, sin jugador, sin email o sin partidos ese mes)."""


def send_monthly_report_manually(email, month):
    """
    Envía a mano el informe de ``month`` a la cuenta con ese ``email``, aunque ya se haya enviado.

    Es la salida de emergencia del backoffice: se salta la idempotencia (y la baja de los
    correos automáticos, porque lo pide el personal), pero deja constancia en
    ``MonthlyReportDelivery`` (``manual_sends`` y ``last_manual_at``). Respeta el alcance
    (todos/competitivos) elegido en «Mi perfil». Devuelve la cuenta; lanza ``ManualSendError``
    si no se puede enviar y propaga el error del correo si falla.
    """
    found = next(((u, ps) for u, ps in recipient_players() if u.email.lower() == email.strip().lower()), None)
    if found is None:
        raise ManualSendError(f"No hay ninguna cuenta activa con ese email enlazada a un jugador: {email}")
    user, players = found
    _enabled, scope = UserPreference.monthly_for(user)
    reports = build_reports(players, month, scope)
    if not reports:
        raise ManualSendError(f"{user.email} no jugó partidos en {month:%Y-%m}: no hay informe que enviar.")
    connection = get_connection(fail_silently=False)
    try:
        connection.open()
        connection.send_messages([build_message(reports, user.email, absolute_unsubscribe_url(user))])
    finally:
        _close(connection)
    now = timezone.now()
    delivery, created = MonthlyReportDelivery.objects.get_or_create(
        user=user, month=month, defaults={"email": user.email, "sent_at": now})
    delivery.email, delivery.sent_at = user.email, now
    delivery.manual_sends += 1
    delivery.last_manual_at = now
    delivery.save(update_fields=["email", "sent_at", "manual_sends", "last_manual_at"])
    return user


def _close(connection):
    """Cierra la conexión SMTP si existe, ignorando errores."""
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass
