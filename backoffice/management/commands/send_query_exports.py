"""Comando ``send_query_exports``: envía por correo el CSV de las consultas guardadas con exportación programada."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from backoffice import sql
from backoffice.csvsafe import to_csv_text
from backoffice.models import SavedQuery
from django.utils.html import format_html

from django.contrib.auth import get_user_model

from backoffice.audit import audit
from core.emails import build_email


def is_due(query, today):
    """True si a la consulta le toca enviarse hoy (diaria, los lunes o el día 1) y hoy aún no se ha enviado."""
    if not query.export_every or not query.export_to:
        return False
    if query.last_exported_at and timezone.localtime(query.last_exported_at).date() >= today:
        return False
    return (query.export_every == "daily"
            or (query.export_every == "weekly" and today.weekday() == 0)
            or (query.export_every == "monthly" and today.day == 1))


class Command(BaseCommand):
    """Ejecuta las consultas guardadas con exportación y envía su CSV a los destinatarios."""
    help = "Envía por correo el CSV de las consultas guardadas con exportación programada que toquen hoy."

    def handle(self, *args, **options):
        """Una línea por consulta enviada; una consulta que falla no impide el resto."""
        today = timezone.localdate()
        sent = 0
        staff = {e.lower() for e in get_user_model().objects.filter(is_staff=True, is_active=True).exclude(email="").values_list("email", flat=True)}
        for query in SavedQuery.objects.exclude(export_every="").exclude(export_to=""):
            if not is_due(query, today):
                continue
            # Solo al personal activo: si alguien dejó de serlo, o se editó el campo a mano, no se le envía nada.
            recipients = [e.strip() for e in query.export_to.split(",") if e.strip() and e.strip().lower() in staff]
            if not recipients:
                self.stderr.write(f"{query.name}: ningún destinatario es personal activo, no se envía.")
                continue
            try:
                result = sql.run(query.sql, limit=sql.EXPORT_LIMIT)
                text = f"Consulta «{query.name}»: {result.row_count} filas."
                email = build_email(f"Zyra · {query.name}", text, format_html("<p>{}</p>", text), to=recipients)
                name = f"zyra-{query.name[:40].replace(' ', '-')}-{today:%Y%m%d}.csv"
                email.attach(name, to_csv_text(result.columns, result.rows), "text/csv")
                email.send(fail_silently=False)
            except Exception as exc:
                self.stderr.write(f"{query.name}: {exc}")
                continue
            SavedQuery.objects.filter(pk=query.pk).update(last_exported_at=timezone.now())
            audit(None, "sql.scheduled_export", query, label=query.name, rows=result.row_count, recipients=recipients)
            sent += 1
            self.stdout.write(f"Enviada: {query.name} ({result.row_count} filas)")
        if not sent:
            self.stdout.write("Nada que enviar.")
