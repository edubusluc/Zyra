"""Modo app: con el User-Agent de la app iOS la web oculta la cabecera y el menú; con cualquier otro no cambia nada."""
import re

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.context_processors import app_mode, google_login, is_app_request
from core.services import create_club

User = get_user_model()
APP_UA = "ZyraApp/1.0 (iPhone; iOS 18.1)"
BROWSER_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"


class AppFlagTests(TestCase):
    """Cuándo se considera que la petición viene de la app."""

    def flag(self, user_agent=None):
        """Valor de ``is_app`` para una petición con ese User-Agent (None = sin cabecera)."""
        extra = {} if user_agent is None else {"HTTP_USER_AGENT": user_agent}
        return app_mode(RequestFactory().get("/", **extra))["is_app"]

    def test_app_user_agent_in_any_version(self):
        """``ZyraApp/`` con cualquier versión es la app."""
        self.assertTrue(self.flag("ZyraApp/1.0"))
        self.assertTrue(self.flag(APP_UA))
        self.assertTrue(self.flag("ZyraApp/2.7.1 CFNetwork"))

    def test_other_user_agents_are_not_the_app(self):
        """Navegadores, sin cabecera, vacío o parecidos no lo son."""
        for agent in (BROWSER_UA, "", None, "MyZyraApp/1.0", "zyraapp/1.0", "ZyraApp", "Mozilla ZyraApp/1.0"):
            self.assertFalse(self.flag(agent), agent)

    def test_helper_matches_the_processor(self):
        """``is_app_request`` es lo que usa el procesador de contexto."""
        request = RequestFactory().get("/", HTTP_USER_AGENT=APP_UA)
        self.assertTrue(is_app_request(request))


class GoogleButtonTests(TestCase):
    """«Entrar con Google» no se ofrece dentro de la app (Google bloquea su acceso en una WebView)."""

    def enabled(self, user_agent=None):
        """Valor de ``google_login_enabled`` para una petición con ese User-Agent."""
        extra = {} if user_agent is None else {"HTTP_USER_AGENT": user_agent}
        return google_login(RequestFactory().get("/", **extra))["google_login_enabled"]

    @override_settings(GOOGLE_LOGIN_ENABLED=True)
    def test_browser_keeps_the_button(self):
        """Con un navegador (o sin User-Agent) y Google configurado, el botón sigue."""
        self.assertTrue(self.enabled(BROWSER_UA))
        self.assertTrue(self.enabled(None))

    @override_settings(GOOGLE_LOGIN_ENABLED=True)
    def test_app_hides_the_button(self):
        """Con el User-Agent de la app el botón no se muestra aunque Google esté configurado."""
        self.assertFalse(self.enabled(APP_UA))

    @override_settings(GOOGLE_LOGIN_ENABLED=False)
    def test_disabled_google_stays_disabled(self):
        """Sin Google configurado no hay botón en ningún caso."""
        self.assertFalse(self.enabled(BROWSER_UA))
        self.assertFalse(self.enabled(APP_UA))


class AppChromeTests(TestCase):
    """La cabecera, el menú inferior y el pie según el User-Agent."""

    def setUp(self):
        """Una cuenta con club que ha iniciado sesión."""
        user = User.objects.create_user("ana", "ana@example.com", "pass-12345-x")
        create_club("Club", "Sevilla", user, gender="M")
        self.client.force_login(user)

    def page(self, user_agent=None, name="home"):
        """HTML de una página con el User-Agent indicado (con el token CSRF, distinto en cada petición, neutralizado)."""
        extra = {} if user_agent is None else {"HTTP_USER_AGENT": user_agent}
        html = self.client.get(reverse(name), **extra).content.decode()
        return re.sub(r'(name="csrfmiddlewaretoken" value=")[^"]+', r"\1x", html)

    def test_browser_keeps_header_menu_and_plain_body(self):
        """Con un navegador siguen la cabecera, el menú inferior y ``<body>`` sin clase."""
        html = self.page(BROWSER_UA)
        self.assertIn('<header class="z-header">', html)
        self.assertIn('class="z-bottom-nav"', html)
        self.assertIn("<body>", html)
        self.assertNotIn("z-app", html)

    def test_no_user_agent_is_the_same_as_a_browser(self):
        """Sin User-Agent y con el de un navegador el HTML es el mismo (el flag no cambia nada más)."""
        self.assertEqual(self.page(None), self.page(BROWSER_UA))

    def test_app_hides_header_and_menu_but_keeps_content(self):
        """Con la app no hay cabecera, menú inferior ni pie legal, pero sí contenido y enlace de salto."""
        html = self.page(APP_UA)
        self.assertNotIn("z-header", html)
        self.assertNotIn("z-bottom-nav", html)
        self.assertNotIn('class="z-nav"', html)
        self.assertIn('<body class="z-app">', html)
        self.assertIn('id="contenido"', html)
        self.assertIn('class="z-skip-link"', html)
        self.assertNotIn("z-footer", html)

    def test_app_page_differs_only_by_the_chrome(self):
        """Quitando la cabecera, el menú, el pie y la clase del cuerpo, las dos páginas son iguales."""
        browser, app = self.page(BROWSER_UA), self.page(APP_UA)
        stripped = re.sub(r'<header class="z-header">.*?</header>', "", browser, flags=re.S)
        stripped = re.sub(r'<nav class="z-bottom-nav".*?</nav>', "", stripped, flags=re.S)
        stripped = re.sub(r'<footer class="z-footer footer">.*?</footer>', "", stripped, flags=re.S)
        blank_lines = re.compile(r"\n\s*\n+")  # las etiquetas {% if %} dejan líneas en blanco distintas
        self.assertEqual(blank_lines.sub("\n", stripped.replace("<body>", '<body class="z-app">')),
                         blank_lines.sub("\n", app))

    def test_anonymous_pages_too(self):
        """También las páginas públicas (login) pierden la cabecera dentro de la app."""
        self.client.logout()
        html = self.client.get(reverse("login"), HTTP_USER_AGENT=APP_UA).content.decode()
        self.assertNotIn("z-header", html)
        self.assertIn('name="password"', html)
        self.assertIn('<header class="z-header">', self.client.get(reverse("login")).content.decode())

    def test_flag_gives_no_extra_permissions(self):
        """El User-Agent solo cambia la presentación: no abre páginas protegidas."""
        self.client.logout()
        response = self.client.get(reverse("list_match"), HTTP_USER_AGENT=APP_UA)
        self.assertEqual(response.status_code, 302)
