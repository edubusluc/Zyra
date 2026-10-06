import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class PasswordResetTests(TestCase):
    """«¿Has olvidado tu contraseña?»: correo con el diseño de Zyra y formulario con los requisitos."""

    def setUp(self):
        self.user = User.objects.create_user("ana", email="ana@example.com", password="Vieja-clave-123")

    def request_reset(self, email="ana@example.com"):
        return self.client.post(reverse("account_reset_password"), {"email": email})

    def reset_link(self):
        return re.search(r"https?://\S+/password/reset/key/\S+/", mail.outbox[0].body).group(0)

    def test_reset_email_uses_zyra_layout(self):
        response = self.request_reset()
        self.assertRedirects(response, reverse("account_reset_password_done"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "Cambia tu contraseña de Zyra")
        self.assertEqual(email.to, ["ana@example.com"])
        self.assertIn("Zyra · Gestión de equipos de pádel", email.body)
        html = email.alternatives[0][0]
        self.assertIn("cid:zyra-logo", html)
        self.assertIn(self.reset_link(), html)
        self.assertIn("<strong>ana</strong>", html)
        self.assertNotIn("example.com]", email.subject)

    def test_unknown_email_gets_zyra_email(self):
        self.request_reset("nadie@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "No hay ninguna cuenta de Zyra con este email")
        self.assertIn("cid:zyra-logo", mail.outbox[0].alternatives[0][0])
        self.assertIn(reverse("register_club"), mail.outbox[0].body)

    def test_reset_pages_use_zyra_style(self):
        page = self.client.get(reverse("account_reset_password"))
        self.assertContains(page, 'class="z-auth-card"')
        self.assertContains(page, 'class="btn btn-primary btn-lg mt-2"')

    def test_new_password_form_shows_live_rules_and_changes_password(self):
        self.request_reset()
        form_url = self.client.get(self.reset_link())["Location"]
        page = self.client.get(form_url)
        self.assertContains(page, 'data-password-rules="password-rules"')
        self.assertContains(page, 'id="password-rules"')
        self.assertContains(page, 'data-username="ana"')
        self.assertContains(page, 'class="btn btn-primary btn-lg mt-2"')

        response = self.client.post(form_url, {"password1": "Nueva-clave-456", "password2": "Nueva-clave-456"})
        self.assertRedirects(response, reverse("account_reset_password_from_key_done"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Nueva-clave-456"))

    def test_invalid_link(self):
        page = self.client.get(reverse("account_reset_password_from_key", args=["zz", "set-password"]))
        self.assertContains(page, "Enlace no válido")

    def test_change_password_logged_in(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("account_change_password"))
        self.assertContains(page, "Contraseña actual")
        self.assertContains(page, 'data-password-rules="password-rules"')
        response = self.client.post(reverse("account_change_password"), {
            "oldpassword": "Vieja-clave-123", "password1": "Nueva-clave-456", "password2": "Nueva-clave-456",
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Nueva-clave-456"))
