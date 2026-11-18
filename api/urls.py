"""URLs de ``/api/v1/``. La última ruta recoge lo desconocido y responde 404 en JSON."""
from django.urls import re_path

from . import views, views_account, views_apple, views_auth, views_devices

urlpatterns = [
    re_path(r"^auth/login/?$", views_auth.LoginView.as_view(), name="api_login"),
    re_path(r"^auth/apple/?$", views_apple.AppleView.as_view(), name="api_apple"),
    re_path(r"^auth/logout/?$", views_auth.LogoutView.as_view(), name="api_logout"),
    re_path(r"^auth/web-session/?$", views_auth.WebSessionView.as_view(), name="api_web_session"),
    re_path(r"^account/delete/?$", views_account.DeleteAccountView.as_view(), name="api_account_delete"),
    re_path(r"^devices/?$", views_devices.DevicesView.as_view(), name="api_devices"),
    re_path(r"^ping/?$", views.PingView.as_view(), name="api_ping"),
    re_path(r"^.*$", views.NotFoundView.as_view(), name="api_not_found"),
]
