"""
Correos que se envían desde el remitente de Zyra (``ZYRA_SENDER``, con el contacto ``CONTACT_EMAIL`` en el pie).

Todos comparten el mismo diseño: el contenido de cada correo va dentro de
``emails/layout.html``, que añade el pie corporativo con el logo de Zyra y los
datos de contacto. El logo viaja incrustado en el propio correo (Content-ID), así
se ve aunque el cliente de correo bloquee las imágenes remotas.
"""
import logging
from email.mime.image import MIMEImage
from functools import lru_cache

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail.message import SafeMIMEMultipart
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from .models import Membership

logger = logging.getLogger(__name__)

LOGO_CID = "zyra-logo"
LOGO_PATH = settings.BASE_DIR / "static" / "zyra" / "email-logo.png"

@lru_cache(maxsize=1)
def _logo_bytes():
    """Bytes del logo de Zyra para incrustarlo en los correos (se lee una sola vez)."""
    return LOGO_PATH.read_bytes()


class ZyraEmail(EmailMultiAlternatives):
    """
    Correo con versión HTML y el logo incrustado.

    La parte HTML y el logo van juntos en un bloque multipart/related, y los
    adjuntos (por ejemplo el PDF de la convocatoria) quedan fuera de él:
    mixed[ related[ alternative[texto, html], logo ], adjuntos ].
    """

    def _create_alternatives(self, msg):
        """Envuelve las versiones texto/HTML en un multipart/related junto con el logo."""
        msg = super()._create_alternatives(msg)
        if not self.alternatives:
            return msg
        related = SafeMIMEMultipart(_subtype="related", encoding=self.encoding or settings.DEFAULT_CHARSET)
        related.attach(msg)
        logo = MIMEImage(_logo_bytes(), _subtype="png")
        logo.add_header("Content-ID", f"<{LOGO_CID}>")
        logo.add_header("Content-Disposition", "inline", filename="zyra.png")
        related.attach(logo)
        return related


def build_email(subject, text, html_content, to, reply_to=None, header_html=""):
    """
    Monta un correo de Zyra con el pie corporativo en texto plano y en HTML.
    ``html_content`` es HTML ya escapado/saneado por quien llama: se inserta sin volver a escaparlo.
    ``header_html`` (opcional, también ya escapado) es una celda ``<td>`` que va a todo el ancho,
    encima del contenido (por ejemplo la cabecera con el marcador).
    """
    contact = settings.CONTACT_EMAIL
    site = settings.SITE_URL
    footer = "\n\n--\n%s\n%s\n%s" % (
        _("Zyra · Gestión de equipos de pádel"),
        _("Contacto: %(contact)s") % {"contact": contact},
        f"{_('Hecho con Zyra')}: {site}\n" if site else "",
    )
    body = text.rstrip() + footer
    html = render_to_string("emails/layout.html", {
        "subject": subject,
        "content": mark_safe(html_content),  # HTML ya preparado (y escapado) por quien llama
        "header": mark_safe(header_html),
        "contact": contact,
        "site_url": site,
        "logo_cid": LOGO_CID,
    })
    email = ZyraEmail(subject=subject, body=body, to=to, reply_to=reply_to)
    email.attach_alternative(html, "text/html")
    return email


def club_admins(club):
    """Usuarios capitanes del club, ordenados por nombre de usuario."""
    return [
        m.user for m in Membership.objects.filter(club=club, role=Membership.ADMIN)
        .select_related("user").order_by("user__username")
    ]


def send_welcome_email(user, club, created=False, site_url=""):
    """
    Correo de bienvenida al entrar en un club (``created=False``) o al registrar
    uno nuevo (``created=True``). Indica el usuario, el club y sus capitanes.
    Si el usuario no tiene email no se envía nada. Un fallo al enviar se registra
    pero no interrumpe el registro. Devuelve True si el correo salió.
    """
    if not user.email:
        return False

    context = {
        "user": user,
        "club": club,
        "created": created,
        "admins": club_admins(club),
        "site_url": site_url,
    }
    subject = (
        _("Bienvenido a Zyra · Has creado %(club)s") % {"club": club.name} if created
        else _("Bienvenido a Zyra · Te has unido a %(club)s") % {"club": club.name}
    )
    email = build_email(
        subject,
        render_to_string("emails/welcome.txt", context),
        render_to_string("emails/welcome.html", context),
        to=[user.email],
    )
    try:
        email.send(fail_silently=False)
    except Exception:  # SMTP caído, credenciales mal configuradas...
        logger.exception("No se pudo enviar el correo de bienvenida a %s", user.email)
        return False
    return True


def send_invitation_email(invitation, url):
    """
    Envía la invitación de un capitán al email indicado. Devuelve True si el
    correo salió; un fallo se registra y el llamante decide qué hacer.
    """
    inviter = invitation.created_by
    context = {
        "club": invitation.club,
        "inviter": (inviter.get_full_name() or inviter.username) if inviter else "",
        "url": url,
        "expires_at": invitation.expires_at,
    }
    email = build_email(
        _("Te han invitado a %(club)s en Zyra") % {"club": invitation.club.name},
        render_to_string("emails/invitation.txt", context),
        render_to_string("emails/invitation.html", context),
        to=[invitation.email],
        reply_to=[inviter.email] if inviter and inviter.email else None,
    )
    try:
        email.send(fail_silently=False)
    except Exception:  # SMTP caído, credenciales mal configuradas...
        logger.exception("No se pudo enviar la invitación a %s", invitation.email)
        return False
    return True


def send_photo_removed_email(user, subjects, reason="", removals=1, site_url=""):
    """
    Avisa a ``user`` de que el personal de Zyra ha eliminado sus fotos (``subjects``:
    «Foto de ANA RUIZ», «Escudo de CD Tomares»...) por no cumplir los términos y
    condiciones. ``removals`` es cuántas veces le ha pasado, contando esta: si se repite
    se le advierte de que la cuenta puede suspenderse y el equipo eliminarse.
    Devuelve True si el correo salió.
    """
    if not user or not user.email:
        return False
    context = {
        "user": user, "subjects": subjects, "reason": reason, "removals": removals,
        "repeated": removals > 1, "site_url": site_url,
    }
    email = build_email(
        _("Hemos eliminado una foto que no cumple los términos de Zyra"),
        render_to_string("emails/photo_removed.txt", context),
        render_to_string("emails/photo_removed.html", context),
        to=[user.email],
    )
    try:
        email.send(fail_silently=False)
    except Exception:  # SMTP caído, credenciales mal configuradas...
        logger.exception("No se pudo enviar el aviso de foto eliminada a %s", user.email)
        return False
    return True


def send_unverified_account_email(user, confirm_url, deadline):
    """
    Avisa a ``user`` de que su email sigue sin confirmar y de que, si no lo confirma antes de
    ``deadline``, su cuenta se eliminará. Incluye el enlace de confirmación. Devuelve True si
    el correo salió.
    """
    if not user or not user.email:
        return False
    context = {"user": user, "confirm_url": confirm_url, "deadline": deadline}
    email = build_email(
        _("Confirma tu email en Zyra o eliminaremos tu cuenta"),
        render_to_string("emails/unverified_account.txt", context),
        render_to_string("emails/unverified_account.html", context),
        to=[user.email],
    )
    try:
        email.send(fail_silently=False)
    except Exception:  # SMTP caído, credenciales mal configuradas...
        logger.exception("No se pudo enviar el aviso de cuenta sin confirmar a %s", user.email)
        return False
    return True
