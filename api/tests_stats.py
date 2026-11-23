"""Tests de ``GET /api/v1/teams/<id>/stats/team``: mismos números que la web, filtros por petición y acceso por equipo."""
from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse

from api.tokens import issue_token
from core.models import Membership
from core.services import create_club
from data_analyse.tests_extra import ClubDataMixin
from players.models import Player

User = get_user_model()


class TeamStatsApiTests(ClubDataMixin, TestCase):
    """Club con dos enfrentamientos cerrados (un empate y una victoria), ver ``ClubDataMixin``."""

    def setUp(self):
        """Además del club de los datos: un miembro, un extraño y un club vacío."""
        super().setUp()
        cache.clear()
        caches["ratelimit"].clear()
        _, self.token = issue_token(self.user, "iPhone")
        member = User.objects.create_user("miembro", password="pass-12345")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        _, self.member_token = issue_token(member, "iPhone")
        stranger = User.objects.create_user("otro", password="pass-12345")
        self.empty_club = create_club("Club Vacío", "Gijón", stranger)
        _, self.stranger_token = issue_token(stranger, "iPhone")

    def get(self, token, team=None, **params):
        """GET con el token dado al equipo (por defecto el de los datos)."""
        url = reverse("api_team_stats", args=[team or self.club.public_id])
        return self.client.get(url, params, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_team_stats", args=[self.club.public_id])).status_code, 401)

    def test_foreign_team_is_404(self):
        """Un equipo ajeno responde 404 como uno que no existe."""
        self.assertEqual(self.get(self.stranger_token).status_code, 404)

    def test_balance_matches_the_web(self):
        """Balance, forma y plantilla salen de las mismas funciones que la página web."""
        response = self.get(self.token, season="2025-2026", match_type="todos")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["balance"], {"total": 2, "won": 1, "drawn": 1, "lost": 0, "won_pct": 50.0})
        self.assertEqual(data["filters"]["season"], "2025-2026")
        self.assertEqual(data["filters"]["match_type"], "todos")
        self.assertEqual(len(data["game_numbers"]), 5)
        roster = {r["player"]["name"][0]: r for r in data["roster"]["rows"]}
        self.assertEqual((roster["A"]["played"], roster["A"]["pct"]), (2, 100))
        self.assertEqual((roster["E"]["played"], roster["E"]["pct"]), (0, None))
        web = self.client.get(reverse("team_statistics"), {"season": "2025-2026", "match_type": "todos"})
        self.assertEqual(web.context["total_matches"], data["balance"]["total"])
        self.assertEqual(web.context["won_matches"], data["balance"]["won"])

    def test_roster_side_and_sort_options(self):
        """``lado`` y ``orden`` llegan a la tabla; un valor desconocido vuelve al de por defecto."""
        local = self.get(self.token, season="all", match_type="todos", lado="local").json()["roster"]
        self.assertEqual(local["side"], "local")
        self.assertEqual({r["player"]["name"][0]: r["played"] for r in local["rows"]}["A"], 1)
        weird = self.get(self.token, season="all", match_type="todos", orden="zzz").json()["roster"]
        self.assertEqual(weird["sort"], "pct")

    def test_invalid_filters_are_400(self):
        """Temporada o tipo desconocidos: 400 ``invalid``."""
        self.assertEqual(self.get(self.token, season="1999-2000").status_code, 400)
        self.assertEqual(self.get(self.token, match_type="raro").status_code, 400)

    def test_member_can_read(self):
        """Cualquier miembro del equipo puede leer las estadísticas."""
        self.assertEqual(self.get(self.member_token, season="all").status_code, 200)

    def test_team_without_matches(self):
        """Sin enfrentamientos cerrados: solo los filtros y ``has_matches`` falso."""
        data = self.get(self.stranger_token, team=self.empty_club.public_id).json()
        self.assertFalse(data["has_matches"])
        self.assertNotIn("balance", data)
        self.assertEqual(data["filters"]["seasons"], [])

    def test_etag_and_304(self):
        """La respuesta lleva ETag y un ``If-None-Match`` igual recibe 304."""
        first = self.get(self.token, season="all")
        again = self.client.get(reverse("api_team_stats", args=[self.club.public_id]), {"season": "all"},
                                HTTP_AUTHORIZATION=f"Bearer {self.token}", HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(again.status_code, 304)


class MyStatsApiTests(ClubDataMixin, TestCase):
    """«Yo»: lo de la persona en todas sus fichas; se comprueba contra los mismos datos que usa la página web."""

    def setUp(self):
        """Club de ``ClubDataMixin`` con el jugador A enlazado a la cuenta; una cuenta sin ficha."""
        super().setUp()
        cache.clear()
        caches["ratelimit"].clear()
        Player.objects.filter(club=self.club, user=self.user).update(user=None)
        self.a.user = self.user
        self.a.save()
        _, self.token = issue_token(self.user, "iPhone")
        loner = User.objects.create_user("sola", password="pass-12345")
        _, self.loner_token = issue_token(loner, "iPhone")

    def get(self, token, **params):
        """GET de ``/me/stats`` con el token dado."""
        return self.client.get(reverse("api_my_stats"), params, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_my_stats")).status_code, 401)

    def test_account_without_player(self):
        """Sin ficha enlazada: ``state`` ``no_player`` y nada más que los filtros."""
        data = self.get(self.loner_token).json()
        self.assertEqual(data["state"], "no_player")
        self.assertNotIn("players", data)

    def test_my_numbers_and_single_player(self):
        """Con una sola ficha: sus cifras, ``single_player`` y el titular; coincide con el resumen de la web."""
        data = self.get(self.token, season="all", match_type="todos").json()
        self.assertEqual(data["state"], "ok")
        self.assertEqual((data["me"]["played"], data["me"]["wins"], data["me"]["losses"]), (2, 2, 0))
        self.assertEqual(len(data["players"]), 1)
        self.assertEqual(data["single_player"], data["players"][0]["player_id"])
        self.assertEqual(data["players"][0]["club"], "Club A")
        self.assertIn("2 de 2", data["headline"])
        self.assertIn("spaces_chart", data["charts"])

    def test_invalid_filter_is_400(self):
        """Una temporada desconocida: 400."""
        self.assertEqual(self.get(self.token, season="1999-2000").status_code, 400)


class PlayerStatsApiTests(ClubDataMixin, TestCase):
    """Ficha de un jugador de la plantilla: mismas cifras que la web, filtros por petición y acceso por equipo."""

    def setUp(self):
        """Un token del capitán, otro de un extraño y la jugadora A del club de los datos."""
        super().setUp()
        cache.clear()
        caches["ratelimit"].clear()
        _, self.token = issue_token(self.user, "iPhone")
        stranger = User.objects.create_user("otro", password="pass-12345")
        create_club("Club Vacío", "Gijón", stranger)
        _, self.stranger_token = issue_token(stranger, "iPhone")
        self.player = Player.objects.filter(club=self.club, in_team=True).order_by("name").first()

    def get(self, token, player=None, **params):
        """GET de la ficha con el token dado."""
        url = reverse("api_player_stats", args=[self.club.public_id, (player or self.player).public_id])
        return self.client.get(url, params, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_requires_token_and_team(self):
        """Sin token 401; con un token de otro equipo 404."""
        url = reverse("api_player_stats", args=[self.club.public_id, self.player.public_id])
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.get(self.stranger_token).status_code, 404)

    def test_numbers_match_the_web(self):
        """Cifras, temporadas y partidos coinciden con la ficha de la web."""
        response = self.get(self.token, season="all", match_type="todos")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        web = self.client.get(reverse("player_statistics"), {"player": self.player.public_id, "season": "all", "match_type": "todos"})
        self.assertEqual(data["summary"]["played"], web.context["s"]["played"])
        self.assertEqual(data["summary"]["wins"], web.context["s"]["wins"])
        self.assertEqual(len(data["games"]), len(web.context["games"]))
        self.assertEqual(len(data["game_numbers"]), 5)
        self.assertEqual(data["hero"]["id"], str(self.player.public_id))

    def test_unknown_player_and_filters(self):
        """Un jugador de otro club da 404; una temporada o tipo desconocidos, 400."""
        other = Player.objects.exclude(club=self.club).first()
        if other:
            self.assertEqual(self.get(self.token, player=other).status_code, 404)
        self.assertEqual(self.get(self.token, season="1999-2000").status_code, 400)
        self.assertEqual(self.get(self.token, match_type="raro").status_code, 400)
