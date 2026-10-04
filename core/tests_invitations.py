import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.emails import LOGO_CID, send_welcome_email
from core.models import Club, Invitation, Membership
from core.services import create_club

User = get_user_model()

SIGNUP = {
    "username": "nuevo", "email": "nuevo@example.com",
    "password1": "Clave-Segura-123", "password2": "Clave-Segura-123",
    "player-name": "Nuevo", "player-last_name": "Jugador",
}

GOOGLE_ON = dict(
    GOOGLE_LOGIN_ENABLED=True,
    SOCIALACCOUNT_PROVIDERS={"google": {"APPS": [{"client_id": "id", "secret": "secret", "key": ""}]}},
)


class InvitationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("capitan", password="pass-12345", email="capitan@example.com")
        self.club = create_club("Club A", "Sevilla", self.admin)
        self.viewer = User.objects.create_user("viewer", password="pass-12345")
        Membership.objects.create(user=self.viewer, club=self.club, role=Membership.MEMBER)

    def invite(self, **kwargs):
        return Invitation.objects.create(club=self.club, created_by=self.admin, **kwargs)

    def url(self, invitation):
        return reverse("invitation", args=[invitation.token])

    # --- Creación y gestión ------------------------------------------------

    def test_captain_invites_by_email(self):
        self.client.login(username="capitan", password="pass-12345")
        response = self.client.post(reverse("create_invitation"), {"email": "Jugador@Example.com"})
        self.assertRedirects(response, reverse("club_members") + "#invitaciones", fetch_redirect_response=False)
        invitation = Invitation.objects.get(club=self.club)
        self.assertEqual((invitation.created_by, invitation.email), (self.admin, "jugador@example.com"))
        self.assertAlmostEqual(
            (invitation.expires_at - timezone.now()).total_seconds(), 24 * 3600, delta=60,
        )

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["jugador@example.com"])
        self.assertEqual(email.reply_to, ["capitan@example.com"])
        self.assertIn("Club A", email.subject)
        self.assertIn(f"http://testserver/core/invite/{invitation.token}/", email.body)
        self.assertIn(f"/core/invite/{invitation.token}/", email.alternatives[0][0])

        page = self.client.get(reverse("club_members"))
        self.assertContains(page, "jugador@example.com")
        self.assertContains(page, f"/core/invite/{invitation.token}/")

    def test_captain_generates_shareable_link(self):
        self.client.login(username="capitan", password="pass-12345")
        self.client.post(reverse("create_invitation_link"))
        invitation = Invitation.objects.get(club=self.club)
        self.assertEqual((invitation.created_by, invitation.email), (self.admin, ""))
        self.assertAlmostEqual(
            (invitation.expires_at - timezone.now()).total_seconds(), 24 * 3600, delta=60,
        )
        self.assertEqual(mail.outbox, [])
        page = self.client.get(reverse("club_members"))
        self.assertContains(page, f"/core/invite/{invitation.token}/")
        self.assertContains(page, "Enlace compartido")

    def test_members_cannot_generate_links(self):
        self.client.login(username="viewer", password="pass-12345")
        self.client.post(reverse("create_invitation_link"))
        self.assertFalse(Invitation.objects.exists())

    def test_reinviting_replaces_pending_invitation(self):
        self.client.login(username="capitan", password="pass-12345")
        self.client.post(reverse("create_invitation"), {"email": "j@example.com"})
        first = Invitation.objects.get()
        self.client.post(reverse("create_invitation"), {"email": "J@example.com"})
        self.assertFalse(Invitation.objects.filter(pk=first.pk).exists())
        self.assertEqual(Invitation.objects.filter(email="j@example.com").count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_cannot_invite_existing_member_or_invalid_email(self):
        self.client.login(username="capitan", password="pass-12345")
        response = self.client.post(reverse("create_invitation"), {"email": "CAPITAN@example.com"})
        self.assertContains(response, "ya pertenece a un miembro del club")
        response = self.client.post(reverse("create_invitation"), {"email": "no-es-un-email"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_failed_email_does_not_leave_invitation(self):
        self.client.login(username="capitan", password="pass-12345")
        with mock.patch("core.emails.ZyraEmail.send", side_effect=OSError("SMTP caído")):
            self.client.post(reverse("create_invitation"), {"email": "j@example.com"})
        self.assertFalse(Invitation.objects.exists())

    def test_members_cannot_create_invitations(self):
        self.client.login(username="viewer", password="pass-12345")
        self.client.post(reverse("create_invitation"), {"email": "j@example.com"})
        self.assertFalse(Invitation.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_used_and_expired_invitations_are_not_listed(self):
        used = self.invite(used_at=timezone.now())
        expired = self.invite(expires_at=timezone.now() - datetime.timedelta(minutes=1))
        active = self.invite()
        self.client.login(username="capitan", password="pass-12345")
        listed = [inv for inv, _ in self.client.get(reverse("club_members")).context["invitations"]]
        self.assertEqual(listed, [active])
        self.assertNotIn(used, listed)
        self.assertNotIn(expired, listed)

    def test_pending_invitations_are_paginated(self):
        for i in range(12):
            self.invite(email=f"jugador{i:02}@example.com")
        self.client.login(username="capitan", password="pass-12345")
        first = self.client.get(reverse("club_members"))
        self.assertEqual(len(first.context["invitations"]), 10)
        self.assertContains(first, "1 de 2")
        second = self.client.get(reverse("club_members"), {"page": 2})
        self.assertEqual(len(second.context["invitations"]), 2)
        listed = {inv for page in (first, second) for inv, _ in page.context["invitations"]}
        self.assertEqual(len(listed), 12)
        # Una página fuera de rango muestra la última en lugar de fallar.
        self.assertEqual(self.client.get(reverse("club_members"), {"page": 99}).context["invitations_page"].number, 2)

    def test_search_invitations_by_email_keeps_query_across_pages(self):
        for i in range(11):
            self.invite(email=f"ana{i:02}@example.com")
        self.invite(email="luis@example.com")
        link = self.invite()
        self.client.login(username="capitan", password="pass-12345")
        response = self.client.get(reverse("club_members"), {"q": "ANA"})
        self.assertEqual(response.context["invitations_page"].paginator.count, 11)
        self.assertContains(response, "?page=2&amp;q=ANA#invitaciones")
        listed = [inv for inv, _ in self.client.get(reverse("club_members"), {"q": "ANA", "page": 2}).context["invitations"]]
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0].email.startswith("ana"))

        response = self.client.get(reverse("club_members"), {"q": "luis"})
        self.assertEqual([inv.email for inv, _ in response.context["invitations"]], ["luis@example.com"])
        self.assertNotIn(link, [inv for inv, _ in response.context["invitations"]])

        response = self.client.get(reverse("club_members"), {"q": "nadie"})
        self.assertEqual(response.context["invitations"], [])
        self.assertContains(response, "No hay invitaciones pendientes para «nadie».")

    def test_revoke_is_scoped_to_the_admins_club(self):
        other_admin = User.objects.create_user("otro", password="pass-12345")
        create_club("Club B", "Madrid", other_admin)
        invitation = self.invite()
        self.client.login(username="otro", password="pass-12345")
        response = self.client.post(reverse("revoke_invitation", args=[invitation.public_id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Invitation.objects.filter(pk=invitation.pk).exists())

        self.client.login(username="capitan", password="pass-12345")
        self.client.post(reverse("revoke_invitation", args=[invitation.public_id]))
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())

    def test_captain_cannot_create_users(self):
        self.client.login(username="capitan", password="pass-12345")
        page = self.client.get(reverse("club_members"))
        self.assertNotContains(page, 'name="password"')
        self.assertNotContains(page, 'name="username"')
        self.client.post(reverse("club_members"), {
            "username": "manual", "password": "Clave-Segura-123", "email": "manual@example.com", "role": Membership.ADMIN,
        })
        self.assertFalse(User.objects.filter(username="manual").exists())

    # --- Registro desde la invitación --------------------------------------

    def test_register_from_invitation_joins_club_as_member_and_sends_welcome(self):
        invitation = self.invite()
        self.assertContains(self.client.get(self.url(invitation)), "Únete a Club A")

        response = self.client.post(self.url(invitation), SIGNUP)
        self.assertRedirects(response, reverse("my_player"), fetch_redirect_response=False)

        user = User.objects.get(username="nuevo")
        membership = Membership.objects.get(user=user, club=self.club)
        self.assertEqual(membership.role, Membership.MEMBER)
        invitation.refresh_from_db()
        self.assertEqual(invitation.used_by, user)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["nuevo@example.com"])
        self.assertIn("Te has unido a Club A", email.subject)
        self.assertIn("Usuario: nuevo", email.body)
        self.assertIn("Capitanes: capitan", email.body)
        html = email.alternatives[0][0]
        self.assertIn("capitan", html)
        self.assertIn("http://testserver/", html)

    def test_signup_from_invitation_prefills_email_and_shows_password_rules(self):
        page = self.client.get(self.url(self.invite(email="j@example.com")))
        self.assertContains(page, 'value="j@example.com"')
        self.assertContains(page, 'data-password-rules="password-rules"')
        self.assertContains(page, "Al menos 8 caracteres")
        self.assertContains(page, "Las dos contraseñas coinciden")
        self.assertContains(page, "js/password.js")

    def test_invitation_is_single_use(self):
        invitation = self.invite()
        self.client.post(self.url(invitation), SIGNUP)
        self.client.logout()
        response = self.client.post(self.url(invitation), {**SIGNUP, "username": "segundo", "email": "s@example.com"})
        self.assertEqual(response.status_code, 410)
        self.assertContains(response, "ya se ha usado", status_code=410)
        self.assertFalse(User.objects.filter(username="segundo").exists())

    def test_shared_link_works_for_many_people(self):
        self.client.login(username="capitan", password="pass-12345")
        self.client.post(reverse("create_invitation_link"))
        invitation = Invitation.objects.get(club=self.club)
        self.assertTrue(invitation.reusable)
        self.client.logout()
        self.client.post(self.url(invitation), SIGNUP)
        self.client.logout()
        self.client.post(self.url(invitation), {**SIGNUP, "username": "segundo", "email": "s@example.com"})
        self.assertEqual(
            set(Membership.objects.filter(club=self.club, user__username__in=["nuevo", "segundo"]).values_list("user__username", flat=True)),
            {"nuevo", "segundo"},
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.use_count, 2)
        # Sigue pendiente (y se puede anular) hasta que caduque.
        self.client.login(username="capitan", password="pass-12345")
        page = self.client.get(reverse("club_members"))
        self.assertContains(page, "2 personas se han unido")
        self.client.post(reverse("revoke_invitation", args=[invitation.public_id]))
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())

    def test_expired_shared_link_is_rejected(self):
        invitation = self.invite(reusable=True, expires_at=timezone.now() - datetime.timedelta(seconds=1))
        response = self.client.post(self.url(invitation), SIGNUP)
        self.assertContains(response, "ha caducado", status_code=410)

    def test_emailed_invitation_is_single_use(self):
        self.client.login(username="capitan", password="pass-12345")
        self.client.post(reverse("create_invitation"), {"email": "j@example.com"})
        invitation = Invitation.objects.get(club=self.club)
        self.assertFalse(invitation.reusable)
        self.client.logout()
        self.client.post(self.url(invitation), {**SIGNUP, "email": "j@example.com"})
        self.client.logout()
        response = self.client.post(self.url(invitation), {**SIGNUP, "username": "segundo", "email": "s@example.com"})
        self.assertEqual(response.status_code, 410)

    def test_expired_invitation_is_rejected(self):
        invitation = self.invite(expires_at=timezone.now() - datetime.timedelta(seconds=1))
        response = self.client.post(self.url(invitation), SIGNUP)
        self.assertContains(response, "ha caducado", status_code=410)
        self.assertFalse(User.objects.filter(username="nuevo").exists())

    def test_unknown_token_is_rejected(self):
        response = self.client.get(reverse("invitation", args=["no-existe"]))
        self.assertEqual(response.status_code, 410)

    def test_signup_requires_unique_email(self):
        invitation = self.invite()
        response = self.client.post(self.url(invitation), {**SIGNUP, "email": "CAPITAN@example.com"})
        self.assertContains(response, "Ya hay una cuenta con este email")
        self.assertFalse(User.objects.filter(username="nuevo").exists())
        invitation.refresh_from_db()
        self.assertFalse(invitation.is_used)

    def test_logged_in_user_joins_with_one_click(self):
        User.objects.create_user("jugador", password="pass-12345", email="j@example.com")
        invitation = self.invite()
        self.client.login(username="jugador", password="pass-12345")
        self.assertContains(self.client.get(self.url(invitation)), "Unirme como jugador")
        self.assertFalse(Membership.objects.filter(user__username="jugador").exists())

        self.client.post(self.url(invitation))
        self.assertTrue(Membership.objects.filter(user__username="jugador", club=self.club).exists())
        self.assertEqual(mail.outbox[0].to, ["j@example.com"])

    def test_existing_member_does_not_consume_invitation(self):
        invitation = self.invite()
        self.client.login(username="viewer", password="pass-12345")
        self.client.post(self.url(invitation))
        invitation.refresh_from_db()
        self.assertFalse(invitation.is_used)

    def test_returning_from_google_joins_automatically(self):
        invitation = self.invite()
        self.client.get(self.url(invitation))  # visitante anónimo abre el enlace
        google_user = User.objects.create_user("google", email="g@example.com")
        self.client.force_login(google_user)  # vuelve autenticado por Google
        response = self.client.get(self.url(invitation))
        self.assertRedirects(response, reverse("my_player"), fetch_redirect_response=False)
        self.assertTrue(Membership.objects.filter(user=google_user, club=self.club).exists())

    # --- Google -------------------------------------------------------------

    def test_google_button_hidden_without_credentials(self):
        invitation = self.invite()
        self.assertNotContains(self.client.get(self.url(invitation)), "Registrarme con Google")
        self.assertNotContains(self.client.get(reverse("login")), "Continuar con Google")

    @override_settings(**GOOGLE_ON)
    def test_google_button_shown_with_credentials(self):
        invitation = self.invite()
        page = self.client.get(self.url(invitation))
        self.assertContains(page, "Registrarme con Google")
        self.assertContains(page, "/accounts/google/login/")
        self.assertContains(self.client.get(reverse("login")), "Continuar con Google")
        self.assertContains(self.client.get(reverse("register_club")), "Crear mi cuenta con Google")

    @override_settings(**GOOGLE_ON)
    def test_google_login_redirects_to_google(self):
        response = self.client.post(reverse("google_login"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://accounts.google.com/"))

    def test_allauth_password_signup_is_closed(self):
        self.client.post(reverse("account_signup"), SIGNUP)
        self.assertFalse(User.objects.filter(username="nuevo").exists())


class PasswordCheckTests(TestCase):
    def check(self, **data):
        return self.client.post(reverse("password_check"), data).json()

    def test_reports_server_side_rules(self):
        self.assertEqual(self.check(password="Clave-Segura-123", username="nuevo"), {"similar": True, "common": True})
        self.assertFalse(self.check(password="password")["common"])
        self.assertFalse(self.check(password="jugadorpadel", username="jugadorpadel")["similar"])
        self.assertFalse(self.check(password="maria.lopez@example.com", email="maria.lopez@example.com")["similar"])

    def test_only_accepts_post(self):
        self.assertEqual(self.client.get(reverse("password_check")).status_code, 405)


class LoginAndWelcomeTests(TestCase):
    def test_login_with_email(self):
        User.objects.create_user("capitan", password="pass-12345", email="capitan@example.com")
        response = self.client.post(reverse("login"), {"username": "capitan@example.com", "password": "pass-12345"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_register_club_sends_welcome_with_created_team(self):
        self.client.post(reverse("register_club"), {
            "name": "Nuevo Club", "location": "Cádiz", "gender": "M", "country": "ES", "division": "future", **SIGNUP,
        })
        self.assertTrue(Club.objects.filter(name="Nuevo Club").exists())
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Has creado Nuevo Club", email.subject)
        self.assertIn("Equipo creado: Nuevo Club", email.body)
        self.assertIn("Capitanes: Nuevo Jugador", email.body)

    def test_welcome_is_skipped_without_email(self):
        user = User.objects.create_user("sinemail")
        club = create_club("Club", "X", user)
        self.assertFalse(send_welcome_email(user, club))
        self.assertEqual(mail.outbox, [])

    def test_welcome_failure_does_not_break_registration(self):
        with mock.patch("core.emails.ZyraEmail.send", side_effect=OSError("SMTP caído")):
            response = self.client.post(reverse("register_club"), {"name": "Club X", "location": "Y", "gender": "F", "country": "PT", "division": "500", **SIGNUP})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Club.objects.filter(name="Club X").exists())

    def test_corporate_footer_with_inline_logo(self):
        user = User.objects.create_user("u", email="u@example.com")
        send_welcome_email(user, create_club("Club", "X", user))
        email = mail.outbox[0]
        self.assertIn("Contacto: join.zyra@gmail.com", email.body)
        self.assertIn(f"cid:{LOGO_CID}", email.alternatives[0][0])
        self.assertIn("mailto:join.zyra@gmail.com", email.alternatives[0][0])

        mime = email.message()
        related = next(p for p in mime.walk() if p.get_content_type() == "multipart/related")
        logo = next(p for p in related.walk() if p.get_content_type() == "image/png")
        self.assertEqual(logo["Content-ID"], f"<{LOGO_CID}>")


@override_settings(**GOOGLE_ON)
class GoogleSameAccountTests(TestCase):
    """Entrar con Google usa la cuenta existente con el mismo email."""

    def setUp(self):
        self.admin = User.objects.create_user("capitan", password="pass-12345", email="Capitan@Example.com")
        self.club = create_club("Club A", "Sevilla", self.admin)

    def google_login(self, email, verified=True, sub="google-123"):
        from allauth.core import context
        from allauth.socialaccount.adapter import get_adapter
        from allauth.socialaccount.helpers import complete_social_login
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        request = RequestFactory().get("/accounts/google/login/callback/")
        request.session = SessionStore()
        request.user = AnonymousUser()
        request._messages = FallbackStorage(request)
        provider = get_adapter(request).get_provider(request, "google")
        sociallogin = provider.sociallogin_from_response(request, {
            "sub": sub, "email": email, "email_verified": verified, "name": "Capitán",
        })
        with context.request_context(request):
            complete_social_login(request, sociallogin)
        return request

    def test_google_login_uses_existing_account_and_keeps_password(self):
        request = self.google_login("capitan@example.com")
        self.assertEqual(request.user, self.admin)
        self.assertEqual(User.objects.count(), 1)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.has_usable_password())
        self.assertTrue(self.admin.socialaccount_set.filter(provider="google").exists())
        # Sigue pudiendo entrar con usuario y contraseña
        self.assertTrue(self.client.login(username="capitan", password="pass-12345"))

    def test_second_google_login_goes_to_same_account(self):
        self.google_login("capitan@example.com")
        request = self.google_login("capitan@example.com")
        self.assertEqual(request.user, self.admin)
        self.assertEqual(User.objects.count(), 1)

    def test_unverified_google_email_does_not_take_over_account(self):
        request = self.google_login("capitan@example.com", verified=False, sub="otro")
        self.assertNotEqual(request.user, self.admin)

    def test_new_email_creates_new_account_without_club(self):
        request = self.google_login("nuevo@example.com", sub="nuevo")
        self.assertNotEqual(request.user, self.admin)
        self.assertEqual(request.user.email, "nuevo@example.com")
        self.assertFalse(Membership.objects.filter(user=request.user).exists())

    # --- "Crear mi cuenta con Google" desde el alta de club -----------------

    def register_with_google(self, email, sub):
        """Vuelve de Google al formulario de alta de club con la sesión que deja allauth."""
        from django.conf import settings

        request = self.google_login(email, sub=sub)
        request.session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = request.session.session_key
        return self.client.get(reverse("register_club") + "?google=1", follow=True)

    def test_register_page_google_button_returns_to_register_club(self):
        response = self.client.get(reverse("register_club"))
        self.assertContains(response, 'name="next" value="/core/register_club/?google=1"')

    def test_existing_email_with_google_from_register_goes_home_not_to_create_club(self):
        response = self.register_with_google("capitan@example.com", sub="google-123")
        self.assertRedirects(response, reverse("home"))
        self.assertContains(response, "Ya tenías una cuenta con este email")
        self.assertEqual(Club.objects.count(), 1)

    def test_existing_email_without_club_lands_on_no_club_with_notice(self):
        User.objects.create_user("sinclub", password="pass-12345", email="sinclub@example.com")
        response = self.register_with_google("sinclub@example.com", sub="sinclub")
        self.assertRedirects(response, reverse("no_club"))
        self.assertContains(response, "Ya tenías una cuenta con este email")

    def test_new_email_with_google_from_register_continues_to_create_club(self):
        response = self.register_with_google("nuevo@example.com", sub="nuevo")
        self.assertRedirects(response, reverse("register_club"))
        self.assertContains(response, "Crear club")
        self.assertNotIn("google_new_account", self.client.session)
