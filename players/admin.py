"""Registro de los jugadores en el admin de Django."""
from django.contrib import admin
from .models import Player


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    """Jugadores en el admin, con filtros por club, plantilla y posición."""
    list_display = ("name", "last_name", "club", "position", "skillfull_hand", "in_team", "joined_season")
    list_filter = ("club", "in_team", "position")
    search_fields = ("name", "last_name")
    list_select_related = ("club",)

    def has_delete_permission(self, request, obj=None):
        """Los jugadores no se borran desde el admin: lo hace la aplicación con sus comprobaciones."""
        return False
