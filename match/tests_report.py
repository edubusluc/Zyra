import datetime
import re
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from call.models import Call, ReportDelivery
from core.models import Membership
from core.services import create_club
from data_analyse.pairs import club_game_log
from match import advisor
from match.models import Game, Match
from match.report import build_report
from match import report_pdf
from match.report_pdf import render_report
from players.models import Player
from team.models import Team

User = get_user_model()


def pdf_pages(data):
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


class AdvisorTests(TestCase):
    def test_win_probability_follows_snp_scoring(self):
        # Ganar seguro los dos de 3 puntos y perder los de 2 = 6 puntos: empate (media victoria)
        win, expected = advisor.win_probability([1, 1, 0, 0, 0])
        self.assertAlmostEqual(win, 0.5)
        self.assertEqual(expected, 6)
        # Ganar los de 3 puntos y uno de 2 = 8 puntos: victoria
        self.assertAlmostEqual(advisor.win_probability([1, 1, 1, 0, 0])[0], 1.0)
        # Ganar solo los tres de 2 puntos = 6: empate
        self.assertAlmostEqual(advisor.win_probability([0, 0, 1, 1, 1])[0], 0.5)
        self.assertAlmostEqual(advisor.win_probability([0.5] * 5)[0], 0.5)


class ReportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass-12345", email="capitan@example.com")
        self.club = create_club("Club A", "Sevilla", self.admin)
        self.viewer = User.objects.create_user("viewer", password="pass-12345", email="viewer@example.com")
        Membership.objects.create(user=self.viewer, club=self.club, role=Membership.MEMBER)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        positions = ["Derecha", "Revés"]
        self.players = [
            Player.objects.create(club=self.club, name=f"Jugador{i}", last_name="Apellido Muy Largo",
                                  snp_score=20 + i * 3, position=positions[i % 2])
            for i in range(20)
        ]
        # Historial: dos enfrentamientos cerrados como visitante contra el mismo rival
        for day, winner in ((1, "Visitante"), (8, "Local")):
            m = Match.objects.create(club=self.club, local=self.rival, visiting=self.club.own_team,
                                     start_date=datetime.date(2025, 10, day), draft_mode=False,
                                     result="Victoria Visitante" if winner == "Visitante" else "Victoria Local",
                                     result_points="3/9" if winner == "Visitante" else "9/3")
            for n in range(1, 6):
                Game.objects.create(match=m, n_game=n, score=3 if n < 3 else 2, winner=winner, draft_mode=False,
                                    player_1_visiting=self.players[2 * n - 2], player_2_visiting=self.players[2 * n - 1])
        self.match = Match.objects.create(club=self.club, local=self.rival, visiting=self.club.own_team,
                                          start_date=datetime.date(2025, 11, 1))
        self.call = Call.objects.create(match=self.match)
        self.call.players.set(self.players)
        self.client.login(username="admin", password="pass-12345")

    def test_report_uses_venue_and_recommends_valid_lineups(self):
        report = build_report(self.call)
        self.assertEqual(report["venue_label"], "visitante")
        self.assertEqual(len(report["precedents"]), 2)
        self.assertEqual(len(report["lineups"]), 2)
        for item in report["lineups"]:
            lineup = item["lineup"]
            players = [f.id for p in lineup.pairs for f in (p.a, p.b)]
            self.assertEqual(len(set(players)), 10)                      # 10 jugadores distintos
            self.assertTrue(set(players) <= {p.id for p in self.players})  # todos convocados
            sums = [p.snp_sum for p in lineup.pairs]
            self.assertEqual(sums, sorted(sums, reverse=True))             # orden oficial SNP
            sentences = [s for s in re.split(r"(?<=[.)])\s+(?=[A-ZÁÉÍÓÚ])", item["explanation"]) if s]
            self.assertLessEqual(len(sentences), 4)
        a, b = (item["lineup"] for item in report["lineups"])
        self.assertGreaterEqual(len(b.keys - a.keys), 1)

    def test_report_with_rival_typed_by_hand(self):
        # Amistosos contra un rival fuera del grupo: no hay equipo, solo su nombre en el partido
        Match.objects.filter(club=self.club).update(local=None, rival_name="Pádel Norte",
                                                    match_type=Match.AMISTOSO)
        Match.objects.create(club=self.club, visiting=self.club.own_team, rival_name="Otro Rival",
                             start_date=datetime.date(2025, 10, 20), draft_mode=False,
                             result="Victoria Visitante", result_points="3/9")
        self.match.refresh_from_db()
        report = build_report(self.call)
        self.assertEqual(report["rival"], "Pádel Norte")
        self.assertEqual(len(report["precedents"]), 2)  # solo los de "Pádel Norte"
        self.assertTrue(render_report(report).startswith(b"%PDF"))

    def test_pdf_fits_in_two_pages_with_many_players(self):
        pdf = render_report(build_report(self.call))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(pdf_pages(pdf), 2)

    def test_pdf_fits_in_two_pages_in_worst_case(self):
        # Máximo de precedentes (4) y jugadores en racha: el espaciado no debe empujar a una tercera página
        for day in (15, 22):
            m = Match.objects.create(club=self.club, local=self.rival, visiting=self.club.own_team,
                                     start_date=datetime.date(2025, 10, day), draft_mode=False,
                                     result="Victoria Visitante", result_points="3/9")
            for n in range(1, 6):
                Game.objects.create(match=m, n_game=n, score=3 if n < 3 else 2, winner="Visitante", draft_mode=False,
                                    player_1_visiting=self.players[2 * n - 2], player_2_visiting=self.players[2 * n - 1])
        report = build_report(self.call)
        self.assertEqual(len(report["precedents"]), 4)
        self.assertTrue(report["hot"])
        self.assertEqual(pdf_pages(render_report(report)), 2)

    def big_call(self, n=30):
        """Convocatoria de ``n`` jugadores con nombres largos e historial variado (rachas, parejas, precedentes)."""
        names = ["Francisco Javier", "José Luis", "María del Carmen", "Juan Antonio", "Alejandro", "Rocío"]
        surnames = ["Fernández-Villalobos de la Torre", "Gutiérrez Domínguez", "Rodríguez Martín"]
        extra = [Player.objects.create(club=self.club, name=names[i % 6], last_name=surnames[i % 3],
                                       snp_score=30 + i, position="Derecha") for i in range(n - len(self.players))]
        squad = self.players + extra
        for k in range(10):
            winner = ("Visitante", "Local")[k % 3 == 0]
            m = Match.objects.create(club=self.club, local=self.rival, visiting=self.club.own_team,
                                     start_date=datetime.date(2025, 9, 1) + datetime.timedelta(days=3 * k),
                                     draft_mode=False, result=f"Victoria {winner}",
                                     result_points="3/9" if winner == "Visitante" else "9/3")
            for g in range(1, 6):
                Game.objects.create(match=m, n_game=g, score=3 if g < 3 else 2, winner=winner, draft_mode=False,
                                    player_1_visiting=squad[(2 * g + k) % n],
                                    player_2_visiting=squad[(2 * g + 1 + 3 * k) % n])
        self.call.players.set(squad)
        return build_report(self.call)

    def test_pdf_fits_in_two_pages_with_a_huge_call(self):
        # Antes salían 3-4 páginas con el segundo bloque casi vacío
        for n in (24, 30, 40):
            with self.subTest(called=n):
                report = self.big_call(n)
                self.assertEqual(len(report["players"]), n)  # el informe trae a todos; el PDF decide cuántos caben
                self.assertEqual(pdf_pages(render_report(report)), 2)

    def test_compact_layout_shows_every_player_when_it_fits(self):
        report = self.big_call(30)
        layouts = [layout for layout in report_pdf.LAYOUTS if report_pdf._build(report, layout)[1] <= 2]
        self.assertIsNone(layouts[0].max_players)  # los 30 en la tabla, sin «no caben»

    def test_footer_counts_the_real_number_of_pages(self):
        report = build_report(self.call)
        for item in report["lineups"]:
            item["explanation"] = "Texto muy largo. " * 600  # no cabe ni en la distribución más compacta
        totals = []
        original = report_pdf._on_page
        with mock.patch.object(report_pdf, "_on_page",
                               side_effect=lambda c, d, r, total: (totals.append(total), original(c, d, r, total))):
            pages = pdf_pages(render_report(report))
        self.assertGreater(pages, 2)
        self.assertEqual(totals[-pages:], [pages] * pages)

    def test_long_names_stay_on_one_line(self):
        player = Player(name="María del Carmen", last_name="Fernández-Villalobos de la Torre")
        width = 30 * mm
        label = report_pdf._player_label(player, width)
        self.assertTrue(label.startswith("M. D. C. "))
        self.assertLessEqual(pdfmetrics.stringWidth(label, "Archivo-Bold", 8), width)
        self.assertEqual(report_pdf._player_label(Player(name="Ana", last_name="Gil"), width), "ANA GIL")

    def test_not_enough_players(self):
        self.call.players.set(self.players[:6])
        report = build_report(self.call)
        self.assertEqual(report["lineups"], [])
        self.assertEqual(pdf_pages(render_report(report)), 2)

    def test_closing_call_emails_report_to_admins_only(self):
        self.client.post(reverse("close_call", args=[self.match.public_id]))
        self.call.refresh_from_db()
        self.assertFalse(self.call.draft_mode)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["capitan@example.com"])
        self.assertEqual(message.reply_to, ["capitan@example.com"])  # responde a quien cerró
        html, html_type = message.alternatives[0]
        self.assertEqual(html_type, "text/html")
        self.assertIn("Club A", html)
        name, content, mimetype = message.attachments[0]
        self.assertEqual(mimetype, "application/pdf")
        self.assertTrue(content.startswith(b"%PDF"))
        # Pie corporativo con el logo incrustado; el PDF sigue siendo un adjunto aparte
        self.assertIn("join.zyra@gmail.com", html)
        self.assertIn("cid:zyra-logo", html)
        parts = [p.get_content_type() for p in message.message().walk()]
        self.assertEqual(parts[:2], ["multipart/mixed", "multipart/related"])
        self.assertIn("image/png", parts)
        self.assertEqual(parts[-1], "application/pdf")

    def test_each_admin_gets_an_individual_email(self):
        second = User.objects.create_user("segundo", password="pass-12345", email="segundo@example.com")
        Membership.objects.create(user=second, club=self.club, role=Membership.ADMIN)
        self.client.post(reverse("close_call", args=[self.match.public_id]))
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["capitan@example.com", "segundo@example.com"])
        self.assertTrue(all(len(m.to) == 1 and not m.cc and not m.bcc for m in mail.outbox))

    def test_email_failure_does_not_block_closing(self):
        with mock.patch("match.views.send_call_report", side_effect=OSError("SMTP caído")):
            response = self.client.post(reverse("close_call", args=[self.match.public_id]), follow=True)
        self.call.refresh_from_db()
        self.assertFalse(self.call.draft_mode)
        self.assertContains(response, "no se pudo enviar el informe")

    def failing_smtp(self, *bad):
        """Backend de correo de pruebas que falla para las direcciones indicadas (todas si no se indica)."""
        from django.core.mail.backends.locmem import EmailBackend
        original = EmailBackend.send_messages

        def send(backend, messages):
            if any(not bad or m.to[0] in bad for m in messages):
                raise OSError("SMTP caído")
            return original(backend, messages)
        return mock.patch.object(EmailBackend, "send_messages", send)

    def make_due(self):
        ReportDelivery.objects.filter(status=ReportDelivery.PENDING).update(
            next_attempt_at=timezone.now() - datetime.timedelta(seconds=1))

    def test_failed_email_is_retried_until_it_is_sent(self):
        with self.failing_smtp():
            response = self.client.post(reverse("close_call", args=[self.match.public_id]), follow=True)
        self.assertContains(response, "se reintentará automáticamente")
        delivery = ReportDelivery.objects.get(call=self.call)
        self.assertEqual((delivery.status, delivery.attempts), (ReportDelivery.PENDING, 1))
        self.assertIn("SMTP caído", delivery.last_error)
        self.assertGreater(delivery.next_attempt_at, timezone.now())

        out = StringIO()
        call_command("send_call_reports", stdout=out)  # aún no le toca
        self.assertIn("No hay informes pendientes", out.getvalue())
        self.assertEqual(len(mail.outbox), 0)

        self.make_due()
        call_command("send_call_reports", stdout=StringIO())
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempts), (ReportDelivery.SENT, 2))
        self.assertEqual(mail.outbox[0].to, ["capitan@example.com"])
        self.assertEqual(mail.outbox[0].reply_to, ["capitan@example.com"])
        self.assertEqual(mail.outbox[0].attachments[0][2], "application/pdf")

    def test_gives_up_after_max_attempts_and_alerts(self):
        from match.notifications import MAX_ATTEMPTS
        with self.failing_smtp():
            self.client.post(reverse("close_call", args=[self.match.public_id]))
            for _ in range(MAX_ATTEMPTS - 2):
                self.make_due()
                call_command("send_call_reports", stdout=StringIO())
            self.make_due()
            with self.assertRaises(CommandError):
                call_command("send_call_reports", stdout=StringIO())
        delivery = ReportDelivery.objects.get(call=self.call)
        self.assertEqual((delivery.status, delivery.attempts), (ReportDelivery.FAILED, MAX_ATTEMPTS))
        page = self.client.get(reverse("call_for_match", args=[self.match.public_id]))
        self.assertContains(page, "no enviado")

    def test_one_bad_recipient_does_not_block_the_others(self):
        second = User.objects.create_user("segundo", password="pass-12345", email="segundo@example.com")
        Membership.objects.create(user=second, club=self.club, role=Membership.ADMIN)
        with self.failing_smtp("capitan@example.com"):
            response = self.client.post(reverse("close_call", args=[self.match.public_id]), follow=True)
        self.assertContains(response, "Informe enviado a segundo@example.com")
        self.assertContains(response, "No se pudo enviar el informe a capitan@example.com")
        self.assertEqual([m.to for m in mail.outbox], [["segundo@example.com"]])
        statuses = dict(ReportDelivery.objects.values_list("email", "status"))
        self.assertEqual(statuses, {"capitan@example.com": "pending", "segundo@example.com": "sent"})

    def test_a_delivery_is_sent_only_once(self):
        from match.notifications import deliver, queue_call_report
        deliveries = queue_call_report(self.call)
        stale = [ReportDelivery.objects.get(pk=d.pk) for d in deliveries]  # otra pasada con las mismas filas
        deliver(deliveries)
        self.assertEqual(deliver(stale), [])
        self.assertEqual(len(mail.outbox), 1)

    def test_admin_can_resend_report(self):
        self.client.post(reverse("close_call", args=[self.match.public_id]))
        self.assertEqual(len(mail.outbox), 1)
        page = self.client.get(reverse("call_for_match", args=[self.match.public_id]))
        self.assertContains(page, "Reenviar informe")
        self.assertContains(page, "enviado")
        self.client.post(reverse("resend_call_report", args=[self.match.public_id]))
        self.assertEqual(len(mail.outbox), 2)
        self.client.login(username="viewer", password="pass-12345")
        self.client.post(reverse("resend_call_report", args=[self.match.public_id]))
        self.assertEqual(len(mail.outbox), 2)

    def test_manual_download_is_admin_only(self):
        response = self.client.get(reverse("call_report", args=[self.match.public_id]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.client.login(username="viewer", password="pass-12345")
        self.assertEqual(self.client.get(reverse("call_report", args=[self.match.public_id])).status_code, 403)

    def test_report_ignores_matches_after_its_date(self):
        old = Match.objects.create(club=self.club, local=self.rival, visiting=self.club.own_team,
                                   start_date=datetime.date(2025, 9, 1))
        call = Call.objects.create(match=old)
        call.players.set(self.players)
        report = build_report(call)
        self.assertEqual(report["precedents"], [])
        self.assertTrue(all(f.played == 0 for f in report["players"]))

    def test_usage_counts_games_calls_and_last_date_of_each_called_player(self):
        # Una convocatoria cerrada anterior con dos jugadores: uno se apuntó y jugó, el otro solo se apuntó
        old = Match.objects.get(club=self.club, start_date=datetime.date(2025, 10, 8))
        Call.objects.create(match=old, draft_mode=False).players.set(self.players[:1] + self.players[15:16])
        usage = build_report(self.call)["usage"]
        self.assertEqual(set(usage), {p.id for p in self.players})  # solo los convocados
        self.assertEqual(usage[self.players[0].id], {"games": 2, "calls": 1, "last": datetime.date(2025, 10, 8)})
        self.assertEqual(usage[self.players[15].id], {"games": 0, "calls": 1, "last": None})
