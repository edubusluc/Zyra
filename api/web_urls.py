"""URLs web de la app (``/app/``): el canje del ticket para abrir la web dentro de la app."""
from django.urls import path

from . import views_web

urlpatterns = [
    path("session/<slug:ticket>/", views_web.start_web_session, name="app_web_session"),
]
