"""
Red de seguridad de la auditoría (fase 8): protege familias enteras de fallo, no casos sueltos.

- Todas las rutas están clasificadas (las de allauth las fija ``core/tests_allauth_urls.py``): de un objeto, con el equipo explícito (``team_explicit``) o excepción razonada.
- Enviar un formulario con el equipo de otra pestaña no cambia nada (el equipo activo no se da por hecho).
- Un generador de temporadas con resultados conocidos comprueba las cifras de las estadísticas.
- Integridad: equipos protegidos, borrados de enfrentamientos auditados, advertencias sin duplicados.
"""
import datetime
import random

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import ProtectedError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import get_resolver, reverse
from django.urls.resolvers import URLResolver

from backoffice.models import AuditLog
from call.models import Call
from core.middleware import SESSION_KEY
from core.models import Club, Invitation, Membership, UserPreference
from core.services import create_club, delete_club
from data_analyse import pairs as pair_stats
from match.models import Game, Match, Result
from penalty.models import OTHER, Penalty
from players.models import Player, SnpAccount
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345"

# Rutas que no escriben sobre el equipo activo, con el motivo. Una ruta nueva que no sea de un objeto ni lleve
# ``team_explicit`` tiene que añadirse aquí a propósito (o llevar el equipo de forma explícita).
EXEMPT = {
    # Públicas, sin equipo.
    "home": "portada", "robots_txt": "público", "favicon_ico": "público", "bing_site_auth": "público",
    "sitemap": "público", "privacy": "público", "terms": "público", "cookies": "público", "guide_index": "público",
    "callup_template_pdf": "público", "guide_detail": "público", "healthz": "público",
    "javascript-catalog": "público", "set_language": "idioma de la cuenta",
    # Páginas de consulta (GET) del equipo activo.
    "list_players": "consulta", "sync_status": "consulta (JSON)", "list_match": "consulta", "calendar_match": "consulta",
    "my_statistics": "consulta", "team_statistics": "consulta", "player_statistics": "consulta",
    "pair_statistics": "consulta", "warnings_statistics": "consulta", "rival_statistics": "consulta",
    "rival_detail": "consulta", "list_teams": "consulta", "club_home": "consulta", "club_members": "consulta",
    "member_welcome": "consulta", "no_club": "consulta",
    # Preferencias de la cuenta: no tocan datos de un equipo.
    "toggle_my_form": "preferencia de la cuenta", "dismiss_manager_tip": "preferencia de la cuenta",
    "dismiss_snp_update_tip": "preferencia de la cuenta", "my_profile": "datos de la cuenta",
    "logout_everywhere": "cuenta", "resend_verification": "cuenta", "delete_account": "cuenta (pide contraseña)",
    "password_check": "comprobación sin escribir",
    "delete_penalty": "ids públicos de advertencias; las de otros clubes se ignoran",
    "link_related_sheet": "ficha propia de la cuenta (id de la ficha)", "reject_related_sheet": "ficha propia de la cuenta",
    "respond_copy_invitation": "token de invitación",
    # Acceso y alta: crean cuentas o clubes nuevos, no escriben en uno existente.
    "login": "acceso", "logout": "acceso", "register_club": "alta de un club nuevo", "register": "alta",
    "register_account": "alta", "switch_club": "elige el equipo de forma explícita (id en el POST)",
    # Enlaces con token propio.
    "monthly_unsubscribe": "token", "result_unsubscribe": "token", "news_unsubscribe": "token",
    "invitation": "token de invitación", "availability": "token de disponibilidad",
}


def _routes():
    """Todas las rutas de la web (sin back-office, admin, allauth ni archivos subidos): (nombre, patrón, vista)."""
    rows = []

    def walk(patterns, prefix=""):
        for pattern in patterns:
            text = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, text)
            else:
                rows.append((pattern.name or "", text, pattern.callback))

    walk(get_resolver().url_patterns)
    return [r for r in rows if not r[1].startswith(("backoffice", "accounts", "^media", "admin", "panel", "gestion"))]


class RoutesAreExplicitAboutTheTeamTests(SimpleTestCase):
    """SEC-01, FUN-01, FUN-03, NAV-01: cada ruta nueva tiene que decir cómo sabe de qué equipo es."""

    def test_every_route_is_classified(self):
        """Una ruta o es de un objeto (``<pid:...>``), o lleva ``team_explicit``, o está en la lista de excepciones."""
        unclassified = [
            f"{path} ({name})" for name, path, view in _routes()
            if "<pid:" not in path and not getattr(view, "team_explicit", False) and name not in EXEMPT
        ]
        self.assertEqual(unclassified, [], "Rutas sin clasificar: lleva el equipo de forma explícita "
                         "(spaces.team_explicit y campo oculto «team») o añádelas a EXEMPT con el motivo.")

    def test_exempt_routes_still_exist(self):
        """La lista de excepciones no arrastra rutas que ya no existen."""
        names = {name for name, _path, _view in _routes()}
        self.assertEqual([n for n in EXEMPT if n not in names], [])


class StaleTeamFormsAreRejectedTests(TestCase):
    """FUN-01, FUN-03, NAV-01: cargar con el equipo A, cambiar a B y enviar no cambia nada en B."""

    ARGS = {"season_prep_step": ["snp_skipped"]}

    def setUp(self):
        self.user = User.objects.create_user("capi", password=PASSWORD)
        self.snp = create_club("Club SNP", "Sevilla", self.user)
        self.lapi = create_club("Club LAPI", "Sevilla", self.user, competition="lapi")
        SnpAccount(club=self.lapi).save()
        self.client = Client()
        self.client.login(username="capi", password=PASSWORD)
        session = self.client.session
        session[SESSION_KEY] = self.lapi.id  # el equipo activo ahora es LAPI
        session.save()

    def snapshot(self):
        """Estado que un envío mal dirigido podría cambiar."""
        return (
            Player.objects.count(), Match.objects.count(), Team.objects.count(), Invitation.objects.count(),
            Membership.objects.count(), SnpAccount.objects.count(), UserPreference.objects.count(),
            list(Club.objects.order_by("id").values_list("onboarding_dismissed_at", "archived_at")),
            list(Membership.objects.order_by("id").values_list("manager_welcome_pending", flat=True)),
            list(Player.objects.order_by("id").values_list("in_team", "name")),
        )

    def marked_routes(self):
        """Nombres de las rutas con ``team_explicit`` (todas se envían sin ``?en=`` para no saltarse la comprobación)."""
        return sorted({name for name, _path, view in _routes()
                       if getattr(view, "team_explicit", False) and "<pid:" not in _path})

    def test_there_are_routes_to_check(self):
        """Si el decorador deja de propagarse, este test falla en vez de dar por buenos cero envíos."""
        self.assertGreaterEqual(len(self.marked_routes()), 15)

    def test_post_with_another_teams_id_changes_nothing(self):
        """Con el equipo de otra pestaña (SNP) en el campo ``team``, el equipo activo (LAPI) no cambia."""
        for name in self.marked_routes():
            for payload in ({"team": self.snp.public_id}, {}):
                with self.subTest(route=name, payload=bool(payload)):
                    before = self.snapshot()
                    response = self.client.post(reverse(name, args=self.ARGS.get(name, [])), payload)
                    self.assertIn(response.status_code, (302, 403, 405), name)
                    self.assertEqual(self.snapshot(), before, f"{name} cambió datos con un equipo que no era el activo")
                    self.assertTrue(Membership.objects.filter(user=self.user, club=self.lapi).exists())


class SeasonFiguresTests(TestCase):
    """EST-01, EST-03: una temporada generada con resultados conocidos da las cifras que se espera."""

    def test_generated_season_matches_the_oracle(self):
        """Victorias, derrotas y sets de cada partido (local o visitante) coinciden con lo guardado."""
        rng = random.Random(2026)
        user = User.objects.create_user("capi", password=PASSWORD)
        club = create_club("Club A", "Sevilla", user)
        rival = Team.objects.create(club=club, name="Rival", location="X", in_group=True)
        players = [Player.objects.create(club=club, name=n, last_name="Test", joined_season="2020-2021")
                   for n in "ABCDEF"]
        expected = []  # (n_game, ganado, sets desde el lado del club)
        day = datetime.date(2025, 10, 1)
        for number in range(12):
            own_local = rng.random() < 0.5
            match = Match.objects.create(
                club=club, local=club.own_team if own_local else rival, visiting=rival if own_local else club.own_team,
                start_date=day + datetime.timedelta(days=7 * number), draft_mode=False, result="EMPATE")
            side = "local" if own_local else "visiting"
            for n_game in (1, 2, 3):
                pair = rng.sample(players, 2)
                sets, mine, theirs = [], 0, 0
                while max(mine, theirs) < 2:
                    own_games, rival_games = rng.choice([(6, 2), (6, 4), (3, 6), (2, 6), (7, 5), (4, 6)])
                    sets.append((own_games, rival_games))
                    mine, theirs = (mine + 1, theirs) if own_games > rival_games else (mine, theirs + 1)
                won = mine > theirs
                winner = ("Local" if own_local else "Visitante") if won else ("Visitante" if own_local else "Local")
                game = Game.objects.create(match=match, n_game=n_game, score=3 if n_game < 3 else 2, winner=winner,
                                           draft_mode=False, **{f"player_1_{side}": pair[0], f"player_2_{side}": pair[1]})
                values = {}
                for i, (own_games, rival_games) in enumerate(sets, start=1):
                    local, visiting = (own_games, rival_games) if own_local else (rival_games, own_games)
                    values[f"set{i}_local"], values[f"set{i}_visiting"] = local, visiting
                Result.objects.create(game=game, draft_mode=False, **values)
                expected.append((n_game, won, sets))
        log = pair_stats.club_game_log(club, "2025-2026")
        self.assertEqual(len(log), len(expected))
        self.assertEqual([(g["n_game"], g["won"], g["sets"]) for g in log], expected)


class DataIntegrityTests(TestCase):
    """DB-01, DB-02: equipos protegidos, borrados de enfrentamientos auditados y advertencias sin duplicados."""

    def setUp(self):
        self.user = User.objects.create_user("capi", password=PASSWORD)
        self.club = create_club("Club A", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date.today() + datetime.timedelta(days=5))
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Ruiz", in_team=True)
        self.client.login(username="capi", password=PASSWORD)

    def test_team_with_matches_cannot_be_deleted(self):
        """Un equipo con enfrentamientos (o con jugadores) no se borra en cascada."""
        with self.assertRaises(ProtectedError):
            self.rival.delete()
        with self.assertRaises(ProtectedError):
            self.club.own_team.delete()

    def test_delete_club_still_removes_everything(self):
        """``delete_club`` borra enfrentamientos y jugadores antes que el club."""
        delete_club(self.club)
        self.assertFalse(Match.objects.exists() or Player.objects.exists() or Team.objects.exists())

    def test_admin_offers_no_delete_for_teams_matches_or_players(self):
        """El admin de Django no ofrece borrar equipos, enfrentamientos ni jugadores."""
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        for model in (Team, Match, Player):
            self.assertFalse(admin.site._registry[model].has_delete_permission(request), model)
        self.assertTrue(Permission.objects.exists())

    def test_deleting_a_match_leaves_an_audit_trail(self):
        """Borrar un enfrentamiento anota quién, cuándo y qué en el registro de auditoría."""
        self.match.draft_mode = True
        self.match.save()
        response = self.client.post(reverse("delete_match", args=[self.match.public_id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Match.objects.filter(pk=self.match.pk).exists())
        entry = AuditLog.objects.get(action="match.delete")
        self.assertEqual(entry.username, "capi")
        self.assertEqual(entry.detail["club"], "Club A")
        self.assertEqual(entry.object_id, self.match.public_id)

    def test_double_submit_does_not_duplicate_a_warning(self):
        """Enviar dos veces la misma advertencia (mismo motivo y detalle) crea una sola."""
        call = Call.objects.create(match=self.match, draft_mode=False)
        url = reverse("create_penalty", args=[call.public_id])
        data = {"kind": OTHER, "reason": "Llegó tarde", "players": [self.player.pk]}
        self.client.post(url, data)
        self.client.post(url, data)
        self.assertEqual(Penalty.objects.filter(player=self.player, call=call).count(), 1)
        self.client.post(url, {**data, "reason": "Otro motivo distinto"})
        self.assertEqual(Penalty.objects.filter(player=self.player, call=call).count(), 2)
