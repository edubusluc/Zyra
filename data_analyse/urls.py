"""URLs de las estadísticas."""
from django.urls import path
from .views import team_statistics, statistics_per_player, statistics_per_pair, warnings_statistics, rival_statistics, rival_detail, my_statistics

urlpatterns = [
    path("mis_estadisticas", my_statistics, name='my_statistics'),
    path("team_statistics",team_statistics, name='team_statistics'),
    path("player_statistics", statistics_per_player, name='player_statistics'),
    path("pair_statistics", statistics_per_pair, name='pair_statistics'),
    path("warnings", warnings_statistics, name='warnings_statistics'),
    path("rival_statistics", rival_statistics, name='rival_statistics'),
    path("rival_detail", rival_detail, name='rival_detail'),
]
