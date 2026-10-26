"""
Envío de correos del personal a varios usuarios a la vez: destinatarios por segmento, plantillas con
variables y personalización de cada correo (cada persona recibe el suyo, sin ver a las demás).
"""
import datetime
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.html import escape
from django.utils.translation import gettext as _

from core import blocklist
from core.emails import build_email
from core.models import Membership

from .models import UserActivity
from .richtext import html_to_text, sanitize_html

User = get_user_model()

# Tope de destinatarios por envío: el envío es síncrono y un exceso bloquearía la petición.
MAX_RECIPIENTS = 300
INACTIVE_DAYS = 30
AUDIENCES = ("captains", "inactive", "all", "custom")


def audience_labels():
    """Segmentos disponibles (clave -> nombre legible)."""
    return {
        "captains": _("Capitanes de clubes activos"),
        "inactive": _("Capitanes de clubes sin actividad en %(days)s días") % {"days": INACTIVE_DAYS},
        "all": _("Todos los usuarios activos"),
        "custom": _("Lista de emails escrita a mano"),
    }


def message_templates():
    """Plantillas (clave -> asunto y texto) con las variables {nombre} y {club}."""
    return {
        "blank": {"subject": "", "body": ""},
        "news": {
            "subject": _("Novedades en Zyra"),
            "body": _("Hola {nombre},\n\nHemos añadido mejoras en Zyra que pueden venirte bien en {club}. "
                      "Entra y échales un vistazo; si algo no te cuadra, respóndeme a este correo.\n\nUn saludo."),
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
    return {"email": user.email, "name": _display_name(user), "club": _club_name(user)}


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
    Devuelve ``(destinatarios, omitidos_por_bloqueo, no_validos)``.
    """
    invalid = []
    if audience == "custom":
        emails, invalid = parse_custom(custom_raw)
        users = {u.email.lower(): u for u in User.objects.filter(is_active=True, email__in=emails)}
        candidates = [
            _recipient(users[e.lower()]) if e.lower() in users else {"email": e, "name": "", "club": ""}
            for e in emails
        ]
    else:
        base = User.objects.filter(is_active=True, is_staff=False).exclude(email="")
        if audience in ("captains", "inactive"):
            memberships = Membership.objects.filter(role=Membership.ADMIN, club__suspended_at__isnull=True)
            if audience == "inactive":
                since = timezone.now() - datetime.timedelta(days=INACTIVE_DAYS)
                active_clubs = set(UserActivity.objects.filter(last_seen__gte=since, club__isnull=False).values_list("club_id", flat=True))
                memberships = memberships.exclude(club_id__in=active_clubs)
            base = base.filter(memberships__in=memberships).distinct()
        candidates = [_recipient(u) for u in base.order_by("email")]
    recipients, blocked, seen = [], 0, set()
    for item in candidates:
        key = item["email"].lower()
        if key in seen:
            continue
        seen.add(key)
        if blocklist.is_blocked(item["email"]):
            blocked += 1
        else:
            recipients.append(item)
    return recipients, blocked, invalid


def personalise(text, recipient, html=True):
    """
    Sustituye {nombre} y {club} en ``text``; con ``html`` se escapan los valores (texto saneado) y sin
    él van tal cual (asunto). Sin club ni nombre queda un texto neutro.
    """
    values = {"{nombre}": recipient["name"] or _("equipo"), "{club}": recipient["club"] or _("tu club")}
    for key, value in values.items():
        text = text.replace(key, escape(value) if html else value)
    return text


def build_message(subject, body_html, recipient, reply_to=None):
    """Correo personalizado para un destinatario, con el formato de los correos de Zyra."""
    html = personalise(sanitize_html(body_html), recipient)
    subject = personalise(subject, recipient, html=False)
    email = build_email(subject, html_to_text(html), html, to=[recipient["email"]], reply_to=reply_to)
    email.extra_headers["X-Zyra-Kind"] = "crm"
    return email
