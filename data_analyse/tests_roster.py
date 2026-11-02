"""Fase 5 de la auditoría de estadísticas: la tabla de plantilla de Equipo y de la entrada de Jugadores."""
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from data_analyse import pairs as pair_stats
from data_analyse import roster_table
from data_analyse.tests_extra import ClubDataMixin
from players.models import Player


class RosterOptionsTests(SimpleTestCase):
    def test_defaults_and_invalid_values(self):
        self.assertEqual(roster_table.parse_options(QueryDict(""), True), ("todos", 3, "pct"))
        bad = QueryDict("lado=raro&minimo=7&orden=zzz")
        self.assertEqual(roster_table.parse_options(bad, True), ("todos", 3, "pct"))
        self.assertEqual(roster_table.parse_options(QueryDict("lado=local&minimo=5&orden=signup"), True),
                         ("local", 5, "signup"))
        self.assertEqual(roster_table.parse_options(QueryDict("minimo=x"), True)[1], 3)

    def test_points_sort_needs_snp(self):
        self.assertEqual(roster_table.parse_options(QueryDict("orden=snp"), True)[2], "snp")
        self.assertEqual(roster_table.parse_options(QueryDict("orden=snp"), False)[2], "pct")


class RosterRowsTests(ClubDataMixin, TestCase):
    """A y B ganan 2 de 2 (uno en casa y otro fuera); C gana 1 de 2 y D, 1 de 2; E no juega."""

    def _rows(self, **options):
        squad = list(Player.objects.filter(club=self.club, in_team=True))
        log = pair_stats.club_game_log(self.club)
        signup = roster_table.signup_by_player(self.club, squad)
        return {r["player"].name: r for r in roster_table.roster_rows(squad, log, signup, **options)}

    def test_balance_percentage_and_signup(self):
        rows = self._rows()
        self.assertEqual((rows["A"]["played"], rows["A"]["wins"], rows["A"]["losses"], rows["A"]["pct"]), (2, 2, 0, 100))
        self.assertEqual((rows["C"]["played"], rows["C"]["pct"]), (2, 50))
        self.assertEqual((rows["E"]["played"], rows["E"]["pct"]), (0, None))
        # Los cinco se apuntaron a las dos convocatorias cerradas.
        self.assertEqual((rows["E"]["signed"], rows["E"]["calls"], rows["E"]["signup"]), (2, 2, 100))

    def test_side_counts_only_that_side(self):
        local = self._rows(side="local")
        self.assertEqual((local["A"]["played"], local["A"]["pct"]), (1, 100))
        self.assertEqual((local["C"]["played"], local["C"]["wins"]), (1, 0))
        away = self._rows(side="visitante")
        self.assertEqual((away["C"]["played"], away["C"]["wins"]), (1, 1))

    def test_minimum_sends_the_rest_to_the_end_and_keeps_their_percentage(self):
        squad = list(Player.objects.filter(club=self.club, in_team=True))
        log = pair_stats.club_game_log(self.club)
        signup = roster_table.signup_by_player(self.club, squad)
        order = lambda **kw: [r["player"].name for r in roster_table.roster_rows(squad, log, signup, **kw)]  # noqa: E731
        # Con mínimo 2 entran A, B, C y D; con 3 nadie y se queda el orden por % (los que no llegan, al final).
        self.assertEqual(set(order(min_games=2)[:4]), {"A", "B", "C", "D"})
        self.assertEqual(order(min_games=2)[-1], "E")
        rows = roster_table.roster_rows(squad, log, signup, min_games=3)
        self.assertFalse(any(r["enough"] for r in rows))
        self.assertEqual(rows[0]["pct"], 100)  # su % se ve igualmente
        self.assertEqual(order(sort="name"), sorted(order(sort="name")))

    def test_signup_ignores_calls_before_joining(self):
        late = Player.objects.get(club=self.club, name="E")
        late.joined_season = "2099-2100"
        late.save()
        squad = list(Player.objects.filter(club=self.club, in_team=True))
        self.assertEqual(roster_table.signup_by_player(self.club, squad)[late.id], {"signed": 0, "total": 0, "pct": None})


class RosterPagesTests(ClubDataMixin, TestCase):
    def test_team_page_has_the_table_instead_of_top_5(self):
        page = self.client.get(reverse("team_statistics"), {"season": "all", "match_type": "todos"})
        self.assertContains(page, 'id="sec-plantilla"')
        self.assertNotContains(page, "Top 5")
        self.assertNotContains(page, "Mejores jugadores como local")
        roster = page.context["roster"]
        self.assertEqual((roster["side"], roster["min_games"], roster["sort"]), ("todos", 3, "pct"))
        self.assertEqual([s[0] for s in roster["sides"]], ["todos", "local", "visitante"])
        # Cada opción conserva los demás filtros y vuelve a la tabla.
        local_url = roster["sides"][1][2]
        self.assertIn("lado=local", local_url)
        self.assertIn("season=all", local_url)
        self.assertTrue(local_url.endswith("#sec-plantilla"))
        self.assertContains(page, "Se apunta")

    def test_options_are_read_from_the_query(self):
        page = self.client.get(reverse("team_statistics"), {"lado": "local", "minimo": "1", "orden": "played",
                                                           "season": "all", "match_type": "todos"})
        roster = page.context["roster"]
        self.assertEqual((roster["side"], roster["min_games"], roster["sort"]), ("local", 1, "played"))
        self.assertTrue(all(r["enough"] for r in roster["rows"] if r["played"]))

    def test_rows_link_to_the_player_sheet_without_table_params(self):
        page = self.client.get(reverse("team_statistics"), {"lado": "local", "season": "all", "match_type": "todos"})
        url = page.context["roster"]["rows"][0]["url"]
        self.assertTrue(url.startswith(reverse("player_statistics")))
        self.assertIn("player=", url)
        self.assertNotIn("lado=", url)

    def test_snp_block_has_no_second_player_table(self):
        page = self.client.get(reverse("team_statistics"))
        self.assertNotContains(page, "st-snp-table")
        self.assertContains(page, "Ver los puntos de cada jugador en la tabla de plantilla")
        self.assertTrue(page.context["roster"]["has_snp"])
        self.assertContains(page, "Puntos SNP</a></th>")

    def test_charts_live_under_profundizar_folded(self):
        page = self.client.get(reverse("team_statistics"))
        self.assertContains(page, "Profundizar")
        self.assertContains(page, 'class="st-fold"')
        self.assertNotContains(page, 'open class="st-fold"')

    def test_records_are_the_five_of_the_design(self):
        page = self.client.get(reverse("team_statistics"), {"season": "all", "match_type": "todos"})
        self.assertContains(page, "Mayor victoria")
        self.assertContains(page, "Pareja con más victorias")
        for gone in ("Partidos ganados seguidos", "Más victorias", "Más partidos jugados"):
            self.assertNotContains(page, gone)

    def test_players_entry_is_the_roster_table(self):
        page = self.client.get(reverse("player_statistics"), {"season": "all", "match_type": "todos"})
        self.assertContains(page, 'id="sec-plantilla"')
        self.assertNotContains(page, "st-player-grid")
        self.assertNotContains(page, "Pulsa en un jugador")
        self.assertEqual(len(page.context["roster"]["rows"]), Player.objects.filter(club=self.club, in_team=True).count())
