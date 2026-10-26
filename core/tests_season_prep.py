"""Pruebas de «Prepara la temporada»: cuándo aparece, quién la ve y cómo se marcan los pasos."""
import datetime
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from core import season_prep
from core.models import Club
from core.tests_roles import ManagerBase
from core.tests_security import PASSWORD
from players import snp_import
from players.models import SnpTeamImport

OCT = datetime.date(2026, 10, 26)
JAN = datetime.date(2027, 1, 15)


def at(day):
    """Parchea «hoy» (``timezone.localdate``) para que valga ``day``."""
    return mock.patch("django.utils.timezone.localdate", return_value=day)


class SeasonPrepBase(ManagerBase):
    """Club creado en marzo de 2026 (existía el 1 de julio) con capitán, gestor y miembro."""

    def setUp(self):
        super().setUp()
        Club.objects.filter(pk=self.club.pk).update(created_at=timezone.make_aware(datetime.datetime(2026, 3, 1)))
        self.club.refresh_from_db()

    def prep(self, membership, day=OCT):
        membership.club = Club.objects.get(pk=self.club.pk)
        with at(day):
            return season_prep.season_prep_for(membership, day)


class AppearanceTests(SeasonPrepBase):
    """Cuándo y a quién se ofrece la tarjeta."""

    def test_year_and_label(self):
        self.assertEqual(season_prep.prep_year(datetime.date(2026, 7, 1)), 2026)
        self.assertEqual(season_prep.prep_year(datetime.date(2026, 10, 31)), 2026)
        for day in (datetime.date(2026, 6, 30), datetime.date(2026, 11, 1), JAN):
            self.assertIsNone(season_prep.prep_year(day))
        self.assertEqual(season_prep.season_label(2026), "2026/27")

    def test_captain_and_manager_see_it_member_does_not(self):
        self.assertEqual(self.prep(self.captain_membership)["label"], "2026/27")
        self.assertEqual(self.prep(self.manager_membership)["total"], 3)
        self.assertIsNone(self.prep(self.membership))

    def test_only_between_july_and_october(self):
        self.assertIsNone(self.prep(self.captain_membership, JAN))
        self.assertIsNone(self.prep(self.captain_membership, datetime.date(2026, 6, 30)))
        self.assertIsNotNone(self.prep(self.captain_membership, datetime.date(2026, 7, 1)))

    def test_new_clubs_do_not_see_it(self):
        Club.objects.filter(pk=self.club.pk).update(created_at=timezone.make_aware(datetime.datetime(2026, 9, 1)))
        self.captain_membership.club.refresh_from_db()
        self.assertIsNone(self.prep(self.captain_membership))

    def test_gestor_does_not_get_the_snp_search_state(self):
        steps = {s["key"]: s for s in self.prep(self.manager_membership)["steps"]}
        self.assertIsNone(steps["snp"]["sync"])


class StepsTests(SeasonPrepBase):
    """Marcar pasos, omitir SNP y ocultar."""

    def test_manual_steps_and_completion(self):
        with at(OCT):
            self.assertFalse(season_prep.mark_step(self.club, season_prep.ROSTER, OCT))
            self.assertFalse(season_prep.mark_step(self.club, season_prep.RIVALS, OCT))
            self.assertEqual(self.prep(self.captain_membership)["done"], 2)
            self.assertTrue(season_prep.mark_step(self.club, season_prep.SNP_SKIPPED, OCT))
        self.club.refresh_from_db()
        self.assertIsNone(self.prep(self.captain_membership))

    def test_unknown_key_and_out_of_season_are_ignored(self):
        self.assertFalse(season_prep.mark_step(self.club, "other", OCT))
        self.assertFalse(season_prep.mark_step(self.club, season_prep.ROSTER, JAN))
        self.club.refresh_from_db()
        self.assertEqual(self.club.season_prep, {})

    def test_progress_resets_next_year(self):
        season_prep.mark_step(self.club, season_prep.ROSTER, OCT)
        self.club.refresh_from_db()
        self.assertEqual(self.prep(self.captain_membership)["done"], 1)
        next_july = datetime.date(2027, 7, 2)
        self.assertEqual(self.prep(self.captain_membership, next_july)["done"], 0)

    def test_snp_step_is_done_by_a_web_import_this_season(self):
        imp = SnpTeamImport.objects.create(club=self.club, started_by=self.captain, source=SnpTeamImport.WEB,
                                           status=SnpTeamImport.DONE)
        SnpTeamImport.objects.filter(pk=imp.pk).update(created_at=timezone.make_aware(datetime.datetime(2026, 9, 10)))
        steps = {s["key"]: s for s in self.prep(self.captain_membership)["steps"]}
        self.assertTrue(steps["snp"]["done"])

    def test_dismiss(self):
        season_prep.close(self.club, OCT)
        self.club.refresh_from_db()
        self.assertIsNone(self.prep(self.captain_membership))


class WebImportPerSeasonTests(SeasonPrepBase):
    """«Completar equipo» desde la web: una vez por temporada."""

    def make(self, when):
        imp = SnpTeamImport.objects.create(club=self.club, started_by=self.captain, source=SnpTeamImport.WEB,
                                           status=SnpTeamImport.DONE)
        SnpTeamImport.objects.filter(pk=imp.pk).update(created_at=timezone.make_aware(when))

    def test_import_of_last_season_does_not_count(self):
        self.make(datetime.datetime(2026, 5, 10))
        with at(OCT):
            self.assertIsNone(snp_import.web_import_done(self.club))

    def test_import_since_july_counts_until_next_july(self):
        self.make(datetime.datetime(2026, 8, 20))
        with at(OCT):
            self.assertIsNotNone(snp_import.web_import_done(self.club))
        with at(JAN):
            self.assertIsNotNone(snp_import.web_import_done(self.club))
        with at(datetime.date(2027, 7, 3)):
            self.assertIsNone(snp_import.web_import_done(self.club))

    def test_window_start(self):
        self.assertEqual(snp_import.season_window_start(datetime.date(2026, 10, 26)).date(), datetime.date(2026, 7, 1))
        self.assertEqual(snp_import.season_window_start(datetime.date(2027, 2, 1)).date(), datetime.date(2026, 7, 1))


class ViewsTests(SeasonPrepBase):
    """Tarjeta en el Inicio y vistas de los pasos."""

    def test_home_shows_card_to_captain_and_manager_but_not_member(self):
        with at(OCT):
            for user, expected in (("captain", True), ("manager", True), ("member", False)):
                self.client.login(username=user, password=PASSWORD)
                page = self.client.get(reverse("home"))
                with self.subTest(user=user):
                    self.assertEqual("Prepara la temporada 2026/27" in page.content.decode(), expected)
                    if user == "captain":
                        self.assertIsNone(page.context["snp_sync"])
                        self.assertContains(page, "Conectar SNP")

    def test_manager_marks_roster_and_rivals_but_not_snp(self):
        self.client.login(username="manager", password=PASSWORD)
        with at(OCT):
            self.assertEqual(self.client.post(reverse("season_prep_step", args=["roster"])).status_code, 302)
            self.assertEqual(self.client.post(reverse("season_prep_step", args=["rivals"])).status_code, 302)
            self.assertEqual(self.client.post(reverse("season_prep_step", args=["snp_skipped"])).status_code, 403)
            self.assertEqual(self.client.post(reverse("season_prep_dismiss")).status_code, 403)
            self.assertEqual(self.client.post(reverse("season_prep_step", args=["nope"])).status_code, 404)
        self.club.refresh_from_db()
        self.assertEqual(sorted(self.club.season_prep["done"]), ["rivals", "roster"])

    def test_member_cannot_mark_steps(self):
        self.client.login(username="member", password=PASSWORD)
        with at(OCT):
            self.assertEqual(self.client.post(reverse("season_prep_step", args=["roster"])).status_code, 403)

    def test_captain_skips_snp_and_finishing_shows_message(self):
        self.client.login(username="captain", password=PASSWORD)
        with at(OCT):
            for key in ("roster", "rivals"):
                self.client.post(reverse("season_prep_step", args=[key]))
            response = self.client.post(reverse("season_prep_step", args=["snp_skipped"]), follow=True)
            self.assertContains(response, "Temporada 2026/27 lista")
            self.assertNotContains(response, "Prepara la temporada 2026/27")

    def test_captain_dismisses_card(self):
        self.client.login(username="captain", password=PASSWORD)
        with at(OCT):
            self.client.post(reverse("season_prep_dismiss"))
            self.assertNotContains(self.client.get(reverse("home")), "Prepara la temporada 2026/27")

    def test_steps_need_post(self):
        self.client.login(username="captain", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("season_prep_step", args=["roster"])).status_code, 405)
