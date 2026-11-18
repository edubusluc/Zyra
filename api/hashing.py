"""Hash de los secretos de la API (tokens de dispositivo y tickets): solo se guarda el hash, nunca el valor."""
import hashlib


def hash_token(raw):
    """SHA-256 en hexadecimal. Basta (sin sal ni hash lento) porque los secretos tienen 256 bits de entropía."""
    return hashlib.sha256(raw.encode()).hexdigest()
