"""
Verificación del ``id_token`` de «Continuar con Google» en la app (un JWT firmado por Google).

La app obtiene el token con el flujo OAuth nativo (hoja del sistema, PKCE) y un cliente OAuth de tipo iOS. Aquí se
comprueba la firma con las claves públicas de Google (JWKS, en caché), el emisor, que ``aud`` sea uno de nuestros
clientes (``GOOGLE_IOS_CLIENT_IDS``), la caducidad y el ``nonce`` (la app lo manda en claro y Google lo devuelve tal cual
en el token), y cada token solo se acepta una vez. La descarga de claves es un parámetro para poder probarla sin red.
"""
import hashlib
import hmac
import time

import jwt
import requests
from django.conf import settings
from django.core.cache import cache

ISSUERS = ("https://accounts.google.com", "accounts.google.com")
JWKS_CACHE_KEY = "api:google-jwks"
JWKS_TTL_SECONDS = 60 * 60
# Como con Apple: una descarga cada pocos minutos como mucho ante un ``kid`` desconocido.
JWKS_REFETCH_SECONDS = 5 * 60
JWKS_TIMEOUT_SECONDS = 3


class GoogleTokenError(Exception):
    """El token no es válido (firma, emisor, destinatario, caducidad, nonce o ya usado)."""


class GoogleUnavailable(Exception):
    """No se pudieron obtener las claves de Google."""


def client_ids():
    """ID de cliente iOS aceptados (``GOOGLE_IOS_CLIENT_IDS``, separados por comas)."""
    return [item.strip() for item in settings.GOOGLE_IOS_CLIENT_IDS.split(",") if item.strip()]


def enabled():
    """True si el inicio de sesión con Google en la app está configurado."""
    return bool(client_ids())


def fetch_jwks():
    """Descarga las claves públicas de Google. Lanza ``GoogleUnavailable`` si no responde con claves."""
    try:
        response = requests.get(settings.GOOGLE_JWKS_URL, timeout=JWKS_TIMEOUT_SECONDS)
        response.raise_for_status()
        keys = response.json()["keys"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise GoogleUnavailable("No se pudieron obtener las claves de Google") from exc
    return keys


def _find(keys, kid):
    """Entrada del JWKS con ese ``kid`` o None."""
    return next((key for key in keys if kid and key.get("kid") == kid), None)


def _signing_key(kid, fetch):
    """Clave pública con ese ``kid``: de la caché o, una vez cada ``JWKS_REFETCH_SECONDS``, recién descargada."""
    keys = cache.get(JWKS_CACHE_KEY)
    if keys is None or (not _find(keys, kid) and cache.add(f"{JWKS_CACHE_KEY}:refetch", 1, JWKS_REFETCH_SECONDS)):
        keys = fetch()
        cache.set(JWKS_CACHE_KEY, keys, JWKS_TTL_SECONDS)
    data = _find(keys, kid)
    if data is None:
        raise GoogleTokenError("Clave de firma desconocida")
    return jwt.PyJWK(data).key


def verify_id_token(token, raw_nonce, fetch=None):
    """
    Valida el token (``fetch`` descarga las claves; por defecto ``fetch_jwks``) y devuelve sus datos
    ``{"sub", "email", "email_verified", "first_name", "last_name"}`` (email en minúsculas, ``""`` si no lo da).
    Lanza ``GoogleTokenError`` si no es válido o ya se usó y ``GoogleUnavailable`` si no hay claves de Google.
    """
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise GoogleTokenError("Algoritmo no permitido")
        claims = jwt.decode(
            token, _signing_key(header.get("kid"), fetch or fetch_jwks), algorithms=["RS256"], audience=client_ids(),
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise GoogleTokenError(str(exc)) from exc
    if claims["iss"] not in ISSUERS:
        raise GoogleTokenError("Emisor no permitido")
    if not raw_nonce or not hmac.compare_digest(str(claims.get("nonce", "")), raw_nonce):
        raise GoogleTokenError("Nonce incorrecto")
    ttl = max(60, int(claims["exp"] - time.time()))
    if not cache.add(f"api:google-used:{hashlib.sha256(token.encode()).hexdigest()}", 1, ttl):
        raise GoogleTokenError("Token ya usado")
    return {
        "sub": str(claims["sub"]), "email": str(claims.get("email") or "").strip().lower(),
        # Google lo envía como booleano (en algunos casos como el texto «true»).
        "email_verified": str(claims.get("email_verified", "")).lower() == "true",
        "first_name": str(claims.get("given_name") or "").strip(), "last_name": str(claims.get("family_name") or "").strip(),
    }
