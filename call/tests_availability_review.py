"""Tests de la revisión de usabilidad y seguridad del enlace de disponibilidad (U-01…U-11, S-01…S-08)."""
import datetime
import json
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core import sessions
from core.models import Membership
from core.services import create_club
from match.models import Game, Match, Result
from match import lineup
from players.models import Player
from team.models import Team

from . import availability
from .models import Availability, Call, ReportDelivery

User = get_user_model()
LOCMEM = override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")


class ReviewBase(TestCase):
    """Club con capitán, gestor, un jugador con cuenta y otro sin cuenta."""

    def setUp(self):
        cache.clear()
        self.captain = User.objects.create_user("capitan", "c@example.com", "pass-12345")
        self.club = create_club("Club", "Sevilla", self.captain, gender="M")
        self.team = self.club.own_team
        rival = Team.objects.create(club=self.club, name="Rival", location="Huelva")
        self.match = Match.objects.create(
            club=self.club, local=self.team, visiting=rival, start_date=datetime.date(2026, 10, 1))
        self.user = User.objects.create_user("ana", "ana@example.com", "pass-12345", first_name="Ana")
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.ana = Player.objects.create(club=self.club, team=self.team, name="Ana", last_name="Gil", user=self.user)
        self.luis = Player.objects.create(club=self.club, team=self.team, name="Luis", last_name="Paz")
        self.manager = User.objects.create_user("gestor", "g@example.com", "pass-12345")
        Membership.objects.create(user=self.manager, club=self.club, role=Membership.MANAGER)
        self.url = reverse("availability", args=[self.match.availability_token])
        self.ficha = reverse("call_for_match", args=[self.match.public_id])


class UsabilityTests(ReviewBase):
    """U-01…U-11."""

    def test_u01_tags_are_yes_no_maybe_none_in_that_order(self):
        """La tarjeta y la ventana usan los mismos cuatro contadores, con los apuntados por el capitán en «Sin respuesta»."""
        availability.set_answer(self.match, self.ana, "yes")
        call = Call.objects.create(match=self.match)
        call.players.add(self.luis)
        board = availability.board(self.match)
        self.assertEqual([t["key"] for t in board["tags"]], ["yes", "no", "maybe", "none"])
        self.assertEqual([t["n"] for t in board["tags"]], [1, 0, 0, 1 + 0 + 1 - 1 + 0 + 0] if False else [1, 0, 0, 1])
        self.client.force_login(self.captain)
        response = self.client.get(self.ficha)
        self.assertNotContains(response, "Apuntados por el capitán ·")
        self.assertNotContains(response, "No responde")

    def test_modal_is_informative_only(self):
        """La ventana «Ver respuestas» lista las respuestas sin botones para cambiarlas."""
        availability.set_answer(self.match, self.luis, "yes")
        self.client.force_login(self.captain)
        response = self.client.get(self.ficha)
        self.assertContains(response, "availabilityModal")
        self.assertNotContains(response, "z-av-set")
        self.assertNotContains(response, "/set/")

    def test_u04_reminder_is_captain_only(self):
        """Un gestor no envía el recordatorio ni ve el botón; el capitán sí."""
        remind = reverse("availability_remind", args=[self.match.public_id])
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(remind).status_code, 403)
        self.assertNotContains(self.client.get(self.ficha), "Recordar ·")
        self.client.force_login(self.captain)
        self.assertContains(self.client.get(self.ficha), "Recordar · 1")

    @LOCMEM
    def test_u04_no_pending_does_not_use_the_wait(self):
        """Sin nadie pendiente no se envía nada ni se gasta la espera."""
        availability.set_answer(self.match, self.ana, "yes")
        self.client.force_login(self.captain)
        remind = reverse("availability_remind", args=[self.match.public_id])
        response = self.client.post(remind, follow=True)
        self.assertContains(response, "Nadie tiene pendiente responder")
        self.assertFalse(availability.reminder_blocked(self.match))
        self.assertNotContains(self.client.get(self.ficha), "Recordar ·")

    @LOCMEM
    def test_u04_failed_send_releases_the_wait(self):
        """Si no sale ningún correo se puede reintentar enseguida."""
        self.client.force_login(self.captain)
        remind = reverse("availability_remind", args=[self.match.public_id])
        with mock.patch("call.availability.build_email", side_effect=RuntimeError("smtp")):
            response = self.client.post(remind, follow=True)
        self.assertContains(response, "No se pudo enviar ningún correo")
        self.assertFalse(availability.reminder_blocked(self.match))
        self.client.post(remind)
        self.assertEqual(len(mail.outbox), 1)

    @LOCMEM
    def test_u04_second_reminder_says_how_long(self):
        """El mensaje de espera dice cuántos minutos faltan."""
        self.client.force_login(self.captain)
        remind = reverse("availability_remind", args=[self.match.public_id])
        self.client.post(remind)
        response = self.client.post(remind, follow=True)
        self.assertContains(response, "Podrás enviar otro en")

    def test_u05_uses_the_shared_tip_component(self):
        """El ⓘ de la tarjeta es el de las estadísticas (botón con data-tip), no un span con title."""
        self.client.force_login(self.captain)
        response = self.client.get(self.ficha)
        self.assertContains(response, 'class="z-tip"')
        self.assertNotContains(response, "z-info")

    def test_u06_reclose_does_not_resend_unless_ticked(self):
        """Al volver a cerrar una convocatoria cuyo informe ya se envió, solo se reenvía con la casilla."""
        call = Call.objects.create(match=self.match)
        call.players.set([self.ana, self.luis] + [Player.objects.create(club=self.club, team=self.team, name=f"J{i}",
                                                                      last_name="X") for i in range(8)])
        close = reverse("close_call", args=[self.match.public_id])
        reopen = reverse("reopen_call", args=[self.match.public_id])
        self.client.force_login(self.captain)
        with mock.patch("match.views._send_report") as send:
            self.client.post(close)
            self.assertEqual(send.call_count, 1)
            ReportDelivery.objects.create(call=call, email="c@example.com", status=ReportDelivery.SENT)
            self.client.post(reopen)
            response = self.client.post(close, follow=True)
            self.assertContains(response, "El informe no se ha vuelto a enviar")
            self.assertEqual(send.call_count, 1)
            self.client.post(reopen)
            self.client.post(close, {"resend_report": "1"})
            self.assertEqual(send.call_count, 2)

    def test_u06_close_dialog_offers_the_checkbox_after_a_send(self):
        """El diálogo de cierre ofrece «Volver a enviar el informe» solo si ya se envió."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.ana)
        self.client.force_login(self.captain)
        self.assertNotContains(self.client.get(self.ficha), "Volver a enviar el informe")
        ReportDelivery.objects.create(call=call, email="c@example.com", status=ReportDelivery.SENT)
        self.assertContains(self.client.get(self.ficha), "Volver a enviar el informe")

    def test_u08_suspended_club_has_its_own_message(self):
        """Un club suspendido no dice «no perteneces»."""
        from django.utils import timezone
        self.club.suspended_at = timezone.now()
        self.club.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "suspendido", status_code=403)
        self.assertNotContains(response, "no pertenece", status_code=403)

    def test_u08_non_member_has_both_ways_out(self):
        """La cuenta de fuera ve cambiar de cuenta y pedir invitación."""
        stranger = User.objects.create_user("otro", "o@example.com", "pass-12345")
        self.client.force_login(stranger)
        response = self.client.get(self.url)
        self.assertContains(response, "Cambiar de cuenta", status_code=403)
        self.assertContains(response, "pídele una invitación", status_code=403)

    def test_u09_old_link_gets_an_explanation(self):
        """Un enlace sustituido da «Este enlace ya no es válido» con 404."""
        old = self.url
        availability.regenerate_token(self.match)
        self.client.force_login(self.user)
        response = self.client.get(old)
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Este enlace ya no es válido", status_code=404)

    def test_u09_ficha_form_does_not_use_the_token(self):
        """La ficha responde por el id del enfrentamiento: un enlace nuevo no la rompe."""
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(self.ficha), self.match.availability_token)
        availability.regenerate_token(self.match)
        self.client.post(reverse("availability_answer", args=[self.match.public_id]), {"answer": "yes"})
        self.assertEqual(Availability.objects.get(player=self.ana).answer, "yes")

    def test_u10_player_sheet_has_no_aria_pressed(self):
        """La ficha del jugador no usa aria-pressed."""
        availability.set_answer(self.match, self.ana, "yes")
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(self.ficha), "aria-pressed")

    def test_u11_reopen_log_is_translatable(self):
        """La línea del registro se escribe con el idioma activo."""
        from callLog.models import CallLog
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.add(self.ana)
        self.client.force_login(self.captain)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.client.post(reverse("reopen_call", args=[self.match.public_id]))
        self.assertIn("Call reopened by capitan", CallLog.objects.get(call=call).text)


class SecurityTests(ReviewBase):
    """S-01…S-08."""

    def _games(self, call, n, with_results=False):
        players = list(call.players.all())
        for i in range(1, n + 1):
            game = Game.objects.create(match=self.match, n_game=i, score=3, winner="Local",
                                       player_1_local=players[2 * i - 2], player_2_local=players[2 * i - 1])
            if with_results:
                Result.objects.create(game=game, set1_local="6", set1_visiting="2", set2_local="6",
                                      set2_visiting="3", set3_local="0", set3_visiting="0")

    def _closed_call(self, n):
        players = [Player.objects.create(club=self.club, team=self.team, name=f"J{i}", last_name="X") for i in range(n)]
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.set(players)
        return call, players

    def test_s01_closed_call_cannot_shrink_below_the_minimum(self):
        """Con la convocatoria cerrada no se puede dejar por debajo del mínimo."""
        call, players = self._closed_call(8)
        self.client.force_login(self.captain)
        response = self.client.post(reverse("edit_call", args=[call.public_id]),
                                    {"update_call": "1", "players": [p.id for p in players[:1]]})
        self.assertEqual(call.players.count(), 8)
        self.assertContains(response, "no puede quedarse por debajo")

    def test_s01_cannot_remove_a_lined_up_player(self):
        """Quien ya está en una pareja no se quita de la convocatoria cerrada."""
        call, players = self._closed_call(10)
        self._games(call, 5)
        self.client.force_login(self.captain)
        keep = [p.id for p in players[2:]] + [self.ana.id, self.luis.id]
        response = self.client.post(reverse("edit_call", args=[call.public_id]), {"update_call": "1", "players": keep})
        self.assertContains(response, "están en una pareja")
        self.assertEqual(set(call.players.values_list("id", flat=True)), {p.id for p in players})

    def test_s01_update_games_never_deletes_results(self):
        """Quitar una pareja con resultado no borra el resultado: se rechaza."""
        call, players = self._closed_call(10)
        self._games(call, 5, with_results=True)
        games = list(self.match.games.order_by("n_game"))
        data = [(g, players[2 * i], players[2 * i + 1]) for i, g in enumerate(games[:4])]
        with self.assertRaises(lineup.LineupError):
            lineup.update_games(self.match, data)
        self.assertEqual(Result.objects.count(), 5)

    def test_s01_short_close_is_checked_on_the_server(self):
        """``allow_short`` no basta: sin «pareja no presentada» (LAPI) o con menos de dos jugadores no se cierra."""
        user = User.objects.create_user("capl", email="capl@example.com", password="pass-12345")
        club = create_club("Club L", "Sevilla", user, competition="lapi")
        rival = Team.objects.create(club=club, name="Rival", location="X", in_group=True)
        match = Match.objects.create(club=club, local=club.own_team, visiting=rival, start_date=datetime.date(2026, 1, 10))
        call = Call.objects.create(match=match)
        call.players.set([Player.objects.create(club=club, name=f"L{i}", last_name="X") for i in range(2)])
        self.client.force_login(user)
        self.client.post(reverse("close_call", args=[match.public_id]), {"allow_short": "1"})
        call.refresh_from_db()
        self.assertTrue(call.draft_mode)
        # SNP con una sola persona tampoco.
        solo = Call.objects.create(match=self.match)
        solo.players.add(self.ana)
        self.client.force_login(self.captain)
        self.client.post(reverse("close_call", args=[self.match.public_id]), {"allow_short": "1"})
        solo.refresh_from_db()
        self.assertTrue(solo.draft_mode)

    def test_s02_captain_can_unlink_and_mute_emails(self):
        """El capitán desenlaza la cuenta y silencia los correos del club desde la ficha del jugador."""
        self.client.force_login(self.captain)
        self.client.post(reverse("toggle_player_emails", args=[self.ana.public_id]))
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.emails_muted)
        self.assertEqual(availability.pending_players(self.match), [])
        self.client.post(reverse("toggle_player_emails", args=[self.ana.public_id]))
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.emails_muted)
        self.client.post(reverse("unlink_player", args=[self.ana.public_id]))
        self.ana.refresh_from_db()
        self.assertIsNone(self.ana.user)

    def test_s02_member_cannot_mute_emails(self):
        """Un miembro no silencia los correos de nadie."""
        self.client.force_login(self.user)
        response = self.client.post(reverse("toggle_player_emails", args=[self.luis.public_id]))
        self.assertEqual(response.status_code, 403)

    def test_s03_login_remember_and_staff_sessions(self):
        """Con «Mantener la sesión» un año (renovable), sin ella hasta cerrar el navegador y el personal 12 horas."""
        login = reverse("login")
        self.client.post(login, {"username": "ana", "password": "pass-12345", "remember": "on"})
        self.assertEqual(self.client.session.get_expiry_age(), sessions.REMEMBER_SESSION_AGE)
        self.client.logout()
        self.client.post(login, {"username": "ana", "password": "pass-12345"})
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.client.logout()
        staff = User.objects.create_user("staff", "s@example.com", "pass-12345", is_staff=True)
        self.client.post(login, {"username": "staff", "password": "pass-12345", "remember": "on"})
        self.assertEqual(self.client.session.get_expiry_age(), sessions.STAFF_SESSION_AGE)
        self.client.force_login(staff)
        self.assertEqual(self.client.session.get_expiry_age(), sessions.STAFF_SESSION_AGE)

    def test_s03_logout_everywhere_keeps_only_this_session(self):
        """«Cerrar sesión en los demás dispositivos» borra las otras sesiones de la cuenta, no las de otros."""
        other_device = self.client_class()
        other_device.force_login(self.user)
        self.client.force_login(self.user)
        stranger = self.client_class()
        stranger.force_login(self.captain)
        self.assertEqual(Session.objects.count(), 3)
        self.client.post(reverse("logout_everywhere"))
        self.assertEqual(Session.objects.count(), 2)
        self.assertEqual(self.client.get(reverse("my_profile")).status_code, 200)

    @LOCMEM
    def test_s04_reminder_cannot_be_claimed_twice(self):
        """La reserva es atómica: la segunda llega tarde aunque la primera no haya terminado."""
        self.assertTrue(availability.claim_reminder(self.match))
        self.assertFalse(availability.claim_reminder(self.match))

    def test_s04_cache_failure_blocks_the_reminder(self):
        """Si la caché falla no se envía (falla cerrado)."""
        with mock.patch("call.availability.cache.add", side_effect=RuntimeError("down")):
            self.assertFalse(availability.claim_reminder(self.match))

    @LOCMEM
    def test_s04_daily_limit_per_club(self):
        """Pasados 10 recordatorios al día el club no puede enviar más."""
        self.client.force_login(self.captain)
        with override_settings(RATE_LIMITS_ENABLED=True):
            for _ in range(availability.REMINDERS_PER_CLUB_PER_DAY):
                availability.club_over_daily_limit(self.club)
            response = self.client.post(reverse("availability_remind", args=[self.match.public_id]), follow=True)
        self.assertContains(response, "muchos recordatorios")
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(availability.reminder_blocked(self.match))

    def test_s05_non_member_sees_no_match_data(self):
        """Quien no es del equipo no ve rivales, fecha ni lugar."""
        self.match.location = "Calle Secreta 7"
        self.match.save()
        stranger = User.objects.create_user("otro", "o@example.com", "pass-12345")
        self.client.force_login(stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "Calle Secreta", status_code=403)
        self.assertNotContains(response, "Rival", status_code=403)
        self.assertNotContains(response, "z-av-sep", status_code=403)

    def test_s06_page_is_not_cached(self):
        """La página del enlace lleva cabeceras que impiden guardarla."""
        self.client.force_login(self.user)
        self.assertIn("no-store", self.client.get(self.url)["Cache-Control"])

    def test_s07_comments_are_cleared_when_the_acta_closes(self):
        """Las observaciones se borran al cerrar el acta; la respuesta se conserva."""
        availability.set_answer(self.match, self.ana, "maybe", "me duele la rodilla")
        players = [Player.objects.create(club=self.club, team=self.team, name=f"K{i}", last_name="X") for i in range(10)]
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.set(players)
        self._games(call, 5, with_results=True)
        self.client.force_login(self.captain)
        self.client.post(reverse("close_match", args=[self.match.public_id]), {"confirm_future": "1"})
        self.match.refresh_from_db()
        self.assertFalse(self.match.draft_mode)
        row = Availability.objects.get(player=self.ana)
        self.assertEqual((row.answer, row.comment), ("maybe", ""))

    def test_s07_privacy_note_under_the_comment_field(self):
        """El campo de observaciones avisa de quién lo ve y de no escribir datos de salud."""
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url + "?cambiar=1"), "No escribas datos de salud")

    @override_settings(SITE_URL="https://zyrapadel.com")
    def test_s08_links_use_the_official_domain(self):
        """Con SITE_URL, el enlace de los correos y de WhatsApp es siempre el del dominio oficial."""
        from django.test import RequestFactory
        request = RequestFactory().get("/", HTTP_HOST="otro-alias.example")
        self.assertEqual(availability.link_url(request, self.match),
                         "https://zyrapadel.com" + availability.link_path(self.match))
