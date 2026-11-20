"""Señales del back-office: limpieza de la actividad al cerrar sesión."""
from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

from .middleware import activity_cache, activity_cache_key
from .models import UserActivity


@receiver(user_logged_out)
def forget_activity(sender, user, **kwargs):
    """Quien cierra sesión deja de contar como conectado."""
    if user is not None:
        UserActivity.objects.filter(user=user).delete()
        activity_cache().delete(activity_cache_key(user.pk))
