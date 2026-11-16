"""Formularios de la app de partidos: alta y edición de enfrentamientos, partidos y resultados."""
from django import forms
from django.db.models import Max, Q
from django.utils.translation import gettext_lazy as _
from core.competitions import CHOICES as COMPETITION_CHOICES, competition_for
from core.models import Club, REPORT_SCOPES, UserPreference
from .models import Match, Game, Result
from team.models import Team
from players.models import Player
from core.similarity import is_similar, same_name

class TeamSelect(forms.Select):
    """Select de equipos que lleva la foto de cada uno (data-photo) para pintar la card del formulario."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        """Añade a cada opción la URL de la foto del equipo en ``data-photo``."""
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        team = getattr(value, 'instance', None)
        if team is not None:
            option['attrs']['data-photo'] = team.photo.url if team.photo else ''
            option['attrs']['data-location'] = team.location or ''
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

    SIDES = [("local", _("En casa")), ("visiting", _("Fuera"))]

    # Competición del enfrentamiento: la del espacio (``Club.competition``). Solo informa, por eso
    # va bloqueada; para otra competición se cambia de espacio.
    competition = forms.ChoiceField(label=_("Competición"), choices=COMPETITION_CHOICES, initial="snp",
                                    disabled=True, required=False)
    mode = forms.ChoiceField(label=_("Modo"), choices=MODES, initial=COMPETITIVE, required=False,
                             widget=forms.RadioSelect)
    own_side = forms.ChoiceField(label=_("Tu equipo juega"), choices=SIDES, initial="local", required=False,
                                 widget=forms.RadioSelect)
    # Rival del equipo propio (un equipo del grupo): con ``own_side`` decide quién es local y quién
    # visitante. ``local`` y ``visiting`` se siguen aceptando por compatibilidad.
    rival = forms.ModelChoiceField(label=_("Rival"), queryset=Team.objects.none(), required=False,
                                   widget=TeamSelect(), empty_label=None)

    class Meta:
        model = Match
        fields = ['match_type', 'round_number', 'local', 'visiting', 'rival_name', 'start_date', 'start_time', 'location', 'report_scope',
                  'report_other_competitions']
        labels = {'local': _('Local'), 'visiting': _('Visitante'), 'rival_name': _('Nombre del rival'),
                  'start_date': _('Fecha'), 'start_time': _('Hora (opcional)'), 'location': _('Lugar'),
                  'report_scope': _('Datos del informe')}
        widgets = {
            'match_type': forms.Select(),
            'round_number': forms.NumberInput(attrs={'min': 1, 'max': 99, 'inputmode': 'numeric'}),
            'report_scope': forms.RadioSelect(),
            'report_other_competitions': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'rival_name': forms.TextInput(attrs={'placeholder': _('Ej.: Pádel Norte'), 'autocomplete': 'off', 'maxlength': 100,
                                                 'list': 'rival-suggestions'}),
            'start_time': forms.TimeInput(format='%H:%M', attrs={
                'type': 'text', 'inputmode': 'numeric', 'placeholder': '20:30', 'maxlength': 5, 'autocomplete': 'off',
                'pattern': '([01][0-9]|2[0-3]):[0-5][0-9]', 'data-time-24h': '', 'title': _('Hora en formato 24 h, por ejemplo 20:30')}),
            'location': forms.TextInput(attrs={'autocomplete': 'off', 'maxlength': 100}),
            'local': TeamSelect(),
            'visiting': TeamSelect(),
            'start_date': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'data-datepicker': '', 'data-placeholder': _('Elige el día del enfrentamiento')},
            ),
        }

    def __init__(self, *args, club=None, user=None, **kwargs):
        """Prepara los campos para el club ``club``.

        ``user`` es quien lo rellena: su preferencia de «Mi perfil» marca los datos del informe
        por defecto. Limita los equipos a los del club, propone el equipo propio como local en un
        formulario nuevo y marca el modo amistoso al editar un amistoso.
        """
        super(MatchForm, self).__init__(*args, **kwargs)
        self.club = club
        if club is not None:
            self.fields['competition'].initial = club.competition
        self.fields['report_scope'].choices = REPORT_SCOPES
        self.fields['report_scope'].widget.choices = REPORT_SCOPES
        # Si el formulario no lo envía, vale la preferencia de la cuenta.
        self.default_report_scope = UserPreference.report_scope_for(user)
        self.fields['report_scope'].required = False
        # «Incluir datos de otras competiciones»: solo si algún jugador del club con cuenta enlazada
        # tiene ficha en otro espacio.
        linked = Player.objects.filter(club=club, user__isnull=False).values("user")
        # Y solo de equipos que gestionan todos los destinatarios del informe (report.can_share_other_competition).
        from .report import can_share_other_competition
        self.other_competitions_available = bool(club) and any(
            can_share_other_competition(club, other_club) for other_club in Club.objects.filter(
                players__user__in=linked).exclude(pk=club.pk).distinct())
        if not self.instance.pk:
            self.initial['report_scope'] = self.default_report_scope
        self.own_team = club.own_team if club else None
        self._manual_team = None  # equipo ya existente con el que se une el rival escrito
        self._new_rival = None  # (nombre, localización) del rival escrito que hay que crear al guardar
        self.rival_matches = []  # equipos existentes con un nombre igual o parecido al escrito (aviso al capitán)
        self.rival_exact = False  # True si alguno se llama igual: solo se puede unir, no crear otro
        self._neutral = False
        # Solo los equipos con «En tu grupo» marcado; el propio siempre se puede elegir, esté o no en el grupo.
        # Los rivales de fuera del grupo se escriben por su nombre (amistoso y Play Off).
        teams = Team.objects.filter(club=club).filter(Q(in_group=True) | Q(is_own=True)).order_by('-is_own', 'name')
        missing_team = _("Uno de los equipos no existe.")
        self.fields['rival'].queryset = teams.filter(is_own=False)
        self.fields['rival'].empty_label = _("Elige equipo")
        self.fields['rival'].widget.choices = self.fields['rival'].choices
        self.fields['start_time'].required = False
        self.fields['start_time'].input_formats = ['%H:%M']
        self.fields['start_time'].error_messages.update(invalid=_("Hora no válida. Usa el formato HH:MM."))
        self.fields['location'].required = False
        # Lugar prerrellenado con el del equipo propio (juega en casa por defecto).
        if not self.is_bound and not self.initial.get('location') and self.own_team:
            self.initial['location'] = self.own_team.location
        # Hora prerrellenada con la habitual del equipo propio (editable); en visitante la elige quien crea el partido.
        if not self.is_bound and not self.instance.pk and not self.initial.get('start_time') and self.own_team:
            self.initial['start_time'] = self.own_team.default_time
        for name in ('local', 'visiting'):
            field = self.fields[name]
            field.queryset = teams
            field.required = True
            field.empty_label = _("Elige una opción")
            field.error_messages.update(required=_("Completa todos los campos."), invalid_choice=missing_team)
        if not self.is_bound and self.own_team and not self.initial.get('local') and not self.initial.get('visiting'):
            self.initial['local'] = self.own_team.pk
        # El tipo solo se elige en un partido competitivo, entre los de la competición del espacio
        # (Enfrentamiento, Reto, Play Off en SNP; Liga, Playoffs, Fase final en LAPI); si no se envía,
        # el primero. La jornada solo existe en la liga regular (``Competition.league_type``).
        self.rules = club.rules if club is not None else competition_for(None)
        self.fields['match_type'].required = False
        self.fields['match_type'].label = _("Tipo de enfrentamiento")
        self.fields['match_type'].choices = [(value, label) for value, label, _plural in self.rules.match_types]
        if not self.instance.pk:
            self.initial.setdefault('match_type', self.rules.default_type)
        if self.instance.pk and self.instance.is_friendly:
            self.initial['mode'] = self.FRIENDLY
            self.initial['match_type'] = self.rules.default_type
        self.has_rounds = bool(self.rules.league_type)
        self.fields['round_number'].required = False
        self.fields['round_number'].label = _("Jornada (opcional)")
        self.fields['round_number'].min_value = 1
        if not self.has_rounds:
            del self.fields['round_number']
        elif not self.instance.pk and not self.is_bound and club is not None:
            # Propone la jornada siguiente a la última de liga ya creada (S-09); se puede cambiar.
            last = Match.objects.filter(club=club, match_type=self.rules.league_type).aggregate(m=Max('round_number'))['m']
            if last:
                self.initial.setdefault('round_number', min(last + 1, 99))
        self.order_fields(['mode'])
        self.fields['rival_name'].required = False
        self.fields['match_type'].error_messages['invalid_choice'] = _("Tipo de enfrentamiento no válido.")
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
    def rival_team(self):
        """Rival elegido ahora (``rival`` o, si vienen ``local``/``visiting``, el que no es el propio)."""
        team = self._selected_team('rival')
        if team:
            return team
        for name in ('local', 'visiting'):
            other = self._selected_team(name)
            if other and not other.is_own:
                return other
        return None

    @property
    def own_side_value(self):
        """«local» o «visiting»: el lado del equipo propio según lo que se ha enviado (en casa por defecto)."""
        if self.is_bound and not self.data.get('own_side'):
            visiting = self._selected_team('visiting')
            if visiting and visiting.is_own:
                return "visiting"
        return self['own_side'].value() or "local"

    @property
    def local_team(self):
        """Equipo local elegido ahora, para pintar su card."""
        return self._selected_team('local')

    @property
    def visiting_team(self):
        """Equipo visitante elegido ahora, para pintar su card."""
        return self._selected_team('visiting')

    def clean_match_type(self):
        """Si no se envía tipo, el de por defecto de la competición (Enfrentamiento en SNP, Liga en LAPI)."""
        return self.cleaned_data.get('match_type') or self.rules.default_type

    def clean_report_scope(self):
        """Si no se envía, los datos del informe que prefiere la cuenta."""
        return self.cleaned_data.get('report_scope') or self.default_report_scope

    def clean_mode(self):
        """Si no se envía modo, es competitivo."""
        return self.cleaned_data.get('mode') or self.COMPETITIVE

    def clean_own_side(self):
        """Si no se envía, el equipo propio juega como local."""
        return self.cleaned_data.get('own_side') or "local"

    @property
    def is_neutral_type(self):
        """True si el tipo elegido siempre se juega en sede neutral (Play Off de la SNP), para pintar el formulario."""
        mode = self['mode'].value() or self.COMPETITIVE
        match_type = self['match_type'].value() or self.rules.default_type
        return mode != self.FRIENDLY and match_type in self.rules.neutral_types

    @property
    def typed_rival(self):
        """True si el rival se escribe por su nombre (amistoso o sede neutral), para pintar el formulario."""
        mode = self['mode'].value() or self.COMPETITIVE
        return mode == self.FRIENDLY or self.is_neutral_type

    @property
    def hide_place(self):
        """True si no se pregunta el lugar: amistoso en casa (es el del equipo propio)."""
        mode = self['mode'].value() or self.COMPETITIVE
        return mode == self.FRIENDLY and self.own_side_value != "visiting"

    def _rival_candidates(self):
        """Equipos del club (del grupo o no) con los que puede coincidir un rival escrito: los de su división y los
        sin división."""
        teams = Team.objects.filter(club=self.club, is_own=False)
        division = self.own_team.division if self.own_team else ""
        return list(teams.filter(division__in=[division, ""]) if division else teams)

    @property
    def rival_suggestions(self):
        """Nombres de los equipos existentes, para sugerirlos al escribir el rival."""
        return [t.name for t in self._rival_candidates()] if self.own_team else []

    def _clean_typed_rival(self, cleaned, neutral=False):
        """Rival escrito por su nombre (amistoso o Play Off). Si coincide con un equipo existente, del grupo o no,
        se avisa al capitán y elige unirlo a ese equipo o crear uno nuevo (``rival_link``: su id o «new»). Un
        equipo nuevo se crea al guardar, fuera del grupo. La localización se pide en la sede neutral y cuando se
        juega fuera; jugando en casa se usa la del equipo propio."""
        for name in ('local', 'visiting'):
            self.errors.pop(name, None)
        rival_name = " ".join((cleaned.get('rival_name') or "").split())
        location = " ".join((cleaned.get('location') or "").split())
        if not rival_name:
            self.add_error('rival_name', _("Escribe el nombre del equipo rival."))
            return cleaned
        if self.own_team is None:
            raise forms.ValidationError(_("Tu club no tiene equipo propio: no se pueden crear enfrentamientos."))
        if same_name(rival_name, self.own_team.name):
            self.add_error('rival_name', _("El rival no puede llamarse igual que tu equipo."))
            return cleaned
        own_local = neutral or cleaned.get('own_side') != "visiting"
        if not own_local or neutral:
            if not location:
                self.add_error('location', _("Escribe la localización de la sede.") if neutral
                               else _("Escribe la localización del equipo rival."))
        matches = [t for t in self._rival_candidates() if is_similar(rival_name, t.name)]
        exact = any(same_name(rival_name, t.name) for t in matches)
        choice = (self.data.get('rival_link') or "").strip()
        chosen = next((t for t in matches if choice.isdigit() and t.pk == int(choice)), None)
        if matches and not chosen and not (choice == "new" and not exact):
            self.rival_matches, self.rival_exact = matches, exact
            self.add_error('rival_name', _("Ya existe un equipo con un nombre igual o parecido. Elige si es el mismo o crea uno nuevo."))
        if self.errors:
            return cleaned
        if chosen:
            self._manual_team = chosen
        else:
            self._new_rival = (rival_name, location if not own_local else "")
        cleaned['rival_name'] = ""
        cleaned['local'] = self.own_team if own_local else None
        cleaned['visiting'] = None if own_local else self.own_team
        if own_local and not neutral and not location:
            cleaned['location'] = self.own_team.location or ""
        return cleaned

    def clean(self):
        """Ajusta el tipo de un amistoso, la sede neutral del Play Off y comprueba los equipos.

        Los dos equipos deben ser distintos y uno de ellos el propio del club. En un amistoso y en un Play
        Off de la SNP (sede neutral, sin local ni visitante) el rival se escribe por su nombre: se une al
        equipo existente que coincida (con aviso al capitán) o se crea uno nuevo fuera del grupo.
        """
        cleaned = super().clean()
        # La jornada solo se guarda en un enfrentamiento de liga.
        if self.has_rounds and (cleaned.get('mode') == self.FRIENDLY or cleaned.get('match_type') != self.rules.league_type):
            cleaned['round_number'] = None
        # Un amistoso no tiene tipo (enfrentamiento, reto, play off): se guarda como AMISTOSO.
        friendly = cleaned.get('mode') == self.FRIENDLY
        if friendly:
            self.errors.pop('match_type', None)
            cleaned['match_type'] = Match.AMISTOSO
        # Los tipos de sede neutral no tienen lado: el propio ocupa el local solo para guardar el resultado.
        self._neutral = not friendly and cleaned.get('match_type') in self.rules.neutral_types
        if self._neutral:
            cleaned['own_side'] = "local"
        # Amistoso y sede neutral: el rival se escribe por su nombre (sin nombre, solo valen un equipo ya elegido).
        if (friendly or self._neutral) and (cleaned.get('rival_name') or not (
                cleaned.get('rival') or cleaned.get('local') or cleaned.get('visiting'))):
            return self._clean_typed_rival(cleaned, neutral=self._neutral)
        cleaned['rival_name'] = ""
        rival = cleaned.get('rival')
        if rival and self.own_team is not None and not (cleaned.get('local') and cleaned.get('visiting')):
            # Rival elegido en una sola card + «en casa / fuera»: de ahí salen local y visitante.
            self.errors.pop('local', None)
            self.errors.pop('visiting', None)
            own_local = cleaned.get('own_side') != "visiting"
            cleaned['local'], cleaned['visiting'] = (self.own_team, rival) if own_local else (rival, self.own_team)
        elif not (cleaned.get('local') or cleaned.get('visiting')):
            self.add_error('rival', _("Elige el equipo rival."))
        local, visiting = cleaned.get('local'), cleaned.get('visiting')
        if local and visiting:
            if local == visiting:
                raise forms.ValidationError(_("El equipo local y el visitante no pueden ser el mismo."))
            # El equipo del capitán (el equipo propio del club) tiene que jugar el partido.
            if self.own_team is None:
                raise forms.ValidationError(_("Tu club no tiene equipo propio: no se pueden crear enfrentamientos."))
            if self.own_team not in (local, visiting):
                raise forms.ValidationError(
                    _("Tu equipo (%(team)s) tiene que jugar el enfrentamiento: elígelo como local o visitante.")
                    % {"team": self.own_team}
                )
        return cleaned

    def _create_rival(self):
        """Crea el rival escrito como equipo fuera del grupo (con la categoría, el país y la división del propio);
        None si no hay que crear ninguno."""
        if not self._new_rival:
            return None
        name, location = self._new_rival
        own = self.own_team
        return Team.objects.create(club=self.club, name=name, location=location, in_group=False,
                                   gender=own.gender, country=own.country, division=own.division)

    def save(self, commit=True):
        """Guarda el enfrentamiento asignándolo al club del formulario."""
        match = super().save(commit=False)
        match.club = self.club
        match.neutral_venue = self._neutral
        rival = self._manual_team or self._create_rival()
        if rival:
            # El rival escrito ocupa el lado que no es el del equipo propio.
            if match.local_id == self.own_team.pk:
                match.visiting = rival
            else:
                match.local = rival
        if commit:
            match.save()
        return match

class MatchDateForm(forms.ModelForm):
    """Cambio de la fecha y la hora de un partido ya creado (mismos campos, formato y mensajes que el alta).

    Al cambiar la fecha se recalcula la temporada, que se deriva de ella. La hora es opcional.
    """

    class Meta:
        model = Match
        fields = ['start_date', 'start_time']
        labels = {'start_date': _('Fecha'), 'start_time': _('Hora (opcional)')}
        widgets = {'start_date': MatchForm.Meta.widgets['start_date'],
                   'start_time': MatchForm.Meta.widgets['start_time']}

    def __init__(self, *args, **kwargs):
        """Fija el formato ISO y el mensaje de fecha no válida, como en ``MatchForm``."""
        super().__init__(*args, **kwargs)
        date_error = _("Fecha no válida. Usa el formato AAAA-MM-DD.")
        self.fields['start_date'].input_formats = ['%Y-%m-%d']
        self.fields['start_date'].error_messages.update(required=date_error, invalid=date_error)
        self.fields['start_time'].required = False
        self.fields['start_time'].input_formats = ['%H:%M']
        self.fields['start_time'].error_messages.update(invalid=_("Hora no válida. Usa el formato HH:MM."))

    def save(self, commit=True):
        """Guarda la fecha y la hora y, si cambió, deja que ``Match.save`` recalcule la temporada."""
        match = super().save(commit=False)
        if 'start_date' in self.changed_data:
            match.season = ""
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