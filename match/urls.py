"""Rutas de la app de partidos (enfrentamientos, convocatorias, partidos y resultados)."""
from django.urls import path
from .views import *
from call.views import delete_call, availability, availability_set, availability_regenerate, availability_remind

urlpatterns = (
    path("create_match",create_match, name='create_match'),
    path("list_match",list_match, name='list_match'),
    path("calendar_match", calendar_match, name='calendar_match'),
    path("edit_match_date/<pid:match_id>/",edit_match_date, name='edit_match_date'),
    path("create_call/<pid:match_id>/",create_call, name='create_call'),
    path('call_for_match/<pid:match_id>/', call_for_match, name='call_for_match'),
    path("create_game/<pid:match_id>/",create_game_for_match, name='create_game'),
    path("create_result/<pid:game_id>/",create_result, name='create_result'),
    path("edit_result/<pid:game_id>/",edit_result, name='edit_result'),
    path("results/<pid:match_id>/", enter_results, name='enter_results'),
    path("existing_call/<pid:match_id>/", existing_call_view, name="existing_call"),
    path("edit_call/<pid:call_id>/", edit_call, name='edit_call'),
    path("closed_call/<pid:call_id>/", closed_call, name="closed_call"),
    path('close_match/<pid:match_id>/', close_match, name='close_match'),
    path('reopen_match/<pid:match_id>/', reopen_match, name='reopen_match'),
    path('no_show/<pid:match_id>/', mark_no_show, name='mark_no_show'),
    path('stage_view/<pid:match_id>/', set_stage_view, name='set_stage_view'),
    path('no_show/<pid:match_id>/undo/', undo_no_show, name='undo_no_show'),
    path('delete_call/<pid:match_id>/', delete_call, name='delete_call'),
    path('close_call/<pid:match_id>/', close_call, name='close_call'),
    path('reopen_call/<pid:match_id>/', reopen_call, name='reopen_call'),
    path('edit_game_match/<pid:match_id>/', edit_game_match, name='edit_games_match'),
    path('suggested_lineup/<pid:match_id>/', suggested_lineup, name='suggested_lineup'),
    path('delete_match/<pid:match_id>/', delete_match, name='delete_match'),
    path('disponibilidad/<str:token>/', availability, name='availability'),
    path('availability/<pid:match_id>/set/', availability_set, name='availability_set'),
    path('availability/<pid:match_id>/regenerate/', availability_regenerate, name='availability_regenerate'),
    path('availability/<pid:match_id>/remind/', availability_remind, name='availability_remind'),
    path('call_report/<pid:match_id>/', call_report_pdf, name='call_report'),
    path('call_report/<pid:match_id>/resend/', resend_call_report, name='resend_call_report'),
)