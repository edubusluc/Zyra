"""Tests de ``setup`` en ``GET /api/v1/home`` y de sus acciones (``api/views_setup.py``): primeros pasos, temporada y SNP."""
import datetime
from unittest import mock

from django.utils import timezone
from django.urls import reverse

from core.models import Membership
from core.services import create_club
from players.models import Player, SnpAccount, SnpTeamImport, SnpUpdateRequest
from django.contrib.auth import get_user_model

from .tests_notices import NoticesBase

User = get_user_model()
OCT = datetime.date(2026, 10, 1)


class SetupBase(NoticesBase):
    """El capitán tiene token; ``self.team`` es el id del club."""

    def setUp(self):
        """Añade el id del equipo."""
        super().setUp()
        self.team = str(self.club.public_id)

    def captain_home(self):
        """Inicio del capitán."""
        return self.home(self.captain_token)

    def block(self):
        """Bloque de configuración del club del capitán (o None)."""
        blocks = self.captain_home()["setup"]
        return blocks[0] if blocks else None

    def act(self, name, body, token=None):
        """POST a una acción de configuración."""
        return self.post(reverse(name), {"team_id": self.team, **body}, token or self.captain_token)

    def add_account(self):
        """Registra la cuenta SNP del club."""
        SnpAccount.objects.create(club=self.club, username="u", password="p")

    def enter_prep(self):
        """Pone la fecha en octubre y el club como creado antes del 1 de julio."""
        from core.models import Club
        Club.objects.filter(pk=self.club.pk).update(created_at=timezone.now() - datetime.timedelta(days=400))
        self.club.refresh_from_db()
        patcher = mock.patch("core.season_prep.timezone.localdate", return_value=OCT)
        patcher.start()
        self.addCleanup(patcher.stop)


class OnboardingTests(SetupBase):
    """«Primeros pasos» del capitán nuevo."""

    def test_new_captain_sees_steps(self):
        """Un club recién creado enseña los tres pasos, con SNP como primer paso y su alternativa."""
        block = self.block()
        steps = block["onboarding"]["steps"]
        self.assertEqual([s["key"] for s in steps], ["players", "invite", "match"])
        self.assertEqual(block["onboarding"]["total"], 3)
        self.assertIn("en=", steps[0]["path"])
        self.assertIsNotNone(steps[0]["alt_path"])
        self.assertFalse(block["snp_missing"])  # los primeros pasos llevan dentro la tarea de SNP

    def test_member_has_no_setup(self):
        """Una jugadora no ve configuración."""
        self.assertEqual(self.home()["setup"], [])

    def test_dismiss(self):
        """El capitán cierra los pasos; una jugadora no puede."""
        self.assertEqual(self.act("api_setup_onboarding_dismiss", {}, self.token).status_code, 403)
        self.assertEqual(self.act("api_setup_onboarding_dismiss", {}).status_code, 200)
        self.assertEqual(self.act("api_setup_onboarding_dismiss", {}).status_code, 200)
        self.assertIsNone(self.captain_home()["setup"] and self.captain_home()["setup"][0]["onboarding"])

    def test_snp_missing_after_dismiss(self):
        """Sin pasos y sin cuenta SNP sale el aviso de registrarla; con cuenta, la sincronización pendiente."""
        self.act("api_setup_onboarding_dismiss", {})
        block = self.block()
        self.assertTrue(block["snp_missing"])
        self.assertTrue(block["snp_account_path"].startswith("/"))
        self.add_account()
        block = self.block()
        self.assertFalse(block["snp_missing"])
        self.assertEqual(block["snp_sync"]["state"], "idle")

    def test_completes_and_disappears(self):
        """Con la jugadora y la invitación hechos faltan 2 de 3; al crear el enfrentamiento los pasos desaparecen."""
        from match.models import Match
        self.assertEqual(self.block()["onboarding"]["done"], 2)
        Match.objects.create(club=self.club, start_date=datetime.date.today() + datetime.timedelta(days=5),
                             rival_name="Rival")
        self.assertIsNone(self.block()["onboarding"])

    def test_unknown_team(self):
        """Un equipo ajeno o inexistente es 404."""
        r = self.post(reverse("api_setup_onboarding_dismiss"), {"team_id": "nope"}, self.captain_token)
        self.assertEqual(r.status_code, 404)


class SeasonPrepTests(SetupBase):
    """«Prepara la temporada» (julio-octubre)."""

    def setUp(self):
        """Sin primeros pasos y en octubre."""
        super().setUp()
        self.act("api_setup_onboarding_dismiss", {})
        self.enter_prep()

    def test_steps_and_mark(self):
        """Aparecen los tres pasos, marcar los manuales sube el progreso y el SNP lleva su estado."""
        prep = self.block()["season_prep"]
        self.assertEqual([s["key"] for s in prep["steps"]], ["roster", "snp", "rivals"])
        self.assertFalse(prep["steps"][1]["has_account"])
        self.assertEqual(self.act("api_setup_season_prep", {"action": "mark", "key": "roster"}).status_code, 200)
        self.assertEqual(self.block()["season_prep"]["done"], 1)
        self.assertFalse(self.block()["snp_missing"])

    def test_skip_snp_is_captain_only(self):
        """Omitir SNP es del capitán; un gestor puede marcar la plantilla."""
        manager = User.objects.create_user("gest", "g@example.com", "Clave-Segura-123")
        Membership.objects.create(user=manager, club=self.club, role=Membership.MANAGER)
        from api.tokens import issue_token
        _, mtoken = issue_token(manager, "iPhone")
        r = self.act("api_setup_season_prep", {"action": "mark", "key": "snp_skipped"}, mtoken)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.act("api_setup_season_prep", {"action": "mark", "key": "roster"}, mtoken).status_code, 200)
        self.assertEqual(self.act("api_setup_season_prep", {"action": "close"}, mtoken).status_code, 403)
        self.assertEqual(self.act("api_setup_season_prep", {"action": "mark", "key": "snp_skipped"}).status_code, 200)
        step = self.block()["season_prep"]["steps"][1]
        self.assertTrue(step["skipped"] and step["done"])
        gh = self.home(mtoken)["setup"]
        self.assertEqual(gh[0]["season_prep"]["steps"][1]["done"], True)
        self.assertNotIn("sync", gh[0]["season_prep"]["steps"][1] if not gh[0]["season_prep"]["steps"][1]["done"] else {})

    def test_invalid_key(self):
        """Una clave desconocida o una acción desconocida son 400."""
        self.assertEqual(self.act("api_setup_season_prep", {"action": "mark", "key": "x"}).status_code, 400)
        self.assertEqual(self.act("api_setup_season_prep", {"action": "zzz"}).status_code, 400)

    def test_close(self):
        """«Ahora no» oculta la tarjeta."""
        self.assertEqual(self.act("api_setup_season_prep", {"action": "close"}).status_code, 200)
        block = self.block()
        self.assertTrue(block is None or block["season_prep"] is None)

    def test_snp_step_with_account(self):
        """Con cuenta SNP el paso trae el estado de la sincronización y la petición abierta."""
        self.add_account()
        step = self.block()["season_prep"]["steps"][1]
        self.assertTrue(step["has_account"])
        self.assertEqual(step["sync"]["state"], "idle")
        self.assertFalse(step["request_open"])
        self.assertEqual(self.act("api_setup_snp_request", {"note": "Nuevos"}).json()["created"], True)
        self.assertEqual(self.act("api_setup_snp_request", {}).json()["created"], False)
        step = self.block()["season_prep"]["steps"][1]
        self.assertTrue(step["request_open"])
        self.assertTrue(SnpUpdateRequest.objects.filter(club=self.club, note="Nuevos").exists())


class SnpSyncTests(SetupBase):
    """Lanzar «Sincronizar datos» desde el Inicio."""

    def setUp(self):
        """Sin primeros pasos."""
        super().setUp()
        self.act("api_setup_onboarding_dismiss", {})

    def test_requires_account(self):
        """Sin cuenta SNP es 409 ``no_account``."""
        r = self.act("api_setup_snp_sync", {})
        self.assertEqual((r.status_code, r.json()["error"]), (409, "no_account"))

    def test_only_captain(self):
        """Una jugadora recibe 403."""
        self.add_account()
        self.assertEqual(self.act("api_setup_snp_sync", {}, self.token).status_code, 403)

    def test_service_off(self):
        """Con SNP apagado es 503."""
        self.add_account()
        with mock.patch("players.snp_service.is_enabled", return_value=False):
            r = self.act("api_setup_snp_sync", {})
        self.assertEqual((r.status_code, r.json()["error"]), (503, "service_off"))

    def test_start_and_running(self):
        """Lanza una búsqueda; con una en curso no crea otra y el Inicio la muestra como ``running``."""
        self.add_account()
        with mock.patch("players.snp_service.is_enabled", return_value=True), \
                mock.patch("players.snp_import.start_search") as start:
            self.assertEqual(self.act("api_setup_snp_sync", {}).json()["started"], True)
            start.assert_called_once()
            self.assertTrue(start.call_args.kwargs["auto_confirm"])
        SnpTeamImport.objects.create(club=self.club, source=SnpTeamImport.WEB, status=SnpTeamImport.RUNNING)
        with mock.patch("players.snp_service.is_enabled", return_value=True):
            self.assertEqual(self.act("api_setup_snp_sync", {}).json()["started"], False)
        self.assertEqual(self.block()["snp_sync"]["state"], "running")

    def test_failed_state(self):
        """Un fallo se ve con su mensaje y reintento posible."""
        self.add_account()
        SnpTeamImport.objects.create(club=self.club, source=SnpTeamImport.WEB, status=SnpTeamImport.ERROR,
                                     message="No se encontró")
        sync = self.block()["snp_sync"]
        self.assertEqual((sync["state"], sync["message"]), ("failed", "No se encontró"))

    def test_done_hides_task(self):
        """Con un resultado correcto la tarea desaparece."""
        self.add_account()
        SnpTeamImport.objects.create(club=self.club, source=SnpTeamImport.WEB, status=SnpTeamImport.DONE)
        self.assertIsNone(self.block())

    def test_closed_when_done(self):
        """Si ya se completó, lanzar de nuevo es 409 ``closed``."""
        self.add_account()
        SnpTeamImport.objects.create(club=self.club, source=SnpTeamImport.WEB, status=SnpTeamImport.DONE)
        with mock.patch("players.snp_service.is_enabled", return_value=True):
            r = self.act("api_setup_snp_sync", {})
        self.assertEqual((r.status_code, r.json()["error"]), (409, "closed"))
