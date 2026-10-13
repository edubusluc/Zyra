"""
Estado del servicio de SNP (la lectura de puntos y de equipos con Playwright).

El personal puede apagarlo desde el back-office (``core.models.ServiceSwitch``): mientras está
apagado no se lanza ninguna lectura y a los capitanes se les enseña que el servicio no está
disponible. Si SNP falla de forma repetida (cambia su web, nos bloquea, está caído) se avisa
por email al personal para que decida si apagarlo.
"""
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.emails import build_email
from core.models import ServiceSwitch

logger = logging.getLogger(__name__)

# Fallos seguidos (de SNP, no de la cuenta de un capitán) que disparan el aviso al personal, y
# tiempo mínimo entre dos avisos.
ALERT_AFTER_FAILURES = 3
ALERT_EVERY = timedelta(hours=6)

UNAVAILABLE_MESSAGE = gettext_lazy(
    "La conexión con SNP no está disponible ahora mismo. Inténtalo más tarde: no hace falta que cambies nada en tu cuenta."
)


def is_enabled():
    """True si la lectura de SNP está activa."""
    return ServiceSwitch.is_enabled(ServiceSwitch.SNP)


def set_enabled(enabled, user=None, reason=""):
    """Enciende o apaga la lectura de SNP (lo hace el personal) y reinicia el contador de fallos."""
    ServiceSwitch.objects.update_or_create(
        name=ServiceSwitch.SNP,
        defaults={"enabled": enabled, "reason": reason[:300], "changed_at": timezone.now(), "changed_by": user,
                  "failure_streak": 0},
    )


def report_success():
    """Una lectura ha ido bien: SNP responde, se pone a cero la racha de fallos."""
    ServiceSwitch.objects.filter(name=ServiceSwitch.SNP, failure_streak__gt=0).update(failure_streak=0)


def report_failure(detail):
    """
    Anota un fallo de SNP (no de la cuenta de un capitán: red, web cambiada, bloqueo). Al llegar a
    ``ALERT_AFTER_FAILURES`` seguidos avisa por email al personal, y no vuelve a hacerlo en
    ``ALERT_EVERY``. Devuelve True si ha enviado el aviso.
    """
    switch, _created = ServiceSwitch.objects.get_or_create(name=ServiceSwitch.SNP)
    switch.failure_streak += 1
    now = timezone.now()
    due = (switch.failure_streak >= ALERT_AFTER_FAILURES and switch.enabled
           and (switch.alerted_at is None or now - switch.alerted_at >= ALERT_EVERY))
    sent = _alert_staff(switch.failure_streak, detail) if due else False
    if sent:
        switch.alerted_at = now
    switch.save(update_fields=["failure_streak", "alerted_at"])
    return sent


def _alert_staff(streak, detail):
    """Manda al personal el aviso de que SNP falla, con el enlace para apagar el servicio."""
    recipients = list(
        get_user_model().objects.filter(is_staff=True, is_active=True).exclude(email="").values_list("email", flat=True)
    )
    if not recipients:
        return False
    from django.conf import settings

    path = reverse("backoffice:services")
    link = (settings.SITE_URL + path) if settings.SITE_URL else path
    context = {"streak": streak, "detail": detail, "link": link}
    email = build_email(
        _("Zyra · La lectura de SNP está fallando"),
        render_to_string("backoffice/emails/snp_down.txt", context),
        render_to_string("backoffice/emails/snp_down.html", context),
        to=recipients,
    )
    try:
        email.send(fail_silently=False)
    except Exception:
        logger.exception("No se pudo enviar el aviso de que SNP falla")
        return False
    return True
