"""
Auditoría de accesibilidad con axe-core en un navegador real (Playwright + Chromium).

Complementa a ``core/tests_accessibility.py`` (que corre en CI sin navegador): aquí se
mide lo que solo se ve con la página pintada, como el contraste de color, los
elementos que crea el JavaScript o las tablas que se desplazan en el móvil.

Uso, con la web arrancada (``python manage.py runserver``) y datos de prueba
(``python populate_db.py``)::

    python scripts/auditoria_accesibilidad.py --usuario capitan --contrasena '...'
    python scripts/auditoria_accesibilidad.py --usuario capitan --contrasena '...' --movil
    python scripts/auditoria_accesibilidad.py --solo-publicas --json

Sin ``--usuario`` solo se revisan las páginas públicas. Las páginas de un partido,
jugador y equipo se descubren solas siguiendo el primer enlace de cada listado.
Termina con código 1 si alguna página tiene fallos graves o críticos.

El fondo de la web es un degradado y axe no sabe medir el contraste sobre degradados
(los deja «por revisar»). Con ``--contraste-solido`` (activado por defecto) se pinta
el fondo con su color más claro, el caso peor para el texto claro de Zyra, y así
axe puede medirlo.
"""
import argparse
import json
import re
import sys

from playwright.sync_api import sync_playwright

AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
# Nombres fijos (no se aceptan rutas por línea de órdenes): siempre en la carpeta actual
LOCAL_AXE = "axe.min.js"
JSON_OUTPUT = "auditoria-accesibilidad.json"
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]
SOLID_BACKGROUND = "body{background:#252821 !important} *:not(body){background-image:none !important}"

PUBLIC_PAGES = ["/", "/core/login/", "/core/register_club/", "/privacidad/", "/terminos/", "/cookies/",
                "/accounts/password/reset/"]
CLUB_PAGES = ["/", "/match/list_match", "/match/create_match", "/players/list_players", "/players/create_player",
              "/players/roster/", "/players/snp/", "/team/list_teams", "/team/create_team", "/team/manage_teams/",
              "/data_analyse/team_statistics", "/data_analyse/player_statistics", "/data_analyse/pair_statistics",
              "/data_analyse/warnings", "/core/profile/", "/core/members/"]
STAFF_PAGES = ["/backoffice/", "/backoffice/usage/", "/backoffice/health/", "/backoffice/clubs/",
               "/backoffice/users/", "/backoffice/photos/"]
# Listado -> patrón del primer enlace a seguir para revisar también la página de detalle
DETAIL_LINKS = {"/match/list_match": r"/match/call_for_match/", "/players/list_players": r"/players/player_details/",
                "/team/list_teams": r"/team/edit_team/"}

AXE_RUN = """async (tags) => {
  const r = await axe.run(document, {runOnly: {type: 'tag', values: tags}});
  return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl,
    nodes: v.nodes.map(n => n.target.join(' '))}));
}"""


def parse_args():
    """Opciones de la línea de órdenes."""
    parser = argparse.ArgumentParser(description="Revisa la accesibilidad de Zyra con axe-core.")
    parser.add_argument("--url", default="http://localhost:8000", help="dirección de la web (por defecto local)")
    parser.add_argument("--usuario", help="usuario con club para revisar también las páginas privadas")
    parser.add_argument("--contrasena", help="contraseña de ese usuario")
    parser.add_argument("--solo-publicas", action="store_true", help="revisa solo las páginas públicas")
    parser.add_argument("--movil", action="store_true", help="pantalla de móvil (390 x 844) en vez de escritorio")
    parser.add_argument("--axe", action="store_true",
                        help=f"usa el {LOCAL_AXE} de la carpeta actual en vez de descargarlo de cdnjs")
    parser.add_argument("--sin-contraste-solido", action="store_true",
                        help="no sustituye el degradado del fondo (el contraste quedará «por revisar»)")
    parser.add_argument("--json", action="store_true", help=f"guarda el resultado completo en {JSON_OUTPUT}")
    return parser.parse_args()


def new_page(browser, args):
    """Pestaña nueva con el tamaño de pantalla elegido."""
    if args.movil:
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    else:
        context = browser.new_context(viewport={"width": 1280, "height": 900})
    return context.new_page()


def login(page, args):
    """Inicia sesión con el formulario de la web."""
    page.goto(args.url + "/core/login/")
    page.fill("input[name=username]", args.usuario)
    page.fill("input[name=password]", args.contrasena)
    page.press("input[name=password]", "Enter")
    page.wait_for_load_state("networkidle")
    if "/core/login/" in page.url:
        sys.exit("No se ha podido iniciar sesión: revisa --usuario y --contrasena.")


def audit_page(page, args, path):
    """Abre una página, ejecuta axe y devuelve sus fallos."""
    page.goto(args.url + path, wait_until="networkidle")
    if not args.sin_contraste_solido:
        page.add_style_tag(content=SOLID_BACKGROUND)
    if args.axe:
        page.add_script_tag(path=LOCAL_AXE)
    else:
        page.add_script_tag(url=AXE_CDN)
    return page.evaluate(AXE_RUN, WCAG_TAGS)


def detail_pages(page, args):
    """Primera página de detalle enlazada desde cada listado (partido, jugador, equipo)."""
    found = []
    for listing, pattern in DETAIL_LINKS.items():
        page.goto(args.url + listing, wait_until="networkidle")
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        href = next((h for h in hrefs if re.search(pattern, h)), None)
        if href:
            found.append(href)
    return found


def main():
    """Recorre las páginas, imprime un resumen y sale con 1 si hay fallos graves."""
    args = parse_args()
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = new_page(browser, args)
        for path in PUBLIC_PAGES:
            results[path] = audit_page(page, args, path)
        if args.usuario and not args.solo_publicas:
            page = new_page(browser, args)
            login(page, args)
            for path in CLUB_PAGES + detail_pages(page, args) + STAFF_PAGES:
                page.goto(args.url + path)
                if path.startswith("/backoffice/") and "/backoffice/" not in page.url:
                    continue  # el usuario no es personal de Zyra
                results["[club] " + path] = audit_page(page, args, path)
        browser.close()

    serious = 0
    for path, violations in results.items():
        print(f"{'OK ' if not violations else 'XX '} {path}")
        for v in violations:
            serious += v["impact"] in ("serious", "critical")
            print(f"      [{v['impact']}] {v['id']}: {v['help']} ({len(v['nodes'])}) -> {v['nodes'][0]}")
    print(f"\n{len(results)} páginas revisadas, {sum(map(len, results.values()))} reglas incumplidas "
          f"({serious} graves o críticas).")
    if args.json:
        with open(JSON_OUTPUT, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
    sys.exit(1 if serious else 0)


if __name__ == "__main__":
    main()
