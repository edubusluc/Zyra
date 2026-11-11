"""
Cifrado simétrico (Fernet: AES-128-CBC + HMAC-SHA256) para datos sensibles que la
aplicación necesita poder leer después, como las credenciales de SNP de cada club.

La clave sale de la variable de entorno FIELD_ENCRYPTION_KEY (genérala con
``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``).
En producción es obligatoria (zyra/settings.py no arranca sin ella). Solo en
desarrollo, si no está definida, se deriva de DJANGO_SECRET_KEY.

Rotación: FIELD_ENCRYPTION_KEY admite varias claves separadas por comas. La PRIMERA cifra y
todas descifran (``MultiFernet``), así se puede poner la nueva delante de la antigua sin perder
datos y volver a cifrar con ``python manage.py rotate_encryption_key``; después se quita la antigua.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


class DecryptionError(Exception):
    """El dato no se puede descifrar (normalmente porque ha cambiado la clave)."""
    pass


def split_keys(value):
    """Lista de claves de un valor de FIELD_ENCRYPTION_KEY (separadas por comas, sin espacios sobrantes)."""
    return [k.strip() for k in (value or "").split(",") if k.strip()]


def _fernet():
    """
    Cifrador con las claves de FIELD_ENCRYPTION_KEY (la primera cifra, todas descifran) o, si no
    está definida (solo en desarrollo), con una clave derivada de SECRET_KEY.
    """
    keys = split_keys(getattr(settings, "FIELD_ENCRYPTION_KEY", ""))
    if not keys:
        digest = hashlib.sha256(f"zyra-field-encryption:{settings.SECRET_KEY}".encode()).digest()
        keys = [base64.urlsafe_b64encode(digest)]
    return MultiFernet([Fernet(k) for k in keys])


def rotate(token):
    """Vuelve a cifrar un token con la clave primera (si ya lo está, devuelve otro token equivalente)."""
    try:
        return _fernet().rotate(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("No se ha podido descifrar el dato: ¿ha cambiado la clave de cifrado?") from exc


def encrypt(value):
    """Cifra un texto y devuelve el token como texto."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token):
    """Descifra un token de encrypt(); lanza DecryptionError si no es válido para la clave actual."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("No se ha podido descifrar el dato: ¿ha cambiado la clave de cifrado?") from exc
