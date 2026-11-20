"""Tests de ``notices`` en ``GET /api/v1/home`` y de las acciones de los avisos (``api/views_notices.py``)."""
import datetime

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache, caches
from django.test import TestCase
from django.urls import reverse

from api.tokens import issue_token
from call.models import Availability, Call
from core.models import Invitation, Membership, UserPreference
from core.services import create_club
from match.models import Match
from players.models import Player
from team.models import Team

User = get_user_model()


class NoticesBase(TestCase):
    """Capitán con club y un jugador (``marta``) con cuenta; los dos con token."""

    def setUp(self):
        """Club SNP con capitán y una jugadora con cuenta en el equipo."""
        cache.clear()
        caches["ratelimit"].clear()
        self.captain = User.objects.create_user("capi", "capi@example.com", "Clave-Segura-123", first_name="Ana")
        self.club = create_club("Club Norte", "Gijón", self.captain, player_name="Ana", player_last_name="Ruiz")
        self.marta = User.objects.create_user("marta", "marta@example.com", "Clave-Segura-123")
        Membership.objects.create(user=self.marta, club=self.club, role=Membership.MEMBER)
        self.me = Player.objects.create(club=self.club, name="Marta", last_name="Gil", user=self.marta, in_team=True)
        for user in (self.captain, self.marta):
            EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        _, self.captain_token = issue_token(self.captain, "iPhone")
        _, self.token = issue_token(self.marta, "iPhone")

    def home(self, token=None):
        """Respuesta del Inicio."""
        return self.client.get(reverse("api_home"), HTTP_AUTHORIZATION=f"Bearer {token or self.token}").json()

    def post(self, url, body=None, token=None):
        """POST JSON con token."""
        return self.client.post(url, body or {}, content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {token or self.token}")

    def kinds(self, token=None):
        """Tipos de aviso del Inicio, en orden."""
        return [n["kind"] for n in self.home(token)["notices"]]


class NoticesTests(NoticesBase):
    """Qué avisos salen en el Inicio."""

    def test_none_for_a_member_up_to_date(self):
        """Una jugadora con el email confirmado no tiene avisos."""
        self.assertEqual(self.home()["notices"], [])

    def test_email_notice_and_resend(self):
        """El email sin confirmar sale como aviso y se puede reenviar el enlace."""
        EmailAddress.objects.filter(user=self.marta).update(verified=False)
        notice = self.home()["notices"][0]
        self.assertEqual((notice["kind"], notice["email"]), ("email", "marta@example.com"))
        response = self.post(reverse("api_resend_verification"))
        self.assertEqual((response.status_code, response.json()), (200, {"sent": True}))
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_with_nothing_to_confirm(self):
        """Con el email ya confirmado no se envía nada."""
        response = self.post(reverse("api_resend_verification"))
        self.assertEqual(response.json(), {"sent": False})
        self.assertEqual(len(mail.outbox), 0)

    def test_google_account_has_no_email_notice(self):
        """Las cuentas sin contraseña (Google) nacen verificadas: sin aviso."""
        EmailAddress.objects.filter(user=self.marta).update(verified=False)
        self.marta.set_unusable_password()
        self.marta.save()
        self.assertEqual(self.home()["notices"], [])

    def test_manager_welcome_and_dismiss(self):
        """La bienvenida de gestor sale hasta que se cierra."""
        Membership.objects.filter(user=self.marta).update(role=Membership.MANAGER, manager_welcome_pending=True)
        notice = self.home()["notices"][0]
        self.assertEqual((notice["kind"], notice["team_name"], notice["has_snp"]), ("manager_welcome", "Club Norte", True))
        response = self.post(reverse("api_home_dismiss"),
                             {"notice": "manager_welcome", "team_id": notice["team_id"]})
        self.assertEqual(response.json(), {"dismissed": True})
        self.assertEqual(self.home()["notices"], [])

    def test_dismiss_welcome_needs_team(self):
        """Cerrar la bienvenida exige el equipo; un aviso desconocido es un error."""
        self.assertEqual(self.post(reverse("api_home_dismiss"), {"notice": "manager_welcome"}).status_code, 400)
        self.assertEqual(self.post(reverse("api_home_dismiss"), {"notice": "otro"}).status_code, 400)

    def test_manager_tip_waits_for_members(self):
        """Un club recién creado, sin más miembros con cuenta, no recibe «Añade un gestor»."""
        Membership.objects.filter(user=self.marta).delete()
        self.assertEqual(self.kinds(self.captain_token), [])
        Membership.objects.create(user=self.marta, club=self.club, role=Membership.MEMBER)
        self.assertEqual(self.kinds(self.captain_token), ["manager_tip"])

    def test_manager_tip_only_without_manager(self):
        """«Añade un gestor» es para el capitán, sin gestor y hasta que lo cierra."""
        self.assertEqual(self.kinds(self.captain_token), ["manager_tip"])
        self.assertEqual(self.home(self.captain_token)["notices"][0]["team_name"], "Club Norte")
        self.post(reverse("api_home_dismiss"), {"notice": "manager_tip"}, token=self.captain_token)
        self.assertEqual(self.kinds(self.captain_token), [])
        UserPreference.objects.filter(user=self.captain).update(manager_tip_dismissed_at=None)
        Membership.objects.filter(user=self.marta).update(role=Membership.MANAGER)
        self.assertEqual(self.kinds(self.captain_token), [])


class CopyInvitationTests(NoticesBase):
    """Invitaciones de una ficha copiada a otro equipo: avisar, aceptar y rechazar."""

    def setUp(self):
        """Un segundo equipo (LAPI) que invita a ``marta`` con una ficha sin enlazar."""
        super().setUp()
        self.lapi_owner = User.objects.create_user("lapi", "lapi@example.com", "Clave-Segura-123", first_name="Pedro")
        self.lapi = create_club("Norte LAPI", "Gijón", self.lapi_owner, competition="lapi")
        self.sheet = Player.objects.create(club=self.lapi, name="Marta", last_name="Gil", in_team=True)
        self.invitation = Invitation.objects.create(
            club=self.lapi, email="marta@example.com", created_by=self.lapi_owner, player=self.sheet)

    def test_notice(self):
        """El aviso trae el club, quién invita, la ficha y si es una vuelta al equipo."""
        notice = self.home()["notices"][0]
        self.assertEqual(notice["kind"], "copy_invitation")
        self.assertEqual(notice["token"], self.invitation.token)
        self.assertEqual(notice["club"], {"name": "Norte LAPI", "competition": "lapi", "competition_name": "LAPI"})
        self.assertEqual((notice["invited_by"], notice["player_name"], notice["returning"]),
                         ("Pedro", "Marta Gil", False))
        self.sheet.past_user = self.marta
        self.sheet.save()
        self.assertTrue(self.home()["notices"][0]["returning"])

    def test_accept(self):
        """Aceptar mete a la cuenta en el equipo, enlaza la ficha y el aviso desaparece."""
        url = reverse("api_copy_invitation", args=[self.invitation.token])
        response = self.post(url, {"action": "accept"})
        self.assertEqual((response.status_code, response.json()["accepted"]), (200, True))
        self.assertTrue(Membership.objects.filter(user=self.marta, club=self.lapi).exists())
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.user, self.marta)
        data = self.home()
        self.assertEqual(data["notices"], [])
        self.assertEqual(len(data["teams"]), 2)

    def test_decline(self):
        """Rechazar borra la invitación y no mete a nadie."""
        url = reverse("api_copy_invitation", args=[self.invitation.token])
        self.assertEqual(self.post(url, {"action": "decline"}).json(), {"accepted": False})
        self.assertFalse(Invitation.objects.filter(pk=self.invitation.pk).exists())
        self.assertFalse(Membership.objects.filter(user=self.marta, club=self.lapi).exists())
        self.assertEqual(self.home()["notices"], [])

    def test_not_pending_for_another_account(self):
        """Solo la cuenta con ese email puede responder; el resto recibe 404."""
        url = reverse("api_copy_invitation", args=[self.invitation.token])
        self.assertEqual(self.post(url, {"action": "accept"}, token=self.captain_token).status_code, 404)

    def test_invalid_action(self):
        """La acción debe ser accept o decline."""
        url = reverse("api_copy_invitation", args=[self.invitation.token])
        self.assertEqual(self.post(url, {"action": "x"}).status_code, 400)


class AvailabilityTests(NoticesBase):
    """Responder desde el Inicio si se puede jugar."""

    def setUp(self):
        """Un enfrentamiento abierto dentro de 3 días."""
        super().setUp()
        rival = Team.objects.create(club=self.club, name="Club Este", location="X", in_group=True)
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                          start_date=datetime.date.today() + datetime.timedelta(days=3))
        self.url = reverse("api_match_availability", args=[self.match.public_id])

    def test_todo_carries_the_match(self):
        """La entrada «Responde si puedes jugar» trae el enfrentamiento para responder sin salir de la app."""
        todo = next(t for t in self.home()["todos"] if t["kind"] == "availability")
        self.assertEqual(todo["match_id"], str(self.match.public_id))

    def test_answer_yes_then_it_disappears(self):
        """Responder Sí guarda la respuesta y quita la entrada de «Tus pendientes»."""
        self.assertEqual(self.post(self.url, {"answer": "yes"}).json(), {"answer": "yes"})
        self.assertEqual(Availability.objects.get(match=self.match, player=self.me).answer, "yes")
        self.assertFalse([t for t in self.home()["todos"] if t["kind"] == "availability"])

    def test_maybe_stays_in_pending_until_yes_or_no(self):
        """«Pendiente» no cierra la tarea: la entrada sigue con su respuesta y desaparece al decir Sí o No."""
        self.post(self.url, {"answer": "maybe"})
        todo = next(t for t in self.home()["todos"] if t["kind"] == "availability")
        self.assertEqual((todo["match_id"], todo["answer"]), (str(self.match.public_id), "maybe"))
        self.assertEqual(self.home()["pending_count"], 2)  # la foto y la convocatoria
        self.post(self.url, {"answer": "no"})
        self.assertFalse([t for t in self.home()["todos"] if t["kind"] == "availability"])

    def test_maybe_leaves_when_call_is_closed_or_called(self):
        """Con la convocatoria cerrada o ya apuntada por el capitán, «Pendiente» deja de ser tarea."""
        self.post(self.url, {"answer": "maybe"})
        Call.objects.create(match=self.match).players.add(self.me)
        self.assertFalse([t for t in self.home()["todos"] if t["kind"] == "availability"])

    def test_unanswered_has_no_answer(self):
        """Sin responder, ``answer`` es null."""
        todo = next(t for t in self.home()["todos"] if t["kind"] == "availability")
        self.assertIsNone(todo["answer"])

    def test_change_answer_and_comment_only_with_maybe(self):
        """Se puede cambiar; el comentario solo se guarda con «Pendiente»."""
        self.post(self.url, {"answer": "maybe", "comment": "Llego tarde"})
        self.assertEqual(Availability.objects.get(match=self.match).comment, "Llego tarde")
        self.post(self.url, {"answer": "no", "comment": "ya no"})
        row = Availability.objects.get(match=self.match)
        self.assertEqual((row.answer, row.comment), ("no", ""))

    def test_closed_call(self):
        """Con la convocatoria cerrada no se puede responder (409)."""
        Call.objects.create(match=self.match, draft_mode=False)
        response = self.post(self.url, {"answer": "yes"})
        self.assertEqual((response.status_code, response.json()["error"]), (409, "closed"))

    def test_validation_and_access(self):
        """Respuesta no válida: 400; enfrentamiento ajeno o cuenta sin ficha: 404; sin token: 401."""
        self.assertEqual(self.post(self.url, {"answer": "quizá"}).status_code, 400)
        outsider = User.objects.create_user("otra", "otra@example.com", "Clave-Segura-123")
        _, token = issue_token(outsider, "iPhone")
        self.assertEqual(self.post(self.url, {"answer": "yes"}, token=token).status_code, 404)
        Player.objects.filter(user=self.marta).update(user=None)
        self.assertEqual(self.post(self.url, {"answer": "yes"}).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"answer": "yes"}, content_type="application/json").status_code, 401)
