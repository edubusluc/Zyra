"""
Fiabilidad de la lectura de SNP (fase 2 de la hoja de ruta): puntos ilegibles (SNP-01), control de
cordura que descarta una lectura rota y coincidencias parciales de nombre que confirma el capitán (SNP-02).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.services import create_club

from . import snp_import
from .models import Player, SnpAccount, SnpScoreHistory, SnpTeamImport
from .scraper import parse_score
from .snp import match_scores, sync_club

User = get_user_model()

# Filas reales de la tabla de SNP (nombre, puntos en notación española).
SAMPLE_ROWS = [
    ("Juan Santiago Rodríguez", "66.406,25"),
    ("JAVIER HIDALGO GÓMEZ DE TEJADA", "65.000,00"),
]


def scraped(rows):
    """Lo que devolvería el scraper para pares (nombre, texto de puntos)."""
    return [{"name": name, "score": parse_score(text)} for name, text in rows]


@override_settings(FIELD_ENCRYPTION_KEY="")
class UnreadableScoreTests(TestCase):
    def setUp(self):
        self.club = create_club("Club A", "Sevilla", User.objects.create_user("admin", password="x"))
        account = SnpAccount(club=self.club, team_id="1")
        account.username, account.password = "capitan", "secreto"
        account.save()
        self.account = account
        self.names = [("Ana", "Álvarez"), ("Luis", "Pérez"), ("Marta", "Gil"), ("Pablo", "Ruiz")]
        self.players = [Player.objects.create(club=self.club, name=n, last_name=a, snp_score=100.0, in_team=True)
                        for n, a in self.names]

    def rows(self, texts):
        """Una fila de SNP por jugador con el texto de puntos indicado."""
        return scraped([(f"{n} {a}", t) for (n, a), t in zip(self.names, texts)])

    def test_sample_values_are_saved_with_thousands_and_decimals(self):
        player = Player.objects.create(club=self.club, name="Juan Santiago", last_name="Rodríguez", snp_score=60000.0, in_team=True)
        result = sync_club(self.account, scraper=lambda *a, **k: scraped(SAMPLE_ROWS))
        self.assertTrue(result.ok)
        player.refresh_from_db()
        self.assertEqual(player.snp_score, 66406.25)

    def test_unreadable_score_keeps_old_points_and_is_reported(self):
        result = sync_club(self.account, scraper=lambda *a, **k: self.rows(["110,0", "100,0", "100,0", "12.5"]))
        self.assertTrue(result.ok)
        pablo = Player.objects.get(name="Pablo")
        self.assertEqual(pablo.snp_score, 100.0)
        self.assertFalse(SnpScoreHistory.objects.filter(player=pablo).exists())
        self.assertEqual(result.unreadable, ["Pablo Ruiz"])  # «12.5» no es notación española
        self.assertIn("Puntos ilegibles en SNP", self.account.__class__.objects.get(pk=self.account.pk).last_sync_message)
        self.assertEqual(Player.objects.get(name="Ana").snp_score, 110.0)

    def test_many_unreadable_scores_roll_back_everything(self):
        result = sync_club(self.account, scraper=lambda *a, **k: self.rows(["120,0", "", "n/d", "--"]))
        self.assertFalse(result.ok)
        self.assertTrue(result.retryable)
        self.assertIn("parece incorrecta", result.message)
        self.assertEqual(set(Player.objects.values_list("snp_score", flat=True)), {100.0})
        self.assertFalse(SnpScoreHistory.objects.exists())

    def test_many_zeros_roll_back_everything(self):
        result = sync_club(self.account, scraper=lambda *a, **k: self.rows(["0", "0,00", "0", "100,0"]))
        self.assertFalse(result.ok)
        self.assertEqual(set(Player.objects.values_list("snp_score", flat=True)), {100.0})

    def test_absurd_jumps_roll_back_everything(self):
        result = sync_club(self.account, scraper=lambda *a, **k: self.rows(["1.000,0", "1.000,0", "1.000,0", "100,0"]))
        self.assertFalse(result.ok)
        self.assertEqual(set(Player.objects.values_list("snp_score", flat=True)), {100.0})

    def test_a_single_real_drop_is_saved(self):
        result = sync_club(self.account, scraper=lambda *a, **k: self.rows(["0", "101,5", "100,0", "99,0"]))
        self.assertTrue(result.ok)
        self.assertEqual(Player.objects.get(name="Ana").snp_score, 0.0)
        self.assertEqual(Player.objects.get(name="Luis").snp_score, 101.5)


class PartialMatchTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.admin)

    def test_partial_match_is_doubtful_not_matched(self):
        juan = Player.objects.create(club=self.club, name="Juan", last_name="García", in_team=True)
        doubtful = []
        matched, unmatched, ambiguous = match_scores([juan], [{"name": "Juan Pedro García Soto", "score": 9.0}], doubtful)
        self.assertEqual((matched, unmatched, ambiguous), ([], [], []))
        self.assertEqual(doubtful, [(juan, "Juan Pedro García Soto")])

    def test_partial_match_without_list_is_unmatched(self):
        juan = Player.objects.create(club=self.club, name="Juan", last_name="García", in_team=True)
        matched, unmatched, _ = match_scores([juan], [{"name": "Juan Pedro García Soto", "score": 9.0}])
        self.assertEqual((matched, unmatched), ([], ["Juan Pedro García Soto"]))

    @override_settings(FIELD_ENCRYPTION_KEY="")
    def test_sync_does_not_give_points_to_a_partial_match(self):
        juan = Player.objects.create(club=self.club, name="Juan", last_name="García", in_team=True, snp_score=5.0)
        account = SnpAccount(club=self.club, team_id="1")
        account.username, account.password = "capitan", "secreto"
        account.save()
        result = sync_club(account, scraper=lambda *a, **k: [{"name": "Juan Pedro García Soto", "score": 99.0}])
        juan.refresh_from_db()
        self.assertEqual(juan.snp_score, 5.0)
        self.assertEqual(result.doubtful, ["Juan Pedro García Soto"])
        account.refresh_from_db()
        self.assertIn("sin seguridad", account.last_sync_message)

    def plan(self):
        juan = Player.objects.create(club=self.club, name="Juan", last_name="García", in_team=True, snp_score=5.0)
        to_add, existing = snp_import.plan_import(self.club, [{"name": "Juan Pedro García Soto 500", "score": 99.0}])
        return juan, to_add, existing

    def test_plan_import_offers_the_candidate_as_suggestion(self):
        juan, to_add, existing = self.plan()
        self.assertEqual(existing, [])
        self.assertEqual(len(to_add), 1)
        self.assertEqual(to_add[0]["doubtful_id"], juan.pk)

    def make_import(self, to_add):
        return SnpTeamImport.objects.create(club=self.club, status=SnpTeamImport.READY, started_at=timezone.now(),
                                            source=SnpTeamImport.WEB, to_add=to_add)

    def test_automatic_confirm_leaves_doubtful_pending(self):
        juan, to_add, _ = self.plan()
        done = snp_import.confirm(self.make_import(to_add))
        juan.refresh_from_db()
        self.assertEqual(juan.snp_score, 5.0)
        self.assertEqual(Player.objects.filter(club=self.club).count(), 1)
        self.assertEqual(done.created_players, [])

    def test_captain_confirms_same_player(self):
        juan, to_add, _ = self.plan()
        snp_import.confirm(self.make_import(to_add), same={to_add[0]["snp_name"]: juan.pk})
        juan.refresh_from_db()
        self.assertEqual(juan.snp_score, 99.0)
        self.assertEqual(Player.objects.filter(club=self.club).count(), 1)

    def test_captain_says_it_is_another_player(self):
        juan, to_add, _ = self.plan()
        snp_import.confirm(self.make_import(to_add), same={})
        juan.refresh_from_db()
        self.assertEqual(juan.snp_score, 5.0)
        self.assertEqual(Player.objects.filter(club=self.club).count(), 2)

    @override_settings(FIELD_ENCRYPTION_KEY="")
    def test_screen_shows_the_suggestion_preselectable(self):
        juan, to_add, _ = self.plan()
        self.make_import(to_add)
        account = SnpAccount(club=self.club)
        account.username, account.password = "capitan", "secreto"
        account.save()
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("list_players"), follow=True)
        self.assertContains(page, "no es seguro que sean la misma persona")
        self.assertContains(page, f'<option value="{juan.pk}">Sí, Juan García</option>', html=True)

    def test_unreadable_score_new_player_is_created_without_points(self):
        to_add, _ = snp_import.plan_import(self.club, [{"name": "Pedro Gil Soto 500", "score": None}])
        snp_import.confirm(self.make_import(to_add), same={})
        pedro = Player.objects.get(name="Pedro")
        self.assertIsNone(pedro.snp_score)
        self.assertFalse(SnpScoreHistory.objects.filter(player=pedro).exists())


class KeyRotationTests(TestCase):
    """Rotación de FIELD_ENCRYPTION_KEY (ROADMAP 20): varias claves, la primera cifra y todas descifran."""

    def setUp(self):
        from cryptography.fernet import Fernet
        self.old, self.new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        self.club = create_club("Club R", "Sevilla", User.objects.create_user("capi", password="x"))

    def make_account(self):
        account = SnpAccount(club=self.club, team_id="1")
        account.username, account.password = "usuario", "secreto"
        account.save()
        return account

    def test_new_key_in_front_still_reads_old_data_and_command_reencrypts(self):
        from io import StringIO
        from django.core.management import call_command
        with override_settings(FIELD_ENCRYPTION_KEY=self.old):
            account = self.make_account()
        before = account.password_encrypted
        with override_settings(FIELD_ENCRYPTION_KEY=f"{self.new},{self.old}"):
            self.assertEqual(SnpAccount.objects.get().password, "secreto")
            call_command("rotate_encryption_key", stdout=StringIO())
        after = SnpAccount.objects.get()
        self.assertNotEqual(after.password_encrypted, before)
        with override_settings(FIELD_ENCRYPTION_KEY=self.new):
            self.assertEqual((after.username, after.password), ("usuario", "secreto"))

    def test_command_aborts_without_saving_when_an_account_is_unreadable(self):
        from io import StringIO
        from django.core.management import call_command
        with override_settings(FIELD_ENCRYPTION_KEY=self.old):
            self.make_account()
        before = SnpAccount.objects.get().password_encrypted
        with override_settings(FIELD_ENCRYPTION_KEY=self.new):
            with self.assertRaises(SystemExit):
                call_command("rotate_encryption_key", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(SnpAccount.objects.get().password_encrypted, before)
