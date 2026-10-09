"""
Descarga de los puntos SNP de los jugadores de un equipo desde snpgalaxy.com.

Entra con la cuenta de SNP del capitán, navega como él (Series Nacionales → el país del
equipo → Mis equipos → el equipo) y lee la tabla de jugadores (todas las páginas). Devuelve una lista de ``{"name": ..., "score": ...}``
con el nombre tal y como aparece en SNP; el cruce con nuestros jugadores está en
players/snp.py.

Para no cargar a SNP (y que no nos bloquee) cada club se lee como lo haría una persona:
un navegador en español y con la hora de Madrid, sin descargar imágenes, vídeos ni
tipos de letra (son la mayoría de las peticiones y no hacen falta para leer la tabla).
Si SNP responde que hay demasiadas peticiones o niega el acceso (429, 403, 503) se lanza
SnpBlockedError para que el proceso por lotes pare en vez de insistir.
"""
import base64
import binascii
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError, sync_playwright

SNP_HOST = "snpgalaxy.com"
LOGIN_URL = "https://snpgalaxy.com/usuario/login"
LOGIN_BUTTONS = ('input[type="submit"][value="Iniciar Sesión"]', 'button[type="submit"]:has-text("Iniciar Sesión")',
                 'input[type="submit"]', 'button[type="submit"]')
USERNAME_FIELDS = ('input[name="email"]', 'input[name="usuario"]', 'input[name="username"]',
                   'input[type="email"]', 'input[type="text"]')
RESULTS_TABLE = "table.results"
NEXT_PAGE = 'a.pag_numerada.page-link[num_pagina="{}"]'
SERIES_MENU = 'a.menu-link.menu-toggle:has([data-i18n="Series Nacionales"])'
COUNTRY_LINK = 'a.menu-link:has([data-i18n="{}"])'
# Nombre de cada país en el menú «Series Nacionales» de SNP, por el código de Team.COUNTRIES.
SNP_COUNTRIES = {"ES": "España", "MX": "México", "PT": "Portugal", "IT": "Italia", "SE": "Suecia"}
DEFAULT_COUNTRY = "ES"
MY_TEAMS = '.card-equipos'
TEAM_LINKS = '#form_equipos table.results tbody td:first-child a[href*="/equipo/view/"]'
MAX_PAGES = 30
TIMEOUT_MS = 30_000
# SNP rellena la tabla de jugadores después de mostrarla (y a veces tarda bastante).
TABLE_TIMEOUT_MS = 60_000
# Respuestas con las que SNP indica que limita o rechaza nuestras peticiones.
BLOCKED_STATUSES = {403, 429, 503}
# Lo que no hace falta descargar para leer la tabla.
SKIPPED_RESOURCES = {"image", "media", "font"}
CONTEXT_OPTIONS = {"locale": "es-ES", "timezone_id": "Europe/Madrid", "viewport": {"width": 1366, "height": 900}}


class SnpScrapeError(Exception):
    """
    Error que se puede enseñar tal cual al capitán del club. ``retryable`` dice si
    tiene sentido volver a intentarlo más tarde (un fallo de red o de carga) o no (la
    contraseña no vale, la cuenta no tiene ese equipo…): reintentar un inicio de sesión
    rechazado una y otra vez puede acabar bloqueando la cuenta del capitán.

    ``kind`` dice dónde puede arreglarlo el capitán: ``ACCOUNT`` en su cuenta SNP (usuario,
    contraseña o equipo de la cuenta), ``TEAM`` en los datos de su equipo (la nacionalidad
    decide en qué país se busca) o vacío si no se sabe.
    """
    retryable = False
    ACCOUNT = "account"
    TEAM = "team"
    kind = ""

    def __init__(self, message="", kind=None):
        """``message`` se enseña al capitán; ``kind`` sustituye al de la clase si se indica."""
        super().__init__(message)
        if kind is not None:
            self.kind = kind


class SnpTemporaryError(SnpScrapeError):
    """Fallo pasajero (red, SNP lento o caído): se reintenta en la siguiente pasada."""
    retryable = True


class SnpBlockedError(SnpTemporaryError):
    """SNP limita o rechaza nuestras peticiones: hay que parar y dejarle descansar."""


def parse_team_id(value):
    """
    Número del equipo en SNP a partir de lo que pegue el capitán: el número
    (4380), la página del equipo (.../equipo/view/4380) o un enlace de snpgalaxy.com
    que la lleve codificada en base64 tras ``u_:``. None si no se reconoce.
    """
    value = (value or "").strip()
    if value.isdigit():
        return value
    candidates = [value]
    encoded = re.search(r"/u_:([A-Za-z0-9+/=_-]+)", value)
    if encoded:
        text = encoded.group(1)
        try:
            candidates.append(base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"+/").decode())
        except (binascii.Error, UnicodeDecodeError):
            pass
    for candidate in candidates:
        match = re.search(r"/equipo/view/(\d+)", candidate)
        if match:
            return match.group(1)
    return None


def parse_score(text):
    """'1.234,5' -> 1234.5; '12,5 / 3' -> 12.5; vacío o ilegible -> 0.0."""
    text = (text or "").split("/")[0].strip()
    if not text:
        return 0.0
    try:
        return float(text.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _first_visible(page, selectors):
    """Primer elemento visible de la página que encaje con alguno de ``selectors`` (en ese orden), o None."""
    for selector in selectors:
        element = page.query_selector(selector)
        if element and element.is_visible():
            return element
    return None


def _login(page, username, password):
    """
    Inicia sesión en SNP con la cuenta del capitán. Lanza SnpBlockedError si SNP limita el
    acceso, SnpTemporaryError si no encuentra el formulario y SnpScrapeError (no reintentable)
    si SNP rechaza el usuario o la contraseña.
    """
    response = page.goto(LOGIN_URL, timeout=TIMEOUT_MS)
    if response is not None and response.status in BLOCKED_STATUSES:
        raise SnpBlockedError(f"SNP ha respondido {response.status} al abrir la página de inicio de sesión: "
                              "está limitando o rechazando nuestras peticiones.")
    user_field = _first_visible(page, USERNAME_FIELDS)
    password_field = page.query_selector('input[type="password"]')
    if not user_field or not password_field:
        raise SnpTemporaryError("No se ha encontrado el formulario de inicio de sesión de SNP.")
    user_field.fill(username)
    password_field.fill(password)
    button = _first_visible(page, LOGIN_BUTTONS)
    if not button:
        raise SnpTemporaryError("No se ha encontrado el botón «Iniciar Sesión» de SNP.")
    button.click()
    page.wait_for_load_state("load", timeout=TIMEOUT_MS)
    page.wait_for_timeout(2000)
    still_on_login = "/usuario/login" in page.url and page.query_selector('input[type="password"]')
    if still_on_login:
        raise SnpScrapeError("SNP no ha aceptado el usuario o la contraseña.", kind=SnpScrapeError.ACCOUNT)


def _frame_label(frame, page):
    """Descripción legible de un frame para los mensajes de log."""
    if frame == page.main_frame:
        return "la página principal"
    return f"el iframe «{frame.name or '(sin nombre)'}» ({frame.url})"


def _find(page, selector, what, log, url_pattern=None, timeout_ms=TIMEOUT_MS):
    """
    Busca ``selector`` visible en la página y en todos sus iframes (SNP carga parte de
    su contenido dentro de iframes) hasta que aparezca. Devuelve (frame, elemento).
    ``url_pattern`` limita la búsqueda a los frames cuya dirección encaje.
    """
    waited = 0
    while True:
        for frame in page.frames:
            if url_pattern and not re.search(url_pattern, frame.url):
                continue
            try:
                element = frame.query_selector(selector)
                if element and element.is_visible():
                    log(f"Encontrado en {_frame_label(frame, page)}: {what}.")
                    return frame, element
            except PlaywrightError:
                continue  # el frame se está recargando
        if waited >= timeout_ms:
            frames = "; ".join(_frame_label(f, page) for f in page.frames)
            log(f"No se encuentra {what}. Frames en la página: {frames}")
            raise SnpTemporaryError(f"No se ha encontrado {what} en SNP (ni en la página ni en sus iframes).")
        page.wait_for_timeout(500)
        waited += 500


def snp_country_name(country):
    """Nombre del país en el menú de SNP; España si el equipo no tiene nacionalidad."""
    return SNP_COUNTRIES.get(country or "", SNP_COUNTRIES[DEFAULT_COUNTRY])


def _same_team_name(a, b):
    """Mismo nombre de equipo sin distinguir mayúsculas, tildes, signos ni espacios."""
    from core.similarity import same_name
    return same_name(a or "", b or "")


def _open_team_page(page, team_id, log, country=None, team_name=None):
    """
    Series Nacionales → el país del equipo → Mis equipos → el equipo, como lo haría el
    capitán. Devuelve el frame donde está la tabla de jugadores. Si la cuenta tiene varios
    equipos y no se indica ``team_id``, se elige el que se llama como el equipo del club
    (``team_name``).
    """
    country_name = snp_country_name(country)
    _find(page, SERIES_MENU, "el menú «Series Nacionales»", log)[1].click()
    _find(page, COUNTRY_LINK.format(country_name), f"la opción «{country_name}»", log)[1].click()
    page.wait_for_load_state("load", timeout=TIMEOUT_MS)
    _find(page, MY_TEAMS, "el botón «Mis equipos»", log)[1].click()
    frame, _ = _find(page, TEAM_LINKS, "la tabla «Mis equipos»", log)

    teams = {}
    for link in frame.query_selector_all(TEAM_LINKS):
        found = re.search(r"/equipo/view/(\d+)", link.get_attribute("href") or "")
        if found:
            teams.setdefault(found.group(1), (link, link.inner_text().strip()))
    if team_id:
        if team_id not in teams:
            raise SnpScrapeError(f"El equipo {team_id} no aparece en «Mis equipos» de esta cuenta SNP.", kind=SnpScrapeError.ACCOUNT)
        link = teams[team_id][0]
    elif len(teams) == 1:
        link = next(iter(teams.values()))[0]
    elif not teams:
        raise SnpScrapeError(f"Esta cuenta SNP no tiene ningún equipo en «Mis equipos» de {country_name}.", kind=SnpScrapeError.TEAM)
    else:
        same = [link for link, name in teams.values() if _same_team_name(name, team_name)]
        if len(same) != 1:
            names = ", ".join(name for _, name in teams.values())
            raise SnpScrapeError(f"La cuenta tiene varios equipos ({names}) y ninguno se llama como tu equipo en Zyra; "
                                 f"pon a tu equipo el mismo nombre que tiene en SNP.", kind=SnpScrapeError.TEAM)
        link = same[0]

    link.click()
    frame, _ = _find(page, RESULTS_TABLE, "la tabla de jugadores", log, url_pattern=r"/equipo/view/\d+")
    return _wait_for_rows(page, frame, log)


def _wait_for_rows(page, frame, log):
    """
    La tabla aparece vacía y SNP la rellena después: espera a que tenga jugadores y a
    que dos lecturas seguidas coincidan (ha terminado de cargar). Leerla nada más
    aparecer daba «la tabla de jugadores está vacía».
    """
    waited, last = 0, None
    while waited < TABLE_TIMEOUT_MS:
        if frame.is_detached():
            frame, _ = _find(page, RESULTS_TABLE, "la tabla de jugadores", log, url_pattern=r"/equipo/view/\d+")
        names = _table_names(frame)
        if names and names == last:
            log(f"Tabla de jugadores cargada tras {waited / 1000:g} s.")
            return frame
        last = names
        page.wait_for_timeout(500)
        waited += 500
    raise SnpTemporaryError(f"La tabla de jugadores de SNP sigue vacía tras {TABLE_TIMEOUT_MS // 1000} s: "
                            "SNP no ha terminado de cargarla.", kind=SnpScrapeError.TEAM)


def _table_names(frame):
    """Nombres de la tabla de jugadores del frame, o None si se está recargando."""
    try:
        return [r["name"] for r in _read_rows(frame)]
    except PlaywrightError:
        return None  # la tabla se está recargando


def _wait_for_next_page(page, frame, previous_names, log):
    """
    Espera a que la tabla muestre la página siguiente: que cambie respecto a la anterior
    y que dos lecturas seguidas coincidan (la tabla ha terminado de cargar). Antes se
    esperaban 3 segundos fijos y, si SNP tardaba más, se leía una página a medio cargar.
    """
    waited, last = 0, None
    while waited < TABLE_TIMEOUT_MS:
        page.wait_for_timeout(500)
        waited += 500
        if frame.is_detached():
            frame, _ = _find(page, RESULTS_TABLE, "la tabla de jugadores", log, url_pattern=r"/equipo/view/\d+")
        names = _table_names(frame)
        if names and names != previous_names and names == last:
            return frame
        last = names
    raise SnpTemporaryError("La página siguiente de la tabla de jugadores de SNP no ha terminado de cargar.")


def _read_rows(page):
    """Filas de la tabla de jugadores de ``page`` (página o frame) como ``{"name", "score"}``."""
    rows = []
    for row in page.query_selector_all(f"{RESULTS_TABLE} tbody tr"):
        name_cell = row.query_selector("td:nth-child(2)")
        value_cell = row.query_selector("td:nth-child(3)")
        name = name_cell.inner_text().strip() if name_cell else ""
        if name:
            rows.append({"name": name, "score": parse_score(value_cell.inner_text() if value_cell else "")})
    return rows


class SnpBrowser:
    """
    Navegador que se reutiliza para leer varios clubes seguidos (un lote): arrancar
    Chromium para cada club es lo más lento. Cada club se lee en un contexto propio
    (como una ventana de incógnito), así las sesiones de los capitanes nunca se mezclan.
    Chromium se arranca la primera vez que hace falta.

    Mientras Playwright está abierto mantiene un bucle asíncrono en su hilo, y en ese
    hilo Django no deja usar la base de datos. Por eso todo el trabajo con el navegador
    se hace en un hilo propio (``run``) y el resto (guardar los puntos) en el del proceso.
    """

    def __init__(self, headed=False):
        """``headed`` abre el navegador a la vista y más despacio, para seguir la ejecución."""
        self.headed = headed
        self._playwright = None
        self.browser = None
        self._executor = None

    def __enter__(self):
        """Arranca el hilo propio del navegador; Chromium no se abre hasta el primer club."""
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="snp-browser")
        return self

    def __exit__(self, *exc):
        """Cierra el navegador desde su propio hilo y termina ese hilo."""
        executor, self._executor = self._executor, None
        if executor:
            executor.submit(self.close).result()
            executor.shutdown()

    def run(self, function, *args, **kwargs):
        """Ejecuta ``function`` en el hilo del navegador y devuelve su resultado (o su error)."""
        if self._executor is None:
            raise RuntimeError("SnpBrowser se usa dentro de un bloque with.")
        return self._executor.submit(function, *args, **kwargs).result()

    def close(self):
        """Cierra Chromium y Playwright ignorando los errores (puede que ya estuvieran caídos)."""
        for closer in (self.browser and self.browser.close, self._playwright and self._playwright.stop):
            if closer:
                try:
                    closer()
                except Exception:
                    pass
        self.browser = self._playwright = None

    def _launch(self):
        """Arranca Playwright y Chromium; si falla lanza SnpTemporaryError."""
        try:
            self._playwright = sync_playwright().start()
            self.browser = self._playwright.chromium.launch(headless=not self.headed, slow_mo=500 if self.headed else 0)
        except PlaywrightError as exc:
            self.close()
            raise SnpTemporaryError(f"No se ha podido abrir el navegador: {str(exc).splitlines()[0]}") from exc

    def new_context(self):
        """
        Contexto nuevo (como una ventana de incógnito) para leer un club. Vuelve a arrancar
        Chromium si no estaba abierto o se ha caído, se presenta como un Chrome normal en español
        y no descarga imágenes, vídeos ni tipos de letra.
        """
        if self.browser is None or not self.browser.is_connected():
            self.close()
            self._launch()
        options = dict(CONTEXT_OPTIONS)
        # Chromium sin ventana se presenta como «HeadlessChrome»; nos presentamos como
        # el mismo Chrome con ventana.
        options["user_agent"] = (f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                 f"Chrome/{self.browser.version} Safari/537.36")
        context = self.browser.new_context(**options)
        context.route("**/*", _skip_heavy_resources)
        return context


def _is_blocked(response):
    """Una página (o iframe) del propio SNP que responde que nos limita o rechaza."""
    return (response.status in BLOCKED_STATUSES and response.request.resource_type == "document"
            and SNP_HOST in (urlsplit(response.url).hostname or ""))


def _skip_heavy_resources(route):
    """Aborta las peticiones de imágenes, vídeos y tipos de letra; deja pasar el resto."""
    if route.request.resource_type in SKIPPED_RESOURCES:
        route.abort()
    else:
        route.continue_()


def scrape_scores(username, password, team_id=None, headed=False, log=None, browser=None, country=None, team_name=None):
    """
    Puntos SNP de los jugadores del equipo ``team_id`` (o del único equipo de la cuenta
    si no se indica). Lanza SnpScrapeError si algo falla. ``country`` es la nacionalidad
    del equipo (código de Team.COUNTRIES) y decide qué país se abre en «Series
    Nacionales»; sin ella se usa España. ``team_name`` es el nombre del equipo del club:
    si la cuenta tiene varios equipos, se lee el que se llama igual.

    ``headed`` abre el navegador a la vista (y más despacio) para seguir la ejecución;
    ``log`` recibe una línea por cada paso. ``browser`` es un SnpBrowser ya abierto que
    se reutiliza (el proceso por lotes); si no se indica, se abre y se cierra uno.
    """
    if browser is None:
        with SnpBrowser(headed=headed) as own:
            return own.run(_scrape, username, password, team_id, log, own, country, team_name)
    return browser.run(_scrape, username, password, team_id, log, browser, country, team_name)


def _scrape(username, password, team_id, log, browser, country=None, team_name=None):
    """
    Lectura de un club en el hilo del navegador: inicia sesión, abre la página del equipo y
    recorre las páginas de la tabla de jugadores. Si durante la lectura SNP ha respondido que
    nos limita, cualquier fallo se convierte en SnpBlockedError; los errores de Playwright pasan
    a SnpTemporaryError. Devuelve los jugadores sin repetir nombres.
    """
    log = log or (lambda message: None)
    players = []
    blocked = []  # respuestas de SNP que indican que nos está limitando
    context = None
    try:
        context = browser.new_context()
        page = context.new_page()
        page.on("response", lambda r: blocked.append(r.status) if _is_blocked(r) else None)
        log("Iniciando sesión en SNP…")
        _login(page, username, password)
        log(f"Sesión iniciada. Abriendo Series Nacionales → {snp_country_name(country)} → Mis equipos…")
        frame = _open_team_page(page, team_id, log, country, team_name)
        log(f"Página del equipo abierta: {frame.url}")
        for page_number in range(2, MAX_PAGES + 2):
            rows = _read_rows(frame)
            log(f"Página {page_number - 1} de la tabla: {len(rows)} jugadores ({', '.join(r['name'] for r in rows)}).")
            players.extend(rows)
            next_button = frame.query_selector(NEXT_PAGE.format(page_number))
            if not next_button or not next_button.is_visible():
                break
            before = [r["name"] for r in rows]
            next_button.click()
            frame = _wait_for_next_page(page, frame, before, log)
    except (SnpScrapeError, PlaywrightError) as exc:
        if blocked and not isinstance(exc, SnpBlockedError):
            raise SnpBlockedError(f"SNP ha respondido {blocked[-1]} mientras se leía el equipo: "
                                  "está limitando o rechazando nuestras peticiones.") from exc
        if isinstance(exc, PlaywrightError):
            raise SnpTemporaryError(f"Error del navegador al leer SNP: {str(exc).splitlines()[0]}") from exc
        raise
    finally:
        if context is not None:
            try:
                context.close()
            except PlaywrightError:
                pass
    if not players:
        raise SnpTemporaryError("La tabla de jugadores de SNP está vacía.", kind=SnpScrapeError.TEAM)
    # Algunas páginas pueden repetir filas: nos quedamos con la primera aparición.
    unique = {}
    for player in players:
        unique.setdefault(player["name"], player)
    return list(unique.values())
