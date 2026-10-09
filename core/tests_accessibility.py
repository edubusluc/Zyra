"""
Pruebas de accesibilidad automáticas sobre el HTML que sirve la web.

Recorren las páginas principales (públicas, del club y del back-office) y comprueban
lo que se puede verificar sin navegador: texto alternativo en las imágenes, un solo
<h1> y encabezados sin saltos de nivel, título de página propio, idioma del
documento, etiquetas en los campos de formulario, nombre accesible en enlaces y
botones, iconos decorativos ocultos a los lectores de pantalla, cabeceras de tabla
con texto, gráficos con descripción y el enlace «Saltar al contenido».

El contraste de color y lo que depende del JavaScript lo revisa
``scripts/auditoria_accesibilidad.py`` (axe-core en un navegador real).
"""
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from core.services import create_club
from match.models import Game, Match
from players.models import Player
from team.models import Team

User = get_user_model()

LABELLABLE = {"input", "select", "textarea"}
NOT_LABELLED_INPUTS = {"hidden", "submit", "button", "reset", "image"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class A11yParser(HTMLParser):
    """Recorre una página y apunta los problemas de accesibilidad que encuentra."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems = []
        self.headings = []
        self.lang = None
        self.title = ""
        self.has_skip_link = False
        self.main_ids = set()
        self.label_for = set()
        self.controls = []          # (descripción, id, dentro de <label>, tiene aria)
        self.stack = []             # elementos abiertos que acumulan texto: [tag, attrs, texto]
        self.label_depth = 0
        self.in_title = False

    # -- utilidades --
    def _collect(self, text):
        for item in self.stack:
            item[2].append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self.in_title = True
        elif tag == "main" and a.get("id"):
            self.main_ids.add(a["id"])
        elif tag == "label":
            self.label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        elif tag == "img":
            if "alt" not in a:
                self.problems.append(f"<img src={a.get('src')!r}> sin atributo alt")
            # El texto alternativo cuenta como texto del enlace o botón que la contiene
            self._collect(a.get("alt") or "")
        elif tag == "i" and cls.startswith("fa"):
            if a.get("aria-hidden") != "true" and not a.get("aria-label"):
                self.problems.append(f'icono <i class="{cls}"> sin aria-hidden="true" ni aria-label')
        elif tag == "canvas":
            if a.get("role") != "img" or not (a.get("aria-label") or a.get("aria-labelledby")):
                self.problems.append(f"<canvas id={a.get('id')!r}> sin role=\"img\" y aria-label")
        if tag in LABELLABLE:
            kind = a.get("type", "text") if tag == "input" else tag
            if kind not in NOT_LABELLED_INPUTS:
                aria = bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title"))
                self.controls.append((f"<{tag} name={a.get('name')!r}>", a.get("id"), self.label_depth > 0, aria))
        if tag == "a" and a.get("class", "").split()[:1] == ["z-skip-link"]:
            self.has_skip_link = a.get("href", "")[1:]
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "a", "button", "th"):
            self.stack.append([tag, a, []])
        if tag in VOID:
            return

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "label":
            self.label_depth = max(0, self.label_depth - 1)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                _, a, text = self.stack.pop(i)
                text = " ".join("".join(text).split())
                self._close(tag, a, text)
                break

    def _close(self, tag, a, text):
        named = text or a.get("aria-label") or a.get("aria-labelledby") or a.get("title")
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append((int(tag[1]), text))
        elif tag == "a" and a.get("href") is not None and not named:
            self.problems.append(f"enlace <a href={a.get('href')!r}> sin texto ni aria-label")
        elif tag == "button" and not named:
            self.problems.append(f"botón <button class={a.get('class')!r}> sin texto ni aria-label")
        elif tag == "th" and not named:
            self.problems.append("<th> vacío (sin texto, ni siquiera oculto)")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        self._collect(data)

    # -- comprobaciones finales --
    def check(self):
        problems = list(self.problems)
        if not self.lang:
            problems.append("<html> sin atributo lang")
        if not self.title.strip():
            problems.append("<title> vacío")
        h1 = [t for level, t in self.headings if level == 1]
        if len(h1) != 1:
            problems.append(f"debe haber un solo <h1> y hay {len(h1)}: {h1}")
        previous = 0
        for level, text in self.headings:
            if level > previous + 1:
                problems.append(f"salto de encabezado h{previous} -> h{level} ({text!r})")
            previous = level
        for desc, cid, wrapped, aria in self.controls:
            if not (wrapped or aria or (cid and cid in self.label_for)):
                problems.append(f"{desc} sin <label> ni aria-label")
        if self.has_skip_link is False or self.has_skip_link not in self.main_ids:
            problems.append("falta el enlace «Saltar al contenido» que lleva a <main id=...>")
        return problems


def audit(html):
    """Lista de problemas de accesibilidad de una página HTML."""
    parser = A11yParser()
    parser.feed(html)
    parser.close()
    return parser.check(), parser.title.strip()


class AccessibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("capi", email="capi@example.com", password="pass-12345",
                                             is_staff=True, is_superuser=True)
        self.club = create_club("Club A", "Sevilla", self.user, player_name="Capi", player_last_name="Tán")
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, team=self.club.own_team, name=f"Jug{i:02d}",
                                              last_name="X") for i in range(10)]
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date="2026-10-10", season="2026")
        self.call = Call.objects.create(match=self.match)
        self.call.players.set(self.players)
        Game.objects.create(match=self.match, n_game=1, player_1_local=self.players[0],
                            player_2_local=self.players[1], score=3)

    def _assert_accessible(self, urls):
        titles = {}
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, url)
                problems, title = audit(response.content.decode())
                self.assertEqual(problems, [], f"{url}:\n  " + "\n  ".join(problems))
                titles.setdefault(title, []).append(url)
        return titles

    def test_public_pages(self):
        self._assert_accessible([
            reverse("home"), reverse("login"), reverse("register_club"), reverse("privacy"),
            reverse("terms"), reverse("cookies"), reverse("account_reset_password"),
        ])

    def test_club_pages(self):
        self.client.login(username="capi", password="pass-12345")
        p, q = self.players[0].public_id, self.players[1].public_id
        titles = self._assert_accessible([
            reverse("home"), reverse("list_match"), reverse("create_match"),
            reverse("call_for_match", args=[self.match.public_id]),
            reverse("edit_call", args=[self.call.public_id]),
            reverse("list_players"), reverse("create_player"), reverse("show_player", args=[p]),
            reverse("edit_player", args=[p]), reverse("manage_roster"), reverse("snp_account"),
            reverse("list_teams"), reverse("create_team"), reverse("edit_team", args=[self.rival.public_id]),
            reverse("manage_teams"),
            reverse("team_statistics"), reverse("player_statistics"),
            reverse("player_statistics") + f"?player={p}", reverse("pair_statistics"),
            reverse("pair_statistics") + f"?p1={p}&p2={q}", reverse("warnings_statistics"),
            reverse("my_profile"), reverse("club_members"),
        ])
        # Cada página tiene su propio título (WCAG 2.4.2), salvo la misma vista con otros datos
        repeated = {t: urls for t, urls in titles.items() if len(urls) > 1}
        self.assertEqual(repeated, {})

    def test_backoffice_pages(self):
        self.client.login(username="capi", password="pass-12345")
        self._assert_accessible([
            reverse("backoffice:dashboard"), reverse("backoffice:usage"), reverse("backoffice:health"),
            reverse("backoffice:club_list"), reverse("backoffice:club_detail", args=[self.club.public_id]),
            reverse("backoffice:user_list"), reverse("backoffice:user_detail", args=[self.user.id]),
            reverse("backoffice:photo_list"),
        ])

    def test_parser_catches_common_mistakes(self):
        html = ('<html><head><title>x</title></head><body><main id="m"><h1>A</h1><h3>B</h3>'
                '<img src="a.png"><a href="/x"><i class="fa-solid fa-pen"></i></a>'
                '<input name="q"><table><tr><th></th></tr></table></main></body></html>')
        problems, _ = audit(html)
        text = "\n".join(problems)
        for expected in ("sin atributo alt", "salto de encabezado h1 -> h3", "enlace <a href='/x'>",
                         "icono", "<input name='q'> sin <label>", "<th> vacío", "lang", "Saltar al contenido"):
            self.assertIn(expected, text)
