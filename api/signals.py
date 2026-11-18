"""Señales que cortan el acceso de la app cuando la cuenta cambia de credenciales."""
from . import tokens


def revoke_tokens_on_password_change(sender, request=None, user=None, **kwargs):
    """
    Señales de allauth ``password_changed``, ``password_set`` y ``password_reset``: quien cambia o restablece la
    contraseña (p. ej. porque le robaron el móvil) cierra la sesión de todas las apps. Tendrán que iniciar sesión de nuevo.
    """
    if user is not None:
        tokens.revoke_all(user)
