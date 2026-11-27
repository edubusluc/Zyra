"""Tests de las advertencias de una convocatoria en la API (``api/views_penalties.py``)."""
import datetime

from django.urls import reverse

from call.models import Call
from match.models import Match
from penalty.models import Penalty
from players.models import Player
from team.models import Team

from .tests_notices import NoticesBase


class PenaltiesApiTests(NoticesBase):
    """Listar, poner y quitar advertencias; solo capitán y gestores."""

    def setUp(self):
        """Un enfrentamiento con convocatoria y dos jugadores."""
        super().setUp()
        rival = Team.objects.create(club=self.club, name="Club Este", location="X", in_group=True)
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                          start_date=datetime.date.today() + datetime.timedelta(days=3))
        self.call_obj = Call.objects.create(match=self.match)
        self.ana = Player.objects.get(club=self.club, name="Ana")

    def url(self, penalty=None):
        """Ruta de las advertencias (o de una)."""
        if penalty:
            return reverse("api_match_penalty", args=[self.match.public_id, penalty])
        return reverse("api_match_penalties", args=[self.match.public_id])

    def send(self, method, url, body=None, token=None):
        """Llamada con token (capitán por defecto)."""
        extra = {"HTTP_AUTHORIZATION": f"Bearer {token or self.captain_token}"}
        if method == "get":
            return self.client.get(url, **extra)
        return getattr(self.client, method)(url, body or {}, content_type="application/json", **extra)

    def test_list_empty(self):
        """Sin advertencias: motivos y jugadores del equipo."""
        data = self.send("get", self.url()).json()
        self.assertEqual(data["penalties"], [])
        self.assertEqual([k["key"] for k in data["kinds"]], ["no_show", "late", "late_drop", "conduct", "other"])
        self.assertEqual({p["name"] for p in data["players"]}, {"Ana Ruiz", "Marta Gil"})

    def test_member_cannot(self):
        """Una jugadora recibe 404 (solo gestiona quien gestiona)."""
        self.assertEqual(self.send("get", self.url(), token=self.token).status_code, 404)
        self.assertEqual(self.send("post", self.url(), {"kind": "late", "players": [str(self.me.public_id)]}, self.token).status_code, 404)

    def test_create_and_list(self):
        """Pone una advertencia a un jugador y aparece en la lista con su texto."""
        r = self.send("post", self.url(), {"kind": "late", "detail": "20 min", "players": [str(self.me.public_id)]})
        self.assertEqual(r.status_code, 201)
        created = r.json()["created"]
        self.assertEqual((len(created), created[0]["text"]), (1, "Llegó tarde: 20 min"))
        listed = self.send("get", self.url()).json()["penalties"]
        self.assertEqual([p["id"] for p in listed], [created[0]["id"]])

    def test_other_requires_detail(self):
        """«Otro» sin detalle es 400 con ``fields.detail``."""
        r = self.send("post", self.url(), {"kind": "other", "players": [str(self.me.public_id)]})
        self.assertEqual((r.status_code, "detail" in r.json()["fields"]), (400, True))

    def test_needs_kind_and_players(self):
        """Sin motivo o sin jugadores es 400."""
        self.assertIn("kind", self.send("post", self.url(), {"players": [str(self.me.public_id)]}).json()["fields"])
        self.assertIn("players", self.send("post", self.url(), {"kind": "late", "players": ["nadie"]}).json()["fields"])

    def test_no_duplicates(self):
        """La misma advertencia no se duplica: la segunda sale como ``skipped``."""
        body = {"kind": "late", "players": [str(self.me.public_id)]}
        self.send("post", self.url(), body)
        again = self.send("post", self.url(), body).json()
        self.assertEqual((again["created"], again["skipped"]), ([], 1))
        self.assertEqual(Penalty.objects.count(), 1)

    def test_delete(self):
        """Quita la advertencia; otra inexistente es 404."""
        penalty = Penalty.objects.create(player=self.me, kind="late", reason="", call=self.call_obj)
        self.assertEqual(self.send("delete", self.url(penalty.public_id)).json(), {"deleted": True})
        self.assertFalse(Penalty.objects.exists())
        self.assertEqual(self.send("delete", self.url(penalty.public_id)).status_code, 404)

    def test_no_call_is_404(self):
        """Un enfrentamiento sin convocatoria no tiene advertencias."""
        Call.objects.all().delete()
        self.assertEqual(self.send("get", self.url()).status_code, 404)
