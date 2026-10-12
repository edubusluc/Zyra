"""
Adaptadores de django-allauth: personalizan el alta y el inicio de sesión con
usuario/contraseña y con Google.

Se activan en settings (ACCOUNT_ADAPTER y SOCIALACCOUNT_ADAPTER).
"""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core import context as allauth_context
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

# Marca en la sesión que el último inicio de sesión con Google ha creado una cuenta
# nueva (y no ha entrado en una que ya existía con ese email).
GOOGLE_NEW_ACCOUNT_KEY = "google_new_account"


class AccountAdapter(DefaultAccountAdapter):
    """Adaptador de cuentas de allauth (usuario/email y contraseña)."""
    def is_open_for_signup(self, request):
        """
        Las cuentas con contraseña se crean desde una invitación, al registrar un
        club o las crea un capitán: el alta genérica de allauth queda cerrada.
        """
        return False

    def clean_email(self, email):
        """Un email bloqueado por el personal no se puede añadir a ninguna cuenta."""
        from django import forms
        from django.utils.translation import gettext as _

        from .blocklist import is_blocked

        email = super().clean_email(email)
        if is_blocked(email):
            raise forms.ValidationError(_("Este email no puede usarse en Zyra."))
        return email

    def add_message(self, *args, **kwargs):
        """Sin avisos de allauth ("Has iniciado sesión como..."): la app ya muestra los suyos."""
        pass

    def get_password_change_redirect_url(self, request):
        """Tras cambiar o crear la contraseña con la sesión iniciada, vuelve a «Mi perfil» con un aviso."""
        from django.contrib import messages
        from django.urls import reverse
        from django.utils.translation import gettext as _

        messages.success(request, _("Contraseña actualizada."))
        return reverse("my_profile")

    def render_mail(self, template_prefix, email, context, headers=None):
        """
        Correos de allauth (p. ej. «¿Has olvidado tu contraseña?») con el diseño de los de
        Zyra (core/emails.py): si hay plantilla ``<prefijo>_message.html`` en
        core/templates/account/email, su contenido va dentro del layout con el logo y el pie.
        Los que no la tienen salen como los manda allauth.
        """
        from .emails import build_email

        request = allauth_context.request
        try:
            html = render_to_string(f"{template_prefix}_message.html", context, request)
        except TemplateDoesNotExist:
            return super().render_mail(template_prefix, email, context, headers)
        subject = render_to_string(f"{template_prefix}_subject.txt", context, request)
        subject = self.format_email_subject(" ".join(subject.splitlines()).strip())
        text = render_to_string(f"{template_prefix}_message.txt", context, request)
        msg = build_email(subject, text, html, to=[email] if isinstance(email, str) else email)
        msg.from_email = self.get_from_email()
        msg.extra_headers.update(headers or {})
        return msg


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Adaptador de allauth para el inicio de sesión con Google."""
    def is_open_for_signup(self, request, sociallogin):
        """
        Cualquiera puede crear su cuenta con Google (salvo con un email bloqueado por el
        personal); para ver datos de un club tiene que unirse con una invitación o
        registrar el suyo.
        """
        from .blocklist import is_blocked

        emails = [a.email for a in sociallogin.email_addresses] or [getattr(sociallogin.user, "email", "")]
        return not any(is_blocked(e) for e in emails)

    def save_user(self, request, sociallogin, form=None):
        """
        Crea la cuenta nueva y lo marca en la sesión (GOOGLE_NEW_ACCOUNT_KEY).
        Solo se llama cuando Google crea una cuenta nueva.
        """
        user = super().save_user(request, sociallogin, form)
        request.session[GOOGLE_NEW_ACCOUNT_KEY] = True
        return user

    def authenticate_by_email(self, sociallogin):
        """
        Quien entra con Google accede a la cuenta que ya existe con ese email.

        Frente al comportamiento por defecto de allauth:
        - El email se compara sin distinguir mayúsculas (Edu@Gmail.com = edu@gmail.com).
        - Si por datos antiguos hay varias cuentas con el mismo email, se elige la que
          pertenece a más clubes (y, a igualdad, la más antigua).
        - El email queda marcado como verificado, porque Google lo acaba de verificar.
          Así allauth no invalida la contraseña de la cuenta: el usuario puede seguir
          entrando también con usuario/email y contraseña.
        """
        User = get_user_model()
        for address in sociallogin.email_addresses:
            if not address.verified or not self.can_authenticate_by_email(sociallogin, address.email):
                continue
            user = (
                User.objects.filter(email__iexact=address.email, is_active=True)
                .annotate(n_clubs=Count("memberships"))
                .order_by("-n_clubs", "id")
                .first()
            )
            if user is not None:
                _mark_verified(user, address.email)
                return user, address.email
        return None


def _mark_verified(user, email):
    """Marca ``email`` como verificado para ``user`` en allauth, creándolo si no existe."""
    record = EmailAddress.objects.filter(user=user, email__iexact=email).first()
    if record is None:
        EmailAddress.objects.create(
            user=user, email=email.lower(), verified=True,
            primary=not EmailAddress.objects.filter(user=user, primary=True).exists(),
        )
    elif not record.verified:
        record.verified = True
        record.save(update_fields=["verified"])
