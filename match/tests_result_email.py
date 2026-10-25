import datetime
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from backoffice.metrics import attention_counts, health_metrics
from core.models import Membership, UserPreference
from core.services import create_club
from core.unsubscribe import result_unsubscribe_path, unsubscribe_path
from match import result_email
from match.models import Game, Match, MatchResultDelivery, Result
from match.notifications import MAX_ATTEMPTS
from players.models import Player
from team.models import Team

User = get_user_model()


@override_settings(SITE_URL="http://testserver")
class ResultEmailFixture(TestCase):
    """Club con capitán, un miembro y un enfrentamiento de cinco partidos para probar el aviso del resultado."""

    def setUp(self):
        self.captain = User.objects.create_user("capi", password="pass-12345", email="capi@example.com")
        self.club = create_club("Club A", "Sevilla", self.captain)
        self.member = self._member("ana", "ana@example.com")
        self.rival = Team.objects.create(club=self.club, name="CD Tomares", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"Jug{i}", last_name="Ape", snp_score=20 + i)
                        for i in range(10)]
        self.players[0].user = self.member
        self.players[0].save()
        self.client.login(username="capi", password="pass-12345")

    def _member(self, username, email):
        user = User.objects.create_user(username, password="pass-12345", email=email)
        Membership.objects.create(user=user, club=self.club, role=Membership.MEMBER)
        return user

    def _match(self, wins=(1, 2, 4), match_type=Match.ENFRENTAMIENTO):
        """Enfrentamiento del club como local con 5 partidos con resultado; el club gana los de ``wins``."""
        match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                     start_date=datetime.date(2020, 1, 1), match_type=match_type)
        for n in range(1, 6):
            game = Game.objects.create(match=match, n_game=n, score=3 if n < 3 else 2,
                                       player_1_local=self.players[2 * n - 2], player_2_local=self.players[2 * n - 1])
            ours, theirs = (6, 2) if n in wins else (2, 6)
            Result.objects.create(game=game, set1_local=ours, set1_visiting=theirs,
                                  set2_local=ours, set2_visiting=theirs)
            game.winner = "Local" if n in wins else "Visitante"
            Game.objects.filter(pk=game.pk).update(winner=game.winner)
        return match

    def _close(self, match):
        return self.client.post(reverse("close_match", args=[match.public_id]))


@override_settings(SITE_URL="http://testserver")
class MatchResultEmailTests(ResultEmailFixture):
    """Aviso por email al cerrar el acta: destinatarios, idempotencia, correcciones, baja y control."""

    def test_closing_sends_result_to_members_and_to_the_captain(self):
        match = self._match()
        self._close(match)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["ana@example.com", "capi@example.com"])
        message = next(m for m in mail.outbox if m.to == ["ana@example.com"])
        self.assertEqual(message.subject, "Victoria 8-4 · Club A vs CD Tomares (01/01/2020)"
                         .replace("Club A", match.local_name))
        self.assertIn("Tu partido:", message.alternatives[0][0])        # Ana jugó el partido 1
        self.assertIn("Ganaste tu partido 1", message.body)
        self.assertIn("List-Unsubscribe", message.extra_headers)
        delivery = MatchResultDelivery.objects.get(user=self.member)
        self.assertEqual((delivery.status, delivery.attempts, delivery.result_points), ("sent", 1, "8/4"))

    def test_defeat_draw_and_friendly_variants(self):
        lost = self._match(wins=(4,))                       # 2 puntos contra 10
        self._close(lost)
        self.assertTrue(mail.outbox[-1].subject.startswith("Derrota 2-10"))
        draw = self._match(wins=(1, 2))                     # 6-6
        self._close(draw)
        self.assertTrue(mail.outbox[-1].subject.startswith("Empate 6-6"))
        friendly = self._match(match_type=Match.AMISTOSO)
        self._close(friendly)
        self.assertTrue(mail.outbox[-1].subject.startswith("Amistoso: victoria 8-4"))
        self.assertIn("no cuenta en las estadísticas competitivas", mail.outbox[-1].alternatives[0][0])

    def test_opt_out_inactive_suspended_and_no_email_skip_sending(self):
        for user in (self.member, self.captain):
            UserPreference.objects.update_or_create(user=user, defaults={"match_result_email": False})
        self._member("sinmail", "")
        off = self._member("baja", "baja@example.com")
        off.is_active = False
        off.save()
        self._close(self._match())
        self.assertEqual(mail.outbox, [])
        self.assertFalse(MatchResultDelivery.objects.exists())
        UserPreference.objects.filter(user=self.member).update(match_result_email=True)
        self.club.suspended_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        self.club.save()
        self._close(self._match())
        self.assertEqual(mail.outbox, [])

    def test_reclosing_after_reopening_sends_nothing_unless_the_captain_ticks_resend(self):
        match = self._match()
        self._close(match)
        self.client.post(reverse("reopen_match", args=[match.public_id]))
        self._close(match)
        self.assertEqual(len(mail.outbox), 2)                # por defecto no se reenvía
        self.client.post(reverse("reopen_match", args=[match.public_id]))
        game = match.games.get(n_game=5)
        Result.objects.filter(game=game).update(set1_local=6, set1_visiting=1, set2_local=6, set2_visiting=1)
        Game.objects.filter(pk=game.pk).update(winner="Local")
        self._close(match)
        self.assertEqual(len(mail.outbox), 2)                # marcador distinto: tampoco hay corrección
        self.client.post(reverse("reopen_match", args=[match.public_id]))
        self.client.post(reverse("close_match", args=[match.public_id]), {"resend_email": "1"})
        self.assertEqual(len(mail.outbox), 4)                # casilla marcada: se reenvía
        self.assertTrue(MatchResultDelivery.objects.get(user=self.member).correction)

    def test_first_close_ignores_the_resend_flag_and_sends_once(self):
        match = self._match()
        self.client.post(reverse("close_match", args=[match.public_id]), {"resend_email": "1"})
        self.assertEqual(len(mail.outbox), 2)

    def test_confirmation_offers_the_resend_checkbox_only_after_reopening(self):
        match = self._match()
        url = reverse("call_for_match", args=[match.public_id])
        self.assertNotContains(self.client.get(url), "data-confirm-check")
        self._close(match)
        self.client.post(reverse("reopen_match", args=[match.public_id]))
        self.assertContains(self.client.get(url), 'data-confirm-check-name="resend_email"')

    def test_failed_send_is_retried_by_the_command_and_never_blocks_closing(self):
        match = self._match()
        with mock.patch("match.result_email.get_connection", side_effect=OSError("SMTP caído")):
            self._close(match)
        match.refresh_from_db()
        self.assertFalse(match.draft_mode)                    # el acta se cerró igualmente
        delivery = MatchResultDelivery.objects.get(user=self.member)
        self.assertEqual((delivery.status, delivery.attempts), ("pending", 1))
        self.assertIn("SMTP caído", delivery.last_error)
        MatchResultDelivery.objects.update(next_attempt_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc))
        call_command("send_call_reports", stdout=StringIO())
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, len(mail.outbox)), ("sent", 2))

    def test_gives_up_after_max_attempts_and_command_fails(self):
        self._close(self._match())
        MatchResultDelivery.objects.update(status="pending", attempts=MAX_ATTEMPTS - 1, sent_at=None,
                                           next_attempt_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc))
        with mock.patch("match.result_email.get_connection", side_effect=OSError("SMTP caído")):
            with self.assertRaises(CommandError):
                call_command("send_call_reports", stdout=StringIO())
        self.assertEqual(MatchResultDelivery.objects.filter(status="failed").count(), 2)

    def test_unsubscribe_link_turns_the_notice_off_and_tokens_are_not_interchangeable(self):
        path = result_unsubscribe_path(self.member)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertTrue(UserPreference.match_result_for(self.member))   # el GET solo confirma
        self.client.post(path)
        self.assertFalse(UserPreference.match_result_for(self.member))
        token = unsubscribe_path(self.member).rstrip("/").rsplit("/", 1)[1]   # token del informe mensual
        bad = self.client.get(reverse("result_unsubscribe", args=[token]))
        self.assertEqual(bad.status_code, 404)

    def test_profile_switch_saves_preference(self):
        self.client.login(username="ana", password="pass-12345")
        self.client.post(reverse("my_profile"), {"results_form": "1"})   # interruptor sin marcar
        self.assertFalse(UserPreference.match_result_for(self.member))
        self.client.post(reverse("my_profile"), {"results_form": "1", "match_result_email": "on"})
        self.assertTrue(UserPreference.match_result_for(self.member))

    def test_backoffice_health_counts_result_deliveries(self):
        self._close(self._match())
        with mock.patch("match.result_email.get_connection", side_effect=OSError("SMTP caído")):
            self._close(self._match())
        MatchResultDelivery.objects.filter(status="pending").update(status="failed")
        health = health_metrics()["results"]
        self.assertEqual((health["sent"], health["failed"], health["ok_pct"]), (2, 2, 50))
        self.assertEqual(len(health["problems"]), 2)
        self.assertEqual(attention_counts()["results_failed"], 2)

    def test_retired_game_shows_played_sets_and_injury_mark(self):
        match = self._match()
        game = match.games.get(n_game=5)
        Result.objects.filter(game=game).update(set1_local=2, set1_visiting=6, set2_local=None,
                                                set2_visiting=None, retired=True)
        rows = result_email.game_rows(match)
        self.assertEqual(rows[4]["sets"], "2-6 · Lesión")
        self.assertEqual(rows[0]["sets"], "6-2 6-2")


@override_settings(SITE_URL="http://testserver")
class BackofficeResendResultTests(ResultEmailFixture):
    """Envío manual del aviso desde la ficha del club en el back-office."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user("staff", password="pass-12345", email="staff@example.com", is_staff=True)
        self.client.login(username="staff", password="pass-12345")

    def _closed_match(self):
        """Enfrentamiento cerrado por el capitán (envía el aviso) y vuelta a la sesión del personal."""
        self.client.login(username="capi", password="pass-12345")
        match = self._match()
        self._close(match)
        self.client.login(username="staff", password="pass-12345")
        return match

    def _resend(self, match):
        return self.client.post(reverse("backoffice:club_match_result", args=[self.club.public_id]),
                                {"match": match.public_id})

    def test_staff_resends_to_every_member_even_if_already_sent(self):
        match = self._closed_match()
        self.assertEqual(len(mail.outbox), 2)
        self._resend(match)
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(MatchResultDelivery.objects.filter(status="sent").count(), 2)

    def test_draft_match_or_other_club_is_refused(self):
        match = self._match()                                  # sigue en borrador
        self._resend(match)
        self.assertEqual(mail.outbox, [])

    def test_opt_out_is_respected_and_non_staff_cannot_send(self):
        match = self._closed_match()
        mail.outbox.clear()
        UserPreference.objects.update_or_create(user=self.member, defaults={"match_result_email": False})
        self._resend(match)
        self.assertEqual([m.to for m in mail.outbox], [["capi@example.com"]])
        mail.outbox.clear()
        self.client.login(username="ana", password="pass-12345")
        self._resend(match)
        self.assertEqual(mail.outbox, [])
