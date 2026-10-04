from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Membership
from core.services import create_club
from team.models import Team

from .models import Player, SnpAccount
from .scraper import SnpScrapeError, parse_score, parse_team_id
from .snp import match_scores, normalize, sync_club

User = get_user_model()

GALAXY_URL = (
    "https://snpgalaxy.com/main/i/abc___def/i_:ghi+jkl/"
    "u_:aHR0cHM6Ly9zZXJpZXNuYWNpb25hbGVzZGVwYWRlbC5zbnBnYWxheHkuY29tL2VxdWlwby92aWV3LzQzODA="
)
DIRECT_URL = "https://seriesnacionalesdepadel.snpgalaxy.com/equipo/view/4380"


class ScraperHelpersTests(TestCase):
    def test_parse_team_id(self):
        self.assertEqual(parse_team_id(" 4380 "), "4380")
        self.assertEqual(parse_team_id(DIRECT_URL), "4380")
        self.assertEqual(parse_team_id(GALAXY_URL), "4380")
        self.assertIsNone(parse_team_id("https://snpgalaxy.com/main"))

    def test_parse_score(self):
        self.assertEqual(parse_score("1.234,5"), 1234.5)
        self.assertEqual(parse_score("12,5 / 3"), 12.5)
        self.assertEqual(parse_score(""), 0.0)
        self.assertEqual(parse_score("n/d"), 0.0)


class MatchScoresTests(TestCase):
    def setUp(self):
        self.club = create_club("Club A", "Sevilla", User.objects.create_user("admin", password="x"))

    def player(self, name, last_name):
        return Player.objects.create(club=self.club, name=name, last_name=last_name)

    def test_normalize_ignores_case_accents_and_punctuation(self):
        self.assertEqual(normalize("  JOSÉ  Pérez-Ruíz "), "jose perez ruiz")
        self.assertEqual(normalize("Íñigo"), "inigo")

    def test_matches_ignoring_case_accents_category_and_second_surname(self):
        jose = self.player("Jose", "perez")
        maria = self.player("María José", "Gómez Ruiz")
        matched, unmatched, ambiguous = match_scores([jose, maria], [
            {"name": "JOSÉ PÉREZ LÓPEZ 500", "score": 10.0},
            {"name": "Maria Jose Gomez Ruiz Future", "score": 20.0},
            {"name": "Otro Jugador 500", "score": 5.0},
        ])
        self.assertEqual({(p.pk, s) for p, s, _ in matched}, {(jose.pk, 10.0), (maria.pk, 20.0)})
        self.assertEqual(unmatched, ["Otro Jugador 500"])
        self.assertEqual(ambiguous, [])

    def test_exact_match_wins_over_prefix(self):
        short = self.player("Juan", "García")
        full = self.player("Juan", "García López")
        matched, _, ambiguous = match_scores([short, full], [{"name": "Juan García López", "score": 7.0}])
        self.assertEqual([(p.pk, s) for p, s, _ in matched], [(full.pk, 7.0)])
        self.assertEqual(ambiguous, [])

    def test_ambiguous_names_are_not_assigned(self):
        a = self.player("Juan", "García López")
        b = self.player("Juan", "García Ruiz")
        matched, _, ambiguous = match_scores([a, b], [{"name": "Juan García", "score": 7.0}])
        self.assertEqual(matched, [])
        self.assertEqual(ambiguous, ["Juan García"])


NO_PAUSES = {"SNP_PAUSE_MIN_SECONDS": 0, "SNP_PAUSE_MAX_SECONDS": 0, "SNP_BATCH_PAUSE_SECONDS": 0}


@override_settings(FIELD_ENCRYPTION_KEY="", **NO_PAUSES)
class SnpAccountTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.admin)
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Álvarez")

    def make_account(self, club=None):
        account = SnpAccount(club=club or self.club, team_id="4380")
        account.username = "capitan"
        account.password = "secreto"
        account.save()
        return account

    def test_credentials_are_stored_encrypted(self):
        account = self.make_account()
        raw = SnpAccount.objects.values("username_encrypted", "password_encrypted").get(pk=account.pk)
        self.assertNotIn("capitan", raw["username_encrypted"])
        self.assertNotIn("secreto", raw["password_encrypted"])
        account.refresh_from_db()
        self.assertEqual((account.username, account.password), ("capitan", "secreto"))

    def test_sync_opens_the_country_of_the_team(self):
        own = self.club.own_team
        own.country = "MX"
        own.save()
        scraper = mock.Mock(return_value=[{"name": "ANA ALVAREZ 500", "score": 1.0}])
        sync_club(self.make_account(), scraper=scraper)
        scraper.assert_called_once_with("capitan", "secreto", "4380", country="MX")

    def test_country_link_defaults_to_spain(self):
        from . import scraper
        self.assertEqual(scraper.snp_country_name("IT"), "Italia")
        self.assertEqual(scraper.snp_country_name("SE"), "Suecia")
        self.assertEqual(scraper.snp_country_name(""), "España")
        self.assertEqual(scraper.snp_country_name(None), "España")
        page, frame = mock.Mock(), mock.Mock()
        frame.query_selector_all.return_value = []  # la cuenta no tiene equipos: para ahí
        clicked = []
        with mock.patch.object(scraper, "_find", side_effect=lambda p, selector, *a, **k: clicked.append(selector) or
                               (frame, mock.Mock())), self.assertRaises(scraper.SnpScrapeError):
            scraper._open_team_page(page, None, lambda m: None, "PT")
        self.assertEqual(clicked[1], 'a.menu-link:has([data-i18n="Portugal"])')

    def test_sync_updates_scores_and_records_result(self):
        account = self.make_account()
        scraper = mock.Mock(return_value=[{"name": "ANA ALVAREZ 500", "score": 42.5}])
        result = sync_club(account, scraper=scraper)
        scraper.assert_called_once_with("capitan", "secreto", "4380", country="")
        self.assertTrue(result.ok)
        self.player.refresh_from_db()
        self.assertEqual(self.player.snp_score, 42.5)
        account.refresh_from_db()
        self.assertTrue(account.last_sync_ok)
        self.assertIsNotNone(account.last_sync_at)

    def test_sync_failure_is_recorded_without_touching_scores(self):
        account = self.make_account()
        result = sync_club(account, scraper=mock.Mock(side_effect=SnpScrapeError("SNP no ha aceptado el usuario")))
        self.assertFalse(result.ok)
        account.refresh_from_db()
        self.assertFalse(account.last_sync_ok)
        self.assertIn("no ha aceptado", account.last_sync_message)
        self.player.refresh_from_db()
        self.assertIsNone(self.player.snp_score)

    def test_command_runs_club_by_club(self):
        self.make_account()
        other_admin = User.objects.create_user("other", password="x")
        other_club = create_club("Club B", "Madrid", other_admin)
        Player.objects.create(club=other_club, name="Bea", last_name="Beta")
        self.make_account(other_club)
        create_club("Club sin cuenta", "Cádiz", User.objects.create_user("third", password="x"))

        calls = []

        def fake_scrape(username, password, team_id, **options):
            calls.append(username)
            return [{"name": "Ana Alvarez", "score": 1.0}, {"name": "Bea Beta", "score": 2.0}]

        out = StringIO()
        with mock.patch("players.snp.scrape_scores", fake_scrape):
            call_command("update_snp_scores", stdout=out)
        self.assertEqual(len(calls), 2)
        self.assertEqual(Player.objects.get(name="Ana").snp_score, 1.0)
        self.assertEqual(Player.objects.get(name="Bea").snp_score, 2.0)
        output = out.getvalue()
        self.assertIn("Equipos a actualizar: 2\n", output)
        self.assertIn("Equipo que se actualiza: Club A\n", output)
        self.assertIn("Equipo que se actualiza: Club B\n", output)
        self.assertIn("Jugadores a actualizar: 1\n", output)
        self.assertIn("Jugadores actualizados correctamente: 1\n", output)
        self.assertIn("Jugadores no actualizados: 0\n", output)

        calls.clear()
        with mock.patch("players.snp.scrape_scores", fake_scrape):
            call_command("update_snp_scores", "--club", "club b", stdout=StringIO())
        self.assertEqual(len(calls), 1)

        # Ya están actualizados en este ciclo: la pasada diaria no repite nada.
        calls.clear()
        out = StringIO()
        with mock.patch("players.snp.scrape_scores", fake_scrape):
            call_command("update_snp_scores", stdout=out)
        self.assertEqual(calls, [])
        self.assertIn("No hay equipos pendientes", out.getvalue())

    def test_admin_can_save_account_and_password_is_kept_when_blank(self):
        self.client.login(username="admin", password="pass-12345")
        response = self.client.post(reverse("snp_account"), {
            "username": "capitan", "password": "secreto", "team": GALAXY_URL,
        })
        self.assertRedirects(response, reverse("snp_account"))
        page = self.client.get(reverse("snp_account")).content.decode()
        self.assertNotIn("secreto", page)
        self.assertIn("4380", page)

        self.client.post(reverse("snp_account"), {"username": "capitan2", "password": "", "team": ""})
        account = SnpAccount.objects.get(club=self.club)
        self.assertEqual((account.username, account.password, account.team_id), ("capitan2", "secreto", ""))

    def test_rejects_url_without_team(self):
        self.client.login(username="admin", password="pass-12345")
        response = self.client.post(reverse("snp_account"), {
            "username": "capitan", "password": "secreto", "team": "https://snpgalaxy.com/main",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SnpAccount.objects.exists())

    def test_members_cannot_see_account(self):
        viewer = User.objects.create_user("viewer", password="pass-12345")
        Membership.objects.create(user=viewer, club=self.club, role=Membership.MEMBER)
        self.make_account()
        self.client.login(username="viewer", password="pass-12345")
        self.assertEqual(self.client.get(reverse("snp_account")).status_code, 403)
        self.assertEqual(self.client.post(reverse("snp_account_delete")).status_code, 403)
        self.assertTrue(SnpAccount.objects.exists())

    def test_log_lists_players_not_updated(self):
        self.make_account()
        Player.objects.create(club=self.club, name="Luis", last_name="Gómez")
        out = StringIO()
        with mock.patch("players.snp.scrape_scores", lambda *a, **k: [{"name": "Ana Alvarez", "score": 3.0}]):
            call_command("update_snp_scores", stdout=out)
        self.assertIn("Jugadores a actualizar: 2\n", out.getvalue())
        self.assertIn("Jugadores actualizados correctamente: 1\n", out.getvalue())
        self.assertIn("Jugadores no actualizados: 1 (LUIS GÓMEZ)\n", out.getvalue())

        out = StringIO()
        with mock.patch("players.snp.scrape_scores", lambda *a, **k: [{"name": "Ana Alvarez", "score": 3.0},
                                                                     {"name": "Luis Gomes 500", "score": 4.0}]):
            call_command("update_snp_scores", "--all", stdout=out)
        self.assertIn("Nombres de SNP sin jugador en Zyra: Luis Gomes 500\n", out.getvalue())

    def test_sync_keeps_one_history_point_per_player_and_day(self):
        from .models import SnpScoreHistory, current_season
        account = self.make_account()
        sync_club(account, scraper=lambda *a, **k: [{"name": "Ana Alvarez", "score": 10.0}])
        sync_club(account, scraper=lambda *a, **k: [{"name": "Ana Alvarez", "score": 12.0}])
        history = SnpScoreHistory.objects.get(player=self.player)
        self.assertEqual((history.score, history.season), (12.0, current_season()))

    def test_player_statistics_include_snp_chart(self):
        import datetime
        from .models import SnpScoreHistory, current_season
        SnpScoreHistory.objects.create(player=self.player, date=datetime.date(2026, 9, 28), score=100.0, season=current_season())
        SnpScoreHistory.objects.create(player=self.player, date=datetime.date(2026, 10, 5), score=120.5, season=current_season())
        SnpScoreHistory.objects.create(player=self.player, date=datetime.date(2020, 1, 1), score=1.0, season="2019-2020")
        self.client.login(username="admin", password="pass-12345")
        response = self.client.get(reverse("player_statistics"), {"player": self.player.public_id})
        self.assertEqual(response.context["chart_snp"], {"labels": ["28/09", "05/10"], "scores": [100.0, 120.5]})
        self.assertContains(response, 'id="chartSnp"')

    def test_home_shows_snp_notice_to_admin_until_account_exists(self):
        viewer = User.objects.create_user("viewer", password="pass-12345")
        Membership.objects.create(user=viewer, club=self.club, role=Membership.MEMBER)
        self.client.login(username="admin", password="pass-12345")
        self.assertContains(self.client.get(reverse("home")), "Registra tu cuenta de SNP")
        self.client.login(username="viewer", password="pass-12345")
        self.assertNotContains(self.client.get(reverse("home")), "Registra tu cuenta de SNP")
        self.make_account()
        self.client.login(username="admin", password="pass-12345")
        self.assertNotContains(self.client.get(reverse("home")), "Registra tu cuenta de SNP")

    def test_snp_job_runs_every_night_and_cycle_starts_on_monday(self):
        from backoffice.jobs import get_spec
        from players.management.commands.update_snp_scores import SNP_SYNC_CYCLE
        self.assertEqual(get_spec("update_snp_scores").schedule, "0 23 * * *")
        self.assertEqual(SNP_SYNC_CYCLE, "0 23 * * 1")


def madrid(*args):
    import datetime
    from zoneinfo import ZoneInfo
    return datetime.datetime(*args, tzinfo=ZoneInfo("Europe/Madrid"))


@override_settings(FIELD_ENCRYPTION_KEY="", **NO_PAUSES)
class SnpBatchTests(TestCase):
    """update_snp_scores por lotes: fallos aislados, parada si SNP limita y reanudación."""

    def setUp(self):
        self.accounts = []
        for letter in "ABCD":
            admin = User.objects.create_user(f"admin{letter}", password="x")
            club = create_club(f"Club {letter}", "Sevilla", admin)
            Player.objects.create(club=club, name="Ana", last_name=letter)
            account = SnpAccount(club=club)
            account.username = f"capitan{letter}"
            account.password = "secreto"
            account.save()
            self.accounts.append(account)
        self.calls = []

    def scraper(self, failures=None):
        failures = failures or {}

        def fake(username, password, team_id, **options):
            self.calls.append(username)
            if username in failures:
                raise failures[username]
            return [{"name": f"Ana {username[-1]}", "score": 10.0}]
        return fake

    def run_command(self, *args, failures=None):
        out = StringIO()
        error = None
        with mock.patch("players.snp.scrape_scores", self.scraper(failures)):
            try:
                call_command("update_snp_scores", *args, stdout=out)
            except CommandError as exc:
                error = exc
        return out.getvalue(), error

    def test_runs_in_batches_and_one_failure_does_not_stop_the_rest(self):
        output, error = self.run_command("--batch-size", "2", failures={"capitanB": RuntimeError("fallo raro")})
        self.assertIsNone(error)
        self.assertEqual(self.calls, ["capitanA", "capitanB", "capitanC", "capitanD"])
        self.assertIn("=== Lote 1 de 2 (2 equipos) ===", output)
        self.assertIn("=== Lote 2 de 2 (2 equipos) ===", output)
        self.assertIn("Lote 1: 1 correctos, 1 con error.", output)
        self.assertIn("Resumen: 3 equipos actualizados, 1 con error, 0 sin procesar.", output)
        self.assertEqual(Player.objects.filter(snp_score=10.0).count(), 3)
        failed = SnpAccount.objects.get(club__name="Club B")
        self.assertEqual((failed.last_sync_ok, failed.last_sync_retryable), (False, True))

    def test_club_scores_are_saved_all_or_nothing(self):
        from .models import SnpScoreHistory
        club = self.accounts[0].club
        Player.objects.create(club=club, name="Bea", last_name="A")
        original = SnpScoreHistory.objects.update_or_create
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("se cae la base de datos")
            return original(*args, **kwargs)

        scores = [{"name": "Ana A", "score": 7.0}, {"name": "Bea A", "score": 8.0}]
        with mock.patch.object(SnpScoreHistory.objects, "update_or_create", flaky):
            result = sync_club(self.accounts[0], scraper=lambda *a, **k: scores)
        self.assertFalse(result.ok)
        self.assertFalse(Player.objects.filter(club=club, snp_score__isnull=False).exists())
        self.assertFalse(SnpScoreHistory.objects.exists())

    def test_stops_when_snp_blocks_and_resumes_on_next_run(self):
        from .scraper import SnpBlockedError
        output, error = self.run_command(failures={"capitanB": SnpBlockedError("SNP ha respondido 429")})
        self.assertIsNotNone(error)
        self.assertIn("limitando", str(error))
        self.assertEqual(self.calls, ["capitanA", "capitanB"])
        self.assertIn("Resumen: 1 equipos actualizados, 1 con error, 2 sin procesar.", output)

        # La siguiente pasada retoma: el bloqueado y los que faltaban, no el que ya estaba hecho.
        self.calls.clear()
        output, error = self.run_command()
        self.assertIsNone(error)
        self.assertEqual(sorted(self.calls), ["capitanB", "capitanC", "capitanD"])
        self.assertEqual(self.calls[-1], "capitanB")  # los nunca intentados van primero

    def test_stops_after_several_network_failures_in_a_row(self):
        from .scraper import SnpTemporaryError
        down = SnpTemporaryError("Error del navegador al leer SNP: timeout")
        with override_settings(SNP_MAX_CONSECUTIVE_FAILURES=2):
            output, error = self.run_command(failures={u: down for u in ("capitanA", "capitanB", "capitanC")})
        self.assertIn("2 equipos seguidos", str(error))
        self.assertEqual(self.calls, ["capitanA", "capitanB"])

    def test_rejected_password_is_not_retried_in_the_same_cycle(self):
        output, error = self.run_command(failures={"capitanA": SnpScrapeError("SNP no ha aceptado el usuario o la contraseña.")})
        self.assertIsNone(error)
        self.calls.clear()
        output, error = self.run_command()
        self.assertEqual(self.calls, [])
        self.assertIn("No hay equipos pendientes", output)

    def test_a_new_cycle_makes_every_club_pending_again(self):
        from players.management.commands.update_snp_scores import pending_accounts
        self.run_command()
        self.assertEqual(pending_accounts().count(), 0)
        SnpAccount.objects.update(last_sync_at=madrid(2026, 9, 28, 22, 0))  # antes del lunes 28 a las 23:00
        self.assertEqual(pending_accounts(madrid(2026, 9, 30, 12, 0)).count(), 4)

    def test_browser_work_runs_outside_the_database_thread(self):
        # Playwright deja un bucle asíncrono abierto en su hilo y ahí Django no deja usar
        # la base de datos: el navegador debe trabajar en un hilo aparte.
        import threading
        from . import scraper
        caller = threading.get_ident()
        seen = []

        def fake_scrape(username, password, team_id, log, browser, country):
            seen.append(threading.get_ident())
            return [{"name": "Ana A", "score": 5.0}]

        with mock.patch.object(scraper, "_scrape", fake_scrape), scraper.SnpBrowser() as browser:
            scores = scraper.scrape_scores("u", "p", browser=browser)
            scraper.scrape_scores("u", "p", browser=browser)
        self.assertEqual(scores, [{"name": "Ana A", "score": 5.0}])
        self.assertNotEqual(seen[0], caller)
        self.assertEqual(seen[0], seen[1])  # el mismo hilo (y navegador) para todo el lote

    def test_waits_until_the_table_is_filled(self):
        # SNP muestra la tabla vacía y la rellena después: no hay que leerla vacía.
        from . import scraper
        page, frame = mock.Mock(), mock.Mock()
        frame.is_detached.return_value = False
        reads = iter([[], [], ["ANA A"], ["ANA A", "BEA B"], ["ANA A", "BEA B"]])
        with mock.patch.object(scraper, "_table_names", lambda f: next(reads)):
            self.assertIs(scraper._wait_for_rows(page, frame, lambda m: None), frame)
        self.assertEqual(page.wait_for_timeout.call_count, 4)

        with mock.patch.object(scraper, "_table_names", lambda f: []), \
                mock.patch.object(scraper, "TABLE_TIMEOUT_MS", 1500), self.assertRaises(scraper.SnpTemporaryError):
            scraper._wait_for_rows(page, frame, lambda m: None)

    @override_settings(BACKOFFICE_RUN_JOBS_INLINE=True)
    def test_back_office_can_run_with_options(self):
        from backoffice.models import JobRun
        from backoffice.scheduler import sync_jobs
        sync_jobs()
        User.objects.create_user("staff", password="pass-12345", is_staff=True)
        self.client.login(username="staff", password="pass-12345")
        page = self.client.get(reverse("backoffice:job_detail", args=["update_snp_scores"]))
        self.assertContains(page, "Repetir todos los equipos")
        self.assertContains(page, 'name="club"')
        url = reverse("backoffice:job_run_now", args=["update_snp_scores"])

        self.run_command()  # todos al día: sin opciones no haría nada
        self.calls.clear()
        with mock.patch("players.snp.scrape_scores", self.scraper()):
            self.client.post(url, {"all": "1", "verbose": "1"})
        run = JobRun.objects.get()
        self.assertEqual(run.args, ["--all", "--verbosity=2"])
        self.assertEqual(len(self.calls), 4)

        with mock.patch("players.snp.scrape_scores", self.scraper()):
            self.client.post(url, {"club": "Club B"})
        self.assertEqual(JobRun.objects.latest("pk").args, ["--club", "Club B"])
        self.assertEqual(self.calls[-1], "capitanB")

        response = self.client.post(url, {"club": "<script>"})
        self.assertRedirects(response, reverse("backoffice:job_detail", args=["update_snp_scores"]))
        self.assertEqual(JobRun.objects.count(), 2)

    def test_cycle_start_is_the_last_monday_at_23(self):
        from players.management.commands.update_snp_scores import cycle_start
        self.assertEqual(cycle_start(madrid(2026, 9, 30, 12, 0)), madrid(2026, 9, 28, 23, 0))
        self.assertEqual(cycle_start(madrid(2026, 9, 28, 23, 0)), madrid(2026, 9, 28, 23, 0))
        self.assertEqual(cycle_start(madrid(2026, 9, 28, 22, 59)), madrid(2026, 9, 21, 23, 0))


SNP_TEAM = [
    {"name": "ANA ALVAREZ 500", "score": 42.5},
    {"name": "PEDRO RAPOSO BELLERIN 1000", "score": 120.0},
    {"name": "MARIA JOSE GOMEZ RUIZ Future", "score": 33.0},
]


class SplitSnpNameTests(TestCase):
    def test_split(self):
        self.assertEqual(__import__("players.snp_import", fromlist=["x"]).split_snp_name("LUIS PEREZ GOMEZ GRAND SLAM"),
                         ("Luis", "Perez Gomez"))
        from .snp_import import split_snp_name
        self.assertEqual(split_snp_name("PEDRO RAPOSO BELLERIN 500"), ("Pedro", "Raposo Bellerin"))
        self.assertEqual(split_snp_name("MARIA JOSE GOMEZ RUIZ Future"), ("Maria Jose", "Gomez Ruiz"))
        self.assertEqual(split_snp_name("JUAN DE LA FUENTE LÓPEZ"), ("Juan", "de la Fuente López"))
        self.assertEqual(split_snp_name("ANA ALVAREZ"), ("Ana", "Alvarez"))
        self.assertEqual(split_snp_name("PELÉ"), ("Pelé", ""))


@override_settings(FIELD_ENCRYPTION_KEY="", SNP_IMPORT_INLINE=True)
class CompleteTeamTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.admin)
        account = SnpAccount(club=self.club)
        account.username, account.password = "capitan", "secreto"
        account.save()
        # Jugador existente con datos propios: no se debe tocar.
        self.ana = Player.objects.create(club=self.club, name="Ana", last_name="Álvarez", position="Revés", snp_score=1.0)
        self.client.login(username="admin", password="pass-12345")
        patcher = mock.patch("players.snp_import.scrape_scores", lambda *a, **k: SNP_TEAM)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_preview_then_confirm_creates_only_new_players(self):
        from .models import SnpScoreHistory, SnpTeamImport
        self.assertContains(self.client.get(reverse("list_players")), "Completar equipo")
        self.assertRedirects(self.client.post(reverse("complete_team_start")), reverse("list_players"))
        team_import = SnpTeamImport.objects.get()
        self.assertEqual(team_import.status, SnpTeamImport.READY)
        self.assertEqual([(p["name"], p["last_name"]) for p in team_import.to_add],
                         [("Maria Jose", "Gomez Ruiz"), ("Pedro", "Raposo Bellerin")])
        self.assertEqual(team_import.existing, [{"snp_name": "ANA ALVAREZ", "category": "500", "player": "ANA ÁLVAREZ"}])
        self.assertEqual(Player.objects.count(), 1)  # la búsqueda no crea nada

        page = self.client.get(reverse("list_players"))
        self.assertContains(page, 'id="completeTeamModal"')
        self.assertContains(page, "PEDRO RAPOSO BELLERIN")
        self.assertContains(page, "ya están registrados")
        self.assertEqual(self.client.get(reverse("complete_team_status", args=[team_import.public_id])).json()["status"], "ready")

        self.client.post(reverse("complete_team_confirm", args=[team_import.public_id]))
        pedro = Player.objects.get(name="Pedro")
        self.assertEqual((pedro.last_name, pedro.snp_score, pedro.in_team, pedro.team), ("Raposo Bellerin", 120.0, True, self.club.own_team))
        self.assertTrue(SnpScoreHistory.objects.filter(player=pedro, score=120.0).exists())
        self.ana.refresh_from_db()
        self.assertEqual((self.ana.last_name, self.ana.position, self.ana.snp_score), ("Álvarez", "Revés", 1.0))
        self.assertEqual(Player.objects.count(), 3)

        # Solo una vez al mes.
        page = self.client.get(reverse("list_players"))
        self.assertContains(page, "Ya se ha completado este mes")
        self.client.post(reverse("complete_team_start"))
        self.assertEqual(SnpTeamImport.objects.count(), 1)

    def test_confirm_skips_players_created_in_the_meantime(self):
        from .models import SnpTeamImport
        self.client.post(reverse("complete_team_start"))
        team_import = SnpTeamImport.objects.get()
        Player.objects.create(club=self.club, name="Pedro", last_name="Raposo")
        self.client.post(reverse("complete_team_confirm", args=[team_import.public_id]))
        self.assertEqual(Player.objects.filter(name="Pedro").count(), 1)
        self.assertTrue(Player.objects.filter(name="Maria Jose").exists())

    def test_cancel_does_not_count_for_the_monthly_limit(self):
        from .models import SnpTeamImport
        self.client.post(reverse("complete_team_start"))
        team_import = SnpTeamImport.objects.get()
        self.client.post(reverse("complete_team_cancel", args=[team_import.public_id]))
        self.assertEqual(Player.objects.count(), 1)
        self.client.post(reverse("complete_team_start"))
        self.assertEqual(SnpTeamImport.objects.filter(status=SnpTeamImport.READY).count(), 1)

    def failed_import(self, error):
        from .models import SnpTeamImport
        with mock.patch("players.snp_import.scrape_scores", side_effect=error):
            self.client.post(reverse("complete_team_start"))
        team_import = SnpTeamImport.objects.get()
        self.assertEqual(team_import.status, SnpTeamImport.ERROR)
        return team_import, self.client.get(reverse("complete_team_status", args=[team_import.public_id])).json()

    def test_rejected_password_leads_to_the_snp_account_form(self):
        team_import, status = self.failed_import(SnpScrapeError("SNP no ha aceptado el usuario o la contraseña.", kind=SnpScrapeError.ACCOUNT))
        self.assertEqual(status["redirect"], reverse("complete_team_failed", args=[team_import.public_id]))
        response = self.client.get(status["redirect"], follow=True)
        self.assertRedirects(response, reverse("snp_account") + "?edit=1")
        self.assertContains(response, "no ha aceptado el usuario")
        self.assertContains(response, 'name="username"')  # el formulario, no la tarjeta

    def test_no_players_found_leads_to_editing_the_own_team(self):
        from .scraper import SnpTemporaryError
        team_import, status = self.failed_import(SnpTemporaryError("La tabla de jugadores de SNP está vacía.", kind=SnpScrapeError.TEAM))
        response = self.client.get(status["redirect"], follow=True)
        self.assertRedirects(response, reverse("edit_team", args=[self.club.own_team.public_id]))
        self.assertContains(response, "Comprueba que la configuración de tu equipo es correcta")

    def test_other_errors_stay_in_the_popup_with_the_team_hint(self):
        from .scraper import SnpTemporaryError
        team_import, status = self.failed_import(SnpTemporaryError("Error del navegador al leer SNP: timeout"))
        self.assertEqual(status["redirect"], "")

    def test_scraper_errors_say_where_to_fix_them(self):
        from . import scraper
        self.assertEqual(scraper.SnpScrapeError("x").kind, "")
        self.assertTrue(scraper.SnpTemporaryError("x", kind=scraper.SnpScrapeError.TEAM).retryable)
        page, frame = mock.Mock(), mock.Mock()
        frame.query_selector_all.return_value = []
        with mock.patch.object(scraper, "_find", return_value=(frame, mock.Mock())), \
                self.assertRaises(scraper.SnpScrapeError) as raised:
            scraper._open_team_page(page, "4380", lambda m: None)
        self.assertEqual(raised.exception.kind, scraper.SnpScrapeError.ACCOUNT)
        with mock.patch.object(scraper, "_find", return_value=(frame, mock.Mock())), \
                self.assertRaises(scraper.SnpScrapeError) as raised:
            scraper._open_team_page(page, None, lambda m: None)
        self.assertEqual(raised.exception.kind, scraper.SnpScrapeError.TEAM)

    def test_no_button_without_snp_account_or_for_members(self):
        viewer = User.objects.create_user("viewer", password="pass-12345")
        Membership.objects.create(user=viewer, club=self.club, role=Membership.MEMBER)
        self.client.login(username="viewer", password="pass-12345")
        self.assertNotContains(self.client.get(reverse("list_players")), "Completar equipo")
        self.client.post(reverse("complete_team_start"))
        self.client.login(username="admin", password="pass-12345")
        SnpAccount.objects.all().delete()
        self.assertNotContains(self.client.get(reverse("list_players")), "Completar equipo")
        self.assertEqual(Player.objects.count(), 1)

    def test_backoffice_command_uses_team_id_and_ignores_monthly_limit(self):
        from .models import SnpTeamImport
        team_id = self.club.own_team.public_id
        out = StringIO()
        call_command("complete_snp_team", team_id, "--dry-run", stdout=out)
        self.assertIn("Jugadores a añadir: 2 (Maria Jose Gomez Ruiz, Pedro Raposo Bellerin)", out.getvalue())
        self.assertIn("No se añaden porque ya están registrados: 1 (ANA ALVAREZ → ANA ÁLVAREZ)", out.getvalue())
        self.assertEqual(Player.objects.count(), 1)

        SnpTeamImport.objects.create(club=self.club, status=SnpTeamImport.DONE, finished_at=timezone.now())
        out = StringIO()
        call_command("complete_snp_team", team_id, stdout=out)
        self.assertIn("Resultado: 2 jugadores añadidos.", out.getvalue())
        self.assertEqual(Player.objects.count(), 3)

        rival = Team.objects.create(club=self.club, name="Rival", location="X")
        with self.assertRaises(CommandError):
            call_command("complete_snp_team", rival.public_id, stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("complete_snp_team", "TEAnoexiste0000", stdout=StringIO())

    def test_complete_team_is_a_manual_backoffice_job(self):
        from backoffice.jobs import get_spec
        spec = get_spec("complete_snp_team")
        self.assertEqual((spec.schedule, [p.name for p in spec.params]), ("", ["team_id"]))

    def test_edit_player_saves_name_and_last_name(self):
        response = self.client.post(reverse("edit_player", args=[self.ana.public_id]), {
            "name": "Ana María", "last_name": "Álvarez Ruiz", "position": "Revés", "skillfull_hand": "Diestro",
            "joined_season": "2026-2027", "in_team": "on",
        })
        self.assertRedirects(response, reverse("list_players"))
        self.ana.refresh_from_db()
        self.assertEqual((self.ana.name, self.ana.last_name), ("Ana María", "Álvarez Ruiz"))
        self.assertContains(self.client.get(reverse("edit_player", args=[self.ana.public_id])), 'name="last_name"')

    def test_names_are_shown_in_uppercase_but_stored_as_typed(self):
        self.ana.name, self.ana.last_name = "ana maría", "álvarez ruiz"
        self.ana.save()
        self.assertEqual((self.ana.full_name, self.ana.short_name), ("ANA MARÍA ÁLVAREZ RUIZ", "ANA MARÍA ÁLVAREZ"))
        self.assertContains(self.client.get(reverse("list_players")), "ANA MARÍA ÁLVAREZ")
        self.assertContains(self.client.get(reverse("show_player", args=[self.ana.public_id])), "ANA MARÍA ÁLVAREZ")
        # El formulario de edición muestra lo guardado, sin cambiarlo.
        self.assertContains(self.client.get(reverse("edit_player", args=[self.ana.public_id])), 'value="álvarez ruiz"')


class CreatePlayerSimilarityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin_sim", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user, gender="F", country="ES")
        Player.objects.create(club=self.club, name="María", last_name="García López")
        other = create_club("Club B", "Madrid", User.objects.create_user("otro", password="pass-12345"))
        Player.objects.create(club=other, name="Lucía", last_name="Martín")
        self.client.force_login(self.user)
        self.url = reverse("create_player")
        self.data = {"name": "Maria", "last_name": "Garcia", "position": "NONE", "skillfull_hand": "NONE"}

    def test_similar_player_asks_before_creating(self):
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["similar"], ["MARÍA GARCÍA LÓPEZ"])
        self.assertEqual(Player.objects.filter(club=self.club).count(), 1)

        self.client.post(self.url, {**self.data, "confirm_similar": "1"})
        self.assertEqual(Player.objects.filter(club=self.club).count(), 2)

    def test_check_request_and_players_of_other_clubs(self):
        response = self.client.post(self.url, self.data, HTTP_X_SIMILAR_CHECK="1")
        self.assertEqual(response.json(), {"valid": True, "similar": ["MARÍA GARCÍA LÓPEZ"]})
        # Solo cuenta el equipo del club activo
        response = self.client.post(self.url, {**self.data, "name": "Lucia", "last_name": "Martin"}, HTTP_X_SIMILAR_CHECK="1")
        self.assertEqual(response.json(), {"valid": True, "similar": []})

    def test_new_player_gets_team_gender(self):
        response = self.client.post(self.url, {**self.data, "name": "Ana", "last_name": "Ruiz"})
        self.assertRedirects(response, reverse("list_players"), fetch_redirect_response=False)
        self.assertEqual(Player.objects.get(name="Ana").gender, "F")


class PlayerChoicePlaceholderTests(TestCase):
    """Posición y mano sin indicar se muestran como «Elige una opción», nunca como NONE."""

    def setUp(self):
        self.user = User.objects.create_user("admin_none", password="pass-12345")
        self.club = create_club("Club N", "Sevilla", self.user)
        self.player = Player.objects.create(club=self.club, name="Ana", last_name="Ruiz")
        self.client.force_login(self.user)

    def assert_placeholder(self, response):
        self.assertNotContains(response, ">NONE<")
        self.assertContains(response, '<option value="NONE" selected>Elige una opción</option>', count=2, html=True)

    def test_create_and_edit_forms(self):
        self.assert_placeholder(self.client.get(reverse("create_player")))
        self.assert_placeholder(self.client.get(reverse("edit_player", args=[self.player.public_id])))

    def test_lists_show_dash(self):
        self.assertNotContains(self.client.get(reverse("list_players")), "NONE")

    def test_match_form_team_selects(self):
        response = self.client.get(reverse("create_match"))
        self.assertNotContains(response, "---------")
        self.assertContains(response, "Elige una opción", count=2)


class DeletePlayerTests(TestCase):
    def setUp(self):
        import datetime
        from call.models import Call
        from match.models import Game, Match, Result
        from penalty.models import Penalty

        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.ana = Player.objects.create(club=self.club, name="Ana", last_name="López")
        self.bea = Player.objects.create(club=self.club, name="Bea", last_name="Ruiz")
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                          start_date=datetime.date(2025, 10, 1))
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.set([self.ana, self.bea])
        self.penalty_model = Penalty
        Penalty.objects.create(player=self.ana, call=call, reason="Retraso")
        self.game = Game.objects.create(match=self.match, n_game=1, score=3, winner="Local", draft_mode=False,
                                        player_1_local=self.ana, player_2_local=self.bea)
        Result.objects.create(game=self.game, set1_local="6", set1_visiting="2", set2_local="6",
                              set2_visiting="3", set3_local="0", set3_visiting="0")
        self.client.login(username="admin", password="pass-12345")

    def test_confirmation_warns_that_statistics_are_deleted(self):
        page = self.client.get(reverse("delete_player", args=[self.ana.public_id])).content.decode()
        self.assertIn("estadísticas relacionadas con este jugador", page)
        self.assertIn("1 partido jugado", page)
        self.assertTrue(Player.objects.filter(pk=self.ana.pk).exists())

    def test_delete_keeps_match_game_and_result(self):
        response = self.client.post(reverse("delete_player", args=[self.ana.public_id]))
        self.assertRedirects(response, reverse("list_players"))
        self.assertFalse(Player.objects.filter(pk=self.ana.pk).exists())
        self.assertFalse(self.penalty_model.objects.exists())

        self.game.refresh_from_db()
        self.assertIsNone(self.game.player_1_local)
        self.assertEqual(self.game.player_2_local, self.bea)
        self.assertTrue(self.game.results.exists())
        self.assertEqual(self.game.local_pair_label, "ANA LÓPEZ / BEA RUIZ")
        page = self.client.get(reverse("call_for_match", args=[self.match.public_id])).content.decode()
        self.assertIn("ANA LÓPEZ / BEA RUIZ", page)
        # El compañero conserva sus estadísticas.
        self.assertEqual(self.client.get(reverse("show_player", args=[self.bea.public_id])).status_code, 200)

    def test_members_cannot_delete(self):
        viewer = User.objects.create_user("viewer", password="pass-12345")
        Membership.objects.create(user=viewer, club=self.club, role=Membership.MEMBER)
        self.client.login(username="viewer", password="pass-12345")
        self.client.post(reverse("delete_player", args=[self.ana.public_id]))
        self.assertTrue(Player.objects.filter(pk=self.ana.pk).exists())


@override_settings(FIELD_ENCRYPTION_KEY="")
class SnpAccountCardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.admin)
        self.client.force_login(self.admin)
        self.url = reverse("snp_account")

    def save_account(self):
        return self.client.post(self.url, {"username": "capitan", "password": "secreto", "team": ""})

    def test_form_until_the_account_is_saved_then_a_card(self):
        self.assertContains(self.client.get(self.url), 'name="username"')
        response = self.save_account()
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        page = self.client.get(self.url)
        self.assertNotContains(page, 'name="username"')
        self.assertContains(page, "capitan")
        self.assertContains(page, "••••••••")
        self.assertNotContains(page, "secreto")  # la contraseña no se escribe en la página
        self.assertContains(page, "?edit=1")

    def test_edit_opens_the_form_with_the_username(self):
        self.save_account()
        page = self.client.get(self.url + "?edit=1")
        self.assertContains(page, 'name="username"')
        self.assertContains(page, 'value="capitan"')
        self.assertNotContains(page, "secreto")
        # Dejar la contraseña vacía mantiene la actual.
        self.client.post(self.url, {"username": "otro", "password": "", "team": ""})
        account = SnpAccount.objects.get(club=self.club)
        self.assertEqual((account.username, account.password), ("otro", "secreto"))

    def test_password_is_shown_only_on_request_to_captains(self):
        self.save_account()
        password_url = reverse("snp_account_password")
        self.assertEqual(self.client.get(password_url).status_code, 405)
        self.assertEqual(self.client.post(password_url).json(), {"password": "secreto"})
        member = User.objects.create_user("member", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)
        self.assertNotEqual(self.client.post(password_url).status_code, 200)
