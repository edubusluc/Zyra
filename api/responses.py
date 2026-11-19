"""Respuestas JSON de la API: un único formato de éxito y de error."""
from django.http import JsonResponse


def json_ok(data=None, status=200):
    """Respuesta correcta con ``data`` (un diccionario; vacío si no hay nada que devolver)."""
    return JsonResponse(data if data is not None else {}, status=status)


def json_error(error):
    """Respuesta de error a partir de un ``ApiError``: ``{"error": código, "detail": texto}`` (más ``error.extra``)."""
    response = JsonResponse({"error": error.code, "detail": str(error.detail), **error.extra}, status=error.status)
    for name, value in error.headers.items():
        response[name] = value
    return response
