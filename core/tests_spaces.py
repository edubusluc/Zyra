"""
Espacios por competición (fase 1a): cada club guarda su competición, una cuenta tiene como mucho
un espacio por competición, se crea otro espacio desde el menú y el de LAPI juega con su ficha.
"""
import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from core.competitions import LAPI, SNP, competition_for
from core.models import Club, Invitation, Membership
from core.services import club_of, create_club, free_competitions
from match.models import Match
from match.phase import phases_for
from players.models import Player
from team.forms import Teamform
from team.models import Team

User = get_user_model()
PASSWORD = "pass-12345-x"
LAPI_CLUB = {"competition": "lapi", "name": "Gladiadores LAPI", "location": "Sevilla", "gender": "M",
             "country": "ES", "division": "lapi_2", "player-name": "Ana", "player-last_name": "Ruiz",
             "snp-mode": "snp"}


class CompetitionOfClubTests(TestCase):
    """La ficha sale de la competición del club, también para sus enfrentamientos."""

    def setUp(self):
        self.user = User.objects.create_user("capi", password=PASSWORD)
        self.snp = create_club("Club SNP", "Sevilla", self.user)
        self.lapi = create_club("Club LAPI", "Sevilla", self.user, competition="lapi")

    def test_rules_follow_the_club(self):
        self.assertIs(competition_for(self.snp), SNP)
        self.assertIs(competition_for(self.lapi), LAPI)
        self.assertIs(self.lapi.rules, LAPI)
        match = Match.objects.create(club=self.lapi, local=self.lapi.own_team, visiting=self.lapi.own_team,
                                     start_date=datetime.date(2026, 11, 1))
        self.assertIs(competition_for(Match.objects.get(pk=match.pk)), LAPI)
        self.assertEqual(phases_for([match])[match.id].total_games, 3)
        self.assertEqual(phases_for([match])[match.id].min_call, 6)

    def test_existing_clubs_are_snp(self):
        self.assertEqual(Club.objects.get(pk=self.snp.pk).competition, "snp")


class LapiMatchCycleTests(TestCase):
    """Un enfrentamiento LAPI de principio a fin: 6 convocados, 3 parejas de 1 punto y acta 2-1."""

    def setUp(self):
        self.user = User.objects.create_user("capi", password=PASSWORD)
        self.club = create_club("Club LAPI", "Sevilla", self.user, competition="lapi")
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"Jug{i:02d}", last_name="X") for i in range(7)]
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                          start_date=datetime.date(2026, 10, 20))
        self.client.login(username="capi", password=PASSWORD)

    def test_full_cycle(self):
        pid = self.match.public_id
        self.client.post(reverse("create_call", args=[pid]), {"players": [p.id for p in self.players[:5]]})
        self.assertFalse(Call.objects.filter(match=self.match).exists())
        self.client.post(reverse("create_call", args=[pid]), {"players": [p.id for p in self.players[:6]]})
        self.client.post(reverse("close_call", args=[pid]))
        self.assertFalse(Call.objects.get(match=self.match).draft_mode)

        page = self.client.get(reverse("create_game", args=[pid]))
        self.assertEqual(page.content.decode().count("data-slot "), 3)
        pairs = [{"player1Id": self.players[i].id, "player2Id": self.players[i + 1].id} for i in (0, 2, 4)]
        self.client.post(reverse("create_game", args=[pid]), {"ordered_games": json.dumps(pairs)})
        games = list(self.match.games.order_by("n_game"))
        self.assertEqual([g.score for g in games], [1, 1, 1])

        results = {}
        for g, (a, b) in zip(games, [(6, 2), (6, 3), (2, 6)]):
            results.update({f"g{g.n_game}_set1_local": str(a), f"g{g.n_game}_set1_visiting": str(b),
                            f"g{g.n_game}_set2_local": str(a), f"g{g.n_game}_set2_visiting": str(b)})
        self.client.post(reverse("enter_results", args=[pid]), {**results, "action": "close"})
        self.match.refresh_from_db()
        self.assertFalse(self.match.draft_mode)
        self.assertEqual(self.match.result_points, "2/1")


class OneSpacePerCompetitionTests(TestCase):
    """Un espacio por competición: se puede estar en SNP y en LAPI, pero no en dos SNP."""

    def setUp(self):
        self.captain = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.club = create_club("Gladiadores", "Sevilla", self.captain, gender="M", country="ES", division="500")
        self.client.login(username="capi", password=PASSWORD)

    def test_create_lapi_space_from_the_menu(self):
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Crear otro espacio")
        page = self.client.get(reverse("register_club") + "?competicion=lapi")
        self.assertContains(page, "Crear otro espacio")
        self.assertContains(page, 'value="Gladiadores"')
        self.assertNotContains(page, 'value="snp" name="competition"')

        response = self.client.post(reverse("register_club"), LAPI_CLUB)
        space = Club.objects.get(name="Gladiadores LAPI")
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(space.competition, "lapi")
        self.assertEqual(space.own_team.division, "lapi_2")
        # Sin cuenta SNP: el jugador del capitán se crea con el nombre escrito.
        self.assertTrue(Player.objects.filter(club=space, user=self.captain, name="Ana").exists())
        self.assertEqual(self.client.session["club_id"], space.id)
        self.assertEqual(club_of(self.captain, "snp"), self.club)
        self.assertEqual(club_of(self.captain, "lapi"), space)
        self.assertEqual(free_competitions(self.captain), [])

        # Con un espacio en cada competición ya no se ofrece crear otro.
        self.assertNotContains(self.client.get(reverse("home")), "Crear otro espacio")
        self.assertRedirects(self.client.get(reverse("register_club")), reverse("home"), fetch_redirect_response=False)

    def test_division_must_belong_to_the_competition(self):
        response = self.client.post(reverse("register_club"), {**LAPI_CLUB, "division": "500"})
        self.assertContains(response, "Elige una división de LAPI")
        self.assertFalse(Club.objects.filter(name="Gladiadores LAPI").exists())

    def test_switch_between_spaces(self):
        space = create_club("Gladiadores LAPI", "Sevilla", self.captain, competition="lapi")
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Cambiar de espacio")
        self.assertContains(home, "z-comp-badge--lapi")
        self.client.post(reverse("switch_club"), {"club_id": space.id})
        self.assertEqual(self.client.get(reverse("home")).context["current_club"], space)

    def test_invitation_to_another_competition_is_accepted(self):
        other = User.objects.create_user("otro", password=PASSWORD, email="otro@example.com")
        lapi = create_club("Otro LAPI", "Huelva", other, competition="lapi")
        invitation = Invitation.objects.create(club=lapi, created_by=other, reusable=True)
        page = self.client.get(reverse("invitation", args=[invitation.token]))
        self.assertContains(page, "Unirme como")
        self.assertContains(page, "Espacio LAPI")
        self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertTrue(Membership.objects.filter(user=self.captain, club=lapi).exists())

    def test_invitation_to_the_same_competition_is_refused(self):
        other = User.objects.create_user("otro", password=PASSWORD, email="otro@example.com")
        snp = create_club("Otro SNP", "Huelva", other)
        invitation = Invitation.objects.create(club=snp, created_by=other, reusable=True)
        page = self.client.get(reverse("invitation", args=[invitation.token]))
        self.assertContains(page, "solo se puede tener un espacio por competición")
        self.client.post(reverse("invitation", args=[invitation.token]))
        self.assertFalse(Membership.objects.filter(user=self.captain, club=snp).exists())


class LapiSpaceWithoutSnpTests(TestCase):
    """En un espacio LAPI no se ofrece nada de SNP y las divisiones son las de LAPI."""

    def setUp(self):
        self.captain = User.objects.create_user("capi", password=PASSWORD, email="capi@example.com")
        self.club = create_club("Club LAPI", "Sevilla", self.captain, competition="lapi", division="lapi_1")
        self.client.login(username="capi", password=PASSWORD)

    def test_home_and_club_have_no_snp(self):
        home = self.client.get(reverse("home"))
        self.assertNotContains(home, "Sincroniza tu equipo con SNP")
        self.assertNotContains(home, "Conectar SNP")
        self.assertContains(home, "Añade a tus jugadores")
        self.assertNotContains(self.client.get(reverse("club_home")), reverse("snp_account"))

    def test_team_divisions_are_lapi_ones(self):
        choices = [code for code, _label in Teamform(club=self.club).fields["division"].choices if code]
        self.assertEqual(choices, list(LAPI.divisions))
        snp_club = create_club("Club SNP", "Sevilla", User.objects.create_user("x", password=PASSWORD))
        choices = [code for code, _label in Teamform(club=snp_club).fields["division"].choices if code]
        self.assertEqual(choices, list(SNP.divisions))
