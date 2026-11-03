"""Fase 5 de la auditoría de estadísticas: la tabla de plantilla de Equipo y de la entrada de Jugadores."""
import datetime

from django.http import QueryDict
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from data_analyse import pairs as pair_stats
from data_analyse import records, roster_table
from data_analyse.tests_extra import ClubDataMixin
from players.models import Player, SnpScoreHistory


class RosterOptionsTests(SimpleTestCase):
    def test_defaults_and_invalid_values(self):
        self.assertEqual(roster_table.parse_options(QueryDict(""), True), ("todos", "pct"))
        bad = QueryDict("lado=raro&orden=zzz")
        self.assertEqual(roster_table.parse_options(bad, True), ("todos", "pct"))
        self.assertEqual(roster_table.parse_options(QueryDict("lado=local&orden=signup"), True), ("local", "signup"))

    def test_points_sort_needs_snp(self):
        self.assertEqual(roster_table.parse_options(QueryDict("orden=snp"), True)[1], "snp")
        self.assertEqual(roster_table.parse_options(QueryDict("orden=snp"), False)[1], "pct")


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

    def test_no_minimum_everyone_who_played_counts_and_the_rest_go_last(self):
        squad = list(Player.objects.filter(club=self.club, in_team=True))
        log = pair_stats.club_game_log(self.club)
        signup = roster_table.signup_by_player(self.club, squad)
        rows = roster_table.roster_rows(squad, log, signup)
        self.assertEqual([r["player"].name for r in rows][-1], "E")  # no ha jugado
        self.assertTrue(all(r["enough"] for r in rows if r["played"]))
        self.assertFalse(rows[-1]["enough"])
        self.assertEqual(rows[0]["pct"], 100)
        names = [r["player"].name for r in roster_table.roster_rows(squad, log, signup, sort="name")]
        self.assertEqual(names, sorted(names))

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
        self.assertEqual((roster["side"], roster["sort"]), ("todos", "pct"))
        self.assertEqual([s[0] for s in roster["sides"]], ["todos", "local", "visitante"])
        # Cada opción conserva los demás filtros y vuelve a la tabla.
        local_url = roster["sides"][1][2]
        self.assertIn("lado=local", local_url)
        self.assertIn("season=all", local_url)
        self.assertTrue(local_url.endswith("#sec-plantilla"))
        self.assertContains(page, "Se apunta")

    def test_options_are_read_from_the_query(self):
        page = self.client.get(reverse("team_statistics"), {"lado": "local", "orden": "played",
                                                           "season": "all", "match_type": "todos"})
        roster = page.context["roster"]
        self.assertEqual((roster["side"], roster["sort"]), ("local", "played"))
        self.assertTrue(all(r["enough"] for r in roster["rows"] if r["played"]))

    def test_rows_link_to_the_player_sheet_without_table_params(self):
        page = self.client.get(reverse("team_statistics"), {"lado": "local", "season": "all", "match_type": "todos"})
        url = page.context["roster"]["rows"][0]["url"]
        self.assertTrue(url.startswith(reverse("player_statistics")))
        self.assertIn("player=", url)
        self.assertNotIn("lado=", url)

    def test_snp_block_is_gone_and_its_summary_sits_over_the_table(self):
        page = self.client.get(reverse("team_statistics"))
        self.assertNotContains(page, "snp-title")
        self.assertNotContains(page, "chartSnpTeam")
        self.assertTrue(page.context["roster"]["has_snp"])
        self.assertContains(page, "orden=snp")
        # La media del equipo y la fecha de actualización (si hay puntos) van en una línea sobre la tabla.
        self.assertContains(page, "Media del equipo:")
        self.assertIsNotNone(page.context["roster"]["snp"]["average"])

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


class RosterSideAndMinimumTests(ClubDataMixin, TestCase):
    def test_there_is_no_minimum_selector(self):
        page = self.client.get(reverse("team_statistics"), {"season": "all", "match_type": "todos"})
        rows = page.context["roster"]["rows"]
        self.assertTrue(all(r["enough"] for r in rows if r["played"]))
        self.assertNotContains(page, "minimo=")
        self.assertNotContains(page, "Mínimo")

    def test_signup_follows_the_side_filter(self):
        squad = list(Player.objects.filter(club=self.club, in_team=True))
        everything = roster_table.signup_by_player(self.club, squad)
        local = roster_table.signup_by_player(self.club, squad, side="local")
        away = roster_table.signup_by_player(self.club, squad, side="visitante")
        # Hay una convocatoria como local (10/10) y otra como visitante (01/11).
        self.assertEqual((everything[self.a.id]["total"], local[self.a.id]["total"], away[self.a.id]["total"]), (2, 1, 1))
        self.assertEqual(local[self.a.id], {"signed": 1, "total": 1, "pct": 100})

    def test_page_passes_the_side_to_the_signup_column(self):
        page = self.client.get(reverse("team_statistics"), {"lado": "local", "season": "all", "match_type": "todos"})
        row = next(r for r in page.context["roster"]["rows"] if r["player"] == self.a)
        self.assertEqual(row["calls"], 1)


class SnpEvolutionTests(ClubDataMixin, TestCase):
    """«Evolución»: mini gráfico de cada jugador y puestos que sube o baja en el ranking SNP."""

    def test_sparkline_needs_two_updates_and_is_flat_without_changes(self):
        self.assertIsNone(records.sparkline([40]))
        flat = records.sparkline([40, 40, 40])
        self.assertEqual(flat["values"], [40, 40, 40])
        self.assertEqual({p.split(",")[1] for p in flat["points"].split()}, {"10.0"})
        rising = records.sparkline([10, 20])
        ys = [float(p.split(",")[1]) for p in rising["points"].split()]
        self.assertGreater(ys[0], ys[1])  # en SVG, más arriba es una y menor

    def test_rank_movement_between_the_last_two_updates(self):
        season = "2025-2026"
        for pid, first, second in ((self.a, 40, 20), (self.b, 30, 35), (self.c, 20, 50)):
            for day, score in ((1, first), (8, second)):
                SnpScoreHistory.objects.create(player=pid, season=season, date=datetime.date(2025, 10, day), score=score)
        rows = {r["player"]: r for r in records.snp_ranking(self.club, season)["rows"]}
        # Antes: A, B, C. Ahora: C, B, A.
        self.assertEqual((rows[self.c]["rank_delta"], rows[self.b]["rank_delta"], rows[self.a]["rank_delta"]), (2, 0, -2))
        self.assertEqual(rows[self.a]["spark"]["values"], [40, 20])
        self.assertIsNone(rows[self.e]["rank_delta"])  # sin histórico

    def test_table_shows_the_trend_column_only_for_snp(self):
        SnpScoreHistory.objects.create(player=self.a, season="2025-2026", date=datetime.date(2025, 10, 1), score=40)
        SnpScoreHistory.objects.create(player=self.a, season="2025-2026", date=datetime.date(2025, 10, 8), score=45)
        page = self.client.get(reverse("team_statistics"), {"season": "2025-2026", "match_type": "todos"})
        self.assertContains(page, "st-roster-evo")
        self.assertContains(page, "<polyline")
