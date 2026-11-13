"""
Selector de competición del alta de equipo (``register_club``): una tarjeta por competición, bloqueada si la
cuenta ya pertenece a un equipo de ella (capitán, gestor o jugador), filtrada por el país del equipo, y un
formulario que pide la división solo si la competición la tiene.
"""
import dataclasses
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core import competitions
from core.competition_picker import picker_entries
from core.competitions import LAPI, SNP
from core.forms import ClubForm
from core.models import Club, Membership
from core.services import create_club

User = get_user_model()
PASSWORD = "pass-12345-x"
PLAYER = {"player-name": "Ana", "player-last_name": "Ruiz", "snp-mode": "manual"}


def club_data(**extra):
    """Datos válidos de una alta de equipo en la LAPI."""
    return {"competition": "lapi", "name": "Pádel Norte", "location": "Sevilla", "gender": "M",
            "country": "ES", "division": "lapi_2", **PLAYER, **extra}


class PickerPageTests(TestCase):
    """Qué enseña el selector a cada visitante."""

    def test_anonymous_sees_every_competition_with_its_stage_and_no_lock(self):
        page = self.client.get(reverse("register_club"))
        for code in ("snp", "lapi"):
            self.assertContains(page, f'data-comp-card="{code}"')
        self.assertContains(page, "data-competition-stage")
        self.assertContains(page, "Liga Amateur de Pádel Internacional")
        self.assertNotContains(page, "is-locked")
        # El rol de capitán se explica en un «i», no en una nota visible.
        self.assertContains(page, "Serás el capitán de este equipo")
        self.assertContains(page, 'data-tip="Al crear el equipo serás su capitán y el encargado')

    def test_captain_of_snp_sees_it_locked_with_the_team_name(self):
        captain = User.objects.create_user("capi", password=PASSWORD)
        create_club("Gladiadores", "Sevilla", captain, gender="M", country="ES", division="500")
        self.client.login(username="capi", password=PASSWORD)
        page = self.client.get(reverse("register_club"))
        self.assertContains(page, "Ya perteneces al equipo «Gladiadores» (Capitán) en esta competición.")
        self.assertContains(page, 'class="z-comp-card is-locked" data-comp-card="snp"')
        self.assertNotContains(page, 'id="id_competition_snp"')
        self.assertContains(page, 'id="id_competition_lapi"')

    def test_player_of_a_team_sees_that_competition_locked_too(self):
        captain = User.objects.create_user("capi", password=PASSWORD)
        club = create_club("Gladiadores", "Sevilla", captain, gender="M", country="ES", division="500")
        member = User.objects.create_user("jugador", password=PASSWORD)
        Membership.objects.create(user=member, club=club, role=Membership.MEMBER)
        self.client.login(username="jugador", password=PASSWORD)
        page = self.client.get(reverse("register_club"))
        self.assertContains(page, "Ya perteneces al equipo «Gladiadores» (Miembro (solo lectura)) en esta competición.")
        self.assertNotContains(page, 'id="id_competition_snp"')

    def test_entries_carry_the_data_of_each_ficha(self):
        entries = {e["code"]: e for e in picker_entries([SNP], [])}
        self.assertTrue(entries["snp"]["free"])
        self.assertFalse(entries["lapi"]["free"])
        self.assertEqual(entries["snp"]["games"], 5)
        self.assertEqual(entries["lapi"]["points"], 3)
        self.assertEqual(entries["lapi"]["countries"], ["ES"])
        self.assertEqual(entries["lapi"]["rgb"], "97, 226, 201")


class LockedCompetitionTests(TestCase):
    """El servidor no deja crear un segundo equipo en una competición, aunque se fuerce el formulario."""

    def setUp(self):
        self.captain = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.club = create_club("Gladiadores LAPI", "Sevilla", self.captain, gender="M", country="ES",
                                division="lapi_1", competition="lapi")
        self.client.login(username="capi", password=PASSWORD)

    def test_captain_cannot_create_a_second_team_in_the_same_competition(self):
        response = self.client.post(reverse("register_club"), club_data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Club.objects.filter(competition="lapi").count(), 1)
        self.assertContains(response, "Ya tienes equipo en esa competición")

    def test_player_cannot_create_a_team_in_the_competition_of_his_team(self):
        player = User.objects.create_user("jugador", password=PASSWORD, email="j@example.com")
        Membership.objects.create(user=player, club=self.club, role=Membership.MEMBER)
        self.client.logout()
        self.client.login(username="jugador", password=PASSWORD)
        response = self.client.post(reverse("register_club"), club_data(name="Otro equipo"))
        self.assertEqual(Club.objects.filter(competition="lapi").count(), 1)
        self.assertContains(response, "Ya tienes equipo en esa competición")

    def test_other_competition_is_still_open(self):
        response = self.client.post(reverse("register_club"), club_data(competition="snp", division="500"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Club.objects.filter(competition="snp", memberships__user=self.captain).exists())


class CountryTests(TestCase):
    """La competición solo se ofrece en los países donde se juega."""

    def test_lapi_is_only_played_in_spain(self):
        self.assertTrue(LAPI.plays_in("ES"))
        self.assertFalse(LAPI.plays_in("MX"))
        self.assertTrue(SNP.plays_in("MX"))

    def test_lapi_team_in_another_country_is_rejected(self):
        form = ClubForm(club_data(country="MX"))
        self.assertFalse(form.is_valid())
        self.assertIn("country", form.errors)

    def test_snp_team_in_mexico_is_valid(self):
        form = ClubForm(club_data(competition="snp", country="MX", division="500"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_competition_without_countries_is_played_everywhere(self):
        everywhere = dataclasses.replace(SNP, code="mundial", countries=())
        self.assertTrue(everywhere.plays_in("SE"))


class DivisionTests(TestCase):
    """La división solo se pide si la competición tiene divisiones."""

    def test_division_is_required_when_the_competition_has_divisions(self):
        form = ClubForm(club_data(division=""))
        self.assertFalse(form.is_valid())
        self.assertIn("division", form.errors)

    def test_division_of_another_competition_is_rejected(self):
        form = ClubForm(club_data(division="500"))
        self.assertFalse(form.is_valid())
        self.assertIn("division", form.errors)

    def test_competition_without_divisions_does_not_ask_for_one(self):
        local = dataclasses.replace(LAPI, code="local", name="Liga local", divisions=(), countries=())
        with mock.patch.dict(competitions.COMPETITIONS, {"local": local}):
            form = ClubForm(club_data(competition="local", division="500", country="PT"), competitions=[local])
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["division"], "")
            form = ClubForm(club_data(competition="local", division=""), competitions=[local])
            self.assertTrue(form.is_valid(), form.errors)
