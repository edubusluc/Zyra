"""URLs de jugadores, cuenta SNP, «Completar equipo» y perfil propio."""
from django.urls import path
from .views import (create_player, list_players, edit_player, delete_player, show_player, manage_roster, snp_account, snp_account_delete, snp_account_password,
                    complete_team_start, complete_team_status, complete_team_failed, complete_team_confirm, complete_team_cancel,
                    my_player, link_player, unlink_player)

urlpatterns = (
    path("create_player",create_player, name='create_player'),
    path("list_players",list_players, name='list_players'),
    path("edit_player/<pid:player_id>",edit_player, name='edit_player'),
    path("delete_player/<pid:player_id>", delete_player, name='delete_player'),
    path("player_details/<pid:player_id>/",show_player, name = 'show_player' ),
    path("snp/", snp_account, name="snp_account"),
    path("snp/delete/", snp_account_delete, name="snp_account_delete"),
    path("snp/password/", snp_account_password, name="snp_account_password"),
    path("complete_team/", complete_team_start, name="complete_team_start"),
    path("complete_team/<pid:import_id>/", complete_team_status, name="complete_team_status"),
    path("complete_team/<pid:import_id>/failed/", complete_team_failed, name="complete_team_failed"),
    path("complete_team/<pid:import_id>/confirm/", complete_team_confirm, name="complete_team_confirm"),
    path("complete_team/<pid:import_id>/cancel/", complete_team_cancel, name="complete_team_cancel"),
    path("roster/", manage_roster, name="manage_roster"),
    path("me/", my_player, name="my_player"),
    path("me/link/<pid:player_id>/", link_player, name="link_player"),
    path("unlink/<pid:player_id>/", unlink_player, name="unlink_player"),
)