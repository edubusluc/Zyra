"""Tests de ``GET /api/v1/home`` (base del Inicio nativo y carrusel «Próximo enfrentamiento»)."""
import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api.tokens import issue_token
from call.models import Call
from core.models import Membership
from core.services import create_club
from match.models import Match
from players.models import Player
from team.models import Team

User = get_user_model()


class HomeApiTests(TestCase):
    """El Inicio nativo recibe la situación de la cuenta, sus equipos y el rol en cada uno."""

    def setUp(self):
        """Capitán con club y una cuenta sin equipo, cada una con su token."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123", first_name="Ana")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.loner = User.objects.create_user("sola", "sola@example.com", "Clave-Segura-123")
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.loner_token = issue_token(self.loner, "iPhone")

    def get(self, token):
        """GET del Inicio con el token indicado."""
        return self.client.get(reverse("api_home"), HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_requires_token(self):
        """Sin token: 401."""
        self.assertEqual(self.client.get(reverse("api_home")).status_code, 401)

    def test_post_is_not_allowed(self):
        """Solo se lee: POST da 405 en JSON."""
        response = self.client.post(reverse("api_home"), HTTP_AUTHORIZATION=f"Bearer {self.captain_token}")
        self.assertEqual((response.status_code, response.json()["error"]), (405, "method_not_allowed"))

    def test_captain_with_team(self):
        """El capitán ve su equipo con rol, competición y su ficha de jugador."""
        data = self.get(self.captain_token).json()
        self.assertEqual(data["state"], "ok")
        self.assertEqual(data["user"], {"username": "capi", "display_name": "Ana"})
        self.assertEqual(len(data["teams"]), 1)
        team = data["teams"][0]
        self.assertEqual((team["name"], team["competition"], team["role"], team["can_manage"]),
                         ("Club Norte", "snp", "admin", True))
        self.assertEqual(team["role_label"], "Capitán")
        self.assertTrue(team["has_snp"])
        self.assertTrue(data["has_player"])
        self.assertTrue(data["has_history"])
        self.assertEqual(data["suspended_clubs"], [])

    def test_display_name_falls_back_to_username(self):
        """Sin nombre de pila se saluda con el usuario."""
        self.assertEqual(self.get(self.loner_token).json()["user"]["display_name"], "sola")

    def test_no_team(self):
        """Cuenta sin equipo: ``no_team`` y sin histórico."""
        data = self.get(self.loner_token).json()
        self.assertEqual((data["state"], data["teams"], data["has_player"], data["has_history"]), ("no_team", [], False, False))

    def test_member_role(self):
        """Un jugador (miembro) no gestiona."""
        Membership.objects.create(user=self.loner, club=self.club, role=Membership.MEMBER)
        team = self.get(self.loner_token).json()["teams"][0]
        self.assertEqual((team["role"], team["role_label"], team["can_manage"]), ("member", "Jugador", False))

    def test_has_player_only_with_linked_sheet(self):
        """``has_player`` es cierto solo si la cuenta tiene ficha enlazada en un equipo activo."""
        Membership.objects.create(user=self.loner, club=self.club, role=Membership.MEMBER)
        self.assertFalse(self.get(self.loner_token).json()["has_player"])
        Player.objects.filter(club=self.club).first()  # la ficha del capitán no es suya
        player = Player.objects.create(club=self.club, name="Sola", last_name="Pérez", user=self.loner)
        self.assertTrue(self.get(self.loner_token).json()["has_player"])
        player.delete()

    def test_suspended_club(self):
        """Con el único club suspendido: ``suspended`` y el nombre del club."""
        self.club.suspended_at = timezone.now()
        self.club.save(update_fields=["suspended_at"])
        data = self.get(self.captain_token).json()
        self.assertEqual((data["state"], data["teams"]), ("suspended", []))
        self.assertEqual(data["suspended_clubs"], [{"name": "Club Norte"}])

    def test_two_spaces_in_competition_order(self):
        """Con dos equipos salen los dos, en el orden de las competiciones (SNP antes que LAPI)."""
        create_club("Norte LAPI", "Gijón", self.captain, competition="lapi")
        data = self.get(self.captain_token).json()
        self.assertEqual([t["competition"] for t in data["teams"]], ["snp", "lapi"])


class HomeUpcomingTests(TestCase):
    """``upcoming``: el carrusel «Próximo enfrentamiento» con las mismas reglas que el Inicio de la web."""

    def setUp(self):
        """Capitán con club, un rival, un jugador con ficha y el lunes de esta semana como referencia."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.rival = Team.objects.create(club=self.club, name="Club Este", location="X", in_group=True)
        self.today = datetime.date.today()
        self.monday = self.today - datetime.timedelta(days=self.today.weekday())
        _, self.token = issue_token(self.captain, "iPhone")

    def match(self, days=1, **extra):
        """Enfrentamiento abierto a ``days`` días de hoy contra el rival (propio como local)."""
        return Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                    start_date=self.today + datetime.timedelta(days=days), **extra)

    def upcoming(self):
        """``upcoming`` de la respuesta."""
        return self.client.get(reverse("api_home"), HTTP_AUTHORIZATION=f"Bearer {self.token}").json()["upcoming"]

    def test_empty_without_matches(self):
        """Sin enfrentamientos abiertos, lista vacía; los cerrados y los pasados no cuentan."""
        self.match(days=-3)
        self.match(days=1, draft_mode=False)
        self.assertEqual(self.upcoming(), [])

    def test_card_data(self):
        """Fecha, hora, lugar con enlace de Maps, lados y ruta de la ficha."""
        m = self.match(days=0, start_time=datetime.time(17, 30), location="Pistas Norte", round_number=6,
                       match_type="liga")
        item = self.upcoming()[0]
        self.assertEqual((item["id"], item["days_left"], item["time"], item["location"]),
                         (str(m.public_id), 0, "17:30", "Pistas Norte"))
        self.assertIn("google.com/maps", item["maps_url"])
        self.assertEqual(item["local"], {"name": "Club Norte", "is_own": True})
        self.assertEqual(item["visiting"], {"name": "Club Este", "is_own": False})
        self.assertEqual(item["competition"], "snp")
        self.assertEqual(item["web_path"], reverse("call_for_match", args=[m.public_id]))
        self.assertFalse(item["neutral_venue"])

    def test_without_time_or_location(self):
        """Sin hora ni lugar (sede neutral sin lugar): ``null`` y la app dice «Sin ubicación»."""
        self.match(days=2, neutral_venue=True)
        item = self.upcoming()[0]
        self.assertEqual((item["time"], item["location"], item["maps_url"]), (None, None, None))

    def test_only_the_week_of_the_nearest(self):
        """Solo los de la semana natural del más cercano, por orden de fecha."""
        near = self.today + datetime.timedelta(days=1)
        sunday = near + datetime.timedelta(days=6 - near.weekday())
        far = sunday + datetime.timedelta(days=1)
        self.match(days=(far - self.today).days)
        second = self.match(days=(sunday - self.today).days)
        first = self.match(days=1)
        self.assertEqual([i["id"] for i in self.upcoming()], [str(first.public_id), str(second.public_id)])

    def test_player_states(self):
        """El estado del jugador en la convocatoria sigue las mismas reglas que la web."""
        member = User.objects.create_user("marta", "marta@example.com", "Clave-Segura-123")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        player = Player.objects.create(club=self.club, name="Marta", last_name="Gil", user=member)
        _, token = issue_token(member, "iPhone")
        m = self.match(days=1)

        def me():
            return self.client.get(reverse("api_home"), HTTP_AUTHORIZATION=f"Bearer {token}").json()["upcoming"][0]["me"]

        self.assertEqual(me(), {"state": "no_call"})
        call = Call.objects.create(match=m)
        self.assertEqual(me(), {"state": "not_called_open"})
        call.players.add(player)
        self.assertEqual(me(), {"state": "applied_open"})
        call.draft_mode = False
        call.save()
        self.assertEqual(me(), {"state": "called_no_pair"})
        call.players.remove(player)
        self.assertEqual(me(), {"state": "not_called"})

    def test_unlinked_member_and_manager(self):
        """Un miembro sin ficha ve ``unlinked``; el capitán sin ficha enlazada no tiene estado."""
        member = User.objects.create_user("sin", "sin@example.com", "Clave-Segura-123")
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        _, token = issue_token(member, "iPhone")
        self.match(days=1)
        item = self.client.get(reverse("api_home"), HTTP_AUTHORIZATION=f"Bearer {token}").json()["upcoming"][0]
        self.assertEqual(item["me"], {"state": "unlinked"})
        Player.objects.filter(user=self.captain).update(user=None)
        self.assertIsNone(self.upcoming()[0]["me"])

    def test_neutral_venue_and_friendly_label(self):
        """Sede neutral y amistoso (sin jornada: el tipo)."""
        self.match(days=1, neutral_venue=True, match_type="amistoso")
        item = self.upcoming()[0]
        self.assertTrue(item["neutral_venue"])
        self.assertEqual(item["kind_label"], "Amistoso")

    def test_all_spaces(self):
        """Con dos equipos salen los enfrentamientos de los dos, mezclados por fecha."""
        lapi = create_club("Norte LAPI", "Gijón", self.captain, competition="lapi")
        rival = Team.objects.create(club=lapi, name="Sur", location="Y", in_group=True)
        later = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                     start_date=self.today + datetime.timedelta(days=1))
        sooner = Match.objects.create(club=lapi, local=lapi.own_team, visiting=rival, start_date=self.today)
        self.assertEqual([i["id"] for i in self.upcoming()], [str(sooner.public_id), str(later.public_id)])
        self.assertEqual(self.upcoming()[0]["competition"], "lapi")
