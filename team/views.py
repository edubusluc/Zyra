"""Vistas de equipos: lista, alta, edición y edición conjunta."""
from django.shortcuts import render, redirect, get_object_or_404
from .forms import Teamform
from .models import Team
from django.contrib import messages
from django.db import transaction
from django.utils.translation import gettext as _, ngettext
from django.views.decorators.http import require_GET, require_http_methods
from core.decorators import club_required, club_admin_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Q
from django.http import JsonResponse
from core import similarity

# Create your views here.
@club_required
@require_GET
def list_team(request):
    """
    Lista paginada de equipos del club con búsqueda por nombre o localidad. Requiere
    pertenecer al club y solo GET. Los capitanes ven también los equipos fuera del grupo.
    """
    search = request.GET.get('search', '').strip()

    # Los capitanes ven también los equipos fuera de grupo
    teams = Team.objects.filter(club=request.club)
    teams = teams.order_by('-in_group', 'name') if request.membership.is_admin else teams.filter(in_group=True).order_by('name')

    if search:
        teams = teams.filter(
            Q(name__icontains=search) | Q(location__icontains=search)
        )

    paginator = Paginator(teams, 4)  # Número de equipos por página
    page = request.GET.get('page')

    try:
        teams = paginator.page(page)
    except PageNotAnInteger:
        teams = paginator.page(1)
    except EmptyPage:
        teams = paginator.page(paginator.num_pages)

    return render(request, "list_teams.html", {"teams": teams, "search": search})

@club_admin_required
@require_http_methods(["GET", "POST"])
def create_team(request):
    """
    Alta de un equipo en el club. Solo capitanes; GET y POST.

    GET muestra el formulario con los valores del equipo propio. POST lo valida y, si hay
    equipos con un nombre igual o parecido, vuelve a mostrarlo para que se confirme. Las
    peticiones de comprobación responden en JSON sin crear nada. Al crearlo redirige a la
    lista de equipos.
    """
    similar = []
    if request.method == "POST":
        form = Teamform(request.POST, request.FILES, club=request.club)
        form.uploader, form.check_only = request.user, similarity.is_check_request(request)
        if form.is_valid():
            # Equipos con un nombre igual o parecido: se pregunta antes de crearlo.
            similar = similarity.similar_teams(request.club, form.cleaned_data['name'])
            if similarity.is_check_request(request):
                return JsonResponse({"valid": True, "similar": [similar_team_label(t) for t in similar]})
            if not similar or similarity.confirmed(request):
                team = form.save(commit=False)
                team.club = request.club
                team.save()
                return redirect("list_teams")
        else:
            if similarity.is_check_request(request):
                return JsonResponse({"valid": False, "similar": []})
            messages.error(request, _("Error al crear el equipo. Por favor, verifica los datos."))

    else:
        form = Teamform(club=request.club)

    for field in form:
        if field.name != 'in_group':
            field.field.widget.attrs.update({'class': 'form-select' if field.name in ('gender', 'country', 'division') else 'form-control'})

    return render(request, "create_team.html", {
        "form": form,
        "own_team": request.club.own_team,
        "similar": [similar_team_label(t) for t in similar],
    })


def similar_team_label(team):
    """«Tomares (Masculino · España · 500)», o solo el nombre si no tiene categoría ni país."""
    details = " · ".join(str(d) for d in (team.get_gender_display(), team.get_country_display(),
                                          team.get_division_display()) if d)
    return f"{team.name} ({details})" if details else team.name

@club_admin_required
@require_http_methods(["GET", "POST"])
def edit_team(request, team_id):
    """
    Edición de un equipo del club. Solo capitanes; GET muestra el formulario y POST lo guarda
    y redirige a la lista de equipos.
    """
    team = get_object_or_404(Team, public_id=team_id, club=request.club)

    if request.method == "POST":
        form = Teamform(request.POST, request.FILES, instance=team, club=request.club)
        form.uploader = request.user
        if form.is_valid():
            form.save()
            return redirect('list_teams')
        else:
            messages.error(request, _("Error al editar el equipo. Por favor, verifica los datos."))
    else:
        form = Teamform(instance=team, club=request.club)

    context = {
        'form': form,
        'team': team,
        'genders': Team.GENDERS,
        'countries': Team.COUNTRIES,
        'divisions': Team.DIVISIONS,
    }
    return render(request, 'edit_team.html', context)



BULK_FIELDS = ('gender', 'country', 'division')


@club_admin_required
@require_http_methods(["GET", "POST"])
def manage_teams(request):
    """
    Cambia de una vez categoría, nacionalidad, división y grupo de los equipos del grupo.
    No muestra el equipo propio (se edita desde su ficha) ni los equipos fuera del grupo.
    """
    club_teams = list(Team.objects.filter(club=request.club).order_by('name'))
    teams = [t for t in club_teams if t.in_group and not t.is_own]
    rows = [{"team": t, "error": "", **{f: getattr(t, f) for f in BULK_FIELDS}, "in_group": t.in_group} for t in teams]

    if request.method == "POST":
        valid = {f: {v for v, _label in Team._meta.get_field(f).choices} for f in BULK_FIELDS}
        for row in rows:
            team = row["team"]
            for f in BULK_FIELDS:
                value = request.POST.get(f"{f}_{team.id}", row[f])
                # No se puede dejar en blanco un dato que ya tenía (los equipos antiguos sí lo tienen vacío).
                if value in valid[f] or value == row[f]:
                    row[f] = value
            row["in_group"] = f"in_group_{team.id}" in request.POST
        # Mismas reglas que Teamform: el nombre no puede repetirse en una división; los
        # equipos sin división cuentan para todas. Se compara con todos los equipos del club.
        shown = {row["team"].pk for row in rows}
        others = rows + [{"team": t, "division": t.division} for t in club_teams if t.pk not in shown]
        for row in rows:
            changed = row["division"] != row["team"].division
            if not changed or not row["division"]:
                continue
            if any(o is not row and o["division"] in (row["division"], "") and similarity.same_name(row["team"].name, o["team"].name)
                   for o in others):
                row["error"] = _("Ya existe un equipo con ese nombre en esa división en tu club.")

        if any(row["error"] for row in rows):
            messages.error(request, _("No se ha guardado nada: revisa los equipos marcados."))
        else:
            changed = 0
            with transaction.atomic():
                for row in rows:
                    team = row["team"]
                    new = {f: row[f] for f in (*BULK_FIELDS, "in_group")}
                    if any(getattr(team, f) != v for f, v in new.items()):
                        for f, v in new.items():
                            setattr(team, f, v)
                        team.save()
                        changed += 1
            if changed:
                messages.success(request, ngettext("%(n)s equipo actualizado.", "%(n)s equipos actualizados.", changed) % {"n": changed})
            else:
                messages.info(request, _("No había cambios que guardar."))
            return redirect('manage_teams')

    return render(request, "manage_teams.html", {
        "rows": rows,
        "genders": Team.GENDERS,
        "countries": Team.COUNTRIES,
        "divisions": Team.DIVISIONS,
        "in_group_count": sum(r["in_group"] for r in rows),
    })
