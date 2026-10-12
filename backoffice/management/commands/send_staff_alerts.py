"""Comando ``send_staff_alerts``: avisa por correo al personal cuando algo falla (y cuando se arregla)."""
from django.core.management.base import BaseCommand

from backoffice.alerts import evaluate


class Command(BaseCommand):
    """Revisa los problemas de la plataforma y envía los avisos que toquen."""
    help = ("Avisa por correo al personal de problemas nuevos, repite el aviso cada 24 h si siguen y avisa al resolverse. "
            "Para detectar que el lanzador está parado, ejecútalo también desde un cron aparte del lanzador.")

    def handle(self, *args, **options):
        """Escribe un aviso por línea o «Sin avisos nuevos.»."""
        sent = evaluate()
        for text in sent:
            self.stdout.write(f"Avisado: {text}")
        if not sent:
            self.stdout.write("Sin avisos nuevos.")
