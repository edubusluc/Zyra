"""
Edición desde el back-office de la configuración de un club: su equipo y los rivales, sus jugadores y su
cuenta SNP. Es para corregir en persona lo que al capitán le cuesta (nacionalidad, división, nombre en
SNP…). Solo personal y por formulario; cada cambio queda en la auditoría con lo que había y lo que hay.
«Entrar como» sigue siendo de solo lectura: las ediciones se hacen aquí, nunca con la cuenta ajena.
"""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from core.crypto import DecryptionError
from core.models import Club
from players.forms import PlayerEditForm, SnpAccountForm
from players.models import Player, SnpAccount
from team.forms import Teamform
from team.models import Team

from .audit import audit
from .decorators import staff_required


def _style(form):
    """Clases de Bootstrap en los campos del formulario (el back-office no usa las plantillas del club)."""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, forms.Select):
            widget.attrs.setdefault("class", "form-select")
        else:
            widget.attrs.setdefault("class", "form-control")


def _changes(form):
    """
    Campos que ha cambiado el formulario como {campo: [antes, ahora]} para la auditoría. De la foto
    solo se anota que cambió y nunca se guarda la contraseña.
    """
    changes = {}
    for name in form.changed_data:
        if name == "password":
            changes[name] = ["", "cambiada"]
        elif name == "photo":
            changes[name] = ["", "cambiada"]
        else:
            changes[name] = [str(form.initial.get(name, "")), str(form.cleaned_data.get(name, ""))]
    return changes


def _render(request, form, title, back, club, multipart=True):
    """Página genérica de edición (``edit_form.html``)."""
    return render(request, "backoffice/edit_form.html", {
        "section": "clubs", "form": form, "title": title, "back": back, "club": club, "multipart": multipart,
    })


@staff_required
@require_http_methods(["GET", "POST"])
def team_edit(request, team_id):
    """Edita un equipo (el propio o un rival) de cualquier club con las mismas reglas que su capitán."""
    team = get_object_or_404(Team.objects.select_related("club"), public_id=team_id)
    form = Teamform(request.POST or None, request.FILES or None, instance=team, club=team.club)
    form.uploader = request.user
    _style(form)
    back = redirect("backoffice:club_detail", club_id=team.club.public_id).url
    if request.method == "POST" and form.is_valid():
        changes = _changes(form)
        form.save()
        if changes:
            audit(request, "team.edit", team, club=team.club.name, changes=changes)
        messages.success(request, _("Equipo guardado."))
        return redirect(back)
    return _render(request, form, _("Editar equipo: %(name)s") % {"name": team.name}, back, team.club)


@staff_required
@require_http_methods(["GET", "POST"])
def player_edit(request, player_id):
    """Edita un jugador de cualquier club con las mismas reglas que su capitán."""
    player = get_object_or_404(Player.objects.select_related("club"), public_id=player_id)
    form = PlayerEditForm(request.POST or None, request.FILES or None, instance=player)
    form.uploader = request.user
    _style(form)
    back = redirect("backoffice:club_detail", club_id=player.club.public_id).url
    if request.method == "POST" and form.is_valid():
        changes = _changes(form)
        form.save()
        if changes:
            audit(request, "player.edit", player, club=player.club.name, changes=changes)
        messages.success(request, _("Jugador guardado."))
        return redirect(back)
    return _render(request, form, _("Editar jugador: %(name)s") % {"name": player.full_name}, back, player.club)


class StaffSnpAccountForm(SnpAccountForm):
    """Cuenta SNP editada por el personal: además del usuario y la contraseña, el número del equipo en SNP."""
    team_id = forms.CharField(
        label=_("Equipo en SNP"), required=False, max_length=20,
        help_text=_("Número del equipo en SNP (…/equipo/view/4380). Vacío: se elige por el nombre del equipo del club."),
    )


@staff_required
@require_http_methods(["GET", "POST"])
def snp_account_edit(request, club_id):
    """
    Crea o cambia la cuenta SNP de un club (usuario, contraseña y equipo de SNP). La contraseña se
    deja vacía para mantener la actual; ni se muestra ni se anota en la auditoría.
    """
    club = get_object_or_404(Club, public_id=club_id)
    account = SnpAccount.objects.filter(club=club).first()
    initial = {}
    if account:
        initial["team_id"] = account.team_id
        try:
            initial["username"] = account.username
        except DecryptionError:
            messages.error(request, _("No se ha podido leer la cuenta guardada: escribe el usuario y la contraseña de nuevo."))
    form = StaffSnpAccountForm(request.POST or None, initial=initial, has_password=account is not None and bool(account.password_encrypted))
    _style(form)
    back = redirect("backoffice:club_detail", club_id=club.public_id).url
    if request.method == "POST" and form.is_valid():
        changes = _changes(form)
        account = account or SnpAccount(club=club)
        account.username = form.cleaned_data["username"]
        if form.cleaned_data["password"]:
            account.password = form.cleaned_data["password"]
        account.team_id = form.cleaned_data["team_id"].strip()
        account.updated_by = request.user
        account.save()
        audit(request, "club.snp_account", club, changes=changes or None)
        messages.success(request, _("Cuenta SNP guardada."))
        return redirect(back)
    return _render(request, form, _("Cuenta SNP de %(club)s") % {"club": club.name}, back, club, multipart=False)


@staff_required
@require_POST
def snp_import_reset(request, club_id):
    """Repone «Completar equipo» en la web de un club bloqueado por fallos: vuelve a contar desde cero."""
    club = get_object_or_404(Club, public_id=club_id)
    before = club.snp_import_failures
    club.snp_import_failures = 0
    club.save(update_fields=["snp_import_failures"])
    audit(request, "club.snp_import_reset", club, before=before)
    messages.success(request, _("«Completar equipo» vuelve a estar disponible para este club."))
    return redirect("backoffice:club_detail", club_id=club.public_id)
