"""
Backend de correo que envuelve al real y anota cada envío en EmailLog (destinatario, asunto y
si salió), para poder contestar «no me ha llegado el correo» desde el back-office.
"""
import logging

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


def _log(message, status, error=""):
    """Anota un envío; si la base de datos falla, solo se registra en el log (el correo no se pierde por eso)."""
    try:
        from .models import EmailLog
        EmailLog.objects.create(
            to=", ".join(message.to)[:500], subject=str(message.subject)[:300],
            kind=str(message.extra_headers.get("X-Zyra-Kind", ""))[:40], status=status, error=error[:2000],
        )
    except Exception:
        logger.exception("No se ha podido anotar el correo en el registro")


class LoggingEmailBackend(BaseEmailBackend):
    """Envía con ``settings.EMAIL_TRANSPORT_BACKEND`` y anota el resultado de cada correo."""

    def __init__(self, fail_silently=False, **kwargs):
        """Crea el backend real que hace el envío."""
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.inner = get_connection(settings.EMAIL_TRANSPORT_BACKEND, fail_silently=fail_silently, **kwargs)

    def open(self):
        """Abre la conexión del backend real."""
        return self.inner.open()

    def close(self):
        """Cierra la conexión del backend real."""
        return self.inner.close()

    def send_messages(self, email_messages):
        """Envía los correos de uno en uno para anotar cuál falla; devuelve cuántos salieron."""
        sent = 0
        for message in email_messages:
            try:
                count = self.inner.send_messages([message]) or 0
            except Exception as exc:
                _log(message, "failed", f"{type(exc).__name__}: {exc}")
                if not self.fail_silently:
                    raise
                continue
            _log(message, "sent" if count else "failed", "" if count else "El servidor no aceptó el correo.")
            sent += count
        return sent
