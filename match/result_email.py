"""
Aviso por email del resultado de un enfrentamiento: al cerrar el acta, cada miembro del club
recibe el marcador y el resultado de cada pareja.

Cada envío es una fila de ``MatchResultDelivery`` (una por enfrentamiento y cuenta), que hace de
cola y de idempotencia: se intenta enviar al momento y, si falla, ``send_call_reports`` lo
reintenta con las mismas esperas que el informe de convocatoria. Si el acta se reabre
y se vuelve a cerrar no se envía nada más salvo que el capitán marque «reenviar el correo» al confirmar
el cierre (por defecto desmarcado): entonces vuelve a pendiente, como corrección si el marcador cambió.
Un fallo aquí nunca impide cerrar el acta.
"""
import datetime
import logging

from django.conf import settings
from django.core.mail import get_connection
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from core.emails import build_email
from core.models import Membership, UserPreference
from core.unsubscribe import result_unsubscribe_path
from players.models import Player

from . import outcomes
from .models import MatchResultDelivery
from .notifications import LEASE, MAX_ATTEMPTS, RETRY_DELAYS, _close

logger = logging.getLogger(__name__)

# Fondo y color de acento de la cabecera según el resultado del club (V, D, E) y el amistoso.
BANDS = {"V": ("#B4F100", "#0B0B0B"), "D": ("#FF5252", "#0B0B0B"), "E": ("#FFF1C7", "#0B0B0B"),
         "A": ("#EDEDE8", "#0B0B0B")}


def recipients(match):
    """Cuentas que reciben el aviso: miembros activos del club con email y el aviso activado.

    Incluye al capitán que cierra el acta; un club suspendido no envía nada.
    """
    club = match.club
    if club is None or club.suspended_at is not None:
        return []
    members = (Membership.objects.filter(club=club, user__is_active=True).exclude(user__email="")
               .select_related("user").order_by("user__username"))
    return [m.user for m in members if UserPreference.match_result_for(m.user)]


def queue_match_result(match, force=False):
    """
    Deja en la cola un aviso para cada destinatario que aún no lo tenga con este marcador.

    Si ya se avisó del mismo marcador no se repite (salvo ``force``); si el acta se reabrió y se cerró
    con otro, la fila vuelve a pendiente como corrección. Devuelve los envíos pendientes.
    """
    now = timezone.now()
    queued = []
    for user in recipients(match):
        delivery, created = MatchResultDelivery.objects.get_or_create(
            match=match, user=user,
            defaults={"email": user.email, "result_points": match.result_points, "next_attempt_at": now})
        if created:
            queued.append(delivery)
        elif force or delivery.result_points != match.result_points:
            changed = delivery.result_points != match.result_points
            delivery.previous_points, delivery.result_points = delivery.result_points, match.result_points
            delivery.email, delivery.correction = user.email, changed
            delivery.status, delivery.attempts = MatchResultDelivery.PENDING, 0
            delivery.next_attempt_at, delivery.last_error, delivery.sent_at = now, "", None
            delivery.save()
            queued.append(delivery)
    return queued


def due_deliveries(now=None, limit=None):
    """Avisos pendientes cuyo próximo intento ya ha llegado, más antiguos primero (como mucho ``limit``)."""
    now = now or timezone.now()
    due = (MatchResultDelivery.objects.filter(status=MatchResultDelivery.PENDING, next_attempt_at__lte=now)
           .select_related("match__club", "match__local", "match__visiting", "user")
           .order_by("next_attempt_at", "pk"))
    return list(due[:limit] if limit else due)


def _claim(delivery, now):
    """Reserva el envío de forma atómica: si otra pasada ya lo tiene, devuelve False."""
    return MatchResultDelivery.objects.filter(
        pk=delivery.pk, status=MatchResultDelivery.PENDING, next_attempt_at__lte=now,
    ).update(next_attempt_at=now + LEASE) == 1


def _failed(delivery, error, now):
    """Anota un intento fallido y programa el siguiente; tras MAX_ATTEMPTS lo da por fallido."""
    delivery.attempts += 1
    delivery.last_error = str(error)[:2000] or error.__class__.__name__
    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.status, delivery.next_attempt_at = MatchResultDelivery.FAILED, None
    else:
        delivery.next_attempt_at = now + datetime.timedelta(minutes=RETRY_DELAYS[delivery.attempts - 1])
    delivery.save(update_fields=["attempts", "last_error", "status", "next_attempt_at"])
    logger.warning("No se pudo enviar el resultado %s a %s (intento %s): %s",
                   delivery.match_id, delivery.email, delivery.attempts, error)


def _sent(delivery, now):
    """Marca el envío como enviado."""
    delivery.attempts += 1
    delivery.status, delivery.sent_at = MatchResultDelivery.SENT, now
    delivery.next_attempt_at, delivery.last_error = None, ""
    delivery.save(update_fields=["attempts", "status", "sent_at", "next_attempt_at", "last_error"])


def _sets_text(result, own_is_local):
    """'6-3 6-4' desde el punto de vista del club; un set no jugado (vacío o 0-0) se omite y, si el
    partido acabó por lesión, se añade «Lesión»."""
    pairs = [(a, b) for n, (a, b) in enumerate(result.sets(), start=1)
             if a is not None and b is not None and (n == 1 or a or b)]
    text = " ".join(f"{a}-{b}" if own_is_local else f"{b}-{a}" for a, b in pairs)
    return f"{text} · {_('Lesión')}" if result.retired else text


def game_rows(match, user=None):
    """
    Una fila por partido (pareja propia, sets, si se ganó y puntos que suma). ``mine`` marca el
    partido de la cuenta ``user`` si su jugador enlazado del club jugó en él.
    """
    mine = set()
    if user is not None:
        mine = set(Player.objects.filter(club=match.club, user=user).values_list("pk", flat=True))
    own_side = "local" if match.own_is_local else "visiting"
    own_winner = outcomes.WINNER_LOCAL if match.own_is_local else outcomes.WINNER_VISITING
    rows = []
    for game in match.games.order_by("n_game").prefetch_related("results"):
        result = game.results.first()
        ids = {getattr(game, f"player_{n}_{own_side}_id") for n in (1, 2)}
        won = game.winner == own_winner
        rows.append({
            "n": game.n_game, "pair": game.pair_label,
            "sets": _sets_text(result, match.own_is_local) if result else (game.get_no_show_display() if game.no_show else ""),
            "won": won, "points": game.score or 0, "mine": bool(mine & ids),
        })
    return rows


def _outcome(match):
    """(clave de resultado V/D/E, puntos propios, puntos del rival) del acta cerrada de ``match``."""
    from .views import club_score, match_outcome  # import tardío: views importa este módulo
    own, rival = club_score(match)
    return match_outcome(match), own, rival


def build_message(delivery):
    """Correo con el resultado para una cuenta: asunto, texto, HTML con la cabecera según el resultado y baja."""
    match, user = delivery.match, delivery.user
    outcome, own, rival = _outcome(match)
    friendly = match.is_friendly
    club = match.club.name
    date = f"{match.start_date:%d/%m/%Y}"
    labels = {"V": _("Victoria"), "D": _("Derrota"), "E": _("Empate")}
    score = f"{own}-{rival}"
    values = {"label": labels[outcome], "score": score, "local": match.local_name,
              "visiting": match.visiting_name, "date": date}
    if friendly:
        subject = _("Amistoso: %(label)s %(score)s · %(local)s vs %(visiting)s (%(date)s)") % {
            **values, "label": labels[outcome].lower()}
    else:
        subject = _("%(label)s %(score)s · %(local)s vs %(visiting)s (%(date)s)") % values
    if delivery.correction:
        subject = _("Resultado corregido: %(subject)s") % {"subject": subject}

    rows = game_rows(match, user)
    mine = next((r for r in rows if r["mine"]), None)
    band, accent = BANDS["A" if friendly else outcome]
    unsubscribe_url = f"{settings.SITE_URL}{result_unsubscribe_path(user)}"
    context = {
        "club": club, "rival": match.rival_label, "date": date, "outcome": outcome,
        "label": labels[outcome], "score": f"{own} – {rival}", "friendly": friendly,
        "tag": match.type_label.upper(),
        "band": band, "accent": accent, "name": user.first_name or user.username,
        "rows": rows, "mine": mine, "correction": delivery.correction,
        "previous": delivery.previous_points.replace("/", "-") if delivery.previous_points else "",
        "match_url": f"{settings.SITE_URL}{reverse('call_for_match', args=[match.public_id])}",
        "profile_url": f"{settings.SITE_URL}{reverse('my_profile')}",
        "unsubscribe_url": unsubscribe_url,
    }
    html = render_to_string("emails/match_result.html", context)
    header = render_to_string("emails/match_result_header.html", context)
    text = render_to_string("emails/match_result.txt", context)
    email = build_email(subject, text, html, to=[delivery.email], header_html=header)
    email.extra_headers = {"List-Unsubscribe": f"<{unsubscribe_url}>"}
    return email


def deliver(deliveries, now=None):
    """
    Envía los avisos pendientes que se le pasen (los que otra pasada no tenga ya reservados), cada
    uno en su propio correo: si falla uno, los demás siguen. Devuelve los envíos intentados.
    """
    now = now or timezone.now()
    claimed = [d for d in deliveries if d.status == MatchResultDelivery.PENDING and _claim(d, now)]
    connection = None
    try:
        for delivery in claimed:
            try:
                message = build_message(delivery)
                if connection is None:
                    connection = get_connection(fail_silently=False)
                    connection.open()
                connection.send_messages([message])
            except Exception as exc:
                _failed(delivery, exc, now)
                # Tras un error la conexión puede quedar inservible: se abre otra.
                _close(connection)
                connection = None
            else:
                _sent(delivery, now)
                logger.info("Resultado del enfrentamiento %s enviado a %s", delivery.match_id, delivery.email)
    finally:
        _close(connection)
    return claimed


def notify_match_closed(match, resend=False):
    """
    Avisa del resultado al cerrarse el acta: encola y envía al momento. Si el acta ya se cerró antes
    (``reopened_at``) solo lo hace con ``resend``. Nunca lanza: si algo falla
    (SMTP caído, SITE_URL sin configurar…) el aviso queda pendiente o se registra, y el acta sigue cerrada.
    """
    if match.reopened_at is not None and not resend:
        return  # recierre tras reabrir: el resultado ya se avisó, solo se repite si el capitán lo pide
    try:
        deliver(queue_match_result(match, force=resend))
    except Exception:
        logger.exception("No se pudo avisar del resultado del enfrentamiento %s", match.pk)


def resend_match_result(match):
    """
    Reenvía a mano el aviso del resultado (desde el back-office) a todos los destinatarios del club.

    A diferencia del cierre del acta no respeta la idempotencia: cada fila vuelve a pendiente y se
    envía de nuevo, con el opt-out de cada cuenta como único filtro. Devuelve los envíos intentados.
    """
    now = timezone.now()
    deliveries = []
    for user in recipients(match):
        delivery, _created = MatchResultDelivery.objects.get_or_create(
            match=match, user=user,
            defaults={"email": user.email, "result_points": match.result_points, "next_attempt_at": now})
        delivery.email, delivery.result_points, delivery.correction = user.email, match.result_points, False
        delivery.status, delivery.attempts = MatchResultDelivery.PENDING, 0
        delivery.next_attempt_at, delivery.last_error, delivery.sent_at = now, "", None
        delivery.save()
        deliveries.append(delivery)
    deliver(deliveries)
    return deliveries
