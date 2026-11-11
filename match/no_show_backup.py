"""
Copia de las parejas y resultados de un enfrentamiento al marcarlo «No presentado» (que los borra para que no
cuenten en jugadores ni parejas) y su restauración al quitarlo.
"""
from .models import Game, Result

SLOTS = Game.PLAYER_SLOTS
RESULT_FIELDS = ("result", "set1_local", "set1_visiting", "set2_local", "set2_visiting", "set3_local",
                 "set3_visiting", "draft_mode", "retired", "injured_side")
GAME_FIELDS = ("n_game", "score", "winner", "draft_mode", "no_show")


def snapshot(match):
    """
    Guarda en ``match.no_show_backup`` (sin salvar el enfrentamiento) los partidos con sus jugadores y resultados.
    Por cada jugador guarda también el nombre, por si se elimina antes de restaurar.
    """
    backup = []
    for game in match.games.select_related(*SLOTS).prefetch_related("results").order_by("n_game", "id"):
        entry = {field: getattr(game, field) for field in GAME_FIELDS}
        entry["players"] = {slot: getattr(game, f"{slot}_id") for slot in SLOTS}
        entry["names"] = {slot: str(getattr(game, slot)) for slot in SLOTS if getattr(game, slot)}
        entry["removed_player_names"] = game.removed_player_names
        entry["results"] = [{field: getattr(r, field) for field in RESULT_FIELDS} for r in game.results.all()]
        backup.append(entry)
    match.no_show_backup = backup


def restore(match):
    """
    Vuelve a crear los partidos y resultados de ``match.no_show_backup`` y lo vacía (sin salvar el enfrentamiento).
    Un jugador eliminado entretanto deja su hueco vacío con el nombre guardado, como al eliminarlo normalmente.
    Devuelve cuántos partidos se han recuperado.
    """
    from players.models import Player
    backup = match.no_show_backup or []
    ids = {pid for entry in backup for pid in entry["players"].values() if pid}
    existing = Player.objects.in_bulk(ids)
    for entry in backup:
        slots, removed = {}, dict(entry.get("removed_player_names") or {})
        for slot in SLOTS:
            pid = entry["players"].get(slot)
            slots[f"{slot}_id"] = pid if pid in existing else None
            if pid and pid not in existing and entry["names"].get(slot):
                removed[slot] = entry["names"][slot]
        game = Game.objects.create(match=match, removed_player_names=removed, **slots,
                                   **{field: entry[field] for field in GAME_FIELDS})
        for result in entry["results"]:
            Result.objects.create(game=game, **result)
    match.no_show_backup = []
    return len(backup)
