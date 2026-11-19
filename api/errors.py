"""Errores de la API con código estable: el cliente se apoya en ``code``, no en el texto."""


class ApiError(Exception):
    """
    Error que una vista o la autenticación lanza para responder en JSON ``{"error": code, "detail": ...}``.
    ``headers`` permite añadir cabeceras a la respuesta (p. ej. ``Retry-After``) y ``extra`` claves de más en el
    cuerpo (p. ej. ``fields`` con los errores por campo).
    """

    def __init__(self, code, detail, status, headers=None, extra=None):
        """Guarda el código estable, el texto para personas, el estado HTTP y las cabeceras extra."""
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.headers = headers or {}
        self.extra = extra or {}
