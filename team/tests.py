from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.services import create_club
from core.similarity import is_similar
from players.models import Player
from .models import Team

User = get_user_model()


class SimilarNameTests(SimpleTestCase):
    def test_same_name_ignoring_case_accents_and_punctuation(self):
        self.assertTrue(is_similar("Pádel Tomares", "padel tomares"))
        self.assertTrue(is_similar("C.D. Tomares", "CD Tomares"))

    def test_contained_or_typo(self):
        self.assertTrue(is_similar("Tomares", "CD Tomares"))
        self.assertTrue(is_similar("Los Gladiadores", "Los Gladiadore"))
        self.assertTrue(is_similar("Juan Pérez", "Juan Perez García", min_subset_tokens=2))

    def test_different_names(self):
        self.assertFalse(is_similar("Tomares", "Burguillos"))
        self.assertFalse(is_similar("Juan Pérez", "Pedro Pérez", min_subset_tokens=2))
        # Un nombre de pila suelto no basta para avisar de todos los Juanes
        self.assertFalse(is_similar("Juan", "Juan Pérez García", min_subset_tokens=2))


class CreateTeamTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user, gender="F", country="ES")
        self.rival = Team.objects.create(club=self.club, name="CD Tomares", location="X", gender="M", country="ES",
                                         division="500")
        self.client.force_login(self.user)
        self.url = reverse("create_team")
        self.data = {"name": "Tomares", "location": "Tomares", "gender": "F", "country": "ES", "division": "500"}

    def test_gender_country_and_division_are_required(self):
        response = self.client.post(self.url, {"name": "Burguillos", "location": "X"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Team.objects.filter(name="Burguillos").exists())

    def test_creates_team_with_gender_country_and_division(self):
        response = self.client.post(self.url, {**self.data, "name": "Burguillos", "country": "PT", "division": "grand_slam"})
        self.assertRedirects(response, reverse("list_teams"), fetch_redirect_response=False)
        team = Team.objects.get(name="Burguillos")
        self.assertEqual((team.gender, team.country, team.division, team.club), ("F", "PT", "grand_slam", self.club))

    def test_similar_name_asks_before_creating(self):
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["similar"], ["CD Tomares (Masculino · España · 500)"])
        self.assertContains(response, 'data-open="1"')
        self.assertFalse(Team.objects.filter(name="Tomares").exists())

        response = self.client.post(self.url, {**self.data, "confirm_similar": "1"})
        self.assertRedirects(response, reverse("list_teams"), fetch_redirect_response=False)
        self.assertTrue(Team.objects.filter(name="Tomares").exists())

    def test_check_request_returns_similar_names_without_creating(self):
        response = self.client.post(self.url, self.data, HTTP_X_SIMILAR_CHECK="1")
        self.assertEqual(response.json(), {"valid": True, "similar": ["CD Tomares (Masculino · España · 500)"]})
        response = self.client.post(self.url, {"name": ""}, HTTP_X_SIMILAR_CHECK="1")
        self.assertEqual(response.json(), {"valid": False, "similar": []})
        self.assertFalse(Team.objects.filter(name="Tomares").exists())

    def test_same_name_in_same_division_is_rejected_even_after_confirming(self):
        # Sin distinguir mayúsculas, tildes ni signos, y aunque cambie la categoría
        response = self.client.post(self.url, {**self.data, "name": "C.D. TOMARES", "confirm_similar": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un equipo con ese nombre en esa división")
        self.assertEqual(Team.objects.filter(club=self.club).count(), 2)

    def test_same_name_in_other_division_asks_and_can_be_created(self):
        data = {**self.data, "name": "CD Tomares", "division": "1000"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.context["similar"], ["CD Tomares (Masculino · España · 500)"])
        self.client.post(self.url, {**data, "confirm_similar": "1"})
        self.assertEqual(Team.objects.filter(club=self.club, name="CD Tomares").count(), 2)

    def test_team_without_division_blocks_its_name_in_every_division(self):
        # Equipos creados antes de existir la división (p. ej. el propio del club)
        own = self.club.own_team
        response = self.client.post(self.url, {**self.data, "name": own.name.upper(), "confirm_similar": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Team.objects.filter(club=self.club, name__iexact=own.name).count(), 1)

    def test_editing_a_team_keeps_its_own_name(self):
        response = self.client.post(reverse("edit_team", args=[self.rival.public_id]),
                                    {**self.data, "name": "CD Tomares", "gender": "M"})
        self.assertRedirects(response, reverse("list_teams"), fetch_redirect_response=False)


class TeamGenderPropagationTests(TestCase):
    def test_players_take_the_gender_of_their_team(self):
        user = User.objects.create_user("admin", password="pass-12345")
        club = create_club("Club A", "Sevilla", user, gender="F", country="ES")
        player = Player.objects.create(club=club, name="Ana", last_name="López")
        self.assertEqual(player.gender, "F")

        own = club.own_team
        own.gender = "M"
        own.save()
        player.refresh_from_db()
        self.assertEqual(player.gender, "M")

    def test_edit_team_saves_gender_and_country(self):
        user = User.objects.create_user("admin", password="pass-12345")
        club = create_club("Club A", "Sevilla", user)
        player = Player.objects.create(club=club, name="Ana", last_name="López")
        self.client.force_login(user)
        self.client.post(reverse("edit_team", args=[club.own_team.public_id]),
                         {"name": "Club A", "location": "Sevilla", "gender": "F", "country": "IT", "division": "future",
                          "in_group": "on"})
        own = Team.objects.get(pk=club.own_team.pk)
        self.assertEqual((own.gender, own.country), ("F", "IT"))
        player.refresh_from_db()
        self.assertEqual(player.gender, "F")


class NewTeamDefaultsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user, gender="F", country="IT", division="1000")
        self.client.force_login(self.user)

    def test_form_starts_with_own_team_category_country_and_division_in_group(self):
        form = self.client.get(reverse("create_team")).context["form"]
        self.assertEqual({f: form[f].value() for f in ("gender", "country", "division", "in_group")},
                         {"gender": "F", "country": "IT", "division": "1000", "in_group": True})

    def test_team_in_group_copies_category_country_and_division_from_own_team(self):
        # Aunque llegue otro valor (o ninguno), un equipo del grupo juega en lo mismo que el propio.
        response = self.client.post(reverse("create_team"), {"name": "Burguillos", "location": "X", "gender": "M",
                                                             "in_group": "on"})
        self.assertRedirects(response, reverse("list_teams"), fetch_redirect_response=False)
        team = Team.objects.get(name="Burguillos")
        self.assertEqual((team.gender, team.country, team.division, team.in_group, team.is_own), ("F", "IT", "1000", True, False))

    def test_team_out_of_group_keeps_its_own_values(self):
        self.client.post(reverse("create_team"), {"name": "Burguillos", "location": "X", "gender": "M", "country": "ES",
                                                  "division": "500"})
        team = Team.objects.get(name="Burguillos")
        self.assertEqual((team.gender, team.country, team.division, team.in_group), ("M", "ES", "500", False))
        response = self.client.post(reverse("create_team"), {"name": "Gines", "location": "X"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Team.objects.filter(name="Gines").exists())

    def test_copied_division_counts_for_duplicate_names(self):
        Team.objects.create(club=self.club, name="Tomares", location="X", gender="F", country="IT", division="1000")
        response = self.client.post(reverse("create_team"), {"name": "TOMARES", "location": "X", "in_group": "on",
                                                             "confirm_similar": "1"})
        self.assertContains(response, "Ya existe un equipo con ese nombre en esa división")

    def test_fields_are_marked_to_hide_when_in_group(self):
        page = self.client.get(reverse("create_team"))
        self.assertEqual(page.content.decode().count("data-group-field"), 4)  # 3 campos + el script


class ManageTeamsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user, gender="F", country="ES", division="500")
        self.own = self.club.own_team
        self.a = Team.objects.create(club=self.club, name="Tomares", location="X", gender="F", country="ES", division="500")
        self.b = Team.objects.create(club=self.club, name="Burguillos", location="X", division="500", in_group=True)
        self.c = Team.objects.create(club=self.club, name="TOMARES", location="X", gender="F", country="ES",
                                     division="1000", in_group=True)
        self.client.force_login(self.user)
        self.url = reverse("manage_teams")

    def post_form(self, **changes):
        data = {}
        for t in (self.own, self.a, self.b, self.c):
            data.update({f"gender_{t.id}": t.gender, f"country_{t.id}": t.country, f"division_{t.id}": t.division})
            if t.in_group:
                data[f"in_group_{t.id}"] = "on"
        for key, value in changes.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        return self.client.post(self.url, data)

    def test_only_admins_see_the_page(self):
        member = User.objects.create_user("member", password="pass-12345")
        from core.models import Membership
        Membership.objects.create(user=member, club=self.club, role=Membership.MEMBER)
        self.client.force_login(member)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)

    def test_saves_several_teams_at_once(self):
        response = self.post_form(**{f"gender_{self.c.id}": "M", f"division_{self.b.id}": "grand_slam",
                                     f"gender_{self.b.id}": "M", f"in_group_{self.b.id}": None})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.c.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual((self.c.gender, self.c.in_group), ("M", True))
        self.assertEqual((self.b.gender, self.b.division, self.b.in_group), ("M", "grand_slam", False))

    def test_only_teams_in_group_are_shown_and_never_the_own_team(self):
        rows = self.client.get(self.url).context["rows"]
        self.assertEqual([r["team"] for r in rows], [self.b, self.c])

    def test_own_team_and_teams_out_of_group_are_not_touched(self):
        self.post_form(**{f"gender_{self.own.id}": "M", f"in_group_{self.own.id}": None, f"gender_{self.a.id}": "M"})
        self.own.refresh_from_db()
        self.a.refresh_from_db()
        self.assertEqual((self.own.gender, self.own.in_group, self.a.gender), ("F", True, "F"))

    def test_name_clash_with_a_team_out_of_group_is_detected(self):
        response = self.post_form(**{f"division_{self.c.id}": "500"})
        self.assertContains(response, "Ya existe un equipo con ese nombre en esa división")

    def test_invalid_or_blank_values_are_ignored(self):
        self.post_form(**{f"gender_{self.c.id}": "", f"division_{self.c.id}": "champions"})
        self.c.refresh_from_db()
        self.assertEqual((self.c.gender, self.c.division), ("F", "1000"))

    def test_same_name_in_same_division_saves_nothing(self):
        response = self.post_form(**{f"division_{self.c.id}": "500", f"gender_{self.b.id}": "M"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe un equipo con ese nombre en esa división")
        self.c.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual((self.c.division, self.b.gender), ("1000", ""))

    def test_teams_of_other_clubs_are_not_touched(self):
        other_user = User.objects.create_user("other", password="pass-12345")
        other = create_club("Club B", "Huelva", other_user, gender="F").own_team
        self.post_form(**{f"gender_{other.id}": "M"})
        other.refresh_from_db()
        self.assertEqual(other.gender, "F")
