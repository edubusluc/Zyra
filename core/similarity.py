"""
Detección de nombres iguales o muy parecidos (equipos y jugadores).

Se usa al crear un equipo o un jugador para avisar al capitán de que quizá ya
existe y evitar duplicados: no bloquea, solo pregunta si quiere continuar.
"""
from difflib import SequenceMatcher

from players.snp import normalize

# Parecido mínimo (0-1) entre dos nombres normalizados para avisar.
SIMILARITY_THRESHOLD = 0.85


def _tokens(text):
    """Palabras del texto normalizado (sin tildes, signos ni mayúsculas)."""
    return normalize(text).split()


def same_name(a, b):
    """Mismo nombre sin distinguir mayúsculas, tildes, signos ni espacios: "C.D. Tomares" = "cd tomares"."""
    return "".join(_tokens(a)) == "".join(_tokens(b))


def is_similar(a, b, min_subset_tokens=1):
    """
    True si los nombres coinciden o se parecen mucho, sin distinguir mayúsculas,
    tildes ni signos: "Pádel Tomares" ≈ "padel tomares", "Tomares" ≈ "CD Tomares",
    "Juan Pérez" ≈ "Juan Perez García", "Jose Lopez" ≈ "Jose Lopes".

    ``min_subset_tokens``: palabras mínimas del nombre más corto para dar por parecido
    que esté contenido en el otro (2 en jugadores, para que "Juan" no avise de todos
    los Juanes).
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short) >= min_subset_tokens and len("".join(short)) >= 4 and set(short) <= set(long_):
        return True
    return SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio() >= SIMILARITY_THRESHOLD


def _distinguishing_tokens(text):
    """
    Palabras que distinguen a dos equipos del mismo club aunque el resto del nombre sea igual: una
    sola letra o un número ("Pádel Sevilla A" frente a "Pádel Sevilla B", "Tomares 2").
    """
    return {t for t in _tokens(text) if len(t) == 1 or t.isdigit()}


def is_same_team(a, b):
    """
    True si dos nombres son del mismo equipo: iguales o muy parecidos (``is_similar``) y sin una
    letra o un número que los distinga. Se usa al traer los equipos del grupo de SNP, donde un
    club puede tener "X A" y "X B" y no deben fundirse en uno solo. (Al crear un equipo a mano,
    ``is_similar`` solo avisa y el capitán decide.)
    """
    return is_similar(a, b) and _distinguishing_tokens(a) == _distinguishing_tokens(b)


def similar_teams(club, name, exclude_pk=None):
    """Equipos del club con un nombre igual o parecido a ``name``."""
    from team.models import Team

    teams = Team.objects.filter(club=club).exclude(pk=exclude_pk).order_by("name")
    return [t for t in teams if is_similar(name, t.name)]


def similar_players(club, name, last_name, exclude_pk=None):
    """Jugadores del club con nombre y apellidos iguales o parecidos."""
    from players.models import Player

    full_name = f"{name} {last_name}"
    players = Player.objects.filter(club=club).exclude(pk=exclude_pk).order_by("name", "last_name")
    return [p for p in players if is_similar(full_name, f"{p.name} {p.last_name}", min_subset_tokens=2)]


# Cabecera con la que el formulario pregunta (por JavaScript) si hay nombres parecidos
# antes de enviarse de verdad.
CHECK_HEADER = "HTTP_X_SIMILAR_CHECK"
CONFIRM_FIELD = "confirm_similar"


def is_check_request(request):
    """True si la petición solo pregunta por nombres parecidos (cabecera X-Similar-Check)."""
    return request.META.get(CHECK_HEADER) == "1"


def confirmed(request):
    """True si el usuario ya ha confirmado que quiere continuar pese a los nombres parecidos."""
    return request.POST.get(CONFIRM_FIELD) == "1"
