"""URLs de ``/api/v1/``. La última ruta recoge lo desconocido y responde 404 en JSON."""
from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^ping/?$", views.PingView.as_view(), name="api_ping"),
    re_path(r"^.*$", views.NotFoundView.as_view(), name="api_not_found"),
]
