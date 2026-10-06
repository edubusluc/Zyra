"""Formularios de la app de partidos: alta y edición de enfrentamientos, partidos y resultados."""
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from .models import Match, Game, Result
from team.models import Team
from core.similarity import same_name

class TeamSelect(forms.Select):
    """Select de equipos que lleva la foto de cada uno (data-photo) para pintar la card del formulario."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        """Añade a cada opción la URL de la foto del equipo en ``data-photo``."""
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        team = getattr(value, 'instance', None)
        if team is not None:
            option['attrs']['data-photo'] = team.photo.url if team.photo else ''
        return option


class MatchForm(forms.ModelForm):
    """Alta y edición de un enfrentamiento del club.

    Los equipos se limitan a los del club que están en el grupo (y siempre el propio),
    que tiene que jugar como local o visitante. En modo amistoso el partido se guarda
    con tipo AMISTOSO; en competitivo, el tipo por defecto es enfrentamiento.
    """
    COMPETITIVE = "competitivo"
    FRIENDLY = "amistoso"
    MODES = [(COMPETITIVE, _("Competitivo")), (FRIENDLY, _("Amistoso"))]

    GROUP = "grupo"
    MANUAL = "manual"
    RIVAL_SOURCES = [(GROUP, _("Equipo del grupo")), (MANUAL, _("Escribir nombre"))]
    SIDES = [("local", _("Local")), ("visiting", _("Visitante"))]

    mode = forms.ChoiceField(label=_("Modo"), choices=MODES, initial=COMPETITIVE, required=False,
                             widget=forms.RadioSelect)
    # Solo en amistosos: el rival puede ser un equipo del grupo o un nombre escrito a mano
    # (no se crea ningún equipo; el nombre se guarda en el propio partido).
    rival_source = forms.ChoiceField(label=_("Rival"), choices=RIVAL_SOURCES, initial=GROUP, required=False,
                                     widget=forms.RadioSelect)
    own_side = forms.ChoiceField(label=_("Tu equipo juega como"), choices=SIDES, initial="local", required=False,
                                 widget=forms.RadioSelect)

    class Meta:
        model = Match
        fields = ['match_type', 'local', 'visiting', 'rival_name', 'start_date']
        labels = {'local': _('Local'), 'visiting': _('Visitante'), 'rival_name': _('Nombre del rival'),
                  'start_date': _('Fecha')}
        widgets = {
            'match_type': forms.Select(),
            'rival_name': forms.TextInput(attrs={'placeholder': _('Ej.: Pádel Norte'), 'autocomplete': 'off'}),
            'local': TeamSelect(),
            'visiting': TeamSelect(),
            'start_date': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'data-datepicker': '', 'data-placeholder': _('Elige el día del partido')},
            ),
        }

    def __init__(self, *args, club=None, **kwargs):
        """Prepara los campos para el club ``club``.

        Limita los equipos a los del club, propone el equipo propio como local en un
        formulario nuevo y marca el modo amistoso al editar un amistoso.
        """
        super(MatchForm, self).__init__(*args, **kwargs)
        self.club = club
        self.own_team = club.own_team if club else None
        # El equipo propio siempre se puede elegir, aunque no esté marcado "en el grupo".
        teams = Team.objects.filter(club=club).filter(Q(in_group=True) | Q(is_own=True)).order_by('-is_own', 'name')
        missing_team = _("Uno de los equipos no existe.")
        for name in ('local', 'visiting'):
            field = self.fields[name]
            field.queryset = teams
            field.required = True
            field.empty_label = _("Elige una opción")
            field.error_messages.update(required=_("Por favor, completa todos los campos."), invalid_choice=missing_team)
        if not self.is_bound and self.own_team and not self.initial.get('local') and not self.initial.get('visiting'):
            self.initial['local'] = self.own_team.pk
        # El tipo solo se elige en un partido competitivo; si no se envía, es un enfrentamiento.
        self.fields['match_type'].required = False
        self.fields['match_type'].choices = Match.COMPETITIVE_TYPES
        if self.instance.pk and self.instance.is_friendly:
            self.initial['mode'] = self.FRIENDLY
            self.initial['match_type'] = Match.ENFRENTAMIENTO
        self.order_fields(['mode'])
        self.fields['rival_name'].required = False
        self.fields['match_type'].error_messages['invalid_choice'] = _("Tipo de partido no válido.")
        date_error = _("Fecha no válida. Usa el formato AAAA-MM-DD.")
        self.fields['start_date'].input_formats = ['%Y-%m-%d']
        self.fields['start_date'].error_messages.update(required=date_error, invalid=date_error)

    def _selected_team(self, name):
        """Equipo elegido ahora en ``name`` (para pintar la card); None si no hay o no es válido."""
        value = self[name].value()
        if not value:
            return None
        return self.fields[name].queryset.filter(pk=value).first() if str(value).isdigit() else None

    @property
    def local_team(self):
        """Equipo local elegido ahora, para pintar su card."""
        return self._selected_team('local')

    @property
    def visiting_team(self):
        """Equipo visitante elegido ahora, para pintar su card."""
        return self._selected_team('visiting')

    def clean_match_type(self):
        """Si no se envía tipo, es un enfrentamiento."""
        return self.cleaned_data.get('match_type') or Match.ENFRENTAMIENTO

    def clean_mode(self):
        """Si no se envía modo, es competitivo."""
        return self.cleaned_data.get('mode') or self.COMPETITIVE

    def clean_rival_source(self):
        """Si no se envía, el rival es un equipo del grupo."""
        return self.cleaned_data.get('rival_source') or self.GROUP

    def clean_own_side(self):
        """Si no se envía, el equipo propio juega como local."""
        return self.cleaned_data.get('own_side') or "local"

    @property
    def manual_rival(self):
        """True si el formulario está en amistoso con el rival escrito a mano (para pintarlo)."""
        mode = self['mode'].value() or self.COMPETITIVE
        return mode == self.FRIENDLY and self['rival_source'].value() == self.MANUAL

    def _clean_manual_rival(self, cleaned):
        """Amistoso contra un rival escrito a mano: el propio en su lado y el otro vacío."""
        for name in ('local', 'visiting'):
            self.errors.pop(name, None)
        rival_name = " ".join((cleaned.get('rival_name') or "").split())
        if not rival_name:
            self.add_error('rival_name', _("Escribe el nombre del equipo rival."))
            return cleaned
        if self.own_team is None:
            raise forms.ValidationError(_("Tu club no tiene equipo propio: no se pueden crear partidos."))
        if same_name(rival_name, self.own_team.name):
            self.add_error('rival_name', _("El rival no puede llamarse igual que tu equipo."))
            return cleaned
        cleaned['rival_name'] = rival_name
        own_local = cleaned.get('own_side') != "visiting"
        cleaned['local'] = self.own_team if own_local else None
        cleaned['visiting'] = None if own_local else self.own_team
        return cleaned

    def clean(self):
        """Ajusta el tipo de un amistoso y comprueba los equipos.

        Los dos equipos deben ser distintos y uno de ellos el propio del club. En un
        amistoso el rival puede escribirse a mano: entonces ese lado queda vacío y solo se
        guarda su nombre en el partido.
        """
        cleaned = super().clean()
        # Un amistoso no tiene tipo (enfrentamiento, reto, play off): se guarda como AMISTOSO.
        if cleaned.get('mode') == self.FRIENDLY:
            self.errors.pop('match_type', None)
            cleaned['match_type'] = Match.AMISTOSO
            if cleaned.get('rival_source') == self.MANUAL:
                return self._clean_manual_rival(cleaned)
        # El nombre escrito a mano solo vale para un amistoso contra un rival fuera del grupo.
        cleaned['rival_name'] = ""
        local, visiting = cleaned.get('local'), cleaned.get('visiting')
        if local and visiting:
            if local == visiting:
                raise forms.ValidationError(_("El equipo local y el visitante no pueden ser el mismo."))
            # El equipo del capitán (el equipo propio del club) tiene que jugar el partido.
            if self.own_team is None:
                raise forms.ValidationError(_("Tu club no tiene equipo propio: no se pueden crear partidos."))
            if self.own_team not in (local, visiting):
                raise forms.ValidationError(
                    _("Tu equipo (%(team)s) tiene que jugar el partido: elígelo como local o visitante.")
                    % {"team": self.own_team}
                )
        return cleaned

    def save(self, commit=True):
        """Guarda el enfrentamiento asignándolo al club del formulario."""
        match = super().save(commit=False)
        match.club = self.club
        if commit:
            match.save()
        return match

class GameForm (forms.ModelForm):
    """Formulario de un partido por parejas (número y jugadores)."""
    class Meta:
        model = Game
        fields= ['n_game', 'player_1_local', 'player_2_local', 'player_1_visiting', 'player_2_visiting']


class ResultForm(forms.ModelForm):
    """Formulario del resultado de un partido."""
    class Meta:
        model = Result
        fields = ['result']