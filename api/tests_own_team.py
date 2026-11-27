"""Tests de ``GET/PUT /api/v1/teams/<id>/own-team`` (edición del equipo propio)."""
from django.urls import reverse

from team.models import divisions_for

from .tests_notices import NoticesBase


class OwnTeamApiTests(NoticesBase):
    """Solo el capitán; mismos errores que el formulario de la web."""

    def setUp(self):
        """El equipo propio con categoría, país y división (el formulario las exige)."""
        super().setUp()
        team = self.club.own_team
        team.gender, team.country, team.division = "M", "ES", divisions_for(self.club.rules)[0][0]
        team.save()

    def url(self):
        """Ruta del equipo propio."""
        return reverse("api_own_team", args=[self.club.public_id])

    def put(self, body, token=None):
        """PUT con token (capitán por defecto)."""
        return self.client.put(self.url(), body, content_type="application/json",
                               HTTP_AUTHORIZATION=f"Bearer {token or self.captain_token}")

    def test_get(self):
        """Enseña el equipo propio y las opciones."""
        data = self.client.get(self.url(), HTTP_AUTHORIZATION=f"Bearer {self.captain_token}").json()
        self.assertEqual(data["name"], self.club.own_team.name)
        self.assertTrue(data["countries"] and data["divisions"] and data["genders"])

    def test_only_captain(self):
        """Una jugadora recibe 403."""
        self.assertEqual(self.client.get(self.url(), HTTP_AUTHORIZATION=f"Bearer {self.token}").status_code, 403)
        self.assertEqual(self.put({"name": "X"}, self.token).status_code, 403)

    def test_update(self):
        """Cambia nombre y sede; el resto se conserva."""
        team = self.club.own_team
        division = team.division
        r = self.put({"name": "Norte A", "location": "Pabellón Sur", "default_time": "20:30"})
        self.assertEqual(r.status_code, 200, r.content)
        team.refresh_from_db()
        self.assertEqual((team.name, team.location, f"{team.default_time:%H:%M}", team.division), ("Norte A", "Pabellón Sur", "20:30", division))
        self.assertEqual(r.json()["name"], "Norte A")

    def test_validation(self):
        """Un nombre vacío o una división inválida da 400 con ``fields``."""
        r = self.put({"name": "", "division": "zzz"})
        self.assertEqual((r.status_code, r.json()["error"]), (400, "validation_error"))
        self.assertIn("name", r.json()["fields"])
        self.assertIn("division", r.json()["fields"])
