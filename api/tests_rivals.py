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
