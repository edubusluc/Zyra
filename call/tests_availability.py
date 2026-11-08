"""Tests del enlace de disponibilidad de un enfrentamiento."""
import datetime
import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Membership
from core.services import create_club
from match.models import Game, Match
from players.models import Player
from team.models import Team

from . import availability
from .models import Availability, Call

User = get_user_model()


class AvailabilityTests(TestCase):
    """Enlace, respuestas, permisos, cierre y recordatorio."""

    def setUp(self):
        """Club con capitán, un jugador con cuenta, otro sin cuenta y un enfrentamiento abierto."""
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
        self.url = reverse("availability", args=[self.match.availability_token])

    def test_new_match_gets_unpredictable_token(self):
        """Cada enfrentamiento nuevo tiene su token y no se repite."""
        other = Match.objects.create(club=self.club, local=self.team, visiting=self.match.visiting,
                                     start_date=datetime.date(2026, 10, 8))
        self.assertGreaterEqual(len(self.match.availability_token), 40)
        self.assertNotEqual(self.match.availability_token, other.availability_token)

    def test_login_required_keeps_next(self):
        """Sin sesión se redirige al login y se vuelve al enlace."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.url, response["Location"])

    def test_unknown_token_is_404(self):
        """Un token inventado no existe."""
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("availability", args=["nope"])).status_code, 404)

    def test_non_member_is_refused(self):
        """Una cuenta de fuera del equipo no ve ni responde nada."""
        stranger = User.objects.create_user("otro", "o@example.com", "pass-12345")
        self.client.force_login(stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "no pertenece a", status_code=403)
        self.assertContains(response, "Cambiar de cuenta", status_code=403)
        self.assertNotContains(response, "Ver el enfrentamiento y las respuestas", status_code=403)
        self.client.post(self.url, {"action": "answer", "answer": "yes"})
        self.assertFalse(Availability.objects.exists())

    def test_unlinked_account_is_offered_to_link_first(self):
        """Sin jugador enlazado se ofrece enlazarlo y no se puede responder antes."""
        newbie = User.objects.create_user("luis", "l@example.com", "pass-12345")
        Membership.objects.create(user=newbie, club=self.club, role=Membership.MEMBER)
        self.client.force_login(newbie)
        response = self.client.get(self.url)
        self.assertContains(response, "availability-player")
        self.client.post(self.url, {"action": "answer", "answer": "yes"})
        self.assertFalse(Availability.objects.exists())
        self.client.post(self.url, {"action": "link", "player": self.luis.public_id})
        self.luis.refresh_from_db()
        self.assertEqual(self.luis.user, newbie)
        self.client.post(self.url, {"action": "answer", "answer": "yes"})
        self.assertEqual(Availability.objects.get(player=self.luis).answer, "yes")

    def test_cannot_link_player_of_another_account(self):
        """Un jugador ya enlazado a otra cuenta no se puede reclamar."""
        newbie = User.objects.create_user("luis", "l@example.com", "pass-12345")
        Membership.objects.create(user=newbie, club=self.club, role=Membership.MEMBER)
        self.client.force_login(newbie)
        self.client.post(self.url, {"action": "link", "player": self.ana.public_id})
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.user, self.user)

    def test_answer_and_change(self):
        """El jugador responde y cambia su respuesta; el comentario solo vale con «Aún no sé»."""
        self.client.force_login(self.user)
        self.client.post(self.url, {"action": "answer", "answer": "maybe", "comment": "  Trabajo   hasta las 20  "})
        row = Availability.objects.get(player=self.ana)
        self.assertEqual((row.answer, row.comment), ("maybe", "Trabajo hasta las 20"))
        self.client.post(self.url, {"action": "answer", "answer": "no", "comment": "ignorado"})
        row.refresh_from_db()
        self.assertEqual((row.answer, row.comment), ("no", ""))
        self.assertEqual(Availability.objects.count(), 1)

    def test_invalid_answer_is_ignored(self):
        """Una respuesta que no es Sí / No / Aún no sé no se guarda."""
        self.client.force_login(self.user)
        self.client.post(self.url, {"action": "answer", "answer": "quizá"})
        self.assertFalse(Availability.objects.exists())

    def test_comment_is_truncated(self):
        """El comentario se recorta a su máximo."""
        self.client.force_login(self.user)
        self.client.post(self.url, {"action": "answer", "answer": "maybe", "comment": "x" * 500})
        self.assertEqual(len(Availability.objects.get().comment), Availability.MAX_COMMENT)

    def test_date_change_keeps_answers(self):
        """Cambiar la fecha o la hora no borra las respuestas."""
        availability.set_answer(self.match, self.ana, "yes")
        self.match.start_date = datetime.date(2026, 10, 3)
        self.match.start_time = datetime.time(19, 0)
        self.match.save()
        self.assertEqual(Availability.objects.get().answer, "yes")

    def test_closed_call_blocks_answers(self):
        """Con la convocatoria cerrada el enlace dice «cerrada» y no admite cambios."""
        availability.set_answer(self.match, self.ana, "yes")
        Call.objects.create(match=self.match, draft_mode=False)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), "Convocatoria cerrada")
        self.client.post(self.url, {"action": "answer", "answer": "no"})
        self.assertEqual(Availability.objects.get().answer, "yes")

    def test_closed_match_blocks_answers(self):
        """Con el acta cerrada tampoco se puede responder."""
        self.match.draft_mode = False
        self.match.save()
        self.assertIsNone(availability.set_answer(self.match, self.ana, "yes"))

    def test_regular_player_sees_no_board_or_other_players(self):
        """La página del jugador no enseña a nadie más ni el resumen."""
        availability.set_answer(self.match, self.luis, "no", by_manager=True)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Luis")
        self.assertNotContains(response, "Ver el enfrentamiento y las respuestas")

    def test_manager_sets_answer_and_player_cannot(self):
        """El capitán cambia la respuesta de un jugador; un jugador normal no puede."""
        set_url = reverse("availability_set", args=[self.match.public_id])
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(set_url, {"player": self.luis.public_id, "answer": "yes"}).status_code, 403)
        self.client.force_login(self.captain)
        self.client.post(set_url, {"player": self.luis.public_id, "answer": "yes"})
        row = Availability.objects.get(player=self.luis)
        self.assertEqual(row.answer, "yes")
        self.assertTrue(row.set_by_manager)

    def test_regenerate_invalidates_old_link(self):
        """Un enlace nuevo deja el anterior sin efecto."""
        old = self.match.availability_token
        self.client.force_login(self.captain)
        self.client.post(reverse("availability_regenerate", args=[self.match.public_id]))
        self.match.refresh_from_db()
        self.assertNotEqual(old, self.match.availability_token)
        self.assertEqual(self.client.get(reverse("availability", args=[old])).status_code, 404)

    def test_regenerate_requires_manager(self):
        """Un jugador normal no regenera el enlace."""
        self.client.force_login(self.user)
        response = self.client.post(reverse("availability_regenerate", args=[self.match.public_id]))
        self.assertEqual(response.status_code, 403)

    def test_board_states_and_captain_signed_up(self):
        """Los ya apuntados sin respuesta salen «apuntado por el capitán»."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.luis)
        availability.set_answer(self.match, self.ana, "yes")
        board = availability.board(self.match)
        states = {r["player"].id: r["state"] for r in board["rows"]}
        self.assertEqual(states, {self.ana.id: "yes", self.luis.id: "captain"})
        self.assertEqual(board["counts"]["captain"], 1)

    def test_yes_preselects_in_create_call(self):
        """Los «Sí» llegan marcados al crear la convocatoria, pero sin crearla."""
        availability.set_answer(self.match, self.ana, "yes")
        availability.set_answer(self.match, self.luis, "no")
        self.client.force_login(self.captain)
        response = self.client.get(reverse("create_call", args=[self.match.public_id]))
        self.assertEqual(response.context["selected_players"], [self.ana.id])
        self.assertFalse(Call.objects.exists())

    def test_ficha_shows_card_only_to_managers(self):
        """La tarjeta con el enlace y las respuestas solo la ven capitán y gestores."""
        url = reverse("call_for_match", args=[self.match.public_id])
        self.client.force_login(self.captain)
        self.assertContains(self.client.get(url), self.match.availability_token)
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(url), "availability-url")

    def test_share_text_has_link(self):
        """El texto prefabricado lleva el partido y el enlace."""
        text = availability.share_text(self.match, "https://zyra.test/x")
        self.assertIn("https://zyra.test/x", text)
        self.assertIn("Rival", text)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_reminder_only_to_pending_and_limited(self):
        """El recordatorio llega a quien no ha respondido y no se puede repetir enseguida."""
        remind = reverse("availability_remind", args=[self.match.public_id])
        self.client.force_login(self.captain)
        self.client.post(remind)
        self.assertEqual([m.to for m in mail.outbox], [["ana@example.com"]])
        self.client.post(remind)
        self.assertEqual(len(mail.outbox), 1)
        cache.clear()
        availability.set_answer(self.match, self.ana, "yes")
        self.client.post(remind)
        self.assertEqual(len(mail.outbox), 1)

    def test_reminder_requires_manager(self):
        """Un jugador normal no envía recordatorios."""
        self.client.force_login(self.user)
        response = self.client.post(reverse("availability_remind", args=[self.match.public_id]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_page_shows_vs_side_and_time(self):
        """La página enseña local VS visitante, si se juega de local y la hora."""
        self.match.start_time = datetime.time(12, 30)
        self.match.location = "Calle Mayor 1"
        self.match.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, "VS")
        self.assertContains(response, "Juegas de local")
        self.assertContains(response, "12:30")
        self.assertContains(response, "Calle Mayor 1")

    def test_after_answering_page_confirms_and_offers_change(self):
        """Tras responder se ve «Has respondido: X» y se puede cambiar la respuesta."""
        self.client.force_login(self.user)
        self.client.post(self.url, {"action": "answer", "answer": "yes"})
        response = self.client.get(self.url)
        self.assertContains(response, "Has respondido: Sí")
        self.assertContains(response, "Cambiar respuesta")
        self.assertNotContains(response, 'value="no"')
        self.assertContains(self.client.get(self.url + "?cambiar=1"), 'value="no"')

    def test_player_answers_from_the_ficha(self):
        """Desde la ficha el jugador ve los botones, responde y vuelve a la ficha."""
        ficha = reverse("call_for_match", args=[self.match.public_id])
        self.client.force_login(self.user)
        self.assertContains(self.client.get(ficha), "¿Puedes jugar?")
        response = self.client.post(reverse("availability_answer", args=[self.match.public_id]), {"answer": "yes"})
        self.assertRedirects(response, ficha)
        self.assertContains(self.client.get(ficha), "Has respondido: Sí")

    def test_board_groups_follow_yes_no_pending_no_answer(self):
        """La ventana «Ver respuestas» agrupa en Sí, No, Pendiente y Sin respuesta."""
        availability.set_answer(self.match, self.ana, "maybe")
        groups = availability.board(self.match)["groups"]
        self.assertEqual([g["key"] for g in groups], ["yes", "no", "maybe", "none"])
        self.assertEqual([r["player"].id for r in groups[2]["rows"]], [self.ana.id])
        self.assertEqual([r["player"].id for r in groups[3]["rows"]], [self.luis.id])
        self.client.force_login(self.captain)
        response = self.client.get(reverse("call_for_match", args=[self.match.public_id]))
        self.assertContains(response, "availabilityModal")
        self.assertContains(response, "Sin respuesta")

    def test_reopen_closed_call_brings_the_link_back(self):
        """Reabrir la convocatoria cerrada devuelve el enlace al capitán y deja responder otra vez."""
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.add(self.ana)
        ficha = reverse("call_for_match", args=[self.match.public_id])
        self.client.force_login(self.captain)
        self.assertNotContains(self.client.get(ficha), "availability-url")
        self.client.post(reverse("reopen_call", args=[self.match.public_id]))
        call.refresh_from_db()
        self.assertTrue(call.draft_mode)
        self.assertContains(self.client.get(ficha), "availability-url")
        self.assertTrue(availability.is_open(self.match))

    def test_reopen_call_requires_manager(self):
        """Un jugador normal no reabre convocatorias."""
        call = Call.objects.create(match=self.match, draft_mode=False)
        self.client.force_login(self.user)
        response = self.client.post(reverse("reopen_call", args=[self.match.public_id]))
        self.assertEqual(response.status_code, 403)
        call.refresh_from_db()
        self.assertFalse(call.draft_mode)

    def test_closed_call_shows_answers_read_only(self):
        """Con la convocatoria cerrada el listado de respuestas no ofrece cambiar ninguna."""
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.add(self.ana)
        self.client.force_login(self.captain)
        response = self.client.get(reverse("call_for_match", args=[self.match.public_id]))
        self.assertContains(response, "availabilityModal")
        self.assertNotContains(response, "availability_set")
        self.assertNotContains(response, "/availability/%s/set/" % self.match.public_id)
        self.assertNotContains(response, "availability-url")

    def test_answered_form_is_folded(self):
        """Tras responder, el formulario de la ficha queda plegado con «Cambiar respuesta»."""
        self.client.force_login(self.user)
        ficha = reverse("call_for_match", args=[self.match.public_id])
        self.assertNotContains(self.client.get(ficha), "Cambiar respuesta")
        availability.set_answer(self.match, self.ana, "yes")
        self.assertContains(self.client.get(ficha), "Cambiar respuesta")


class ShortLineupTests(TestCase):
    """Con la convocatoria cerrada por debajo del mínimo se alinean las parejas posibles y el resto no se presenta."""

    def setUp(self):
        self.user = User.objects.create_user("capi2", email="capi2@example.com", password="pass-12345")
        self.club = create_club("Club B", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"Jug{i:02d}", last_name="X") for i in range(7)]
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date(2026, 1, 10))
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.set(self.players)
        self.client.login(username="capi2", password="pass-12345")
        self.url = reverse("create_game", args=[self.match.public_id])

    def pairs(self, n):
        return json.dumps([{"player1Id": self.players[2 * i].id, "player2Id": self.players[2 * i + 1].id}
                           for i in range(n)])

    def test_three_pairs_with_seven_players(self):
        """7 convocados forman 3 parejas: los partidos 4 y 5 quedan como no presentados por el club."""
        self.assertContains(self.client.get(self.url), 'data-required-pairs="3"')
        self.client.post(self.url, {"ordered_games": self.pairs(3)})
        games = list(self.match.games.order_by("n_game"))
        self.assertEqual([g.n_game for g in games], [1, 2, 3, 4, 5])
        self.assertEqual([g.no_show for g in games], ["", "", "", Game.NO_SHOW_OWN, Game.NO_SHOW_OWN])

    def test_more_pairs_than_possible_rejected(self):
        """No se aceptan parejas de menos ni de más de las que se pueden formar."""
        self.client.post(self.url, {"ordered_games": self.pairs(2)})
        self.assertFalse(self.match.games.exists())

    def test_edit_moves_unfilled_games_to_the_end(self):
        """Al editar, los partidos sin pareja pasan al final como no presentados."""
        self.client.post(self.url, {"ordered_games": self.pairs(3)})
        games = list(self.match.games.order_by("n_game"))
        data = [{"gameId": g.id, "player1Id": self.players[2 * i].id, "player2Id": self.players[2 * i + 1].id}
                for i, g in enumerate(games[:3])]
        self.client.post(reverse("edit_games_match", args=[self.match.public_id]), {"ordered_games": json.dumps(data)})
        self.assertEqual(self.match.games.filter(no_show=Game.NO_SHOW_OWN).count(), 2)

    def test_lapi_has_no_pair_no_show(self):
        """La LAPI no tiene «pareja no presentada»: con menos de 6 convocados no se alinean parejas."""
        user = User.objects.create_user("capi3", email="capi3@example.com", password="pass-12345")
        club = create_club("Club L", "Sevilla", user, competition="lapi")
        rival = Team.objects.create(club=club, name="Rival", location="X", in_group=True)
        players = [Player.objects.create(club=club, name=f"L{i}", last_name="X") for i in range(4)]
        match = Match.objects.create(club=club, local=club.own_team, visiting=rival, start_date=datetime.date(2026, 1, 10))
        call = Call.objects.create(match=match, draft_mode=False)
        call.players.set(players)
        self.client.login(username="capi3", password="pass-12345")
        self.client.get(reverse("create_game", args=[match.public_id]))
        pairs = [{"player1Id": players[0].id, "player2Id": players[1].id},
                 {"player1Id": players[2].id, "player2Id": players[3].id}]
        self.client.post(reverse("create_game", args=[match.public_id]), {"ordered_games": json.dumps(pairs)})
        self.assertFalse(match.games.exists())
