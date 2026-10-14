from datetime import timedelta
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

from . import snp_import
from .models import Player, SnpAccount, SnpTeamImport, current_season
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
        scraper.assert_called_once_with("capitan", "secreto", "4380", country="MX", team_name="Club A")

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
        scraper.assert_called_once_with("capitan", "secreto", "4380", country="", team_name="Club A")
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
        response = self.client.post(reverse("snp_account"), {"username": "capitan", "password": "secreto"})
        self.assertRedirects(response, reverse("snp_account"))
        page = self.client.get(reverse("snp_account")).content.decode()
        self.assertNotIn("secreto", page)

        self.client.post(reverse("snp_account"), {"username": "capitan2", "password": ""})
        account = SnpAccount.objects.get(club=self.club)
        self.assertEqual((account.username, account.password, account.team_id), ("capitan2", "secreto", ""))

    def test_form_does_not_ask_for_the_snp_team(self):
        # El equipo ya no se pide; uno guardado antes se olvida al volver a guardar la cuenta.
        self.client.login(username="admin", password="pass-12345")
        self.assertNotContains(self.client.get(reverse("snp_account")), "Equipo en SNP")
        account = SnpAccount(club=self.club, team_id="4380")
        account.username, account.password = "capitan", "secreto"
        account.save()
        self.assertNotContains(self.client.get(reverse("snp_account")), "4380")
        self.client.post(reverse("snp_account"), {"username": "capitan", "password": "", "team": "4380"})
        self.assertEqual(SnpAccount.objects.get().team_id, "")

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
        # La tarea sigue en «Primeros pasos», pero ya hecha y sin botón.
        self.assertNotContains(self.client.get(reverse("home")), "Registrar cuenta")

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

        def fake_scrape(username, password, team_id, log, browser, country, team_name=None, with_group_teams=False, group_only=False):
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
        self.assertEqual(team_import.existing, [{"snp_name": "ANA ALVAREZ", "category": "500", "player": "ANA ÁLVAREZ",
                                                 "player_id": self.ana.pk, "score": 42.5}])
        self.assertEqual(Player.objects.count(), 1)  # la búsqueda no crea nada

        page = self.client.get(reverse("list_players"))
        self.assertContains(page, 'id="completeTeamModal"')
        self.assertContains(page, "PEDRO RAPOSO BELLERIN")
        self.assertContains(page, "solo se actualizan sus puntos SNP")
        self.assertContains(page, "llegarán sin posición")
        self.assertEqual(self.client.get(reverse("complete_team_status", args=[team_import.public_id])).json()["status"], "ready")

        response = self.client.post(reverse("complete_team_confirm", args=[team_import.public_id]), follow=True)
        self.assertContains(response, "su posición en pista ha quedado vacía")
        pedro = Player.objects.get(name="Pedro")
        self.assertEqual((pedro.last_name, pedro.snp_score, pedro.in_team, pedro.team), ("Raposo Bellerin", 120.0, True, self.club.own_team))
        self.assertTrue(SnpScoreHistory.objects.filter(player=pedro, score=120.0).exists())
        # Del jugador que ya existía solo cambian los puntos SNP.
        self.ana.refresh_from_db()
        self.assertEqual((self.ana.last_name, self.ana.position, self.ana.snp_score), ("Álvarez", "Revés", 42.5))
        self.assertTrue(SnpScoreHistory.objects.filter(player=self.ana, score=42.5).exists())
        self.assertEqual(Player.objects.count(), 3)

        # Solo una vez: después el botón desaparece y no se puede lanzar otra.
        page = self.client.get(reverse("list_players"))
        self.assertNotContains(page, "complete_team/\"")
        self.assertNotContains(page, "Añade los jugadores de tu equipo de SNP")
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

    def test_cancel_does_not_close_the_option(self):
        from .models import SnpTeamImport
        self.client.post(reverse("complete_team_start"))
        team_import = SnpTeamImport.objects.get()
        self.client.post(reverse("complete_team_cancel", args=[team_import.public_id]))
        self.assertEqual(Player.objects.count(), 1)
        SnpTeamImport.objects.update(created_at=timezone.now() - timedelta(minutes=10))  # pasada la pausa
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

    def test_repeated_failures_hide_the_option_and_notify_staff(self):
        from django.core import mail
        from backoffice.models import AuditLog
        User.objects.create_user("staff", email="staff@example.com", password="pass-12345", is_staff=True)
        error = SnpScrapeError("SNP no ha aceptado el usuario o la contraseña.", kind=SnpScrapeError.ACCOUNT)
        for attempt in range(snp_import.MAX_FAILED_SEARCHES):
            SnpTeamImport.objects.update(created_at=timezone.now() - timedelta(hours=25))  # fuera del límite diario
            with mock.patch("players.snp_import.scrape_scores", side_effect=error):
                self.client.post(reverse("complete_team_start"))
            if attempt < snp_import.MAX_FAILED_SEARCHES - 1:
                SnpTeamImport.objects.update(created_at=timezone.now() - timedelta(hours=25))
                self.assertContains(self.client.get(reverse("list_players")), "Añade los jugadores de tu equipo de SNP")
        self.club.refresh_from_db()
        self.assertEqual(self.club.snp_import_failures, snp_import.MAX_FAILED_SEARCHES)
        page = self.client.get(reverse("list_players"))
        self.assertNotContains(page, "Añade los jugadores de tu equipo de SNP")
        self.assertContains(page, "hemos avisado al administrador")
        self.assertTrue(AuditLog.objects.filter(action="club.snp_import_blocked").exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("staff@example.com", mail.outbox[0].to)
        count = SnpTeamImport.objects.count()
        response = self.client.post(reverse("complete_team_start"), follow=True)
        self.assertContains(response, "Hemos avisado al administrador")
        self.assertEqual(SnpTeamImport.objects.count(), count)

    def test_snp_switched_off_does_not_count_as_a_failure(self):
        from . import snp_service
        with mock.patch.object(snp_service, "is_enabled", return_value=False):
            self.client.post(reverse("complete_team_start"))
        self.club.refresh_from_db()
        self.assertEqual(self.club.snp_import_failures, 0)

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

    def test_backoffice_command_uses_team_id_and_ignores_web_limit(self):
        from .models import SnpTeamImport
        team_id = self.club.own_team.public_id
        out = StringIO()
        call_command("complete_snp_team", team_id, "--dry-run", stdout=out)
        self.assertIn("Jugadores a añadir: 2 (Maria Jose Gomez Ruiz, Pedro Raposo Bellerin)", out.getvalue())
        self.assertIn("Ya registrados (solo se actualizan sus puntos SNP): 1 (ANA ALVAREZ → ANA ÁLVAREZ)", out.getvalue())
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


@override_settings(FIELD_ENCRYPTION_KEY="", SNP_IMPORT_INLINE=True, SNP_IMPORT_UNLIMITED_CLUBS=["Los Gladiadores"])
class CompleteTeamLimitsTests(TestCase):
    """Límites de «Completar equipo» desde la web y la excepción del equipo de pruebas."""

    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass-12345")
        self.client.login(username="admin", password="pass-12345")
        patcher = mock.patch("players.snp_import.scrape_scores", return_value=SNP_TEAM)
        patcher.start()
        self.addCleanup(patcher.stop)

    def club(self, name):
        club = create_club(name, "Sevilla", self.admin)
        account = SnpAccount(club=club)
        account.username, account.password = "capitan", "secreto"
        account.save()
        return club

    def start_and_cancel(self):
        from .models import SnpTeamImport
        self.client.post(reverse("complete_team_start"))
        SnpTeamImport.objects.filter(status=SnpTeamImport.READY).update(status=SnpTeamImport.CANCELLED)

    def test_repeated_searches_are_limited(self):
        from . import snp_import
        from .models import SnpTeamImport
        club = self.club("Club A")
        self.start_and_cancel()
        # Pulsar otra vez enseguida no lanza otra búsqueda.
        response = self.client.post(reverse("complete_team_start"), follow=True)
        self.assertContains(response, "varias veces seguidas")
        self.assertEqual(SnpTeamImport.objects.count(), 1)
        # Pasada la pausa sí, pero no más de SEARCHES_PER_DAY en 24 horas.
        for _ in range(snp_import.SEARCHES_PER_DAY - 1):
            SnpTeamImport.objects.update(created_at=timezone.now() - timedelta(minutes=10))
            self.start_and_cancel()
        SnpTeamImport.objects.update(created_at=timezone.now() - timedelta(hours=2))
        self.assertIsNotNone(snp_import.search_limit(club))
        self.assertContains(self.client.get(reverse("list_players")), "Podrás volver a intentarlo")
        self.client.post(reverse("complete_team_start"))
        self.assertEqual(SnpTeamImport.objects.count(), snp_import.SEARCHES_PER_DAY)

    def test_test_team_has_no_limits(self):
        from . import snp_import
        from .models import SnpTeamImport
        club = self.club("Club de pruebas")
        self.assertFalse(snp_import.is_unlimited(club))
        club.snp_unlimited = True
        club.save(update_fields=["snp_unlimited"])
        self.assertTrue(snp_import.is_unlimited(club))
        for _ in range(snp_import.SEARCHES_PER_DAY + 1):
            self.client.post(reverse("complete_team_start"))
            team_import = SnpTeamImport.objects.get(status=SnpTeamImport.READY)
            self.client.post(reverse("complete_team_confirm", args=[team_import.public_id]))
        self.assertEqual(SnpTeamImport.objects.filter(status=SnpTeamImport.DONE).count(), snp_import.SEARCHES_PER_DAY + 1)
        self.assertIsNone(snp_import.web_import_done(club))

    def test_only_existing_players_still_updates_scores(self):
        from .models import SnpTeamImport
        club = self.club("Club B")
        for name, last_name in (("Ana", "Alvarez"), ("Pedro", "Raposo Bellerin"), ("Maria Jose", "Gomez Ruiz")):
            Player.objects.create(club=club, name=name, last_name=last_name, snp_score=1.0)
        self.client.post(reverse("complete_team_start"))
        page = self.client.get(reverse("list_players"))
        self.assertContains(page, "Actualizar puntos SNP")
        team_import = SnpTeamImport.objects.get()
        self.client.post(reverse("complete_team_confirm", args=[team_import.public_id]))
        self.assertEqual(Player.objects.get(name="Pedro").snp_score, 120.0)
        self.assertEqual(Player.objects.count(), 3)


class ScraperTeamChoiceTests(TestCase):
    """Sin número de equipo, una cuenta con varios equipos usa el que se llama como el del club."""

    def page_with_teams(self, *names):
        page, frame = mock.Mock(), mock.Mock()
        links = []
        for number, name in enumerate(names, start=1):
            link = mock.Mock()
            link.get_attribute.return_value = f"/equipo/view/{number}"
            link.inner_text.return_value = name
            links.append(link)
        frame.query_selector_all.return_value = links
        return page, frame, links

    def test_picks_the_team_with_the_club_name(self):
        from . import scraper
        page, frame, links = self.page_with_teams("Otro Club", "LOS GLADIADORES")
        with mock.patch.object(scraper, "_find", return_value=(frame, mock.Mock())), \
                mock.patch.object(scraper, "_wait_for_rows", side_effect=lambda p, f, log: f):
            scraper._open_team_page(page, None, lambda m: None, team_name="Los Gladiadores")
        links[1].click.assert_called_once()
        links[0].click.assert_not_called()

    def test_several_teams_without_a_matching_name_is_a_team_error(self):
        from . import scraper
        page, frame, _ = self.page_with_teams("Uno", "Dos")
        with mock.patch.object(scraper, "_find", return_value=(frame, mock.Mock())), \
                self.assertRaises(scraper.SnpScrapeError) as raised:
            scraper._open_team_page(page, None, lambda m: None, team_name="Tres")
        self.assertEqual(raised.exception.kind, scraper.SnpScrapeError.TEAM)


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
        return self.client.post(self.url, {"username": "capitan", "password": "secreto"})

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
        self.client.post(self.url, {"username": "otro", "password": ""})
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


class PlayerListSearchTests(TestCase):
    """El listado envía todos los jugadores y filtra en el navegador, como el selector de convocatorias."""

    def test_list_renders_every_player_for_live_search_and_paging(self):
        admin = User.objects.create_user("admin", password="pass-12345")
        club = create_club("Club A", "Sevilla", admin)
        for n in range(12):
            Player.objects.create(club=club, name=f"Jugador{n}", last_name="Álvarez")
        self.client.force_login(admin)
        response = self.client.get(reverse("list_players"))
        self.assertEqual(len(response.context["players"]), 12)
        self.assertContains(response, "data-selector-search")
        self.assertContains(response, 'data-name="JUGADOR3 ÁLVAREZ"')
        self.assertContains(response, 'data-page-size="9"')


GROUP_TABLE_HTML = """
<div class="clasificacion_content panel-body"><table><tbody>
<tr><td idequipo="2849"><a class="competicion_link" href="/equipo/view/2849"><span>NorthPadel </span> </a></td><td>15</td></tr>
<tr><td idequipo="3910"><a class="competicion_link" href="/equipo/view/3910"><span>ICONICO 500 PLUS</span> </a></td><td>13</td></tr>
<tr><td idequipo="4380"><a class="competicion_link" href="/equipo/view/4380"><span class="negrita">LOS GLADIADORES</span> </a></td><td>5</td></tr>
<tr><td idequipo="3910"><a href="/equipo/view/3910"><span>ICONICO 500 PLUS</span></a></td><td>13</td></tr>
</tbody></table></div>
"""
GROUP_TEAMS = [{"snp_id": "2849", "name": "NorthPadel", "own": False},
               {"snp_id": "3910", "name": "ICONICO 500 PLUS", "own": False},
               {"snp_id": "4380", "name": "LOS GLADIADORES", "own": True}]


class GroupTeamsScraperTests(TestCase):
    @staticmethod
    def cells():
        """Celdas ``td[idequipo]`` falsas con el HTML de GROUP_TABLE_HTML (id, nombre y clase del span)."""
        import re

        def element(attrs=None, text=""):
            node = mock.Mock()
            node.get_attribute.side_effect = lambda name: (attrs or {}).get(name)
            node.inner_text.return_value = text
            return node

        out = []
        for snp_id, cls, text in re.findall(r'<td idequipo="(\d+)">.*?<span( class="[^"]*")?>([^<]*)</span>', GROUP_TABLE_HTML):
            cell = element({"idequipo": snp_id})
            span = element({"class": cls[8:-1]} if cls else {}, text)
            cell.query_selector.side_effect = lambda selector, span=span: span
            out.append(cell)
        return out

    def test_parse_group_teams_from_classification_table(self):
        from .scraper import parse_group_teams
        self.assertEqual(parse_group_teams(self.cells()), GROUP_TEAMS)  # sin repetidos y con el propio en negrita


class CompleteTeamGroupTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.admin)
        own = self.club.own_team
        own.name, own.gender, own.country, own.division = "Los Gladiadores", "M", "ES", "500"
        own.save()
        account = SnpAccount(club=self.club)
        account.username, account.password = "capitan", "secreto"
        account.save()
        self.client.login(username="admin", password="pass-12345")

    def run_import(self, teams):
        from . import snp_import
        with mock.patch("players.snp_import.scrape_scores", lambda *a, **k: ([{"name": "ANA ALVAREZ", "score": 1.0}], teams)):
            team_import = snp_import.start_search(self.club, self.admin)
        return snp_import.confirm(team_import)

    @override_settings(SNP_IMPORT_INLINE=True)
    def test_creates_group_teams_copying_own_team_data(self):
        team_import = self.run_import(GROUP_TEAMS)
        # El propio ya existe (mismo nombre) y no se duplica.
        self.assertEqual(sorted(team_import.created_teams), ["ICONICO 500 PLUS", "NorthPadel"])
        created = Team.objects.get(club=self.club, name="NorthPadel")
        self.assertEqual((created.in_group, created.is_own, created.gender, created.country, created.division),
                         (True, False, "M", "ES", "500"))
        self.assertEqual(Team.objects.filter(club=self.club, is_own=True).count(), 1)
        self.assertIn("2 equipos del grupo añadidos", team_import.message)

    @override_settings(SNP_IMPORT_INLINE=True)
    def test_existing_similar_team_is_not_duplicated_but_joins_the_group(self):
        rival = Team.objects.create(club=self.club, name="Northpadel", location="X", division="500")
        self.run_import(GROUP_TEAMS)
        self.assertEqual(Team.objects.filter(club=self.club, name__icontains="northpadel").count(), 1)
        rival.refresh_from_db()
        self.assertTrue(rival.in_group)

    @override_settings(SNP_IMPORT_INLINE=True)
    def test_group_step_failure_does_not_block_players(self):
        team_import = self.run_import([])
        self.assertEqual(team_import.status, "done")
        self.assertEqual(Team.objects.filter(club=self.club).count(), 1)
        self.assertEqual(Player.objects.filter(club=self.club, name="Ana").count(), 1)

    def test_marks_snp_own_team_when_club_has_none(self):
        from . import snp_import
        Team.objects.filter(club=self.club).update(is_own=False, name="Otro nombre")
        to_add, existing = snp_import.plan_group_teams(self.club, GROUP_TEAMS)
        created = snp_import._create_group_teams(self.club, to_add, existing)
        self.assertIn("LOS GLADIADORES", created)
        self.assertTrue(Team.objects.get(club=self.club, name="LOS GLADIADORES").is_own)


class AddGroupTeamsCommandTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", admin)
        own = self.club.own_team
        own.name, own.gender, own.country, own.division = "Los Gladiadores", "M", "ES", "500"
        own.save()
        account = SnpAccount(club=self.club)
        account.username, account.password = "capitan", "secreto"
        account.save()
        patcher = mock.patch("players.snp_import.scrape_scores", lambda *a, **k: ([{"name": "ANA ALVAREZ", "score": 1.0}], GROUP_TEAMS))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dry_run_then_create_only_teams(self):
        team_id = self.club.own_team.public_id
        out = StringIO()
        call_command("add_group_teams", team_id, "--dry-run", stdout=out)
        self.assertIn("Equipos a crear: 2 (ICONICO 500 PLUS, NorthPadel)", out.getvalue())
        self.assertEqual(Team.objects.filter(club=self.club).count(), 1)

        out = StringIO()
        call_command("add_group_teams", team_id, stdout=out)
        self.assertIn("Resultado: 2 equipos del grupo añadidos.", out.getvalue())
        self.assertEqual(Team.objects.filter(club=self.club, in_group=True).count(), 3)
        self.assertEqual(Player.objects.filter(club=self.club).count(), 0)  # no crea jugadores

    def test_rejects_rivals_and_unknown_ids(self):
        rival = Team.objects.create(club=self.club, name="Rival", location="X")
        with self.assertRaises(CommandError):
            call_command("add_group_teams", rival.public_id, stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("add_group_teams", "TEAnoexiste0000", stdout=StringIO())

    def test_is_a_manual_backoffice_job(self):
        from backoffice.jobs import get_spec
        spec = get_spec("add_group_teams")
        self.assertEqual((spec.schedule, [p.name for p in spec.params]), ("", ["team_id"]))


class GroupOnlyScrapeTests(TestCase):
    def run_scrape(self, **options):
        from . import scraper
        context = mock.Mock()
        browser = mock.Mock(new_context=mock.Mock(return_value=context))
        calls = []
        patches = {
            "_login": lambda *a: calls.append("login"),
            "_open_country": lambda *a: calls.append("country") or "España",
            "_read_group_teams": lambda *a: calls.append("competiciones") or GROUP_TEAMS,
            "_open_team_page": lambda *a, **k: calls.append("mis equipos") or mock.Mock(url="x"),
            "_read_all_pages": lambda *a: calls.append("jugadores") or [{"name": "ANA", "score": 1.0}],
        }
        with mock.patch.multiple(scraper, **patches):
            result = scraper._scrape("u", "p", None, None, browser, **options)
        return result, calls

    def test_group_only_enters_competitions_without_reading_players(self):
        result, calls = self.run_scrape(with_group_teams=True, group_only=True)
        self.assertEqual(result, ([], GROUP_TEAMS))
        self.assertEqual(calls, ["login", "country", "competiciones"])

    def test_with_group_teams_reads_competitions_before_my_teams(self):
        result, calls = self.run_scrape(with_group_teams=True)
        self.assertEqual(result[1], GROUP_TEAMS)
        self.assertEqual(calls, ["login", "country", "competiciones", "mis equipos", "jugadores"])


class JoinedSeasonSelectorTests(TestCase):
    """«Temporada en la que se unió»: solo valores de la lista y estadísticas coherentes con ella."""

    def test_helpers(self):
        from players.models import joined_by, season_choices, season_start
        self.assertEqual(season_start("2025-2026"), 2025)
        self.assertIsNone(season_start("abc"))
        self.assertTrue(joined_by("2025-2026", "2025-2026"))
        self.assertFalse(joined_by("2025-2026", "2024-2025"))
        self.assertTrue(joined_by("", "2020-2021"))
        choices = season_choices(extra=["1999-2000", "raro"])
        self.assertEqual(choices[0], f"{int(current_season()[:4]) + 1}-{int(current_season()[:4]) + 2}")
        self.assertIn("1999-2000", choices)
        self.assertNotIn("raro", choices)

    def test_form_rejects_free_text_and_keeps_old_value(self):
        from players.forms import PlayerEditForm
        club = create_club("Club", "Sevilla", get_user_model().objects.create_user("c", "c@x.com", "pass-12345"))
        p = Player.objects.create(club=club, name="Ana", last_name="Ruiz", joined_season="1999-2000")
        data = {"name": "Ana", "last_name": "Ruiz", "position": "NONE", "skillfull_hand": "NONE", "in_team": "on"}
        self.assertTrue(PlayerEditForm({**data, "joined_season": "1999-2000"}, instance=p).is_valid())
        self.assertTrue(PlayerEditForm({**data, "joined_season": "2024-2025"}, instance=p).is_valid())
        self.assertFalse(PlayerEditForm({**data, "joined_season": "2024-2026"}, instance=p).is_valid())
        self.assertFalse(PlayerEditForm({**data, "joined_season": "hola"}, instance=p).is_valid())

class ListPlayersTeamToggleTests(TestCase):
    """Interruptor «solo jugadores de mi equipo» del listado: por defecto solo los del equipo."""

    def setUp(self):
        self.user = User.objects.create_user("capi", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        Player.objects.create(club=self.club, name="Ana", last_name="López", in_team=True)
        Player.objects.create(club=self.club, name="Bea", last_name="Ruiz", in_team=False)
        self.client.force_login(self.user)

    def test_default_only_team(self):
        page = self.client.get(reverse("list_players"))
        self.assertTrue(page.context["only_team"])
        self.assertEqual([p.name for p in page.context["players"]], ["Ana"])
        self.assertContains(page, "Mostrar solo jugadores de mi equipo")

    def test_captain_sees_all_unchecked(self):
        page = self.client.get(reverse("list_players"), {"team": "0", "order_by": "-snp_score"})
        self.assertFalse(page.context["only_team"])
        self.assertEqual([p.name for p in page.context["players"]], ["Ana", "Bea"])
        self.assertContains(page, "?order_by=name&amp;team=0")
