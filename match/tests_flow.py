"""
Ciclo completo de un enfrentamiento por la web, como lo hace un capitán:
crear partido -> convocatoria -> editarla -> cerrarla (informe por email) -> parejas ->
resultados -> cambiar parejas -> cerrar actas -> PDF. Y borrar un partido en borrador.
"""
import datetime
import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from callLog.models import CallLog
from core.services import create_club
from match.models import Game, Match
from players.models import Player
from team.models import Team

User = get_user_model()


class MatchLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("capi", email="capi@example.com", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"Jug{i:02d}", last_name="X") for i in range(12)]
        self.client.login(username="capi", password="pass-12345")

    def _create_match(self):
        response = self.client.post(reverse("create_match"), {
            "mode": "competitivo", "match_type": Match.ENFRENTAMIENTO,
            "local": self.club.own_team.id, "visiting": self.rival.id, "start_date": "2026-10-10",
        })
        match = Match.objects.get(club=self.club)
        self.assertRedirects(response, reverse("call_for_match", args=[match.public_id]),
                             fetch_redirect_response=False)
        return match

    def test_full_match_lifecycle(self):
        match = self._create_match()
        self.assertTrue(match.draft_mode)

        # Convocatoria con 11 jugadores; al editarla se quita uno y queda en el registro
        self.client.post(reverse("create_call", args=[match.public_id]),
                         {"players": [p.id for p in self.players[:11]]})
        call = Call.objects.get(match=match)
        self.assertEqual(call.players.count(), 11)
        self.client.post(reverse("edit_call", args=[call.public_id]),
                         {"players": [p.id for p in self.players[:10]]})
        self.assertEqual(call.players.count(), 10)
        self.assertIn("JUG10", CallLog.objects.get(call=call).text)

        # Sin convocatoria cerrada no se pueden crear partidos
        self.client.post(reverse("create_game", args=[match.public_id]), {"ordered_games": "[]"})
        self.assertFalse(match.games.exists())

        # Cerrar la convocatoria envía el informe PDF al capitán
        self.client.post(reverse("close_call", args=[match.public_id]))
        call.refresh_from_db()
        self.assertFalse(call.draft_mode)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["capi@example.com"])
        self.assertTrue(any(a[0].endswith(".pdf") for a in mail.outbox[0].attachments))

        # Cinco parejas en orden: los dos primeros partidos valen 3 puntos y el resto 2
        lineup = [{"player1Id": self.players[2 * i].id, "player2Id": self.players[2 * i + 1].id} for i in range(5)]
        self.client.post(reverse("create_game", args=[match.public_id]), {"ordered_games": json.dumps(lineup)})
        games = list(match.games.order_by("n_game"))
        self.assertEqual([g.score for g in games], [3, 3, 2, 2, 2])
        self.assertEqual(games[0].player_1_local, self.players[0])

        # Con un partido sin resultado no se pueden cerrar las actas
        self.client.post(reverse("close_match", args=[match.public_id]))
        match.refresh_from_db()
        self.assertTrue(match.draft_mode)

        # Resultados: ganamos los partidos 1, 3 y 4; el 2 y el 5 los pierde el club (local)
        won = {1, 3, 4}
        for g in games:
            ours, theirs = ("6", "2") if g.n_game in won else ("2", "6")
            self.client.post(reverse("create_result", args=[g.public_id]), {
                "set1_local": ours, "set1_visiting": theirs, "set2_local": ours, "set2_visiting": theirs,
            })
        # Corregir un resultado: el 5 también lo gana el club
        self.client.post(reverse("edit_result", args=[games[4].public_id]), {
            "set1_local": "6", "set1_visiting": "4", "set2_local": "6", "set2_visiting": "4",
        })
        self.assertEqual(Game.objects.get(pk=games[4].pk).winner, "Local")

        # Cambiar el orden de las parejas: el partido 2 pasa a ser el último
        order = [games[0], games[2], games[3], games[4], games[1]]
        edited = [{"gameId": g.id, "player1Id": g.player_1_local_id, "player2Id": g.player_2_local_id} for g in order]
        self.client.post(reverse("edit_games_match", args=[match.public_id]), {"ordered_games": json.dumps(edited)})
        moved = Game.objects.get(pk=games[1].pk)
        self.assertEqual((moved.n_game, moved.score), (5, 2))
        self.assertEqual(Game.objects.get(pk=games[2].pk).score, 3)  # el antiguo 3 sube al puesto 2

        # Cerrar actas: 3 + 3 + 2 + 2 ganados por el club, 2 perdidos (el antiguo 2, ahora 5)
        self.client.post(reverse("close_match", args=[match.public_id]))
        match.refresh_from_db()
        self.assertFalse(match.draft_mode)
        self.assertEqual(match.result, "Victoria Local")
        self.assertEqual(match.result_points, "10/2")

        # Partido cerrado: no se puede borrar ni cambiar
        self.client.post(reverse("delete_match", args=[match.public_id]))
        self.assertTrue(Match.objects.filter(pk=match.pk).exists())
        self.client.post(reverse("edit_result", args=[games[0].public_id]), {
            "set1_local": "0", "set1_visiting": "6", "set2_local": "0", "set2_visiting": "6",
        })
        self.assertEqual(Game.objects.get(pk=games[0].pk).winner, "Local")

        pdf = self.client.get(reverse("call_report", args=[match.public_id]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        self.assertEqual(page.status_code, 200)

    def test_draft_match_can_be_deleted(self):
        match = self._create_match()
        confirm = self.client.get(reverse("delete_match", args=[match.public_id]))
        self.assertEqual(confirm.status_code, 200)
        self.client.post(reverse("delete_match", args=[match.public_id]))
        self.assertFalse(Match.objects.filter(pk=match.pk).exists())

    def test_match_page_offers_delete_only_to_captains_while_open(self):
        match = self._create_match()
        page = self.client.get(reverse("call_for_match", args=[match.public_id]))
        delete_url = reverse("delete_match", args=[match.public_id]) + "?desde=ficha"
        self.assertContains(page, delete_url)
        confirm = self.client.get(delete_url)
        self.assertContains(confirm, reverse("call_for_match", args=[match.public_id]))


class NoDrawTiebreakTests(TestCase):
    """Reto y Play Off no admiten empate: el 6-6 lo decide el ganador del partido 3."""

    def setUp(self):
        self.user = User.objects.create_user("capi", email="capi@example.com", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.client.login(username="capi", password="pass-12345")

    def _closed_match(self, match_type, winners):
        """Cierra un acta con los ganadores dados por partido (3,3,2,2,2 puntos): 'L' local o 'V' visitante."""
        match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                     start_date=datetime.date(2026, 10, 10), match_type=match_type)
        for n, side in enumerate(winners, start=1):
            game = Game(match=match, n_game=n, score=3 if n <= 2 else 2,
                        winner="Local" if side == "L" else "Visitante")
            game.save()
            game.results.create(set1_local=6 if side == "L" else 2, set1_visiting=2 if side == "L" else 6,
                                set2_local=6 if side == "L" else 2, set2_visiting=2 if side == "L" else 6,
                                result="Victoria Local" if side == "L" else "Victoria Visitante")
        self.client.post(reverse("close_match", args=[match.public_id]))
        match.refresh_from_db()
        return match

    def test_playoff_tie_decided_by_game_three(self):
        # Local gana 1, 2 (6 puntos) y visitante 3, 4, 5 (6 puntos): 6-6, gana el visitante (partido 3)
        match = self._closed_match(Match.PLAYOFF, "LLVVV")
        self.assertEqual(match.result_points, "6/6")
        self.assertEqual(match.result, "Victoria Visitante")

    def test_reto_tie_won_by_local_in_game_three(self):
        # Local gana 1, 3 y 4 = 3+2+2 = 7; usamos 6-6: local gana 3,4,5 y visitante 1, 2
        match = self._closed_match(Match.RETO, "VVLLL")
        self.assertEqual(match.result_points, "6/6")
        self.assertEqual(match.result, "Victoria Local")

    def test_other_types_keep_the_draw(self):
        match = self._closed_match(Match.ENFRENTAMIENTO, "LLVVV")
        self.assertEqual(match.result, "EMPATE")

    def test_tiebreak_stat_counts_for_and_against(self):
        from data_analyse.views import calculate_tiebreak_stats
        self._closed_match(Match.PLAYOFF, "VVLLL")  # a favor
        self._closed_match(Match.RETO, "LLVVV")     # en contra
        self._closed_match(Match.ENFRENTAMIENTO, "LLVVV")  # no cuenta
        team = self.club.own_team
        self.assertEqual(calculate_tiebreak_stats(None, team), {"total": 2, "for": 1, "against": 1,
                                                                      "for_pct": 50, "against_pct": 50})
        self.assertEqual(calculate_tiebreak_stats(None, team, Match.RETO), {"total": 1, "for": 0, "against": 1,
                                                                              "for_pct": 0, "against_pct": 100})

    def test_card_explains_tiebreak_only_for_no_draw_types(self):
        self._closed_match(Match.PLAYOFF, "VVLLL")
        self._closed_match(Match.ENFRENTAMIENTO, "LLVVV")
        html = self.client.get(reverse("list_match") + "?season=all").content.decode()
        self.assertEqual(html.count("z-fixture-tiebreak"), 1)  # solo el Play Off, no el enfrentamiento
        self.assertIn("la pareja 3 ganó su partido y desempató", html)
