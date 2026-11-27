"""Tests de ``GET /api/v1/matches/<id>`` (ficha nativa de un enfrentamiento)."""
import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse

from api.tokens import issue_token
from call.models import Availability, Call
from core.models import Membership
from core.services import create_club
from match import outcomes
from match.models import Game, Match, Result
from players.models import Player
from team.models import Team

User = get_user_model()


class MatchApiTests(TestCase):
    """La ficha trae estado, fases, convocados y lo que toca a cada rol."""

    def setUp(self):
        """Capitán con club, un jugador con ficha enlazada y un enfrentamiento abierto dentro de 3 días."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123", first_name="Ana")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.user = User.objects.create_user("jug", "jug@example.com", "Clave-Segura-123")
        Membership.objects.create(user=self.user, club=self.club, role=Membership.MEMBER)
        self.me = Player.objects.create(club=self.club, name="Luis", last_name="Gil", user=self.user, in_team=True)
        self.rival = Team.objects.create(club=self.club, name="Club Este", location="X", in_group=True)
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date.today() + datetime.timedelta(days=3))
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.user_token = issue_token(self.user, "iPhone")
        self.stranger = User.objects.create_user("otro", "otro@example.com", "Clave-Segura-123")
        _, self.stranger_token = issue_token(self.stranger, "iPhone")

    def get(self, token, match=None):
        """GET de la ficha con el token indicado."""
        match = match or self.match
        return self.client.get(reverse("api_match", args=[match.public_id]), HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_match", args=[self.match.public_id])).status_code, 401)

    def test_other_account_gets_404(self):
        """Una cuenta ajena al equipo no ve el enfrentamiento."""
        self.assertEqual(self.get(self.stranger_token).status_code, 404)

    def test_captain_without_call(self):
        """Sin convocatoria el capitán ve «Por convocar» y la acción «Crear convocatoria»."""
        data = self.get(self.captain_token).json()
        self.assertEqual(data["match"]["status_label"], "Por convocar")
        self.assertEqual(data["primary"]["key"], "create_call")
        self.assertTrue(data["primary"]["enabled"])
        self.assertIsNone(data["call"])
        self.assertIsNone(data["outcome"])
        self.assertEqual([s["state"] for s in data["steps"]], ["cur", "todo", "todo", "todo"])
        self.assertTrue(data["can_manage"])

    def test_player_has_no_primary_action(self):
        """El jugador no recibe acciones de gestión y puede responder si puede jugar."""
        data = self.get(self.user_token).json()
        self.assertFalse(data["can_manage"])
        self.assertIsNone(data["primary"])
        self.assertNotIn("availability", data)
        self.assertEqual(data["me"]["state"], "no_call")

    def test_open_call_blocks_close_with_reason(self):
        """Con pocos apuntados «Cerrar convocatoria» sale desactivado y dice cuántos faltan."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.me)
        data = self.get(self.captain_token).json()
        self.assertEqual(data["match"]["status_label"], "Convocatoria abierta")
        self.assertEqual(data["primary"]["key"], "close_call")
        self.assertFalse(data["primary"]["enabled"])
        self.assertIn("Falta", data["primary"]["reason"])
        self.assertEqual(data["call"]["count"], 1)
        self.assertEqual(data["call"]["players"][0]["name"], self.me.short_name)
        self.assertEqual({k: v for k, v in data["availability"]["counts"].items() if k != "none"}, {"yes": 0, "no": 0, "maybe": 0})

    def test_my_answer_is_returned(self):
        """La respuesta del jugador y si aún puede cambiarla."""
        Availability.objects.create(match=self.match, player=self.me, answer="maybe", comment="El jueves")
        data = self.get(self.user_token).json()
        self.assertEqual(data["answer"]["value"], "maybe")
        self.assertEqual(data["answer"]["comment"], "El jueves")
        self.assertTrue(data["answer"]["can_answer"])

    def test_closed_match_has_outcome(self):
        """Con el acta cerrada sale el desenlace y no hay respuesta posible."""
        self.match.draft_mode = False
        self.match.result = outcomes.LOCAL_WIN
        self.match.result_points = "7/5"
        self.match.save()
        data = self.get(self.user_token).json()
        self.assertEqual(data["outcome"]["code"], "V")
        self.assertEqual((data["outcome"]["own"], data["outcome"]["rival"]), ("7", "5"))
        self.assertFalse(data["answer"]["can_answer"])
        self.assertEqual(data["match"]["status_label"], "Acta cerrada")

    def test_players_do_not_see_the_call_list_by_default(self):
        """Sin el ajuste del equipo, el jugador no recibe la lista de la convocatoria (sí quien gestiona)."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.me)
        self.assertIsNone(self.get(self.user_token).json()["call"])
        self.assertIsNotNone(self.get(self.captain_token).json()["call"])

    def test_games_carry_the_players_of_each_pair(self):
        """Cada pareja trae sus jugadores (nombre corto y si soy yo) para pintar los avatares."""
        partner = Player.objects.create(club=self.club, name="Ana", last_name="Gil", in_team=True)
        Game.objects.create(match=self.match, n_game=1, score=3, player_1_local=self.me, player_2_local=partner)
        game = self.get(self.user_token).json()["games"][0]
        self.assertEqual([p["me"] for p in game["players"]], [True, False])
        self.assertEqual(game["players"][1]["name"], partner.short_name)

    def test_actions_only_for_managers_and_locked_with_results(self):
        """Las acciones solo las recibe quien gestiona; con resultados guardados editar la convocatoria sale bloqueada."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.me)
        self.assertEqual(self.get(self.user_token).json()["actions"], [])
        actions = {a["key"]: a for a in self.get(self.captain_token).json()["actions"]}
        self.assertFalse(actions["edit_call"]["locked"])
        self.assertIn("edit_date", actions)
        self.assertTrue(actions["delete"]["danger"])
        game = Game.objects.create(match=self.match, n_game=1, score=3, player_1_local=self.me,
                                   player_2_local=Player.objects.create(club=self.club, name="Ana", last_name="Gil", in_team=True))
        Result.objects.create(game=game, result=outcomes.LOCAL_WIN, set1_local=6, set1_visiting=3, set2_local=6, set2_visiting=4)
        actions = {a["key"]: a for a in self.get(self.captain_token).json()["actions"]}
        self.assertTrue(actions["edit_call"]["locked"])
        self.assertTrue(actions["edit_call"]["reason"])


class CloseCallApiTests(TestCase):
    """``POST /matches/<id>/close-call``: cerrar la convocatoria desde la ficha nativa."""

    setUp = MatchApiTests.setUp

    def post(self, token, body=None, match=None):
        """POST con el token indicado."""
        match = match or self.match
        return self.client.post(reverse("api_match_close_call", args=[match.public_id]), data=body or {},
                                content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    def _call(self, n):
        """Convocatoria abierta con ``n`` jugadores."""
        call = Call.objects.create(match=self.match)
        players = [Player.objects.create(club=self.club, name=f"J{i}", last_name="X", in_team=True) for i in range(n)]
        call.players.set(players)
        return call

    def test_closes_with_enough_players(self):
        """Con los mínimos, cierra de verdad y deja la convocatoria cerrada."""
        from core.competitions import competition_for
        call = self._call(competition_for(self.match).min_call_players)
        response = self.post(self.captain_token)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["closed"])
        call.refresh_from_db()
        self.assertFalse(call.draft_mode)

    def test_player_cannot_close(self):
        """Un jugador sin gestión recibe 404 y no se cierra nada."""
        call = self._call(3)
        self.assertEqual(self.post(self.user_token).status_code, 404)
        call.refresh_from_db()
        self.assertTrue(call.draft_mode)

    def test_no_call_is_404(self):
        """Sin convocatoria no hay nada que cerrar."""
        self.assertEqual(self.post(self.captain_token).status_code, 404)

    def test_empty_call_cannot_close(self):
        """Sin apuntados: 409 y sigue abierta."""
        call = Call.objects.create(match=self.match)
        response = self.post(self.captain_token)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "cannot_close")
        call.refresh_from_db()
        self.assertTrue(call.draft_mode)

    def test_closing_twice_conflicts(self):
        """Cerrar una convocatoria ya cerrada da 409."""
        from core.competitions import competition_for
        self._call(competition_for(self.match).min_call_players)
        self.assertEqual(self.post(self.captain_token).status_code, 200)
        self.assertEqual(self.post(self.captain_token).status_code, 409)

    def test_rejects_non_boolean_flags(self):
        """Las marcas deben ser booleanos."""
        self._call(3)
        self.assertEqual(self.post(self.captain_token, {"allow_short": "si"}).status_code, 400)

    def test_primary_close_call_carries_confirmation(self):
        """«Cerrar convocatoria» trae el aviso de la web: título, texto, acción y, si procede, casilla."""
        from core.competitions import competition_for
        self._call(competition_for(self.match).min_call_players)
        confirm = self.client.get(reverse("api_match", args=[self.match.public_id]),
                                  HTTP_AUTHORIZATION=f"Bearer {self.captain_token}").json()["primary"]["confirm"]
        self.assertEqual(confirm["title"], "Cerrar la convocatoria")
        self.assertEqual(confirm["action"], "Cerrar y enviar")
        self.assertIn("Se cierra la convocatoria con", confirm["message"])
        self.assertFalse(confirm["allow_short"])
        self.assertIsNone(confirm["check"])


class AvailabilityLinkApiTests(TestCase):
    """Respuestas antes de crear la convocatoria, enlace para compartir y recordatorio por correo."""

    setUp = MatchApiTests.setUp
    get = MatchApiTests.get

    def auth(self, token):
        """Cabecera de autenticación con el token indicado."""
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_responses_are_visible_before_the_call_exists(self):
        """Sin convocatoria creada, quien gestiona ya ve quién ha respondido qué."""
        Availability.objects.create(match=self.match, player=self.me, answer="yes")
        data = self.get(self.captain_token).json()
        self.assertIsNone(data["call"])
        groups = {g["key"]: g for g in data["availability"]["groups"]}
        self.assertEqual([p["name"] for p in groups["yes"]["players"]], [self.me.short_name])
        self.assertEqual(data["availability"]["counts"]["yes"], 1)
        self.assertTrue(data["availability"]["can_remind"])
        self.assertNotIn("availability", self.get(self.user_token).json())

    def test_link_for_managers_only(self):
        """El enlace y su texto salen para capitán y gestores; un jugador recibe 404."""
        url = reverse("api_match_availability_link", args=[self.match.public_id])
        data = self.client.get(url, **self.auth(self.captain_token)).json()
        self.assertIn(self.match.availability_token, data["url"])
        self.assertIn(data["url"], data["text"])
        self.assertTrue(data["whatsapp_url"].startswith("https://wa.me/?text="))
        self.assertEqual(self.client.get(url, **self.auth(self.user_token)).status_code, 404)

    def test_remind_only_for_the_captain_and_once_per_hour(self):
        """El capitán recuerda por correo a quien no ha respondido; el segundo intento espera una hora."""
        url = reverse("api_match_availability_remind", args=[self.match.public_id])
        self.assertEqual(self.client.post(url, **self.auth(self.user_token)).status_code, 404)
        first = self.client.post(url, **self.auth(self.captain_token))
        self.assertEqual(first.status_code, 200)
        self.assertGreaterEqual(first.json()["sent"], 1)
        again = self.client.post(url, **self.auth(self.captain_token))
        self.assertEqual((again.status_code, again.json()["error"]), (409, "cooldown"))
        self.assertGreaterEqual(again.json()["minutes"], 1)

    def test_remind_is_refused_to_managers_and_when_closed(self):
        """Un gestor (no capitán) no puede recordar y con la convocatoria cerrada tampoco."""
        manager = User.objects.create_user("gest", "gest@example.com", "Clave-Segura-123")
        Membership.objects.create(user=manager, club=self.club, role=Membership.MANAGER)
        _, token = issue_token(manager, "iPhone")
        url = reverse("api_match_availability_remind", args=[self.match.public_id])
        self.assertEqual(self.client.post(url, **self.auth(token)).status_code, 403)
        Call.objects.create(match=self.match, draft_mode=False)
        self.assertEqual(self.client.post(url, **self.auth(self.captain_token)).json()["error"], "closed")


class MatchCallApiTests(TestCase):
    """``GET`` y ``PUT /matches/<id>/call``: seleccionar jugadores al crear y editar la convocatoria."""

    setUp = MatchApiTests.setUp

    def url(self, match=None):
        """Ruta de la convocatoria del enfrentamiento."""
        return reverse("api_match_call", args=[(match or self.match).public_id])

    def auth(self, token):
        """Cabecera de autenticación con el token indicado."""
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def put(self, token, body, match=None):
        """PUT JSON con el token indicado."""
        return self.client.put(self.url(match), body, content_type="application/json", **self.auth(token))

    def test_players_only_for_managers(self):
        """Un jugador recibe 404 y quien gestiona la lista de seleccionables."""
        self.assertEqual(self.client.get(self.url(), **self.auth(self.user_token)).status_code, 404)
        data = self.client.get(self.url(), **self.auth(self.captain_token)).json()
        self.assertFalse(data["exists"])
        self.assertIn(str(self.me.public_id), [p["id"] for p in data["players"]])
        self.assertIsNone(data["locked"])

    def test_yes_answers_arrive_selected_before_the_call_exists(self):
        """Sin convocatoria, los «Sí» del enlace llegan marcados y cada jugador trae su respuesta."""
        Availability.objects.create(match=self.match, player=self.me, answer="yes")
        data = self.client.get(self.url(), **self.auth(self.captain_token)).json()
        mine = next(p for p in data["players"] if p["id"] == str(self.me.public_id))
        self.assertEqual((mine["answer"], mine["selected"]), ("yes", True))

    def test_create_and_edit_the_call(self):
        """Crear con una selección; volver a enviar cambia los jugadores en la misma convocatoria."""
        other = Player.objects.create(club=self.club, name="Ana", last_name="Gil", in_team=True)
        first = self.put(self.captain_token, {"players": [str(self.me.public_id)]})
        self.assertEqual((first.status_code, first.json()), (200, {"created": True, "count": 1}))
        second = self.put(self.captain_token, {"players": [str(self.me.public_id), str(other.public_id)]})
        self.assertEqual(second.json(), {"created": False, "count": 2})
        self.assertEqual(Call.objects.get(match=self.match).players.count(), 2)

    def test_rejects_empty_unknown_and_foreign_players(self):
        """Selección vacía, ids desconocidos o de otro club: error y no se crea nada."""
        self.assertEqual(self.put(self.captain_token, {"players": []}).json()["error"], "invalid_call")
        self.assertEqual(self.put(self.captain_token, {"players": ["nope"]}).status_code, 400)
        self.assertEqual(self.put(self.captain_token, {"players": "x"}).status_code, 400)
        self.assertFalse(Call.objects.filter(match=self.match).exists())

    def test_players_cannot_change_the_call(self):
        """Un jugador recibe 404 al enviar."""
        self.assertEqual(self.put(self.user_token, {"players": [str(self.me.public_id)]}).status_code, 404)

    def test_locked_with_results_or_closed_match(self):
        """Con resultados guardados o el acta cerrada no se puede cambiar la convocatoria."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.me)
        game = Game.objects.create(match=self.match, n_game=1, score=3, player_1_local=self.me,
                                   player_2_local=Player.objects.create(club=self.club, name="Ana", last_name="Gil", in_team=True))
        Result.objects.create(game=game, result=outcomes.LOCAL_WIN, set1_local=6, set1_visiting=3, set2_local=6, set2_visiting=4)
        got = self.client.get(self.url(), **self.auth(self.captain_token)).json()
        self.assertTrue(got["locked"])
        response = self.put(self.captain_token, {"players": [str(self.me.public_id)]})
        self.assertEqual((response.status_code, response.json()["error"]), (409, "locked"))


class MatchScheduleApiTests(TestCase):
    """``PATCH /matches/<id>``: cambiar fecha, hora y sede."""

    setUp = MatchApiTests.setUp

    def url(self):
        """Ruta de la ficha."""
        return reverse("api_match", args=[self.match.public_id])

    def patch(self, token, body):
        """PATCH JSON con el token indicado."""
        return self.client.patch(self.url(), body, content_type="application/json",
                                 HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_only_managers(self):
        """Un jugador recibe 404."""
        self.assertEqual(self.patch(self.user_token, {"date": "2030-01-05"}).status_code, 404)

    def test_changes_date_time_and_location(self):
        """Cambia los tres campos y devuelve lo guardado."""
        response = self.patch(self.captain_token, {"date": "2030-01-05", "time": "10:30", "location": "  Pádel  Sur "})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data["date"], data["time"], data["location"]), ("2030-01-05", "10:30", "Pádel Sur"))
        self.match.refresh_from_db()
        self.assertEqual(self.match.start_date.isoformat(), "2030-01-05")

    def test_omitted_fields_are_kept_and_null_clears_time(self):
        """Sin campo se conserva y ``time`` nulo borra la hora."""
        self.patch(self.captain_token, {"time": "09:00"})
        kept = self.patch(self.captain_token, {"date": "2030-02-01"}).json()
        self.assertEqual(kept["time"], "09:00")
        self.assertIsNone(self.patch(self.captain_token, {"time": None}).json()["time"])

    def test_invalid_date_is_a_validation_error(self):
        """Una fecha mala da 400 con el motivo por campo."""
        response = self.patch(self.captain_token, {"date": "mañana"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("date", response.json()["fields"])

    def test_closed_acta_is_locked(self):
        """Con el acta cerrada, 409 ``locked``."""
        self.match.draft_mode = False
        self.match.save()
        response = self.patch(self.captain_token, {"date": "2030-01-05"})
        self.assertEqual((response.status_code, response.json()["error"]), (409, "locked"))


class MatchReportApiTests(TestCase):
    """``GET /matches/<id>/report.pdf``: informe en PDF para quien gestiona."""

    setUp = MatchApiTests.setUp

    def get(self, token):
        """GET con el token indicado."""
        url = reverse("api_match_report", args=[self.match.public_id])
        return self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_needs_a_call_and_a_manager(self):
        """Sin convocatoria o siendo jugador: 404."""
        self.assertEqual(self.get(self.captain_token).status_code, 404)
        Call.objects.create(match=self.match)
        self.assertEqual(self.get(self.user_token).status_code, 404)

    def test_returns_the_pdf(self):
        """El capitán recibe un PDF con el nombre del informe."""
        call = Call.objects.create(match=self.match)
        call.players.add(self.me)
        response = self.get(self.captain_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(".pdf", response["Content-Disposition"])


class MatchResultImageApiTests(TestCase):
    """``GET /matches/<id>/result.jpg``: imagen del resultado para compartir."""

    setUp = MatchApiTests.setUp

    def get(self, token):
        """GET con el token indicado."""
        url = reverse("api_match_result_image", args=[self.match.public_id])
        return self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_needs_a_manager_and_a_closed_record(self):
        """Un jugador recibe 404; con el acta abierta, también el capitán."""
        self.assertEqual(self.get(self.user_token).status_code, 404)
        self.match.draft_mode = True
        self.match.save()
        self.assertEqual(self.get(self.captain_token).status_code, 404)

    def test_returns_the_jpeg(self):
        """Con el acta cerrada el capitán recibe un JPEG."""
        self.match.draft_mode = False
        self.match.save()
        response = self.get(self.captain_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertTrue(response.content.startswith(b"\xff\xd8"))


class MatchesListApiTests(TestCase):
    """``GET /matches``: la lista de Partidos con grupos, resumen, filtros y paginación."""

    setUp = MatchApiTests.setUp

    def auth(self, token):
        """Cabecera de autenticación con el token indicado."""
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def list(self, token=None, **params):
        """GET de la lista con los parámetros indicados."""
        return self.client.get(reverse("api_matches"), params, **self.auth(token or self.captain_token))

    def closed(self, days_ago, points="7/5", result=outcomes.LOCAL_WIN, **extra):
        """Un enfrentamiento ya cerrado hace ``days_ago`` días."""
        return Match.objects.create(
            club=self.club, local=self.club.own_team, visiting=self.rival, draft_mode=False, result=result,
            result_points=points, start_date=datetime.date.today() - datetime.timedelta(days=days_ago), **extra)

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_matches")).status_code, 401)

    def test_groups_summary_and_order(self):
        """Acción (capitán, fecha pasada), próximos y jugados, con el marcador propio y el resumen."""
        late = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                    start_date=datetime.date.today() - datetime.timedelta(days=2))
        self.closed(10)
        data = self.list().json()
        self.assertEqual([m["group"] for m in data["matches"]], ["action", "upcoming", "played"])
        self.assertEqual(data["matches"][0]["id"], str(late.public_id))
        played = data["matches"][2]
        self.assertEqual((played["outcome"], played["own_points"], played["rival_points"]), ("V", "7", "5"))
        self.assertEqual(data["summary"], {"played": 1, "won": 1, "drawn": 0, "lost": 0, "pending": 2})
        self.assertTrue(data["can_create"])
        self.assertFalse(any(m["has_lineup"] for m in data["matches"]))

    def test_has_lineup_when_open_with_pairs(self):
        """``has_lineup`` es cierto con el acta abierta y parejas alineadas."""
        Game.objects.create(match=self.match, n_game=1)
        self.assertTrue(self.list().json()["matches"][0]["has_lineup"])

    def test_player_sees_no_action_group(self):
        """Un jugador ve los abiertos como próximos y no puede crear."""
        data = self.list(self.user_token).json()
        self.assertEqual([m["group"] for m in data["matches"]], ["upcoming"])
        self.assertFalse(data["can_create"])
        self.assertFalse(data["matches"][0]["can_manage"])

    def test_stranger_sees_nothing_and_foreign_team_is_404(self):
        """Una cuenta sin equipos recibe la lista vacía; pedir un equipo ajeno, 404."""
        self.assertEqual(self.list(self.stranger_token).json()["matches"], [])
        self.assertEqual(self.list(self.stranger_token, team=str(self.club.public_id)).status_code, 404)

    def test_filters_by_rival_search_and_type(self):
        """``rival``, ``q`` y ``match_type`` acotan la lista; un rival desconocido se ignora."""
        other = Team.objects.create(club=self.club, name="Club Oeste", location="Y", in_group=True)
        friendly = Match.objects.create(club=self.club, local=self.club.own_team, visiting=other,
                                        match_type=Match.AMISTOSO,
                                        start_date=datetime.date.today() + datetime.timedelta(days=1))
        self.assertEqual(len(self.list().json()["matches"]), 2)
        self.assertEqual([m["id"] for m in self.list(rival="Club Oeste").json()["matches"]], [str(friendly.public_id)])
        self.assertEqual(len(self.list(rival="Nadie").json()["matches"]), 2)
        self.assertEqual([m["id"] for m in self.list(q="oeste").json()["matches"]], [str(friendly.public_id)])
        self.assertEqual([m["id"] for m in self.list(match_type="amistoso").json()["matches"]], [str(friendly.public_id)])
        self.assertEqual([m["id"] for m in self.list(match_type="competitivo").json()["matches"]], [str(self.match.public_id)])

    def test_far_matches_are_hidden_unless_asked(self):
        """Los abiertos a más de 14 días se resumen en ``hidden_far``; ``all=1`` los muestra."""
        Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                             start_date=datetime.date.today() + datetime.timedelta(days=60))
        data = self.list().json()
        self.assertEqual((len(data["matches"]), data["hidden_far"]), (1, 1))
        self.assertEqual(len(self.list(all=1).json()["matches"]), 2)

    def test_pagination(self):
        """De 12 en 12; una página fuera de rango devuelve la última."""
        for i in range(14):
            self.closed(20 + i)
        data = self.list().json()
        self.assertEqual((len(data["matches"]), data["pages"], data["page"]), (12, 2, 1))
        self.assertEqual(self.list(page=9).json()["page"], 2)


class MatchesCalendarApiTests(TestCase):
    """``GET /matches/calendar``: los enfrentamientos de un mes agrupados por día."""

    setUp = MatchApiTests.setUp

    def get(self, token=None, **params):
        """GET del calendario con el token del capitán por defecto."""
        return self.client.get(reverse("api_matches_calendar"), params,
                               HTTP_AUTHORIZATION=f"Bearer {token or self.captain_token}")

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_matches_calendar")).status_code, 401)

    def test_groups_the_month_by_day_in_time_order(self):
        """Solo salen los días del mes con partidos, y cada día ordena por hora."""
        day = datetime.date(2027, 3, 14)
        late = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival, start_date=day,
                                    start_time=datetime.time(20, 0))
        early = Match.objects.create(club=self.club, local=self.rival, visiting=self.club.own_team, start_date=day,
                                     start_time=datetime.time(10, 0))
        Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                             start_date=datetime.date(2027, 4, 2))
        data = self.get(month="2027-03").json()
        self.assertEqual((data["month"], data["prev"], data["next"]), ("2027-03", "2027-02", "2027-04"))
        self.assertEqual([d["date"] for d in data["days"]], ["2027-03-14"])
        self.assertEqual([m["id"] for m in data["days"][0]["matches"]], [str(early.public_id), str(late.public_id)])
        self.assertFalse(data["days"][0]["matches"][0]["own_is_local"])

    def test_invalid_month_falls_back_to_current(self):
        """Un mes mal escrito no falla: devuelve el actual."""
        data = self.get(month="xx").json()
        self.assertTrue(data["is_current"])

    def test_stranger_sees_nothing_and_foreign_team_is_404(self):
        """Una cuenta sin equipos recibe días vacíos; pedir un equipo ajeno, 404."""
        self.assertEqual(self.get(self.stranger_token).json()["days"], [])
        self.assertEqual(self.get(self.stranger_token, team=str(self.club.public_id)).status_code, 404)


class CreateMatchApiTests(TestCase):
    """``GET /matches/new`` y ``POST /matches``: crear un enfrentamiento con las reglas de ``MatchForm``."""

    setUp = MatchApiTests.setUp

    def auth(self, token):
        """Cabecera de autenticación con el token indicado."""
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def post(self, body, token=None):
        """POST de un enfrentamiento nuevo en el equipo del capitán."""
        body = {"team": str(self.club.public_id), **body}
        return self.client.post(reverse("api_matches"), body, content_type="application/json",
                                **self.auth(token or self.captain_token))

    def test_lists_managed_teams_and_options(self):
        """Sin ``team`` lista los equipos gestionados; con ``team`` trae reglas, rivales y valores por defecto."""
        data = self.client.get(reverse("api_match_new"), **self.auth(self.captain_token)).json()
        self.assertEqual([t["id"] for t in data["teams"]], [str(self.club.public_id)])
        url = reverse("api_match_new") + f"?team={self.club.public_id}"
        options = self.client.get(url, **self.auth(self.captain_token)).json()
        self.assertEqual([r["name"] for r in options["rivals"]], ["Club Este"])
        self.assertIn("match_types", options["rules"])
        self.assertEqual(options["defaults"]["own_team"], self.club.own_team.name)

    def test_players_cannot_create(self):
        """Un jugador (no gestiona) recibe 403 al pedir el equipo y al crear; un equipo ajeno, 404."""
        url = reverse("api_match_new") + f"?team={self.club.public_id}"
        self.assertEqual(self.client.get(url, **self.auth(self.user_token)).status_code, 403)
        self.assertEqual(self.post({"rival": str(self.rival.public_id)}, self.user_token).status_code, 403)
        self.assertEqual(self.post({"rival": str(self.rival.public_id)}, self.stranger_token).status_code, 404)

    def test_creates_a_match_playing_away(self):
        """Rival del grupo y «fuera»: el rival es local y nuestro equipo visitante."""
        day = (datetime.date.today() + datetime.timedelta(days=9)).isoformat()
        response = self.post({"mode": "competitivo", "own_side": "visiting", "rival": str(self.rival.public_id),
                              "start_date": day, "start_time": "20:30", "location": "Pista 1"})
        self.assertEqual(response.status_code, 201, response.content)
        match = Match.objects.get(public_id=response.json()["id"])
        self.assertEqual((match.local, match.visiting), (self.rival, self.club.own_team))
        self.assertEqual(match.location, "Pista 1")

    def test_missing_rival_returns_field_errors(self):
        """Sin rival: 400 ``invalid_match`` con el error en ``fields``."""
        day = (datetime.date.today() + datetime.timedelta(days=9)).isoformat()
        response = self.post({"start_date": day})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_match")
        self.assertIn("rival", response.json()["fields"])

    def test_friendly_with_similar_rival_asks_to_choose(self):
        """Amistoso con un rival escrito parecido a uno existente: devuelve ``rival_matches`` hasta que se elige."""
        day = (datetime.date.today() + datetime.timedelta(days=9)).isoformat()
        body = {"mode": "amistoso", "rival_name": "Club Este", "start_date": day}
        response = self.post(body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["rival_matches"][0]["id"], str(self.rival.public_id))
        body["rival_link"] = str(self.rival.public_id)
        self.assertEqual(self.post(body).status_code, 201)


class MatchLineupApiTests(TestCase):
    """``GET`` y ``PUT /matches/<id>/lineup``: alinear y editar las parejas."""

    setUp = MatchApiTests.setUp

    def url(self):
        """Ruta de la alineación."""
        return reverse("api_match_lineup", args=[self.match.public_id])

    def auth(self, token):
        """Cabecera de autenticación con el token indicado."""
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def closed_call(self, closed=True):
        """Convocatoria con diez jugadores (el mínimo de la SNP), cerrada o no; devuelve sus jugadores."""
        players = [self.me] + [Player.objects.create(club=self.club, name=f"J{i}", last_name="X", in_team=True,
                                                     snp_score=1000 - i) for i in range(9)]
        call = Call.objects.create(match=self.match, draft_mode=not closed)
        call.players.set(players)
        return players

    def pairs(self, players):
        """Cinco parejas con los jugadores en orden."""
        ids = [str(p.public_id) for p in players]
        return [ids[i:i + 2] for i in range(0, 10, 2)]

    def put(self, token, body):
        """PUT JSON con el token indicado."""
        return self.client.put(self.url(), body, content_type="application/json", **self.auth(token))

    def test_only_managers_with_a_call(self):
        """Jugador o sin convocatoria: 404."""
        self.assertEqual(self.client.get(self.url(), **self.auth(self.captain_token)).status_code, 404)
        self.closed_call()
        self.assertEqual(self.client.get(self.url(), **self.auth(self.user_token)).status_code, 404)

    def test_open_call_is_locked(self):
        """Con la convocatoria sin cerrar, ``locked`` trae el motivo y no hay sugerencias."""
        self.closed_call(closed=False)
        data = self.client.get(self.url(), **self.auth(self.captain_token)).json()
        self.assertIn("Cierra la convocatoria", data["locked"])
        self.assertEqual(data["suggestions"], [])
        self.assertEqual(self.put(self.captain_token, {"pairs": []}).status_code, 409)

    def test_create_and_edit_the_lineup(self):
        """Crear las cinco parejas y luego intercambiar dos jugadores."""
        players = self.closed_call()
        data = self.client.get(self.url(), **self.auth(self.captain_token)).json()
        self.assertEqual((data["exists"], data["pairs"], data["points"], data["ordered"]), (False, 5, [3, 3, 2, 2, 2], True))
        pairs = self.pairs(players)
        first = self.put(self.captain_token, {"pairs": pairs})
        self.assertEqual((first.status_code, first.json()), (200, {"created": True, "count": 5}))
        swapped = [[pairs[0][0], pairs[1][0]], [pairs[1][1], pairs[0][1]]] + pairs[2:]
        second = self.put(self.captain_token, {"pairs": swapped})
        self.assertEqual((second.status_code, second.json()["created"]), (200, False))
        games = self.client.get(self.url(), **self.auth(self.captain_token)).json()["games"]
        self.assertEqual([g["players"] for g in games][:2], swapped[:2])

    def test_rejects_repeated_players_and_incomplete_lineups(self):
        """Un jugador repetido o faltan parejas: 409 ``invalid_lineup``."""
        players = self.closed_call()
        pairs = self.pairs(players)
        repeated = [pairs[0], [pairs[0][0], pairs[1][1]]] + pairs[2:]
        self.assertEqual(self.put(self.captain_token, {"pairs": repeated}).json()["error"], "invalid_lineup")
        self.assertEqual(self.put(self.captain_token, {"pairs": pairs[:3]}).json()["error"], "invalid_lineup")
        self.assertEqual(self.put(self.captain_token, {"pairs": "x"}).status_code, 400)

    def test_closed_acta_is_locked(self):
        """Con el acta cerrada, 409 ``locked``."""
        players = self.closed_call()
        self.match.draft_mode = False
        self.match.save()
        self.assertEqual(self.put(self.captain_token, {"pairs": self.pairs(players)}).json()["error"], "locked")


class MatchResultsApiTests(TestCase):
    """Resultados por partido y cierre del acta de la app nativa."""

    setUp = MatchApiTests.setUp

    def auth(self, token):
        """Cabecera de autenticación con el token indicado."""
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def lined_up(self):
        """Convocatoria cerrada con diez jugadores y cinco parejas alineadas; devuelve los partidos."""
        players = [self.me] + [Player.objects.create(club=self.club, name=f"J{i}", last_name="X", in_team=True,
                                                     snp_score=1000 - i) for i in range(9)]
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.set(players)
        ids = [str(p.public_id) for p in players]
        self.client.put(reverse("api_match_lineup", args=[self.match.public_id]),
                        {"pairs": [ids[i:i + 2] for i in range(0, 10, 2)]}, content_type="application/json",
                        **self.auth(self.captain_token))
        return list(self.match.games.order_by("n_game"))

    def result_url(self, game):
        """Ruta del resultado de un partido."""
        return reverse("api_game_result", args=[self.match.public_id, game.public_id])

    def put(self, game, body, token=None):
        """PUT del resultado de un partido."""
        return self.client.put(self.result_url(game), body, content_type="application/json",
                               **self.auth(token or self.captain_token))

    def test_only_managers(self):
        """Un jugador recibe 404 en la lista y al poner un resultado."""
        games = self.lined_up()
        url = reverse("api_match_results", args=[self.match.public_id])
        self.assertEqual(self.client.get(url, **self.auth(self.user_token)).status_code, 404)
        self.assertEqual(self.put(games[0], {"sets": [[6, 3], [6, 4]]}, self.user_token).status_code, 404)

    def test_put_get_and_delete_a_result(self):
        """Poner un resultado (sets desde nuestro lado), verlo en la lista y borrarlo."""
        games = self.lined_up()
        response = self.put(games[0], {"sets": [[6, 3], [4, 6], [7, 5]]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["state"], response.json()["result"]["sets"]), ("win", [[6, 3], [4, 6], [7, 5]]))
        data = self.client.get(reverse("api_match_results", args=[self.match.public_id]), **self.auth(self.captain_token)).json()
        self.assertEqual((data["missing"], data["can_close"]), ([2, 3, 4, 5], False))
        self.assertEqual(data["games"][0]["points"], 3)
        deleted = self.client.delete(self.result_url(games[0]), **self.auth(self.captain_token)).json()
        self.assertEqual((deleted["state"], deleted["result"]), ("", None))

    def test_invalid_sets_are_a_validation_error(self):
        """Unos sets imposibles dan 400 con el motivo."""
        games = self.lined_up()
        response = self.put(games[0], {"sets": [[6, 6]]})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["fields"]["sets"])
        self.assertEqual(self.put(games[0], {"sets": "x"}).status_code, 400)

    def test_close_needs_all_results_and_confirmation_for_future_dates(self):
        """Sin resultados 409 ``cannot_close``; con todos, la fecha futura pide ``confirm_future``."""
        games = self.lined_up()
        url = reverse("api_match_close", args=[self.match.public_id])
        post = lambda body=None: self.client.post(url, body or {}, content_type="application/json",
                                                  **self.auth(self.captain_token))
        self.assertEqual(post().json()["error"], "cannot_close")
        for game in games:
            r = self.put(game, {"sets": [[6, 3], [6, 4]]}); self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(post().json()["error"], "future_date")
        done = post({"confirm_future": True})
        self.assertEqual((done.status_code, done.json()["closed"]), (200, True))
        self.match.refresh_from_db()
        self.assertFalse(self.match.draft_mode)
        self.assertEqual(self.put(games[0], {"sets": [[6, 0], [6, 0]]}).json()["error"], "locked")


class MatchLineupImageApiTests(TestCase):
    """``GET /matches/<id>/lineup.jpg``: imagen de la alineación para compartir."""

    setUp = MatchApiTests.setUp
    url = MatchLineupApiTests.url
    auth = MatchLineupApiTests.auth
    closed_call = MatchLineupApiTests.closed_call
    pairs = MatchLineupApiTests.pairs
    put = MatchLineupApiTests.put

    def image(self, token):
        """GET de la imagen con el token indicado."""
        url = reverse("api_match_lineup_image", args=[self.match.public_id])
        return self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_needs_a_manager_and_a_lineup(self):
        """Sin parejas alineadas, 404 incluso para el capitán; un jugador, 404."""
        self.assertEqual(self.image(self.captain_token).status_code, 404)
        players = self.closed_call()
        self.put(self.captain_token, {"pairs": self.pairs(players)})
        self.assertEqual(self.image(self.user_token).status_code, 404)

    def test_returns_the_jpeg_while_open(self):
        """Con las parejas alineadas y el acta abierta, el capitán recibe un JPEG."""
        players = self.closed_call()
        self.assertEqual(self.put(self.captain_token, {"pairs": self.pairs(players)}).status_code, 200)
        response = self.image(self.captain_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertTrue(response.content.startswith(b"\xff\xd8"))
        self.match.draft_mode = False
        self.match.save()
        self.assertEqual(self.image(self.captain_token).status_code, 404)


class MatchActionsApiTests(TestCase):
    """Acciones de la hoja «Acciones» hechas dentro de la app: reabrir, reenviar, no presentado y eliminar."""

    setUp = MatchApiTests.setUp

    def post(self, name, token=None, body=None, match=None):
        """POST a la acción ``name`` con el token del capitán por defecto."""
        match = match or self.match
        return self.client.post(reverse(name, args=[match.public_id]), data=body or {}, content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {token or self.captain_token}")

    def get(self, token):
        """GET de la ficha."""
        return self.client.get(reverse("api_match", args=[self.match.public_id]), HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_player_gets_404_everywhere(self):
        """Quien no gestiona recibe 404 y no cambia nada."""
        for name in ("api_match_reopen_call", "api_match_reopen", "api_match_resend_report", "api_match_no_show",
                     "api_match_undo_no_show", "api_match_delete"):
            self.assertEqual(self.post(name, self.user_token, {"side": "own"}).status_code, 404, name)
        self.assertTrue(Match.objects.filter(pk=self.match.pk).exists())

    def test_delete_open_match(self):
        """Un enfrentamiento abierto se elimina."""
        self.assertEqual(self.post("api_match_delete").json(), {"deleted": True})
        self.assertFalse(Match.objects.filter(pk=self.match.pk).exists())

    def test_delete_closed_match_is_refused(self):
        """Con el acta cerrada no se elimina."""
        Match.objects.filter(pk=self.match.pk).update(draft_mode=False)
        response = self.post("api_match_delete")
        self.assertEqual((response.status_code, response.json()["error"]), (409, "cannot_delete"))

    def test_manager_cannot_delete_reopened_match(self):
        """El gestor no elimina un enfrentamiento que ya tuvo el acta cerrada; el capitán sí."""
        manager = User.objects.create_user("gest", "gest@example.com", "Clave-Segura-123")
        Membership.objects.create(user=manager, club=self.club, role=Membership.MANAGER)
        _, token = issue_token(manager, "iPhone")
        Match.objects.filter(pk=self.match.pk).update(was_closed=True)
        self.assertEqual(self.post("api_match_delete", token).status_code, 403)
        self.assertEqual(self.post("api_match_delete").status_code, 200)

    def test_reopen_match(self):
        """Reabrir el acta la deja abierta y anota que estuvo cerrada."""
        Match.objects.filter(pk=self.match.pk).update(draft_mode=False)
        self.assertEqual(self.post("api_match_reopen").status_code, 200)
        self.match.refresh_from_db()
        self.assertTrue(self.match.draft_mode)
        self.assertTrue(self.match.was_closed)
        self.assertEqual(self.post("api_match_reopen").status_code, 409)

    def test_reopen_call(self):
        """Reabre la convocatoria cerrada; con parejas alineadas lo impide."""
        call = Call.objects.create(match=self.match, draft_mode=False)
        self.assertEqual(self.post("api_match_reopen_call").status_code, 200)
        call.refresh_from_db()
        self.assertTrue(call.draft_mode)
        self.assertEqual(self.post("api_match_reopen_call").status_code, 409)

    def test_reopen_call_with_games_is_refused(self):
        """Con parejas alineadas no se reabre la convocatoria."""
        Call.objects.create(match=self.match, draft_mode=False)
        Game.objects.create(match=self.match, n_game=1)
        self.assertEqual(self.post("api_match_reopen_call").json()["error"], "cannot_reopen")

    def test_resend_report_needs_closed_call(self):
        """Solo se reenvía el informe de una convocatoria cerrada."""
        call = Call.objects.create(match=self.match)
        self.assertEqual(self.post("api_match_resend_report").status_code, 409)
        call.draft_mode = False
        call.save()
        response = self.post("api_match_resend_report")
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["report"], ("sent", "pending", "no_email", "failed"))

    def test_no_show_and_undo(self):
        """Marca «No presentado» (cierra el acta) y lo deshace (la reabre)."""
        self.club.competition = "lapi"
        self.club.save()
        response = self.post("api_match_no_show", body={"side": "rival"})
        self.assertEqual(response.status_code, 200, response.content)
        self.match.refresh_from_db()
        self.assertEqual((self.match.no_show, self.match.draft_mode), ("rival", False))
        self.assertEqual(self.post("api_match_undo_no_show").status_code, 200)
        self.match.refresh_from_db()
        self.assertEqual((self.match.no_show, self.match.draft_mode), ("", True))

    def test_no_show_validates_side(self):
        """Un lado desconocido es un error de validación."""
        self.assertEqual(self.post("api_match_no_show", body={"side": "x"}).status_code, 400)

    def test_undo_without_no_show_is_409(self):
        """Quitar un «No presentado» que no existe es 409."""
        self.assertEqual(self.post("api_match_undo_no_show").status_code, 409)

    def test_actions_list_offers_reopen_for_closed_match(self):
        """La ficha de un acta cerrada ofrece «Reabrir acta» en las acciones."""
        Match.objects.filter(pk=self.match.pk).update(draft_mode=False)
        keys = [a["key"] for a in self.get(self.captain_token).json()["actions"]]
        self.assertIn("reopen_match", keys)
