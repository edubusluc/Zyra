"""Formularios de alta de club, registro de usuario, invitación de miembros y contraseñas."""
from allauth.account.forms import ChangePasswordForm, ResetPasswordKeyForm, SetPasswordForm
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import MinimumLengthValidator, get_default_password_validators
from django.template.loader import render_to_string
from django.utils.translation import gettext, gettext_lazy as _

from team.models import Team
from .blocklist import is_blocked
from .models import Membership
from .validators import plain_text

User = get_user_model()


def password_min_length():
    """Longitud mínima de MinimumLengthValidator en AUTH_PASSWORD_VALIDATORS (8 si no está)."""
    for validator in get_default_password_validators():
        if isinstance(validator, MinimumLengthValidator):
            return validator.min_length
    return 8


def password_rules(user=None):
    """
    Lista de requisitos de la contraseña (includes/password_rules.html) que
    static/js/password.js va marcando mientras se escribe. ``user``: cuenta cuya
    contraseña se cambia, para avisar si la nueva se parece a su usuario o email
    cuando el formulario no tiene esos campos.
    """
    return render_to_string("includes/password_rules.html", {
        "min_length": password_min_length(),
        "user": user,
    })


class ClubForm(forms.Form):
    """Datos del club nuevo y de su equipo propio."""
    name = forms.CharField(label=_("Nombre del club"), max_length=100)
    location = forms.CharField(label=_("Localización"), max_length=100)
    gender = forms.ChoiceField(label=_("Categoría"), choices=[("", _("Elige una opción"))] + Team.GENDERS,
                               help_text=_("Los jugadores del club tendrán esta categoría."))
    country = forms.ChoiceField(label=_("Nacionalidad del equipo"), choices=[("", _("Elige una opción"))] + Team.COUNTRIES)
    division = forms.ChoiceField(label=_("División"), choices=[("", _("Elige una opción"))] + Team.DIVISIONS)

    def __init__(self, *args, **kwargs):
        """Los nombres solo admiten texto plano (core.validators)."""
        super().__init__(*args, **kwargs)
        plain_text(self, "name", "location")


class CaptainPlayerForm(forms.Form):
    """
    Nombre y apellidos del capitán al registrar el club: con ellos se crea su jugador,
    enlazado a su cuenta. Deben coincidir con los de SNP para que se le asignen los puntos.
    """
    name = forms.CharField(label=_("Nombre"), max_length=100)
    last_name = forms.CharField(
        label=_("Apellidos"), max_length=100,
        help_text=_("Escríbelos exactamente como aparecen en SNP."),
    )

    def __init__(self, *args, **kwargs):
        """Los nombres solo admiten texto plano (core.validators)."""
        super().__init__(*args, **kwargs)
        plain_text(self, "name", "last_name")


class CaptainSnpForm(forms.Form):
    """
    Cómo se crea el jugador del capitán al registrar el club: escribiendo su nombre
    (CaptainPlayerForm) o conectando su cuenta de SNP, que trae todo el equipo con sus
    puntos; después elige cuál de esos jugadores es él. El usuario y la contraseña solo
    son obligatorios con la opción de SNP.
    """
    MANUAL = "manual"
    SNP = "snp"
    MODES = [
        (SNP, _("Conectar mi cuenta de SNP y traer mi equipo")),
        (MANUAL, _("Escribir mi nombre y apellidos")),
    ]
    mode = forms.ChoiceField(label=_("¿Cómo quieres empezar?"), choices=MODES, initial=MANUAL,
                             required=False, widget=forms.RadioSelect)
    username = forms.CharField(label=_("Usuario de SNP"), max_length=150, required=False)
    password = forms.CharField(
        label=_("Contraseña de SNP"), required=False, widget=forms.PasswordInput(render_value=False),
        help_text=_("Se guarda cifrada. Con ella actualizamos los puntos SNP de tu equipo cada semana."),
    )

    def __init__(self, *args, **kwargs):
        """El usuario y la contraseña no los autocompleta el navegador con los de Zyra."""
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["autocomplete"] = "off"
        self.fields["password"].widget.attrs["autocomplete"] = "new-password"

    @property
    def uses_snp(self):
        """True si el capitán ha elegido conectar su cuenta de SNP (según lo enviado)."""
        return self.data.get(self.add_prefix("mode")) == self.SNP

    def clean(self):
        """Con la opción de SNP, el usuario y la contraseña son obligatorios."""
        cleaned = super().clean()
        if cleaned.get("mode") == self.SNP:
            if not cleaned.get("username", "").strip():
                self.add_error("username", _("Escribe tu usuario de SNP."))
            if not cleaned.get("password"):
                self.add_error("password", _("Escribe la contraseña de SNP."))
        return cleaned


class SignUpForm(UserCreationForm):
    """
    Registro de una cuenta con usuario, email y contraseña (al registrar un club o desde
    una invitación). El email no puede estar ya en uso ni bloqueado.
    """
    email = forms.EmailField(
        label=_("Email"), help_text=_("Te enviaremos la confirmación del registro. También puedes usarlo para iniciar sesión."),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        """Traduce las etiquetas y añade la lista de requisitos de la contraseña."""
        super().__init__(*args, **kwargs)
        # UserCreationForm pone el foco en el usuario, pero en el alta de club ese campo va
        # después de los datos del club y la página saltaba hasta él al abrirse (y en el
        # móvil abría el teclado). La página empieza arriba, sin foco en ningún campo.
        self.fields["username"].widget.attrs.pop("autofocus", None)
        self.fields["username"].label = _("Usuario")
        self.fields["username"].help_text = _("Letras, números y @ . + - _ (máximo 150).")
        self.fields["password1"].label = _("Contraseña")
        # Lista de requisitos que static/js/password.js va marcando mientras se escribe.
        self.fields["password1"].help_text = password_rules()
        self.fields["password1"].widget.attrs["data-password-rules"] = "password-rules"
        self.fields["password2"].label = _("Repite la contraseña")
        self.fields["password2"].help_text = ""

    def clean_email(self):
        """Normaliza el email a minúsculas y rechaza los que ya tienen cuenta o están bloqueados."""
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(gettext("Ya hay una cuenta con este email: inicia sesión con ella."))
        if is_blocked(email):
            raise forms.ValidationError(gettext("Este email no puede registrarse en Zyra."))
        return email


class InviteMemberForm(forms.Form):
    """El capitán invita por email: la cuenta la crea el propio jugador desde el enlace."""
    email = forms.EmailField(
        label=_("Email del jugador"),
        help_text=_("Le enviaremos un enlace para registrarse (o unirse con su cuenta) como miembro. Caduca en 24 horas."),
    )

    def __init__(self, *args, club=None, **kwargs):
        """``club``: club al que se invita (para comprobar si el email ya es miembro)."""
        self.club = club
        super().__init__(*args, **kwargs)

    def clean_email(self):
        """Normaliza el email y rechaza los de miembros del club o bloqueados."""
        email = self.cleaned_data["email"].strip().lower()
        if Membership.objects.filter(club=self.club, user__email__iexact=email).exists():
            raise forms.ValidationError(gettext("Ese email ya pertenece a un miembro del club."))
        if is_blocked(email):
            raise forms.ValidationError(gettext("No se puede invitar a este email."))
        return email


class PasswordRulesMixin:
    """
    Formularios de allauth para elegir contraseña nueva: etiquetas de Zyra y la misma
    lista de requisitos que el registro, marcada mientras se escribe.
    """
    def __init__(self, *args, **kwargs):
        """Traduce las etiquetas, quita los placeholders en inglés y añade la lista de requisitos."""
        super().__init__(*args, **kwargs)
        if "oldpassword" in self.fields:
            self.fields["oldpassword"].label = _("Contraseña actual")
            self.fields["oldpassword"].help_text = ""
            self.fields["oldpassword"].widget.attrs.pop("placeholder", None)
        password1, password2 = self.fields["password1"], self.fields["password2"]
        password1.label = _("Contraseña nueva")
        password1.help_text = password_rules(self.user)
        password1.widget.attrs["data-password-rules"] = "password-rules"
        password1.widget.attrs.pop("placeholder", None)
        password2.label = _("Repite la contraseña nueva")
        password2.help_text = ""
        password2.widget.attrs.pop("placeholder", None)


class ZyraResetPasswordKeyForm(PasswordRulesMixin, ResetPasswordKeyForm):
    """Contraseña nueva desde el enlace del correo de «¿Has olvidado tu contraseña?»."""


class ZyraChangePasswordForm(PasswordRulesMixin, ChangePasswordForm):
    """Cambio de contraseña con la sesión iniciada (pide la actual)."""


class ZyraSetPasswordForm(PasswordRulesMixin, SetPasswordForm):
    """Primera contraseña de una cuenta creada con Google."""
