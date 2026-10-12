"""URLs de equipos."""
from django.urls import path
from .views import list_team, create_team, edit_team, manage_teams, reactivate_team

urlpatterns = [
    path("list_teams",list_team, name='list_teams'), 
    path("create_team",create_team, name='create_team'),
    path("edit_team/<pid:team_id>/",edit_team, name='edit_team'),
    path("manage_teams/", manage_teams, name='manage_teams'),
    path("reactivate_team/<pid:team_id>/", reactivate_team, name='reactivate_team'),
]