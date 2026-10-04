"""Formulario de alta y edición de equipos."""
from django import forms
from django.utils.translation import gettext as _
from core.images import clean_photo_field
from core.similarity import same_name
from core.validators import plain_text
from .models import Team

GROUP_FIELDS = ('gender', 'country', 'division')


class Teamform (forms.ModelForm):
    """
    Alta y edición de un equipo. Categoría, nacionalidad y división son obligatorias, y el
    nombre no puede repetirse en la misma división del club. Un equipo nuevo del grupo
    las copia del equipo propio (no se piden en el formulario).
    """
    class Meta:
        model = Team
        fields = ['name', 'gender', 'country', 'division', 'location', 'photo', 'in_group']

    def __init__(self, *args, club=None, **kwargs):
        """
        ``club`` es el club activo. Un equipo nuevo se propone en el grupo y con la categoría,
        nacionalidad y división del equipo propio. ``group_fields`` son las que se copian del
        equipo propio si el equipo nuevo es del grupo (las que este tiene rellenas).
        """
        self.club = club
        super().__init__(*args, **kwargs)
        own = club.own_team if club else None
        self.own_team = own
        self.group_fields = [f for f in GROUP_FIELDS if own and getattr(own, f)] if self.instance.pk is None else []
        if self.instance.pk is None and not self.is_bound:
            # Un equipo nuevo suele ser un rival del grupo del club: se propone en el grupo y
            # con la categoría, nacionalidad y división del equipo propio (se pueden cambiar).
            self.initial.setdefault('in_group', True)
            if own:
                for name in ('gender', 'country', 'division'):
                    if getattr(own, name):
                        self.initial.setdefault(name, getattr(own, name))
        plain_text(self, 'name', 'location')
        # Obligatorios en el formulario aunque los equipos antiguos los tengan vacíos.
        for name in ('gender', 'country', 'division'):
            self.fields[name].required = True
            self.fields[name].choices = [("", _("Elige una opción"))] + list(Team._meta.get_field(name).choices)
        if self.is_bound and self._copies_from_own_team():
            for name in self.group_fields:
                self.fields[name].required = False

    def _copies_from_own_team(self):
        """True si es un equipo nuevo marcado «en tu grupo»: se copian los datos del equipo propio."""
        return bool(self.group_fields) and self.fields['in_group'].widget.value_from_datadict(self.data, self.files, self.add_prefix('in_group'))

    def clean_photo(self):
        """Valida, reduce y pasa a WebP la foto antes de guardarla (core/images.py)."""
        return clean_photo_field(self)

    def clean(self):
        """
        No puede haber dos equipos del club con el mismo nombre (sin distinguir mayúsculas,
        tildes ni signos) en la misma división. Los equipos antiguos sin división cuentan
        para todas. Los nombres solo parecidos se avisan (ver core/similarity.py). En un equipo
        nuevo del grupo, categoría, nacionalidad y división se toman del equipo propio.
        """
        cleaned = super().clean()
        if self._copies_from_own_team():
            # Los equipos del grupo juegan en la misma categoría, país y división que el propio.
            for field in self.group_fields:
                cleaned[field] = getattr(self.own_team, field)
                setattr(self.instance, field, cleaned[field])
                self.errors.pop(field, None)
        name, division = cleaned.get('name'), cleaned.get('division')
        if name and division:
            others = Team.objects.filter(club=self.club, division__in=[division, ""]).exclude(pk=self.instance.pk)
            if any(same_name(name, t.name) for t in others):
                self.add_error('name', _("Ya existe un equipo con ese nombre en esa división en tu club."))
        return cleaned
