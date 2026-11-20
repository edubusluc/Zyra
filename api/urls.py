"""URLs de ``/api/v1/``. La última ruta recoge lo desconocido y responde 404 en JSON."""
from django.urls import re_path

from . import (views, views_account, views_apple, views_auth, views_club, views_devices, views_google, views_home,
               views_invitations)

urlpatterns = [
    re_path(r"^auth/login/?$", views_auth.LoginView.as_view(), name="api_login"),
    re_path(r"^auth/apple/?$", views_apple.AppleView.as_view(), name="api_apple"),
    re_path(r"^auth/google/?$", views_google.GoogleView.as_view(), name="api_google"),
    re_path(r"^club/options/?$", views_club.ClubOptionsView.as_view(), name="api_club_options"),
    re_path(r"^club/register/?$", views_club.RegisterClubView.as_view(), name="api_club_register"),
    re_path(r"^club/create/?$", views_club.CreateClubView.as_view(), name="api_club_create"),
    re_path(r"^auth/password-reset/?$", views_auth.PasswordResetView.as_view(), name="api_password_reset"),
    re_path(r"^auth/register/?$", views_auth.RegisterAccountView.as_view(), name="api_register"),
    re_path(r"^invitations/(?P<token>[\w-]+)/accept/?$", views_invitations.AcceptInvitationView.as_view(),
            name="api_invitation_accept"),
    re_path(r"^invitations/(?P<token>[\w-]+)/?$", views_invitations.InvitationView.as_view(), name="api_invitation"),
    re_path(r"^auth/logout/?$", views_auth.LogoutView.as_view(), name="api_logout"),
    re_path(r"^auth/web-session/?$", views_auth.WebSessionView.as_view(), name="api_web_session"),
    re_path(r"^account/delete/?$", views_account.DeleteAccountView.as_view(), name="api_account_delete"),
    re_path(r"^devices/?$", views_devices.DevicesView.as_view(), name="api_devices"),
    re_path(r"^home/my-form/?$", views_home.MyFormView.as_view(), name="api_home_my_form"),
    re_path(r"^home/?$", views_home.HomeView.as_view(), name="api_home"),
    re_path(r"^ping/?$", views.PingView.as_view(), name="api_ping"),
    re_path(r"^.*$", views.NotFoundView.as_view(), name="api_not_found"),
]
