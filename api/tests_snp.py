"""Tests de la cuenta SNP y de la revisión de «Completar equipo» en la API (``api/views_snp.py``)."""
from unittest import mock

from django.urls import reverse

from players.models import Player, SnpAccount, SnpTeamImport

from .tests_notices import NoticesBase


class SnpBase(NoticesBase):
    """El capitán tiene token; ``self.team`` es el id del club."""

    def setUp(self):
        """Añade el id del equipo."""
        super().setUp()
        self.team = str(self.club.public_id)

    def call(self, method, name, token=None, body=None, **kwargs):
        """Llamada a una ruta de la API con token (capitán por defecto)."""
        url = reverse(name, kwargs={"team_id": self.team, **kwargs})
        func = getattr(self.client, method)
        extra = {"HTTP_AUTHORIZATION": f"Bearer {token or self.captain_token}"}
        if method == "get":
            return func(url, **extra)
        return func(url, body or {}, content_type="application/json", **extra)


class SnpAccountApiTests(SnpBase):
    """``/teams/<id>/snp-account``."""

    def test_empty(self):
        """Sin cuenta: ``has_account`` falso."""
        data = self.call("get", "api_snp_account").json()
        self.assertEqual((data["has_account"], data["username"]), (False, None))

    def test_only_captain(self):
        """Una jugadora recibe 403 en las tres operaciones."""
        for method in ("get", "put", "delete"):
            self.assertEqual(self.call(method, "api_snp_account", token=self.token).status_code, 403, method)

    def test_create_requires_password(self):
        """Sin cuenta la contraseña es obligatoria."""
        r = self.call("put", "api_snp_account", body={"username": "capi.snp"})
        self.assertEqual((r.status_code, r.json()["error"]), (400, "validation_error"))
        self.assertIn("password", r.json()["fields"])

    def test_save_and_never_returns_password(self):
        """Guarda la cuenta y devuelve el usuario sin contraseña."""
        r = self.call("put", "api_snp_account", body={"username": "capi.snp", "password": "secreta-1"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual((data["has_account"], data["username"], data["changed"]), (True, "capi.snp", True))
        self.assertNotIn("secreta-1", r.content.decode())
        self.assertNotIn("password", data)
        self.assertEqual(SnpAccount.objects.get(club=self.club).password, "secreta-1")

    def test_unchanged_and_keep_password(self):
        """Mismo usuario y contraseña vacía: no cambia nada. Usuario nuevo con contraseña vacía conserva la guardada."""
        SnpAccount.objects.create(club=self.club, username="capi.snp", password="secreta-1")
        same = self.call("put", "api_snp_account", body={"username": "capi.snp"}).json()
        self.assertFalse(same["changed"])
        new = self.call("put", "api_snp_account", body={"username": "otro"}).json()
        self.assertEqual((new["changed"], new["username"]), (True, "otro"))
        self.assertEqual(SnpAccount.objects.get(club=self.club).password, "secreta-1")

    def test_saving_resets_failures(self):
        """Guardar datos nuevos devuelve la opción de sincronizar tras fallos."""
        type(self.club).objects.filter(pk=self.club.pk).update(snp_import_failures=3)
        self.call("put", "api_snp_account", body={"username": "capi.snp", "password": "secreta-1"})
        self.club.refresh_from_db()
        self.assertEqual(self.club.snp_import_failures, 0)

    def test_delete(self):
        """Borra la cuenta y es idempotente."""
        SnpAccount.objects.create(club=self.club, username="u", password="p")
        self.assertEqual(self.call("delete", "api_snp_account").json(), {"deleted": True})
        self.assertFalse(SnpAccount.objects.filter(club=self.club).exists())
        self.assertEqual(self.call("delete", "api_snp_account").status_code, 200)


class SnpImportApiTests(SnpBase):
    """Revisión y confirmación de «Completar equipo»."""

    def ready_import(self):
        """Una búsqueda lista con un jugador nuevo y uno que ya estaba."""
        return SnpTeamImport.objects.create(
            club=self.club, source=SnpTeamImport.WEB, status=SnpTeamImport.READY,
            to_add=[{"name": "Luis", "last_name": "Moreno", "snp_name": "MORENO LUIS", "score": 980}],
            existing=[{"snp_name": "RUIZ ANA", "player": "Ana Ruiz", "player_id": self.me.pk, "score": 1240}],
        )

    def test_no_import(self):
        """Sin búsquedas, ``import`` es nulo."""
        self.assertEqual(self.call("get", "api_snp_import").json(), {"import": None})

    def test_ready_state(self):
        """Lista: enseña lo que se crearía, lo que se actualiza y los jugadores elegibles para «es el mismo»."""
        team_import = self.ready_import()
        data = self.call("get", "api_snp_import").json()["import"]
        self.assertEqual((data["id"], data["status"], data["has_changes"]), (str(team_import.public_id), "ready", True))
        self.assertEqual(data["to_add"], [{"index": 0, "name": "MORENO LUIS", "category": "", "score": 980, "doubtful": False}])
        self.assertEqual(data["existing"][0]["score"], 1240)
        self.assertTrue(any(o["id"] == str(self.me.public_id) for o in data["same_options"]))

    def test_only_captain(self):
        """Una jugadora no ve la búsqueda ni la confirma."""
        team_import = self.ready_import()
        self.assertEqual(self.call("get", "api_snp_import", token=self.token).status_code, 403)
        r = self.call("post", "api_snp_import_confirm", token=self.token, import_id=str(team_import.public_id))
        self.assertEqual(r.status_code, 403)

    def test_confirm_creates_player(self):
        """Confirmar crea al jugador nuevo y actualiza los puntos del que ya estaba."""
        team_import = self.ready_import()
        r = self.call("post", "api_snp_import_confirm", import_id=str(team_import.public_id))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["position_notice"])
        self.assertTrue(Player.objects.filter(club=self.club, name="Luis", last_name="Moreno").exists())
        self.me.refresh_from_db()
        self.assertEqual(self.me.snp_score, 1240)
        team_import.refresh_from_db()
        self.assertEqual(team_import.status, SnpTeamImport.DONE)

    def test_confirm_same_player(self):
        """«Es el mismo jugador»: no se crea y el elegido recibe los puntos."""
        team_import = self.ready_import()
        r = self.call("post", "api_snp_import_confirm", body={"same": {"0": str(self.me.public_id)}},
                      import_id=str(team_import.public_id))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Player.objects.filter(club=self.club, name="Luis").exists())
        self.me.refresh_from_db()
        self.assertEqual(self.me.snp_score, 980)

    def test_confirm_not_ready(self):
        """Una búsqueda ya hecha no se confirma otra vez: 409 ``not_ready``."""
        team_import = self.ready_import()
        SnpTeamImport.objects.filter(pk=team_import.pk).update(status=SnpTeamImport.DONE)
        r = self.call("post", "api_snp_import_confirm", import_id=str(team_import.public_id))
        self.assertEqual((r.status_code, r.json()["error"]), (409, "not_ready"))

    def test_cancel(self):
        """Cancelar deja la búsqueda en ``cancelled`` y es idempotente."""
        team_import = self.ready_import()
        for _ in range(2):
            self.assertEqual(self.call("post", "api_snp_import_cancel", import_id=str(team_import.public_id)).json(),
                             {"cancelled": True})
        team_import.refresh_from_db()
        self.assertEqual(team_import.status, SnpTeamImport.CANCELLED)

    def test_other_team_import_is_404(self):
        """Una búsqueda inexistente es 404."""
        r = self.call("post", "api_snp_import_cancel", import_id="SNI-NOEXISTE")
        self.assertEqual(r.status_code, 404)

    def test_sync_with_review_does_not_auto_confirm(self):
        """``review`` lanza la búsqueda sin confirmarla sola y devuelve su id."""
        SnpAccount.objects.create(club=self.club, username="u", password="p")
        fake = mock.Mock(public_id="SNI-ABC")
        with mock.patch("players.snp_service.is_enabled", return_value=True), \
                mock.patch("players.snp_import.start_search", return_value=fake) as start:
            r = self.client.post(reverse("api_setup_snp_sync"), {"team_id": self.team, "review": True},
                                 content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.captain_token}")
        self.assertEqual(r.json(), {"started": True, "import_id": "SNI-ABC"})
        self.assertFalse(start.call_args.kwargs["auto_confirm"])
