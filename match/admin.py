"""Registro de Match, Game y Result en el admin de Django."""
from django.contrib import admin
from .models import Match, Game, Result


class GameInline(admin.TabularInline):
    """Partidos de un enfrentamiento, editables dentro de su ficha."""
    model = Game
    extra = 0
    can_delete = False
    fields = ("n_game", "player_1_local", "player_2_local", "player_1_visiting", "player_2_visiting", "winner", "draft_mode")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    """Admin de enfrentamientos, con sus partidos en línea."""
    list_display = ("__str__", "club", "start_date", "season", "result", "result_points", "draft_mode")
    list_filter = ("club", "season", "result", "draft_mode")
    search_fields = ("local__name", "visiting__name", "location")
    date_hierarchy = "start_date"
    list_select_related = ("club", "local", "visiting")
    inlines = [GameInline]

    def has_delete_permission(self, request, obj=None):
        """Un enfrentamiento solo se borra desde la aplicación, que deja constancia en el registro de auditoría."""
        return False


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    """Admin de partidos por parejas."""
    list_display = ("match", "n_game", "winner", "draft_mode")
    list_filter = ("match__club", "draft_mode")
    list_select_related = ("match__local", "match__visiting")


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    """Admin de resultados por sets."""
    list_display = ("game", "result", "set1_local", "set1_visiting", "set2_local", "set2_visiting", "set3_local", "set3_visiting")
    list_filter = ("game__match__club",)
