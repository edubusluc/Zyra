"""
Envío de correos del personal a varios usuarios a la vez: destinatarios por segmento, plantillas con
variables y personalización de cada correo (cada persona recibe el suyo, sin ver a las demás).

El envío no ocurre en la petición web: ``queue`` guarda el correo y un destinatario por fila (``MassEmail`` y
``MassEmailRecipient``) y el proceso ``send_mass_emails`` los va enviando respetando el cupo diario; si se corta,
continúa donde se quedó sin repetir a nadie. Todo correo lleva su enlace de baja, y los segmentos solo incluyen
emails verificados de personas que no se han dado de baja de estos correos.
"""
import datetime
import re

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.translation import gettext as _

from core import blocklist
from core.emails import build_email
from core.models import Membership, UserPreference
from core.unsubscribe import news_unsubscribe_path

from .metrics import accounts_without_club
from .models import MassEmail, MassEmailRecipient, UserActivity
from .richtext import html_to_text, sanitize_html

User = get_user_model()

# Tope de destinatarios por envío (el cupo diario de correos es de 300).
MAX_RECIPIENTS = 300
# Intentos por destinatario antes de darlo por fallido.
MAX_ATTEMPTS = 3
INACTIVE_DAYS = 30
AUDIENCES = ("captains", "inactive", "no_club", "all", "custom")


def audience_labels():
    """Segmentos disponibles (clave -> nombre legible)."""
    return {
        "captains": _("Capitanes de clubes activos"),
        "inactive": _("Capitanes de clubes sin actividad en %(days)s días") % {"days": INACTIVE_DAYS},
        "no_club": _("Usuarios sin club (esperan una invitación)"),
        "all": _("Todos los usuarios activos"),
        "custom": _("Lista de emails escrita a mano"),
    }


def message_templates():
    """Plantillas (clave -> asunto y texto) con las variables {nombre} y {club}."""
    return {
        "blank": {"subject": "", "body": ""},
        "news": {
            "subject": _("Novedades en Zyra"),
            "body": _("Hola {nombre},\n\nHemos sacado mejoras nuevas en Zyra y creo que os vendrán bien en {club}. "
                      "Échales un ojo y, si algo no te cuadra, respóndeme a este correo.\n\nUn saludo."),
        },
        "inactive": {
            "subject": _("¿Te echamos una mano con Zyra?"),
            "body": _("Hola {nombre},\n\nHe visto que {club} lleva un tiempo sin actividad en Zyra. ¿Hay algo que no te haya "
                      "funcionado o que eches de menos? Cuéntamelo y lo arreglamos.\n\nUn saludo."),
        },
        "feedback": {
            "subject": _("¿Qué tal va Zyra?"),
            "body": _("Hola {nombre},\n\nQuería saber qué tal os va con Zyra en {club} y qué mejoraríais. "
                      "Cualquier comentario me sirve.\n\nUn saludo."),
        },
        "no_club": {
            "subject": _("Tus estadísticas te esperan"),
            "body": _("Hola {nombre},\n\nTus estadísticas te esperan en Zyra, pero todavía no estás en ningún club. "
                      "Crea un nuevo club o solicita a tu capitán que te invite.\n\nSi necesitas ayuda, respóndeme a este correo.\n\nUn saludo."),
        },
        "maintenance": {
            "subject": _("Aviso: mantenimiento de Zyra"),
            "body": _("Hola {nombre},\n\nVamos a hacer tareas de mantenimiento en Zyra y puede que el servicio no esté "
                      "disponible unos minutos. Perdona las molestias.\n\nUn saludo."),
        },
    }


def _display_name(user):
    """Nombre con el que saludar: nombre y apellidos si existen, si no el usuario."""
    return user.get_full_name().strip() or user.get_username()


def _club_name(user):
    """Nombre del primer club del usuario (vacío si no tiene)."""
    membership = Membership.objects.filter(user=user).select_related("club").order_by("id").first()
    return membership.club.name if membership else ""


def _recipient(user):
    """Datos del destinatario para personalizar el correo."""
    return {"email": user.email, "name": _display_name(user), "club": _club_name(user), "user_id": user.pk}


def parse_custom(raw):
    """Emails válidos de un texto separado por comas, espacios o saltos de línea, sin repetir; y los no válidos."""
    valid, invalid, seen = [], [], set()
    for token in re.split(r"[\s,;]+", raw or ""):
        if not token:
            continue
        try:
            validate_email(token)
        except ValidationError:
            invalid.append(token)
            continue
        if token.lower() not in seen:
            seen.add(token.lower())
            valid.append(token)
    return valid, invalid


def recipients_for(audience, custom_raw=""):
    """
    Destinatarios del segmento: lista de dicts ``email``, ``name``, ``club`` sin emails repetidos ni bloqueados.
    Devuelve ``(destinatarios, omitidos, no_validos)``; los omitidos son los bloqueados, los que se han dado de baja de
    estos correos y, en los segmentos (no en la lista a mano), los que no tienen el email verificado.
    """
    invalid = []
    if audience == "custom":
        emails, invalid = parse_custom(custom_raw)
        users = {u.email.lower(): u for u in User.objects.filter(is_active=True, email__in=emails)}
        candidates = [
            _recipient(users[e.lower()]) if e.lower() in users else {"email": e, "name": "", "club": "", "user_id": None}
            for e in emails
        ]
    else:
        base = User.objects.filter(is_active=True, is_staff=False).exclude(email="")
        if audience == "no_club":
            base = accounts_without_club(base)
        if audience in ("captains", "inactive"):
            memberships = Membership.objects.filter(role=Membership.ADMIN, club__suspended_at__isnull=True)
            if audience == "inactive":
                since = timezone.now() - datetime.timedelta(days=INACTIVE_DAYS)
                active_clubs = set(UserActivity.objects.filter(last_seen__gte=since, club__isnull=False).values_list("club_id", flat=True))
                memberships = memberships.exclude(club_id__in=active_clubs)
            base = base.filter(memberships__in=memberships).distinct()
        users = list(base.order_by("email"))
        verified = {e.lower() for e in EmailAddress.objects.filter(verified=True, user__in=users).values_list("email", flat=True)}
        candidates = [_recipient(u) for u in users if u.email.lower() in verified]
        omitted_unverified = len(users) - len(candidates)
    opted_out = UserPreference.news_opted_out()
    recipients, blocked, seen = [], 0, set()
    for item in candidates:
        key = item["email"].lower()
        if key in seen:
            continue
        seen.add(key)
        if blocklist.is_blocked(item["email"]) or item["user_id"] in opted_out:
            blocked += 1
        else:
            recipients.append(item)
    return recipients, blocked + (0 if audience == "custom" else omitted_unverified), invalid


def personalise(text, recipient, html=True):
    """
    Sustituye {nombre} y {club} en ``text``; con ``html`` se escapan los valores (texto saneado) y sin
    él van tal cual (asunto). Sin club ni nombre queda un texto neutro.
    """
    values = {"{nombre}": recipient["name"] or _("equipo"), "{club}": recipient["club"] or _("tu club")}
    for key, value in values.items():
        text = text.replace(key, escape(value) if html else value)
    return text


def unsubscribe_url(recipient):
    """Enlace de baja de los correos informativos de la cuenta del destinatario ("" si no tiene cuenta)."""
    user = User.objects.filter(pk=recipient.get("user_id")).first() if recipient.get("user_id") else None
    return f"{settings.SITE_URL}{news_unsubscribe_path(user)}" if user else ""


def build_message(subject, body_html, recipient, reply_to=None):
    """
    Correo personalizado para un destinatario, con el formato de los correos de Zyra y su enlace de baja (en el
    pie y en la cabecera List-Unsubscribe). Quien no tiene cuenta puede pedir la baja respondiendo al correo.
    """
    url = unsubscribe_url(recipient)
    if url:
        footer = format_html('<p style="margin:22px 0 0; font-size:12px; color:#6B6B6B;">{} <a href="{}">{}</a></p>',
                             _("Recibes este correo porque tienes una cuenta en Zyra."), url, _("Dejar de recibir estos correos"))
    else:
        footer = format_html('<p style="margin:22px 0 0; font-size:12px; color:#6B6B6B;">{}</p>',
                             _("Si no quieres recibir más correos como este, respóndeme a este correo."))
    html = personalise(sanitize_html(body_html), recipient) + str(footer)
    subject = personalise(subject, recipient, html=False)
    email = build_email(subject, html_to_text(html), html, to=[recipient["email"]], reply_to=reply_to)
    email.extra_headers["X-Zyra-Kind"] = "crm"
    if url:
        email.extra_headers["List-Unsubscribe"] = f"<{url}>"
    return email


def queue(user, subject, body_html, audience, recipients, reply_to=""):
    """
    Pone en cola un envío masivo: guarda el correo y un destinatario por fila (datos para personalizarlo)
    y devuelve el ``MassEmail``. No envía nada: lo hace ``send_mass_emails``.
    """
    mass = MassEmail.objects.create(created_by=user, subject=subject, body_html=body_html, audience=audience, reply_to=reply_to or "")
    MassEmailRecipient.objects.bulk_create([
        MassEmailRecipient(mass=mass, email=r["email"], name=r["name"], club=r["club"], user_id=r.get("user_id"))
        for r in recipients
    ])
    return mass


def room_now():
    """Correos que el envío masivo puede gastar ahora: lo que queda del cupo diario menos la reserva para los avisos de la web."""
    from .metrics import email_quota
    return max(email_quota()["remaining"] - settings.EMAIL_MASS_RESERVE, 0)


def send_pending(limit=None):
    """
    Envía lo pendiente de los envíos masivos en cola, del más antiguo al más nuevo, hasta agotar el cupo de ahora
    (y ``limit``, si se da). Cada destinatario se anota al enviarse, así que una pasada cortada se reanuda sin repetir.
    Un destinatario que falla se reintenta en la pasada siguiente hasta ``MAX_ATTEMPTS`` veces. Devuelve ``(enviados, fallidos)``.
    """
    room = room_now() if limit is None else min(limit, room_now())
    sent = failed = 0
    for mass in MassEmail.objects.filter(status=MassEmail.PENDING).order_by("created_at"):
        while room > 0:
            recipient = mass.recipients.filter(status=MassEmailRecipient.PENDING).order_by("pk").first()
            if recipient is None:
                break
            room -= 1
            data = {"email": recipient.email, "name": recipient.name, "club": recipient.club, "user_id": recipient.user_id}
            try:
                build_message(mass.subject, mass.body_html, data, [mass.reply_to] if mass.reply_to else None).send(fail_silently=False)
            except Exception as exc:
                recipient.attempts += 1
                recipient.last_error = str(exc)[:300]
                if recipient.attempts >= MAX_ATTEMPTS:
                    recipient.status = MassEmailRecipient.FAILED
                    failed += 1
                recipient.save(update_fields=["attempts", "last_error", "status"])
            else:
                recipient.status, recipient.sent_at = MassEmailRecipient.SENT, timezone.now()
                recipient.save(update_fields=["status", "sent_at"])
                sent += 1
        if not mass.recipients.filter(status=MassEmailRecipient.PENDING).exists():
            mass.status, mass.finished_at = MassEmail.DONE, timezone.now()
            mass.save(update_fields=["status", "finished_at"])
            from .audit import audit
            audit(None, "email.mass_done", mass, label=mass.subject[:150], sent=mass.recipients.filter(status=MassEmailRecipient.SENT).count(),
                  failed=mass.recipients.filter(status=MassEmailRecipient.FAILED).count())
        if room <= 0:
            break
    return sent, failed
