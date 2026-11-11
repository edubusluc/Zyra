"""Comando ``rotate_encryption_key``: vuelve a cifrar las cuentas SNP con la primera clave de FIELD_ENCRYPTION_KEY."""
from django.core.management.base import BaseCommand

from core import crypto
from players.models import SnpAccount


class Command(BaseCommand):
    """Rotación de la clave de cifrado: tras poner la clave nueva delante de la antigua, re-cifra todo."""
    help = "Vuelve a cifrar usuario y contraseña de las cuentas SNP con la primera clave de FIELD_ENCRYPTION_KEY."

    def add_arguments(self, parser):
        """``--dry-run`` solo comprueba que todo se puede descifrar con las claves actuales."""
        parser.add_argument("--dry-run", action="store_true", help="Comprueba sin guardar nada.")

    def handle(self, *args, **options):
        """Re-cifra cada cuenta; si alguna no se puede descifrar no se guarda ninguna y el comando falla."""
        accounts = list(SnpAccount.objects.all())
        updated, broken = [], []
        for account in accounts:
            try:
                account.username_encrypted = crypto.rotate(account.username_encrypted)
                account.password_encrypted = crypto.rotate(account.password_encrypted)
            except crypto.DecryptionError:
                broken.append(account)
            else:
                updated.append(account)
        if broken:
            names = ", ".join(str(a.club) for a in broken)
            self.stderr.write(f"No se puede descifrar con las claves actuales: {names}. No se ha guardado nada.")
            raise SystemExit(1)
        if not options["dry_run"]:
            SnpAccount.objects.bulk_update(updated, ["username_encrypted", "password_encrypted"])
        verb = "Comprobadas" if options["dry_run"] else "Re-cifradas"
        self.stdout.write(f"{verb} {len(updated)} cuentas SNP.")
