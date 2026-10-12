"""
URLs de la app core (montadas en /core/): inicio de sesión, alta de club, cambio de
club, «Mi perfil», miembros e invitaciones.
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
    path('profile/', views.my_profile, name='my_profile'),
    path('profile/verify-email/', views.resend_verification, name='resend_verification'),
    path('profile/delete/', views.delete_account_view, name='delete_account'),
    path('members/', views.club_members, name='club_members'),
    path('members/leave/', views.leave_club, name='leave_club'),
    path('members/<pid:membership_id>/update/', views.update_member, name='update_member'),
    path('members/<pid:membership_id>/transfer/', views.transfer_captaincy_view, name='transfer_captaincy'),
    path('members/<pid:membership_id>/remove/', views.remove_member, name='remove_member'),
    path('members/invitations/new/', views.create_invitation, name='create_invitation'),
    path('members/invitations/link/', views.create_invitation_link, name='create_invitation_link'),
    path('members/invitations/<pid:invitation_id>/revoke/', views.revoke_invitation, name='revoke_invitation'),
    path('monthly-report/unsubscribe/<str:token>/', views.monthly_unsubscribe, name='monthly_unsubscribe'),
    path('invite/<str:token>/', views.invitation, name='invitation'),
    path('password-check/', views.password_check, name='password_check'),
)
