"""
Vistas que unen los espacios de una cuenta (su equipo en cada competición: SNP, LAPI…): lo que se
consulta (Enfrentamientos, Calendario, Inicio, Estadísticas) junta los espacios con un filtro
«Todas · SNP · LAPI»; lo que se gestiona (Plantilla, Club, crear, convocar…) sigue siendo del
espacio activo.

El filtro va en la URL (``?espacio=snp``) y se recuerda en la sesión; por defecto, «Todas». Quien
solo tiene un espacio no ve el filtro y todo funciona como antes. En la interfaz no se habla de
«espacios» sino de equipos y competiciones, y el espacio activo cambia sin avisar: al abrir un
enfrentamiento, al elegir una competición o al ir a Plantilla, Club o Rivales.
"""
from functools import wraps

from django.utils.translation import gettext as _

from .competitions import COMPETITIONS
from .middleware import SESSION_KEY

SPACE_PARAM = "espacio"
ALL_SPACES = "todas"
SESSION_FILTER_KEY = "space_filter"


def user_clubs(request):
    """Clubes (espacios) del usuario sin los suspendidos, en el orden de las competiciones (SNP, LAPI…)."""
    order = list(COMPETITIONS)
    clubs = [m.club for m in getattr(request, "user_memberships", [])]
    return sorted(clubs, key=lambda c: order.index(c.competition) if c.competition in order else len(order))


def is_multi_space(request):
    """True si el usuario tiene más de un espacio (entonces se ven el filtro y las etiquetas)."""
    return len(getattr(request, "user_memberships", [])) > 1


def membership_for(request, club):
    """Membresía del usuario en ``club`` (de las ya cargadas por el middleware) o None."""
    return next((m for m in getattr(request, "user_memberships", []) if m.club_id == club.id), None)


def selected_spaces(request, allow_all=True, session_key=SESSION_FILTER_KEY):
    """
    Espacios que se consultan: (código elegido, clubes). El código es «todas» o el de una
    competición en la que el usuario tiene espacio; viene de ``?espacio=`` (y se recuerda en la
    sesión, en ``session_key``) o, si no, de lo último elegido. Con un solo espacio devuelve
    (None, [club activo]).

    Sin ``allow_all`` (páginas que no mezclan competiciones, como Estadísticas › Equipo) siempre es
    una competición: la primera vez, la del primer equipo que gestiona o, si no gestiona ninguno,
    la primera (SNP).
    """
    if not is_multi_space(request):
        return None, [request.club] if request.club else []
    clubs = user_clubs(request)
    codes = {c.competition for c in clubs}
    valid = codes | ({ALL_SPACES} if allow_all else set())
    wanted = request.GET.get(SPACE_PARAM)
    if wanted in valid:
        request.session[session_key] = wanted
    else:
        wanted = request.session.get(session_key)
        if wanted not in valid:
            if allow_all:
                wanted = ALL_SPACES
            else:
                managed = managed_clubs(request, clubs)
                wanted = (managed or clubs)[0].competition
    if wanted == ALL_SPACES:
        return ALL_SPACES, clubs
    return wanted, [c for c in clubs if c.competition == wanted]


def plays_only(request):
    """
    True si la cuenta tiene varios equipos y en todos es jugador (no gestiona ninguno): no ve
    Plantilla ni el listado de jugadores de Estadísticas, solo lo suyo («Mis estadísticas»).
    """
    memberships = getattr(request, "user_memberships", [])
    return len(memberships) > 1 and not any(m.can_manage for m in memberships)


def linked_players(request):
    """
    Jugadores enlazados a la cuenta en sus espacios, en el orden de las competiciones (uno por
    competición). «Mis estadísticas» existe cuando hay dos o más.
    """
    from players.models import Player
    clubs = user_clubs(request)
    players = Player.objects.filter(user=request.user, club__in=clubs).select_related("club") \
        if clubs and request.user.is_authenticated else []
    return sorted(players, key=lambda p: clubs.index(p.club) if p.club in clubs else len(clubs))


def space_filter_context(request, selected, allow_all=True):
    """
    Chips «Todas» (salvo sin ``allow_all``) y una por competición (``space_chips``) para la plantilla
    ``includes/space_filter.html``; vacío con un solo espacio. Cada enlace conserva el resto de la
    URL salvo la página.
    """
    if selected is None:
        return {"space_chips": [], "space_selected": None, "multi_space": False}

    def url(value):
        """URL de la página actual con el espacio ``value``."""
        params = request.GET.copy()
        params.pop("page", None)
        params[SPACE_PARAM] = value
        return f"{request.path}?{params.urlencode()}"

    chips = [{"code": ALL_SPACES, "label": _("Todas"), "url": url(ALL_SPACES), "active": selected == ALL_SPACES}] \
        if allow_all else []
    seen = set()
    for club in user_clubs(request):
        if club.competition in seen:
            continue
        seen.add(club.competition)
        chips.append({"code": club.competition, "label": str(club.rules.name), "url": url(club.competition),
                      "active": selected == club.competition})
    return {"space_chips": chips, "space_selected": selected, "multi_space": True}


def managed_clubs(request, clubs=None):
    """De ``clubs`` (por defecto, todos los del usuario), los que puede gestionar (capitán o gestor)."""
    clubs = user_clubs(request) if clubs is None else clubs
    return [c for c in clubs if (m := membership_for(request, c)) and m.can_manage]


def switch_to(request, club):
    """
    Hace activo el espacio ``club`` (debe ser de los del usuario) para el resto de la petición y
    las siguientes, sin avisar: la página ya dice de qué competición es. No hace nada si ya era el
    activo. Devuelve True si cambia.
    """
    if request.club is not None and club.id == request.club.id:
        return False
    membership = membership_for(request, club)
    if membership is None:
        return False
    request.session[SESSION_KEY] = club.id
    request.club = club
    request.membership = membership
    return True


SWITCH_PARAM = "en"


def follow_space(view_func):
    """
    Decorador para vistas de un espacio concreto enlazadas desde una vista unida: con ``?en=lapi``
    cambia antes al espacio de esa competición (si el usuario lo tiene), así los permisos que se
    comprueban después (``club_manager_required``…) son los de ese espacio. Va encima de ellos.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Cambia al espacio de ``?en=`` y sigue con la vista."""
        code = request.GET.get(SWITCH_PARAM)
        if code and getattr(request, "user_memberships", None):
            club = next((c for c in user_clubs(request) if c.competition == code), None)
            if club is not None:
                switch_to(request, club)
        return view_func(request, *args, **kwargs)
    return wrapper


def management_view(view_func):
    """
    Decorador de Plantilla, Club y Rivales, que son de un solo espacio. Con ``?en=`` cambia a ese
    espacio (follow_space). Si el usuario gestiona unos espacios y en otros solo juega, estas
    páginas son solo de los que gestiona: si el activo es uno en el que juega, cambia al primero
    que gestiona. Quien gestiona todos sus espacios (capitán o gestor en SNP y en LAPI) o es jugador
    en todos elige desde la página: deja en ``request.space_switcher`` sus espacios; para los demás
    (gestiona unos y juega en otros), vacío.
    """
    @follow_space
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Elige el espacio de la página y prepara el selector."""
        request.space_switcher = []
        if getattr(request, "club", None) is not None and is_multi_space(request):
            clubs = user_clubs(request)
            managed = managed_clubs(request, clubs)
            if managed and len(managed) < len(clubs):
                if request.club not in managed:
                    switch_to(request, managed[0])
            else:
                request.space_switcher = [
                    {"club": c, "code": c.competition, "name": c.rules.name, "active": c.id == request.club.id}
                    for c in clubs]
        return view_func(request, *args, **kwargs)
    return wrapper


def consult_view(view_func):
    """
    Decorador de las páginas de consulta de un solo espacio (estadísticas de jugador, parejas,
    rivales…): con ``?en=`` cambia a ese espacio (follow_space) y deja en
    ``request.space_switcher`` todos los espacios del usuario para cambiar desde la página.
    """
    @follow_space
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        """Prepara el selector con todos los espacios."""
        request.space_switcher = []
        if getattr(request, "club", None) is not None and is_multi_space(request):
            request.space_switcher = [
                {"club": c, "code": c.competition, "name": c.rules.name, "active": c.id == request.club.id}
                for c in user_clubs(request)]
        return view_func(request, *args, **kwargs)
    return wrapper
