import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from core.services import create_club
from match.models import Game, Match, Result
from players.models import Player
from team.models import Team

User = get_user_model()


class CloseMatchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"P{i}", last_name="X") for i in range(10)]
        self.match = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                          start_date=datetime.date(2025, 10, 1))
        call = Call.objects.create(match=self.match, draft_mode=False)
        call.players.set(self.players)
        for n in range(1, 6):
            game = Game.objects.create(
                match=self.match, n_game=n, score=3 if n < 3 else 2, winner="Local",
                player_1_local=self.players[2 * n - 2], player_2_local=self.players[2 * n - 1],
            )
            Result.objects.create(game=game, set1_local="6", set1_visiting="2", set2_local="6",
                                  set2_visiting="3", set3_local="0", set3_visiting="0")
        self.client.login(username="admin", password="pass-12345")

    def test_closing_match_confirms_match_and_games(self):
        self.client.post(reverse("close_match", args=[self.match.public_id]))
        self.match.refresh_from_db()
        self.assertFalse(self.match.draft_mode)
        self.assertEqual(self.match.result_points, "12/0")
        self.assertFalse(self.match.games.filter(draft_mode=True).exists())


class DrawResultTests(TestCase):
    def test_draw_uses_the_field_choice(self):
        """Un 6-6 se guarda como «EMPATE», el valor de las opciones, y se muestra como «Empate»."""
        from match.views import determine_match_result
        self.assertEqual(determine_match_result(6, 6), "EMPATE")
        self.assertIn("EMPATE", dict(Match.POSSIBLE_RESULT))
        match = Match(result=determine_match_result(6, 6))
        self.assertEqual(match.get_result_display(), "Empate")


class MatchesAndCallsTests(TestCase):
    def setUp(self):
        from core.models import Membership
        from penalty.models import Penalty
        from players.models import current_season
        self.Penalty = Penalty
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.viewer = User.objects.create_user("viewer", password="pass-12345")
        Membership.objects.create(user=self.viewer, club=self.club, role=Membership.MEMBER)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        start = int(current_season()[:4])
        self.current = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                            start_date=datetime.date(start, 10, 1))
        self.old = Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                        start_date=datetime.date(start - 2, 10, 1))
        self.zoe = Player.objects.create(club=self.club, name="Zoe", last_name="Z")
        self.ana = Player.objects.create(club=self.club, name="Ana", last_name="A")
        self.gone = Player.objects.create(club=self.club, name="Bea", last_name="B", in_team=False)
        self.client.login(username="admin", password="pass-12345")

    def test_match_list_defaults_to_current_season(self):
        response = self.client.get(reverse("list_match"))
        self.assertEqual([m.id for m in response.context["matches"]], [self.current.id])
        response = self.client.get(reverse("list_match"), {"season": "all"})
        self.assertEqual(len(response.context["matches"]), 2)

    def test_match_list_season_selector_and_draws(self):
        """Chips con la temporada actual activa, «Todas» con ?season=all, la temporada de cada
        partido a la vista y los empates en el resumen."""
        self.old.draft_mode = False
        self.old.result = "EMPATE"
        self.old.save()
        response = self.client.get(reverse("list_match"))
        chips = response.context["season_chips"]
        self.assertTrue(chips[0]["active"])
        self.assertEqual(chips[0]["label"], self.current.season)
        self.assertTrue(response.context["season_all"]["url"].endswith("?season=all"))
        self.assertContains(response, f"Temporada {self.current.season}")

        response = self.client.get(reverse("list_match"), {"season": "all", "page": "1"})
        self.assertTrue(response.context["season_all"]["active"])
        self.assertEqual(response.context["summary"]["drawn"], 1)
        self.assertNotIn("page=", response.context["season_chips"][0]["url"])
        self.assertContains(response, 'class="z-fixture is-draw"')

        # Una temporada que no existe vuelve a la actual
        response = self.client.get(reverse("list_match"), {"season": "1999-2000"})
        self.assertEqual(response.context["selected_season"], self.current.season)

    def test_match_list_search_for_older_seasons(self):
        """Con más de tres temporadas aparece el buscador; la antigua elegida sale como chip activo."""
        start = int(self.current.season[:4])
        for years_ago in (1, 3, 4):
            Match.objects.create(club=self.club, local=self.club.own_team, visiting=self.rival,
                                 start_date=datetime.date(start - years_ago, 10, 1))
        oldest = f"{start - 4}-{start - 3}"
        response = self.client.get(reverse("list_match"))
        self.assertIn(oldest, response.context["season_search"])
        self.assertEqual(len(response.context["season_chips"]), 3)
        response = self.client.get(reverse("list_match"), {"season": oldest})
        self.assertEqual([c["label"] for c in response.context["season_chips"] if c["active"]], [oldest])
        self.assertEqual(len(response.context["matches"]), 1)

    def test_long_call_groups_are_collapsed(self):
        """Con muchos convocados en una posición, se ven los primeros y el resto tras «Ver N más»."""
        players = [Player.objects.create(club=self.club, name=f"P{i:02d}", last_name="X", position="Derecha")
                   for i in range(11)]
        call = Call.objects.create(match=self.current, draft_mode=False)
        call.players.set(players)
        response = self.client.get(reverse("call_for_match", args=[self.current.public_id]))
        drive = next(g for g in response.context["groups"] if len(g["players"]) == 11)
        self.assertEqual(drive["hidden"], 3)
        self.assertContains(response, "Ver 3 más")

    def test_call_players_are_alphabetical_and_current(self):
        response = self.client.get(reverse("create_call", args=[self.current.public_id]))
        self.assertEqual([p.name for p in response.context["players"]], ["Ana", "Zoe"])

    def test_penalties_only_for_current_players(self):
        call = Call.objects.create(match=self.current, draft_mode=False)
        call.players.set([self.ana])
        response = self.client.get(reverse("view_call_log", args=[call.public_id]))
        self.assertEqual([p.name for p in response.context["players"]], ["Ana", "Zoe"])

        # Zoe no está convocada pero sí en el equipo: se la puede sancionar; Bea ya no está.
        self.client.post(reverse("create_penalty", args=[call.public_id]), {"players": [self.zoe.id, self.gone.id]})
        self.assertEqual(list(self.Penalty.objects.values_list("player__name", flat=True)), ["Zoe"])

    def test_warnings_view_is_admin_only(self):
        call = Call.objects.create(match=self.current, draft_mode=False)
        self.Penalty.objects.create(player=self.ana, call=call, reason="Advertencia")
        response = self.client.get(reverse("warnings_statistics"))
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(self.client.get(reverse("warnings_statistics"), {"season": "1999-2000"}).context["total"], 0)

        self.client.login(username="viewer", password="pass-12345")
        self.assertEqual(self.client.get(reverse("warnings_statistics")).status_code, 403)

    def test_manage_roster_updates_many_players_at_once(self):
        self.client.post(reverse("manage_roster"), {"in_team": [self.ana.id, self.gone.id]})
        states = dict(Player.objects.values_list("name", "in_team"))
        self.assertEqual(states, {"Ana": True, "Bea": True, "Zoe": False})

        self.client.login(username="viewer", password="pass-12345")
        self.client.post(reverse("manage_roster"), {"in_team": []})
        self.assertEqual(Player.objects.filter(in_team=True).count(), 2)


import io
import json

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction

from match import scoring


class PadelScoringTests(TestCase):
    def ok(self, s1, s2, s3=(None, None)):
        return scoring.validate_padel_result(s1, s2, s3)[1]

    def bad(self, s1, s2, s3=(None, None)):
        with self.assertRaises(ValidationError):
            scoring.validate_padel_result(s1, s2, s3)

    def test_valid_results(self):
        self.assertEqual(self.ok((6, 3), (6, 4)), "local")
        self.assertEqual(self.ok((7, 6), (7, 5)), "local")
        self.assertEqual(self.ok((3, 6), (6, 7)), "visiting")
        self.assertEqual(self.ok((6, 3), (4, 6), (6, 2)), "local")
        self.assertEqual(self.ok((6, 3), (4, 6), (8, 10)), "visiting")   # super tie-break
        self.assertEqual(self.ok((6, 3), (4, 6), (12, 10)), "local")
        self.assertEqual(self.ok((6, 3), (6, 4), (0, 0)), "local")        # 0-0 = no jugado

    def test_invalid_results(self):
        self.bad((6, 5), (6, 4))          # 6-5 no existe
        self.bad((7, 3), (6, 4))          # 7 solo con 5 o 6
        self.bad((6, 6), (6, 4))
        self.bad((None, None), (6, 4))    # falta el set 1
        self.bad((6, 3), (6, 4), (6, 2))  # set 3 sin necesidad
        self.bad((6, 3), (4, 6))          # falta el set 3
        self.bad((6, 3), (4, 6), (10, 9)) # super tie-break sin 2 de diferencia
        self.bad((6, 3), (4, 6), (13, 10))
        self.bad((6, 3), (4, 6), (8, 7))


class LineupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.players = [Player.objects.create(club=self.club, name=f"P{i}", last_name="X", snp_score=i) for i in range(10)]
        self.match = Match.objects.create(club=self.club, local=rival, visiting=self.club.own_team,
                                          start_date=datetime.date(2025, 10, 1))
        self.call = Call.objects.create(match=self.match, draft_mode=False)
        self.call.players.set(self.players)
        self.client.login(username="admin", password="pass-12345")

    def lineup(self, n=5, games=None):
        data = [{"player1Id": self.players[2 * i].id, "player2Id": self.players[2 * i + 1].id} for i in range(n)]
        for item, g in zip(data, games or []):
            item["gameId"] = g.id
        return json.dumps(data)

    def test_incomplete_lineup_saves_nothing(self):
        self.client.post(reverse("create_game", args=[self.match.public_id]), {"ordered_games": self.lineup(3)})
        self.assertEqual(self.match.games.count(), 0)

    def test_creating_twice_does_not_duplicate(self):
        url = reverse("create_game", args=[self.match.public_id])
        self.client.post(url, {"ordered_games": self.lineup()})
        response = self.client.post(url, {"ordered_games": self.lineup()})
        self.assertRedirects(response, reverse("edit_games_match", args=[self.match.public_id]), fetch_redirect_response=False)
        self.assertEqual(sorted(self.match.games.values_list("n_game", flat=True)), [1, 2, 3, 4, 5])
        # El club juega como visitante: las parejas van en ese lado y el orden fija los puntos
        g1 = self.match.games.get(n_game=1)
        self.assertIsNone(g1.player_1_local)
        self.assertEqual([g.score for g in self.match.games.order_by("n_game")], [3, 3, 2, 2, 2])

    def test_repeated_player_is_rejected(self):
        data = json.loads(self.lineup())
        data[1]["player1Id"] = data[0]["player1Id"]
        self.client.post(reverse("create_game", args=[self.match.public_id]), {"ordered_games": json.dumps(data)})
        self.assertEqual(self.match.games.count(), 0)

    def test_edit_reorders_without_breaking_uniqueness(self):
        self.client.post(reverse("create_game", args=[self.match.public_id]), {"ordered_games": self.lineup()})
        games = list(self.match.games.order_by("n_game"))
        data = json.loads(self.lineup(games=games))
        data.reverse()  # el último pasa a ser el partido 1
        self.client.post(reverse("edit_games_match", args=[self.match.public_id]), {"ordered_games": json.dumps(data)})
        games[4].refresh_from_db()
        self.assertEqual((games[4].n_game, games[4].score), (1, 3))
        self.assertEqual(self.match.games.count(), 5)

    def test_database_rejects_duplicate_game_numbers(self):
        Game.objects.create(match=self.match, n_game=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Game.objects.create(match=self.match, n_game=1)

    def test_result_views_validate_and_block_second_result(self):
        self.client.post(reverse("create_game", args=[self.match.public_id]), {"ordered_games": self.lineup()})
        game = self.match.games.get(n_game=1)
        url = reverse("create_result", args=[game.public_id])
        bad = {"set1_local": "6", "set1_visiting": "5", "set2_local": "6", "set2_visiting": "4"}
        self.assertIn("errors", self.client.post(url, bad).context)
        good = {"set1_local": "3", "set1_visiting": "6", "set2_local": "6", "set2_visiting": "4",
                "set3_local": "8", "set3_visiting": "10"}
        self.client.post(url, good)
        game.refresh_from_db()
        self.assertEqual(game.winner, "Visitante")
        self.assertRedirects(self.client.get(url), reverse("edit_result", args=[game.public_id]), fetch_redirect_response=False)
        self.assertEqual(Result.objects.filter(game=game).count(), 1)


class FixDuplicateGamesCommandTests(TestCase):
    def test_dry_run_without_duplicates_changes_nothing(self):
        # Con la restricción ya migrada no se pueden crear duplicados; el caso con duplicados
        # reales se ha probado sobre una base de datos con el esquema anterior.
        user = User.objects.create_user("a", password="x")
        club = create_club("Club A", "Sevilla", user)
        rival = Team.objects.create(club=club, name="Rival", location="X", in_group=True)
        m = Match.objects.create(club=club, local=club.own_team, visiting=rival, start_date=datetime.date(2025, 10, 1))
        g = Game.objects.create(match=m, n_game=1)
        out = io.StringIO()
        call_command("fix_duplicate_games", "--dry-run", stdout=out)
        self.assertIn("0 partidos", out.getvalue())
        self.assertTrue(Game.objects.filter(pk=g.pk).exists())


class CreateMatchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.client.force_login(self.user)
        self.url = reverse("create_match")

    def test_form_uses_custom_date_picker(self):
        response = self.client.get(self.url)
        self.assertContains(response, "data-datepicker")
        self.assertContains(response, "js/date-picker.js")

    def test_creates_match_with_iso_date(self):
        response = self.client.post(self.url, {"local": self.club.own_team.id, "visiting": self.rival.id,
                                               "start_date": "2026-11-15"})
        self.assertRedirects(response, reverse("list_match"), fetch_redirect_response=False)
        self.assertTrue(Match.objects.filter(club=self.club, start_date=datetime.date(2026, 11, 15)).exists())

    def test_missing_date_shows_error_instead_of_crashing(self):
        response = self.client.post(self.url, {"local": self.club.own_team.id, "visiting": self.rival.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fecha no válida")
        self.assertFalse(Match.objects.exists())


class CreateMatchOwnTeamTests(TestCase):
    """El equipo del capitán (equipo propio del club) tiene que jugar como local o visitante."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.own = self.club.own_team
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.other = Team.objects.create(club=self.club, name="Otro", location="Y", in_group=True)
        self.client.force_login(self.user)
        self.url = reverse("create_match")

    def post(self, local, visiting):
        return self.client.post(self.url, {"local": local.id, "visiting": visiting.id, "start_date": "2026-11-15"})

    def test_match_between_two_rivals_is_rejected(self):
        response = self.post(self.rival, self.other)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tiene que jugar el partido")
        self.assertFalse(Match.objects.exists())

    def test_own_team_as_visiting_is_allowed(self):
        response = self.post(self.rival, self.own)
        self.assertRedirects(response, reverse("list_match"), fetch_redirect_response=False)
        match = Match.objects.get()
        self.assertEqual((match.local, match.visiting, match.club), (self.rival, self.own, self.club))

    def test_same_team_twice_is_rejected(self):
        self.post(self.own, self.own)
        self.assertFalse(Match.objects.exists())

    def test_own_team_is_selectable_even_if_not_in_group(self):
        Team.objects.filter(pk=self.own.pk).update(in_group=False)
        self.post(self.own, self.rival)
        self.assertTrue(Match.objects.filter(local=self.own).exists())

    def test_form_preselects_own_team_as_local(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["form"].initial["local"], self.own.pk)

    def test_team_from_another_club_is_rejected(self):
        other_user = User.objects.create_user("b", password="pass-12345")
        foreign = Team.objects.create(club=create_club("Club B", "Madrid", other_user), name="Ajeno", location="Z",
                                      in_group=True)
        response = self.post(self.own, foreign)
        self.assertContains(response, "Uno de los equipos no existe")
        self.assertFalse(Match.objects.exists())

class CreateMatchTypeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.client.force_login(self.user)
        self.data = {"local": self.club.own_team.id, "visiting": self.rival.id, "start_date": "2026-11-15"}

    def test_form_offers_match_types(self):
        response = self.client.get(reverse("create_match"))
        for label in ("Enfrentamiento", "Reto", "Play Off"):
            self.assertContains(response, label)

    def test_creates_match_with_type(self):
        self.client.post(reverse("create_match"), {**self.data, "match_type": Match.PLAYOFF})
        self.assertEqual(Match.objects.get(club=self.club).match_type, Match.PLAYOFF)

    def test_invalid_type_is_rejected(self):
        response = self.client.post(reverse("create_match"), {**self.data, "match_type": "amistoso"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Match.objects.exists())


class CreateFriendlyMatchTests(TestCase):
    """Modo Amistoso / Competitivo: un amistoso no tiene tipo (enfrentamiento, reto, play off)."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.client.force_login(self.user)
        self.url = reverse("create_match")
        self.data = {"local": self.club.own_team.id, "visiting": self.rival.id, "start_date": "2026-11-15"}

    def test_competitive_is_the_default_mode(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["form"]["mode"].value(), "competitivo")
        self.assertContains(response, "Amistoso")
        self.client.post(self.url, {**self.data, "match_type": Match.RETO})
        self.assertEqual(Match.objects.get().match_type, Match.RETO)

    def test_friendly_match_ignores_type(self):
        response = self.client.post(self.url, {**self.data, "mode": "amistoso", "match_type": Match.PLAYOFF})
        self.assertRedirects(response, reverse("list_match"), fetch_redirect_response=False)
        match = Match.objects.get()
        self.assertEqual(match.match_type, Match.AMISTOSO)
        self.assertTrue(match.is_friendly)

    def test_friendly_still_requires_own_team(self):
        other = Team.objects.create(club=self.club, name="Otro", location="Y", in_group=True)
        response = self.client.post(self.url, {**self.data, "local": other.id, "mode": "amistoso"})
        self.assertContains(response, "tiene que jugar el partido")
        self.assertFalse(Match.objects.exists())

    def test_type_select_does_not_offer_friendly(self):
        form = self.client.get(self.url).context["form"]
        self.assertNotIn(Match.AMISTOSO, dict(form.fields["match_type"].choices))

    def test_team_cards_show_selected_team_and_photos(self):
        response = self.client.get(self.url)
        self.assertContains(response, "data-team-card", count=2)
        self.assertContains(response, 'data-photo=""')
        self.assertEqual(response.context["form"].local_team, self.club.own_team)
        self.assertIsNone(response.context["form"].visiting_team)
        self.assertContains(response, "js/match-form.js")
