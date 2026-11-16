"""Número de consultas SQL al cerrar el acta: el aviso del resultado no hace trabajo repetido por destinatario."""
from django.core import mail
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from .tests_result_email import ResultEmailFixture


@override_settings(SITE_URL="http://testserver")
class CloseMatchQueriesTests(ResultEmailFixture):
    """Cerrar el acta de un club grande cuesta casi lo mismo por destinatario extra: solo marcar, enviar y anotar."""

    def _close_counting(self, members):
        for i in range(members):
            self._member(f"u{i}", f"u{i}@example.com")
        match = self._match()
        with CaptureQueriesContext(connection) as ctx:
            response = self._close(match)
        self.assertEqual(response.status_code, 302)
        return len(ctx), match

    def test_queries_per_extra_recipient_stay_small(self):
        small, _ = self._close_counting(5)
        self.assertEqual(len(mail.outbox), 5 + 2)  # miembros + capitán + Ana
        mail.outbox.clear()
        for i in range(5, 35):
            self._member(f"u{i}", f"u{i}@example.com")
        match = self._match(wins=(1, 3, 5))
        with CaptureQueriesContext(connection) as ctx:
            self._close(match)
        self.assertEqual(len(mail.outbox), 35 + 2)
        # 30 destinatarios más: como mucho 3 consultas cada uno (reservar el envío, marcarlo enviado y margen);
        # antes eran ~25 (partidos, parejas, resultados y fichas por cada correo).
        self.assertLessEqual(len(ctx) - small, 30 * 3)
        self.assertLess(len(ctx), 250)

    def test_each_member_still_sees_their_own_game(self):
        match = self._match()
        self._close(match)
        message = next(m for m in mail.outbox if m.to == ["ana@example.com"])
        self.assertIn("Ganaste tu partido 1", message.body)
        other = next(m for m in mail.outbox if m.to == ["capi@example.com"])
        self.assertNotIn("Ganaste tu partido", other.body)
