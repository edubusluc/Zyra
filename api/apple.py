"""
Verificación del ``identity_token`` de «Iniciar sesión con Apple» (un JWT firmado por Apple).

Se comprueba la firma con las claves públicas de Apple (JWKS, en caché), el emisor, que ``aud`` sea una de nuestras
apps (``APPLE_CLIENT_IDS``), la caducidad y el ``nonce`` (la app manda el valor en claro y Apple firmó su SHA-256), y
cada token solo se acepta una vez. Sin HTTP de vistas: la descarga de claves es un parámetro para poder probarla sin red.
"""
import hashlib
import hmac
import time

import jwt
import requests
from django.conf import settings
from django.core.cache import cache

ISSUER = "https://appleid.apple.com"
JWKS_CACHE_KEY = "api:apple-jwks"
JWKS_TTL_SECONDS = 60 * 60
# Cuánto se espera antes de volver a descargar las claves cuando llega un ``kid`` desconocido (evita que enviar
# tokens inventados obligue a llamar a Apple en cada petición).
JWKS_REFETCH_SECONDS = 5 * 60
JWKS_TIMEOUT_SECONDS = 3


class AppleTokenError(Exception):
    """El token no es válido (firma, emisor, destinatario, caducidad, nonce o ya usado)."""


class AppleUnavailable(Exception):
    """No se pudieron obtener las claves de Apple."""


def client_ids():
    """Identificadores de app aceptados (``APPLE_CLIENT_IDS``, separados por comas)."""
    return [item.strip() for item in settings.APPLE_CLIENT_IDS.split(",") if item.strip()]


def enabled():
    """True si el inicio de sesión con Apple está configurado."""
    return bool(client_ids())


def fetch_jwks():
    """Descarga las claves públicas de Apple. Lanza ``AppleUnavailable`` si no responde con claves."""
    try:
        response = requests.get(settings.APPLE_JWKS_URL, timeout=JWKS_TIMEOUT_SECONDS)
        response.raise_for_status()
        keys = response.json()["keys"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise AppleUnavailable("No se pudieron obtener las claves de Apple") from exc
    return keys


def _signing_key(kid, fetch):
    """Clave pública con ese ``kid``: de la caché o, una vez cada ``JWKS_REFETCH_SECONDS``, recién descargada."""
    keys = cache.get(JWKS_CACHE_KEY)
    if keys is None or (not _find(keys, kid) and cache.add(f"{JWKS_CACHE_KEY}:refetch", 1, JWKS_REFETCH_SECONDS)):
        keys = fetch()
        cache.set(JWKS_CACHE_KEY, keys, JWKS_TTL_SECONDS)
    data = _find(keys, kid)
    if data is None:
        raise AppleTokenError("Clave de firma desconocida")
    return jwt.PyJWK(data).key


def _find(keys, kid):
    """Entrada del JWKS con ese ``kid`` o None."""
    return next((key for key in keys if kid and key.get("kid") == kid), None)


def _digest(value):
    """SHA-256 hexadecimal de un texto."""
    return hashlib.sha256(value.encode()).hexdigest()


def verify_identity_token(token, raw_nonce, fetch=None):
    """
    Valida el token (``fetch`` descarga las claves; por defecto ``fetch_jwks``) y devuelve sus datos ``{"sub", "email", "email_verified"}`` (email en minúsculas, ``""`` si Apple
    no lo da). Lanza ``AppleTokenError`` si no es válido o ya se usó y ``AppleUnavailable`` si no hay claves de Apple.
    """
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise AppleTokenError("Algoritmo no permitido")
        claims = jwt.decode(
            token, _signing_key(header.get("kid"), fetch or fetch_jwks), algorithms=["RS256"], audience=client_ids(),
            issuer=ISSUER, options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AppleTokenError(str(exc)) from exc
    if not hmac.compare_digest(str(claims.get("nonce", "")), _digest(raw_nonce)):
        raise AppleTokenError("Nonce incorrecto")
    ttl = max(60, int(claims["exp"] - time.time()))
    if not cache.add(f"api:apple-used:{_digest(token)}", 1, ttl):
        raise AppleTokenError("Token ya usado")
    return {
        "sub": str(claims["sub"]), "email": str(claims.get("email") or "").strip().lower(),
        # Apple lo envía como booleano o como el texto «true».
        "email_verified": str(claims.get("email_verified", "")).lower() == "true",
    }
