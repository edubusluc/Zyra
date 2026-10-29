"""Asistencia a las convocatorias: qué % de la plantilla se apunta (gráfico de la página de equipo)."""
from call.models import Call
from data_analyse.pairs import match_type_lookup
from players.models import Player, joined_by


def _pct(signed, eligible):
    """Porcentaje entero de apuntados sobre los que podían apuntarse; None si no había nadie."""
    return round(signed / eligible * 100) if eligible else None


def signup_attendance(club, season=None, match_type=None):
    """
    % de jugadores que se apuntan a las convocatorias cerradas del club.

    En cada convocatoria, apuntados / jugadores que podían apuntarse: los de la plantilla actual
    (``in_team``) que ya estaban en el equipo esa temporada (``joined_by``) más los que se apuntaron
    aunque hoy ya no estén. No se guarda quién estaba en la plantilla en cada fecha, así que las bajas
    que no se apuntaron no cuentan.

    Sin ``season`` devuelve ``{'mode': 'seasons', 'rows': [...], 'average': pct}`` con una fila por
    temporada (media de sus convocatorias). Con ``season`` devuelve ``{'mode': 'calls', ...}`` con una
    fila por convocatoria, por fecha (``day``: AAAA-MM-DD). Cada fila: ``label``, ``signed``, ``eligible``, ``pct`` (y
    ``calls`` en el modo por temporadas). ``average`` es None si no hay convocatorias.
    """
    calls = Call.objects.filter(match__club=club, match__draft_mode=False, draft_mode=False, match__no_show="",
                                **match_type_lookup(match_type, "match__"))
    if season:
        calls = calls.filter(match__season=season)
    calls = calls.select_related('match', 'match__local', 'match__visiting').prefetch_related('players') \
        .order_by('match__start_date', 'match_id')
    squad = list(Player.objects.filter(club=club, in_team=True).values_list('id', 'joined_season'))

    per_call = []
    for call in calls:
        signed = {p.id for p in call.players.all()}
        eligible = {pid for pid, joined in squad if joined_by(joined, call.match.season)} | signed
        per_call.append({
            'season': call.match.season,
            'label': f"{call.match.start_date:%d/%m} · {call.match.rival_label}",
            'day': f"{call.match.start_date:%Y-%m-%d}",
            'signed': len(signed),
            'eligible': len(eligible),
            'pct': _pct(len(signed), len(eligible)),
            'ratio': len(signed) / len(eligible) * 100 if eligible else None,
        })
    average = round(sum(c['ratio'] or 0 for c in per_call) / len(per_call)) if per_call else None
    if season:
        return {'mode': 'calls', 'rows': per_call, 'average': average}

    by_season = {}
    for c in per_call:
        by_season.setdefault(c['season'], []).append(c)
    rows = [{
        'label': s,
        'calls': len(cs),
        'signed': sum(c['signed'] for c in cs),
        'eligible': sum(c['eligible'] for c in cs),
        'pct': round(sum(c['ratio'] for c in cs) / len(cs)),
    } for s, cs in sorted(by_season.items()) if all(c['ratio'] is not None for c in cs)]
    return {'mode': 'seasons', 'rows': rows, 'average': average}
