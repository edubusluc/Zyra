"""
Recomendador de alineaciones a partir del historial del club, para la ficha de cada competición.

Sirve para cualquier competición de ``core.competitions``: estima la probabilidad de victoria
de cada pareja con el historial y la afinidad de los convocados y busca la combinación que más
opciones tiene de ganar. Solo en la SNP el orden de las parejas sale de los puntos SNP; en el
resto (LAPI) las parejas se cruzan por sorteo y todos los partidos valen lo mismo, así que no
hay orden ni partidos «más valiosos».

Formato de la SNP, el más complejo:
- Cada eliminatoria son 5 partidos por parejas. Los partidos 1 y 2 valen 3 puntos
  y los partidos 3, 4 y 5 valen 2: hay 12 puntos en juego.
- El orden NO lo elige el capitán: las parejas se ordenan por la suma de los
  puntos SNP de sus dos jugadores (la suma más alta juega el partido 1).
- Gana la eliminatoria quien suma 7 o más puntos (6-6 es empate). Por eso no basta
  con ganar 3 partidos: ganar los dos de 3 puntos y uno de 2 da 8 puntos, pero
  ganar solo los tres de 2 puntos da 6 (empate).

La decisión real del capitán es CÓMO FORMAR LAS PAREJAS (y, si hay más de 10
convocados, quién juega). Este módulo estima la probabilidad de victoria de cada
pareja posible a partir del historial del club y busca las combinaciones que
maximizan la probabilidad de ganar la eliminatoria.
"""
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations

from django.utils.translation import gettext as _, gettext_lazy

from core.competitions import SNP

# Formato de la SNP, sacado de su ficha (core.competitions): es la competición por defecto
# de las funciones que reciben ``comp``.
GAME_VALUES = SNP.game_points
POINTS_TO_WIN = SNP.total_points // 2 + 1
PLAYERS_PER_LINEUP = SNP.players_per_lineup
MAX_CANDIDATES = 12      # con más convocados se consideran los 12 en mejor momento
RECENT_GAMES = 6


def _smooth(wins, played, prior=0.5, weight=2):
    """% de victorias suavizado hacia `prior` cuando hay pocos partidos."""
    return (wins + prior * weight) / (played + weight)


def current_streak(results):
    """('V', n) o ('D', n) según los últimos resultados; (None, 0) sin partidos."""
    if not results:
        return None, 0
    last, n = results[-1], 0
    for r in reversed(results):
        if r != last:
            break
        n += 1
    return ('V' if last else 'D'), n


@dataclass
class PlayerForm:
    """Historial de un jugador convocado: global, en la sede del partido y resultados recientes."""
    player: object
    played: int = 0
    wins: int = 0
    venue_played: int = 0
    venue_wins: int = 0
    results: list = field(default_factory=list)   # cronológico, True = victoria

    @property
    def id(self):
        """Id del jugador."""
        return self.player.id

    @property
    def name(self):
        """Nombre corto del jugador."""
        return self.player.short_name

    @property
    def snp(self):
        """Puntos SNP del jugador (0 si no tiene)."""
        return self.player.snp_score or 0

    @property
    def losses(self):
        """Partidos perdidos."""
        return self.played - self.wins

    @property
    def pct(self):
        """% de victorias global, o None sin partidos."""
        return round(self.wins / self.played * 100) if self.played else None

    @property
    def venue_pct(self):
        """% de victorias en la sede del partido, o None sin partidos allí."""
        return round(self.venue_wins / self.venue_played * 100) if self.venue_played else None

    @property
    def streak(self):
        """Racha actual: ('V', n), ('D', n) o (None, 0)."""
        return current_streak(self.results)

    @property
    def form(self):
        """Últimos 5 resultados (True = victoria)."""
        return self.results[-5:]

    @property
    def strength(self):
        """Probabilidad estimada de ganar un partido (0-1)."""
        recent = self.results[-RECENT_GAMES:]
        p = (0.40 * _smooth(self.wins, self.played)
             + 0.35 * _smooth(self.venue_wins, self.venue_played)
             + 0.25 * _smooth(sum(recent), len(recent)))
        kind, n = self.streak
        if kind:
            p += (0.015 if kind == 'V' else -0.015) * min(n, 4)
        return min(max(p, 0.05), 0.95)


@dataclass
class PairForm:
    """Historial de una pareja de convocados jugando juntos."""
    a: PlayerForm
    b: PlayerForm
    played: int = 0
    wins: int = 0
    venue_played: int = 0
    venue_wins: int = 0
    results: list = field(default_factory=list)

    @property
    def key(self):
        """Ids de los dos jugadores ordenados: identifica la pareja."""
        return tuple(sorted((self.a.id, self.b.id)))

    @property
    def name(self):
        """'Jugador A / Jugador B'."""
        return f"{self.a.name} / {self.b.name}"

    @property
    def snp_sum(self):
        """Suma de los puntos SNP de la pareja: decide el orden de los partidos."""
        return round(self.a.snp + self.b.snp, 1)

    @property
    def losses(self):
        """Partidos perdidos juntos."""
        return self.played - self.wins

    @property
    def streak(self):
        """Racha actual de la pareja: ('V', n), ('D', n) o (None, 0)."""
        return current_streak(self.results)

    @property
    def complementary(self):
        """1 si es una pareja derecha + revés, -1 si los dos juegan del mismo lado, 0 en otro caso."""
        positions = {self.a.player.position, self.b.player.position}
        if positions == {"Derecha", "Revés"}:
            return 1
        if len(positions) == 1 and positions <= {"Derecha", "Revés"}:
            return -1  # dos jugadores del mismo lado
        return 0

    @property
    def strength(self):
        """Probabilidad estimada de que la pareja gane un partido (0,05-0,95).

        Parte de la media de los dos jugadores, se ajusta con su historial juntos (más
        cuantos más partidos tengan), y suma un poco por posiciones complementarias y racha.
        """
        base = (self.a.strength + self.b.strength) / 2
        # La química de la pareja pesa más cuantos más partidos hayan jugado juntos
        p = _smooth(self.wins, self.played, prior=base, weight=3)
        p += 0.03 * self.complementary
        kind, n = self.streak
        if kind:
            p += (0.01 if kind == 'V' else -0.01) * min(n, 3)
        return min(max(p, 0.05), 0.95)


def build_forms(log, players, own_local):
    """
    Forma de cada jugador y de cada pareja a partir del log de partidos del club
    (data_analyse.pairs.club_game_log). `own_local` indica dónde se juega ahora.
    """
    forms = {p.id: PlayerForm(p) for p in players}
    pairs = {}
    for g in log:
        same_venue = g['local'] == own_local
        for pid in g['pair']:
            f = forms.get(pid)
            if f:
                f.played += 1
                f.wins += g['won']
                f.results.append(g['won'])
                if same_venue:
                    f.venue_played += 1
                    f.venue_wins += g['won']
        a, b = g['pair']
        if a in forms and b in forms:
            pf = pairs.setdefault(g['pair'], PairForm(forms[a], forms[b]))
            pf.played += 1
            pf.wins += g['won']
            pf.results.append(g['won'])
            if same_venue:
                pf.venue_played += 1
                pf.venue_wins += g['won']
    return forms, pairs


def get_pair(pairs, forms, a_id, b_id):
    """PairForm de dos jugadores; si nunca han jugado juntos, la crea vacía y la añade a ``pairs``."""
    key = tuple(sorted((a_id, b_id)))
    if key not in pairs:
        pairs[key] = PairForm(forms[key[0]], forms[key[1]])
    return pairs[key]


def win_probability(ps, comp=SNP):
    """
    P(ganar la eliminatoria) y puntos esperados, con las parejas ya ordenadas, según los
    puntos de cada partido de ``comp``. Se construye la distribución de puntos partido a
    partido (más rápido que enumerar todos los resultados posibles).
    """
    values = comp.game_points
    dist = {0: 1.0}
    for p, value in zip(ps, values):
        nxt = {}
        for pts, prob in dist.items():
            nxt[pts + value] = nxt.get(pts + value, 0.0) + prob * p
            nxt[pts] = nxt.get(pts, 0.0) + prob * (1 - p)
        dist = nxt
    half = comp.total_points / 2
    win = sum(prob for pts, prob in dist.items() if pts >= comp.total_points // 2 + 1)
    win += dist.get(half, 0.0) / 2  # el empate cuenta como media victoria
    expected = sum(p * v for p, v in zip(ps, values))
    return win, expected


def _matchings(ids):
    """Todas las formas de repartir una lista (de tamaño par) en parejas."""
    if not ids:
        yield []
        return
    first, rest = ids[0], ids[1:]
    for i, other in enumerate(rest):
        for tail in _matchings(rest[:i] + rest[i + 1:]):
            yield [(first, other)] + tail


@lru_cache(maxsize=None)
def _templates(size):
    """Formas de emparejar ``size`` posiciones (945 para 10, 15 para 6), calculadas una sola vez."""
    return [tuple(m) for m in _matchings(list(range(size)))]


STRATEGY_BEST = "best"
STRATEGY_CHEMISTRY = "chemistry"
STRATEGY_TOP = "top"
STRATEGY_ALTERNATIVE = "alternative"
STRATEGY_TITLES = {
    STRATEGY_ALTERNATIVE: gettext_lazy("Alternativa"),
    STRATEGY_BEST: gettext_lazy("Máximas opciones"),
    STRATEGY_CHEMISTRY: gettext_lazy("Parejas consolidadas"),
    STRATEGY_TOP: gettext_lazy("Refuerzo de los partidos de 3 puntos"),
}


@dataclass
class Lineup:
    """Alineación recomendada: parejas (en orden de juego si la competición lo fija), probabilidad
    de ganar, puntos esperados, banquillo y ficha de la competición."""
    pairs: list          # PairForm; en la SNP en orden de juego (partido 1 primero), si no de más a menos fuerte
    win: float
    expected: float
    bench: list          # PlayerForm que no juegan
    strategy: str = STRATEGY_BEST
    comp: object = SNP

    @property
    def title(self):
        """Nombre de la estrategia de la alineación, traducido."""
        return str(STRATEGY_TITLES[self.strategy])

    @property
    def keys(self):
        """Claves de las parejas de la alineación."""
        return {p.key for p in self.pairs}

    @property
    def rows(self):
        """Filas para mostrar: número de partido (o de pareja), puntos, pareja y % estimado."""
        return [
            {'n': n, 'value': v, 'pair': p, 'pct': round(p.strength * 100)}
            for n, (p, v) in enumerate(zip(self.pairs, self.comp.game_points), start=1)
        ]


def recommend(forms, pairs, called_ids, comp=SNP):
    """
    Devuelve (alineacion_a, alineacion_b) para la competición ``comp``:
    - A: la que maximiza la probabilidad de ganar la eliminatoria.
    - B: alternativa que da más peso a parejas con historial juntas y cambia
      al menos dos parejas respecto a A (si es posible).
    """
    size = comp.players_per_lineup
    called = [forms[i] for i in called_ids if i in forms]
    if len(called) < size:
        return None, None
    called.sort(key=lambda f: f.strength, reverse=True)
    pool = [f.id for f in called[:MAX_CANDIDATES]]

    # Datos de cada pareja posible, precalculados: (orden, fuerza, química). En la SNP el orden
    # oficial es la suma de puntos SNP; sin orden oficial, de la pareja más fuerte a la menos.
    info = {}
    for a, b in combinations(pool, 2):
        pf = get_pair(pairs, forms, a, b)
        # Química: solo cuentan las parejas que ya han jugado juntas y ganan al menos la mitad
        proven = min(pf.played, 6) / 6 if pf.played and pf.wins * 2 >= pf.played else 0
        order = (pf.snp_sum, pf.strength) if comp.has_snp else (pf.strength,)
        info[(a, b)] = info[(b, a)] = (order, pf.strength, proven, pf)

    best_a = None      # (win, expected, pair_infos)
    candidates = []    # (win, expected, chemistry, keys, pair_infos)
    for group in combinations(pool, size):
        for template in _templates(size):
            ps = [info[(group[i], group[j])] for i, j in template]
            ps.sort(key=lambda x: x[0], reverse=True)
            win, expected = win_probability([x[1] for x in ps], comp)
            chemistry = sum(x[2] for x in ps) / len(ps)
            item = (win, expected, chemistry, ps)
            if best_a is None or (win, expected) > (best_a[0], best_a[1]):
                best_a = item
            candidates.append(item)

    def lineup(item):
        """Convierte un candidato de la búsqueda en un Lineup con su banquillo."""
        ps = [x[3] for x in item[3]]
        playing = {f.id for p in ps for f in (p.a, p.b)}
        return Lineup(ps, item[0], item[1], [f for f in called if f.id not in playing], comp=comp)

    a = lineup(best_a)
    options = []
    for min_changes in (2, 1):
        options = [c for c in candidates if len({x[3].key for x in c[3]} - a.keys) >= min_changes]
        if options:
            break
    if not options:
        return a, None

    # Plan B con una estrategia distinta:
    # - si hay parejas con más rodaje juntas que las de A, se priorizan ("consolidadas");
    # - si no y hay partidos que valen más (los dos de 3 puntos de la SNP), se refuerzan;
    # - si no, la segunda mejor.
    consolidated = [c for c in options if c[2] >= best_a[2] + 0.05]
    top = max(options, key=lambda c: (c[3][0][1] * c[3][1][1], c[0])) if comp.has_snp else None
    if consolidated:
        b = lineup(max(consolidated, key=lambda c: (c[0] + 0.15 * c[2], c[1])))
        b.strategy = STRATEGY_CHEMISTRY
    else:
        if top and top[3][0][1] * top[3][1][1] > best_a[3][0][1] * best_a[3][1][1] + 0.02:
            b = lineup(top)
            b.strategy = STRATEGY_TOP
        else:
            b = lineup(max(options, key=lambda c: (c[0], c[1])))
            b.strategy = STRATEGY_ALTERNATIVE
    return a, b


# ---------------------------------------------------------------
# Explicaciones (3-4 frases por alineación)
# ---------------------------------------------------------------

def _pct(x):
    """0.634 -> '63 %'."""
    return f"{round(x * 100)} %"


def explain(lineup, venue_label, compare_to=None):
    """3-4 frases que justifican la alineación; `compare_to` es la alineación A si esta es la B."""
    p1, p2 = lineup.pairs[0], lineup.pairs[1]
    sentences = []
    if compare_to is not None:
        new_pairs = [p for p in lineup.pairs if p.key not in compare_to.keys]
        if lineup.strategy == STRATEGY_CHEMISTRY:
            with_history = sorted((p for p in new_pairs if p.played and p.wins * 2 >= p.played),
                                  key=lambda p: (p.wins, p.played), reverse=True)
            detail = (
                " (" + ", ".join(_("%(pair)s: %(wins)sV-%(losses)sD juntos") % {"pair": p.name, "wins": p.wins, "losses": p.losses}
                                 for p in with_history[:2]) + ")"
                if with_history else ""
            )
            sentences.append(
                _("Alternativa que cambia %(n)s parejas respecto a la A para apostar por parejas "
                  "que ya se conocen%(detail)s.") % {"n": len(new_pairs), "detail": detail}
            )
        elif lineup.strategy == STRATEGY_ALTERNATIVE:
            sentences.append(
                _("Segunda mejor opción, con %(n)s parejas distintas a la A: "
                  "sirve de plan B si hay bajas o si se prefieren esas combinaciones.") % {"n": len(new_pairs)}
            )
        else:
            both = p1.strength * p2.strength
            sentences.append(
                _("Alternativa que cambia %(n)s parejas para asegurar los dos partidos de 3 puntos, "
                  "que valen la mitad de la eliminatoria: %(pct)s %% de ganar ambos.")
                % {"n": len(new_pairs), "pct": round(both * 100)}
            )
    comp = lineup.comp
    if comp.has_snp:
        sentences.append(
            _("%(pair1)s y %(pair2)s tienen la mayor suma de puntos SNP, así que disputarán "
              "los dos partidos de 3 puntos (victoria estimada %(pct1)s %% y %(pct2)s %%).")
            % {"pair1": p1.name, "pair2": p2.name,
               "pct1": round(p1.strength * 100), "pct2": round(p2.strength * 100)}
        )
    else:
        sentences.append(
            _("%(pair1)s y %(pair2)s son las parejas con más opciones según el historial y la afinidad "
              "(victoria estimada %(pct1)s %% y %(pct2)s %%); el cruce de las parejas lo decide el sorteo.")
            % {"pair1": p1.name, "pair2": p2.name,
               "pct1": round(p1.strength * 100), "pct2": round(p2.strength * 100)}
        )

    with_history = sorted((p for p in lineup.pairs if p.played), key=lambda p: (p.wins / p.played, p.played), reverse=True)
    if with_history:
        best = with_history[0]
        extra = (_(", %(wins)sV-%(losses)sD como %(venue)s") % {
            "wins": best.venue_wins, "losses": best.venue_played - best.venue_wins, "venue": venue_label,
        }) if best.venue_played else ""
        sentences.append(_("%(pair)s llega con %(wins)sV-%(losses)sD juntos%(extra)s.") % {
            "pair": best.name, "wins": best.wins, "losses": best.losses, "extra": extra})
    else:
        complementary = [p for p in lineup.pairs if p.complementary > 0]
        if complementary:
            sentences.append(
                _("Ninguna pareja tiene historial, así que se combinan perfiles de derecha y revés "
                  "en %(n)s de las %(total)s parejas.") % {"n": len(complementary), "total": comp.games}
            )

    hot = sorted(
        (f for p in lineup.pairs for f in (p.a, p.b) if f.streak[0] == 'V' and f.streak[1] >= 2),
        key=lambda f: f.streak[1], reverse=True,
    )
    if hot:
        names = ", ".join(_("%(name)s (%(n)sV seguidas)") % {"name": f.name, "n": f.streak[1]} for f in hot[:2])
        sentences.append(_("Apuesta por jugadores en racha como %(names)s.") % {"names": names})
    elif lineup.bench:
        sentences.append(_("Descansan %(names)s por su momento de forma.") % {
            "names": ", ".join(f.name for f in lineup.bench[:3])})

    closing = _(
        "Probabilidad estimada de ganar la eliminatoria: %(pct)s "
        "(%(expected)s de %(total)s puntos esperados)."
    ) % {"pct": _pct(lineup.win), "expected": f"{lineup.expected:.1f}", "total": comp.total_points}
    # Máximo 4 frases: la última siempre es la probabilidad
    return " ".join(sentences[:3] + [closing])
