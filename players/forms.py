"""Formularios de jugadores (alta, edición, perfil propio) y de la cuenta SNP del capitán."""
from django import forms
from django.utils.translation import gettext_lazy as _
from core.images import clean_photo_field
from core.similarity import same_name
from core.validators import plain_text
from .models import Player

def with_placeholder(choices):
    """Las opciones con «NONE» (sin indicar) al principio y rotulada «Elige una opción»."""
    return [("NONE", _("Elige una opción"))] + [c for c in choices if c[0] != "NONE"]


class PlayerForm (forms.ModelForm):
    """Alta de un jugador por el capitán: nombre, apellidos, posición, mano hábil y foto."""
    class Meta:
        model = Player
        fields = ['name', 'last_name', 'position', 'skillfull_hand', 'photo']

    def __init__(self, *args, **kwargs):
        """Pone «Elige una opción» en posición y mano hábil y limpia el texto de nombre y apellidos."""
        super().__init__(*args, **kwargs)
        self.fields['position'].choices = with_placeholder(Player.POSITIONS)
        self.fields['skillfull_hand'].choices = with_placeholder(Player.HAND)
        plain_text(self, 'name', 'last_name')

    def clean_photo(self):
        """Valida, reduce y pasa a WebP la foto antes de guardarla (core/images.py)."""
        return clean_photo_field(self)


class PlayerEditForm(forms.ModelForm):
    """
    Edición de un jugador. Antes la vista guardaba lo que llegara en el POST sin
    validar (posiciones inventadas, temporadas con cualquier formato, nombres de más
    de 100 caracteres); ahora se aplican las mismas reglas que al crearlo. El capitán
    también puede cambiar la foto (sin subir ninguna se queda la que tenía).
    """
    class Meta:
        model = Player
        fields = ['name', 'last_name', 'position', 'skillfull_hand', 'joined_season', 'in_team', 'photo']

    def __init__(self, *args, **kwargs):
        """Pone «Elige una opción» en posición y mano hábil y limpia el texto de nombre y apellidos."""
        super().__init__(*args, **kwargs)
        self.fields['position'].choices = with_placeholder(Player.POSITIONS)
        self.fields['skillfull_hand'].choices = with_placeholder(Player.HAND)
        self.fields['photo'].widget = forms.FileInput(attrs={"class": "form-control", "accept": "image/*"})
        plain_text(self, 'name', 'last_name')

    def clean_photo(self):
        """Valida, reduce y pasa a WebP la foto antes de guardarla (core/images.py)."""
        return clean_photo_field(self)


class OwnPlayerForm(forms.ModelForm):
    """El propio jugador edita su perfil: posición, mano hábil y foto (el nombre y la temporada, no)."""
    class Meta:
        model = Player
        fields = ['position', 'skillfull_hand', 'photo']

    def __init__(self, *args, **kwargs):
        """Pone «Elige una opción» en posición y mano hábil y las clases de Bootstrap en los campos."""
        super().__init__(*args, **kwargs)
        self.fields['position'].choices = with_placeholder(Player.POSITIONS)
        self.fields['skillfull_hand'].choices = with_placeholder(Player.HAND)
        for name, f in self.fields.items():
            f.widget.attrs["class"] = "form-control" if name == "photo" else "form-select"
        self.fields['photo'].widget = forms.FileInput(attrs={"class": "form-control", "accept": "image/*"})

    def clean_photo(self):
        """Valida, reduce y pasa a WebP la foto antes de guardarla (core/images.py)."""
        return clean_photo_field(self)


class NewOwnPlayerForm(OwnPlayerForm):
    """Quien entra con una invitación y no está en la lista crea su jugador."""
    class Meta(OwnPlayerForm.Meta):
        fields = ['name', 'last_name', 'position', 'skillfull_hand', 'photo']

    def __init__(self, *args, club=None, **kwargs):
        """``club`` es el club en el que se crea el jugador (para comprobar que no exista ya)."""
        self.club = club
        super().__init__(*args, **kwargs)
        for name in ('name', 'last_name'):
            self.fields[name].widget.attrs["class"] = "form-control"
        plain_text(self, 'name', 'last_name')

    def clean(self):
        """
        No se puede crear un jugador que ya existe en el club (mismo nombre y apellidos, sin
        distinguir mayúsculas, tildes ni signos): hay que elegirlo en la lista.
        """
        cleaned = super().clean()
        name, last_name = cleaned.get('name'), cleaned.get('last_name')
        if name and last_name:
            full = f"{name} {last_name}"
            if any(same_name(full, f"{p.name} {p.last_name}") for p in Player.objects.filter(club=self.club)):
                raise forms.ValidationError(
                    _("Ya existe un jugador con ese nombre en el club. Búscalo en la lista y pulsa «Soy yo».")
                )
        return cleaned


class SnpAccountForm(forms.Form):
    """
    Cuenta SNP del capitán. La contraseña solo es obligatoria si todavía no hay una guardada.
    No se pide el equipo: si la cuenta tiene varios, se lee el que se llama como el del club.
    """
    username = forms.CharField(label=_("Usuario de SNP"), max_length=150)
    password = forms.CharField(
        label=_("Contraseña de SNP"), required=False, widget=forms.PasswordInput(render_value=False),
        help_text=_("Se guarda cifrada. Déjala vacía para mantener la actual."),
    )

    def __init__(self, *args, has_password=False, **kwargs):
        """``has_password`` indica si ya hay una contraseña guardada (entonces puede dejarse vacía)."""
        super().__init__(*args, **kwargs)
        self.has_password = has_password
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"
        self.fields["username"].widget.attrs["autocomplete"] = "off"
        self.fields["password"].widget.attrs["autocomplete"] = "new-password"

    def clean_password(self):
        """Obligatoria solo si no hay una guardada; vacía significa mantener la actual."""
        password = self.cleaned_data["password"]
        if not password and not self.has_password:
            raise forms.ValidationError(_("Escribe la contraseña de SNP."))
        return password
