"""Tests de ``GET /api/v1/teams/<id>/rivals`` (lista de rivales)."""
from django.urls import reverse

from team.models import Team

from .tests_notices import NoticesBase


class RivalsApiTests(NoticesBase):
    """Mismas reglas que ``team.views.list_team``: solo rivales, solo el grupo salvo gestores con ``group=0``."""

    def setUp(self):
        """Dos rivales del grupo, uno de fuera y el equipo propio (que no sale)."""
        super().setUp()
        Team.objects.create(club=self.club, name="Zeta", location="Oviedo", in_group=True)
        Team.objects.create(club=self.club, name="Alfa", location="Gijón", in_group=True, division="future")
        Team.objects.create(club=self.club, name="Fuera", location="Cádiz", in_group=False)

    def get(self, query="", token=None):
        """GET con token (capitán por defecto)."""
        return self.client.get(reverse("api_rivals", args=[self.club.public_id]) + query,
                               HTTP_AUTHORIZATION=f"Bearer {token or self.captain_token}")

    def test_only_group_by_default(self):
        """Por orden de nombre, sin el equipo propio ni los de fuera del grupo."""
        data = self.get().json()
        self.assertEqual([r["name"] for r in data["rivals"]], ["Alfa", "Zeta"])
        self.assertEqual((data["count"], data["can_manage"], data["only_group"]), (2, True, True))
        self.assertEqual(data["rivals"][0]["division_label"], "Future")

    def test_manager_sees_all(self):
        """El capitán con ``group=0`` ve también los de fuera, los del grupo primero."""
        self.assertEqual([r["name"] for r in self.get("?group=0").json()["rivals"]], ["Alfa", "Zeta", "Fuera"])

    def test_player_cannot_widen(self):
        """Una jugadora sin rol ve solo el grupo aunque pida ``group=0``."""
        data = self.get("?group=0", self.token).json()
        self.assertEqual((len(data["rivals"]), data["can_manage"], data["only_group"]), (2, False, True))

    def test_search(self):
        """Busca por nombre o localidad."""
        self.assertEqual([r["name"] for r in self.get("?search=oviedo").json()["rivals"]], ["Zeta"])
        self.assertEqual([r["name"] for r in self.get("?search=alf").json()["rivals"]], ["Alfa"])

    def test_requires_token(self):
        """Sin token, 401."""
        url = reverse("api_rivals", args=[self.club.public_id])
        self.assertEqual(self.client.get(url).status_code, 401)


class RivalWriteApiTests(NoticesBase):
    """Alta y edición de rivales: mismo formulario que la web, solo capitán y gestores."""

    def setUp(self):
        """El equipo propio con categoría, país y división (se copian a los rivales del grupo)."""
        super().setUp()
        from team.models import divisions_for
        own = self.club.own_team
        own.gender, own.country, own.division = "M", "ES", divisions_for(self.club.rules)[0][0]
        own.save()
        self.url = reverse("api_rivals", args=[self.club.public_id])

    def send(self, method, url, body, token=None):
        """Petición JSON con token (capitán por defecto)."""
        return getattr(self.client, method)(url, body, content_type="application/json",
                                            HTTP_AUTHORIZATION=f"Bearer {token or self.captain_token}")

    def test_options_for_managers_only(self):
        """El listado trae las opciones y los valores propuestos solo para quien gestiona."""
        data = self.client.get(self.url, HTTP_AUTHORIZATION=f"Bearer {self.captain_token}").json()
        self.assertEqual(data["options"]["defaults"]["country"], "ES")
        self.assertTrue(data["options"]["divisions"])
        self.assertIsNone(self.client.get(self.url, HTTP_AUTHORIZATION=f"Bearer {self.token}").json()["options"])

    def test_create_in_group_copies_own_team(self):
        """Un rival del grupo toma categoría, país y división del equipo propio."""
        r = self.send("post", self.url, {"name": "Norte B", "location": "Avilés"})
        self.assertEqual(r.status_code, 201, r.content)
        team = Team.objects.get(club=self.club, name="Norte B")
        self.assertEqual((team.in_group, team.country, team.location), (True, "ES", "Avilés"))

    def test_create_requires_manager(self):
        """Una jugadora sin rol recibe 403."""
        self.assertEqual(self.send("post", self.url, {"name": "X", "location": "Y"}, self.token).status_code, 403)

    def test_create_validation(self):
        """Fuera del grupo hay que dar categoría, país y división."""
        r = self.send("post", self.url, {"name": "Fuera", "location": "Y", "in_group": False})
        self.assertEqual((r.status_code, r.json()["error"]), (400, "validation_error"))
        self.assertIn("division", r.json()["fields"])

    def test_similar_needs_confirmation(self):
        """Un nombre parecido da 409 y se confirma con ``confirm_similar``; ``check`` no crea nada."""
        Team.objects.create(club=self.club, name="Padel Barcelona", location="BCN", in_group=True)
        body = {"name": "Padel Barcelon", "location": "BCN"}
        self.assertEqual(self.send("post", self.url, {**body, "check": True}).json()["similar"][0]["name"], "Padel Barcelona")
        self.assertEqual(Team.objects.filter(club=self.club, name="Padel Barcelon").count(), 0)
        r = self.send("post", self.url, body)
        self.assertEqual((r.status_code, r.json()["error"]), (409, "similar_teams"))
        self.assertEqual(self.send("post", self.url, {**body, "confirm_similar": True}).status_code, 201)

    def test_inactive_namesake(self):
        """Un homónimo dado de baja del grupo da 409 ``team_exists`` con su id."""
        old = Team.objects.create(club=self.club, name="Zeta", location="Oviedo", in_group=False,
                                  gender="M", country="ES", division=self.club.own_team.division)
        r = self.send("post", self.url, {"name": "Zeta", "location": "Oviedo"})
        self.assertEqual((r.status_code, r.json()["error"], r.json()["id"]), (409, "team_exists", str(old.public_id)))

    def test_update(self):
        """Edita nombre y localidad; el resto se conserva. Un gestor también puede."""
        team = Team.objects.create(club=self.club, name="Alfa", location="Gijón", in_group=True, gender="M", country="ES",
                                   division=self.club.own_team.division)
        from core.models import Membership
        Membership.objects.filter(user=self.marta, club=self.club).update(role=Membership.MANAGER)
        url = reverse("api_rival", args=[self.club.public_id, team.public_id])
        r = self.send("put", url, {"name": "Alfa B", "location": "Mieres"}, self.token)
        self.assertEqual(r.status_code, 200, r.content)
        team.refresh_from_db()
        self.assertEqual((team.name, team.location, team.in_group), ("Alfa B", "Mieres", True))

    def test_update_other_team_or_own(self):
        """El equipo propio y los de otro club no se editan por aquí (404)."""
        url = reverse("api_rival", args=[self.club.public_id, self.club.own_team.public_id])
        self.assertEqual(self.send("put", url, {"name": "X"}).status_code, 404)
