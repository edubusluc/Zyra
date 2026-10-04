"""
URLs de la app core (montadas en /core/): inicio de sesión, alta de club, cambio de
club, miembros e invitaciones.
"""
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = (
    path('login/', views.ThrottledLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register_club/', views.register_club, name='register_club'),
    path('no_club/', views.no_club, name='no_club'),
    path('switch_club/', views.switch_club, name='switch_club'),
    path('onboarding/dismiss/', views.dismiss_onboarding, name='dismiss_onboarding'),
    path('members/', views.club_members, name='club_members'),
    path('members/leave/', views.leave_club, name='leave_club'),
    path('members/<pid:membership_id>/update/', views.update_member, name='update_member'),
    path('members/<pid:membership_id>/remove/', views.remove_member, name='remove_member'),
    path('members/invitations/new/', views.create_invitation, name='create_invitation'),
    path('members/invitations/link/', views.create_invitation_link, name='create_invitation_link'),
    path('members/invitations/<pid:invitation_id>/revoke/', views.revoke_invitation, name='revoke_invitation'),
    path('invite/<str:token>/', views.invitation, name='invitation'),
    path('password-check/', views.password_check, name='password_check'),
)
