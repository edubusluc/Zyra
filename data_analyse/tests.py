import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.services import create_club
from data_analyse import pairs as pair_stats
from match.models import Game, Match, Result
from players.models import Player
from team.models import Team

User = get_user_model()


class PairStatisticsTests(TestCase):
    """
    Datos controlados (orden cronológico):
      2024-2025  local      A+B gana, A+B gana
      2024-2025  visitante  A+B pierde, C+D gana
      2025-2026  local      A+B gana, C+D pierde
      2025-2026  visitante  A+C gana (C fuera del equipo)
    """

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        own = self.club.own_team
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        mk = lambda n: Player.objects.create(club=self.club, name=n, last_name=f"{n}son")
        self.a, self.b, self.c, self.d = mk("A"), mk("B"), mk("C"), mk("D")
        self.c.in_team = False
        self.c.save()

        def match(date, own_local, games):
            m = Match.objects.create(
                club=self.club, local=own if own_local else rival, visiting=rival if own_local else own,
                start_date=date, draft_mode=False,
            )
            for n, (p1, p2, won) in enumerate(games, start=1):
                side = 'local' if own_local else 'visiting'
                winner = ('Local' if own_local else 'Visitante') if won else ('Visitante' if own_local else 'Local')
                Game.objects.create(match=m, n_game=n, score=3 if n < 3 else 2, winner=winner, draft_mode=False,
                                    **{f'player_1_{side}': p1, f'player_2_{side}': p2})
            return m

        match(datetime.date(2024, 10, 1), True, [(self.a, self.b, True), (self.b, self.a, True)])
        match(datetime.date(2024, 11, 1), False, [(self.a, self.b, False), (self.c, self.d, True)])
        match(datetime.date(2025, 10, 1), True, [(self.a, self.b, True), (self.c, self.d, False)])
        match(datetime.date(2025, 11, 1), False, [(self.a, self.c, True)])

        self.client.login(username="admin", password="pass-12345")

    def test_pair_summary(self):
        s = pair_stats.pair_summary(pair_stats.club_game_log(self.club), self.b.id, self.a.id)
        self.assertEqual((s['played'], s['wins'], s['losses'], s['pct']), (4, 3, 1, 75.0))
        self.assertEqual(s['matches'], 3)
        self.assertEqual((s['local_wins'], s['local_losses']), (3, 0))
        self.assertEqual((s['visiting_wins'], s['visiting_losses']), (0, 1))
        self.assertEqual((s['streak_type'], s['streak_len']), ('V', 1))
        self.assertEqual(s['best_win_streak'], 2)
        self.assertEqual(s['form'], [True, True, False, True])
        self.assertEqual(
            [(r['season'], r['played'], r['wins'], r['pct']) for r in s['seasons']],
            [('2024-2025', 3, 2, 66.7), ('2025-2026', 1, 1, 100.0)],
        )

    def test_hot_streaks(self):
        """A encadena 2 victorias; ninguna pareja del equipo llega al mínimo (C está fuera)."""
        squad = list(Player.objects.filter(club=self.club, in_team=True))
        player, pair = pair_stats.hot_streaks(pair_stats.club_game_log(self.club), squad)
        self.assertEqual((player['player'], player['streak']), (self.a, 2))
        self.assertIsNone(pair)

        # Con C en la lista, A+C (1 victoria) sigue sin llegar; C+D va perdiendo
        everyone = list(Player.objects.filter(club=self.club))
        self.assertIsNone(pair_stats.hot_streaks(pair_stats.club_game_log(self.club), everyone)[1])

    def test_top_tables(self):
        log = pair_stats.club_game_log(self.club)
        squad = list(Player.objects.filter(club=self.club, in_team=True))
        local = pair_stats.top_players(log, squad, local=True)
        # A y B: 3 de 3 en casa; D: 0 de 1 (no llega al mínimo); C no está en el equipo.
        self.assertEqual([(r['name'], r['pct']) for r in local], [("A ASON", 100.0), ("B BSON", 100.0)])
        away = pair_stats.top_players(log, squad, local=False)
        # Fuera solo A llega al mínimo de 2 partidos (1 de 2)
        self.assertEqual([(r['name'], r['played'], r['pct']) for r in away], [("A ASON", 2, 50.0)])

        pairs_local = pair_stats.top_pairs(log, squad, local=True)
        self.assertEqual([(r['name'], r['played'], r['pct']) for r in pairs_local], [("A ASON / B BSON", 3, 100.0)])
        self.assertEqual(pair_stats.top_pairs(log, squad, local=False), [])  # A+B solo 1 fuera

    def test_top_tables_respect_season(self):
        log = pair_stats.club_game_log(self.club, "2025-2026")
        squad = list(Player.objects.filter(club=self.club, in_team=True))
        self.assertEqual(pair_stats.top_players(log, squad, local=True), [])  # 1 partido por jugador

    def test_pair_view(self):
        response = self.client.get(reverse("pair_statistics"), {"p1": self.a.public_id, "p2": self.b.public_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["s"]["played"], 4)
        # Con una pareja elegida ya no se muestra el listado de parejas destacadas
        self.assertNotContains(response, "Parejas destacadas")

        overview = self.client.get(reverse("pair_statistics"))
        self.assertEqual(overview.status_code, 200)
        self.assertContains(overview, "Parejas destacadas")
        same = self.client.get(reverse("pair_statistics"), {"p1": self.a.public_id, "p2": self.a.public_id})
        self.assertIn("error", same.context)

    def test_best_and_worst_pairs(self):
        # A+B 3/4 y C+D 1/2; A+C solo 1 partido, no llega al mínimo
        response = self.client.get(reverse("pair_statistics"))
        key = lambda rows: [(r["p1"].name, r["p2"].name, r["played"], r["pct"]) for r in rows]
        self.assertEqual(key(response.context["best_pairs"]), [("A", "B", 4, 75.0)])
        self.assertEqual(key(response.context["worst_pairs"]), [("C", "D", 2, 50.0)])

    def test_ranking_links_open_the_pair(self):
        """Los enlaces de mejores/peores parejas llevan identificadores públicos (antes daban 404)."""
        response = self.client.get(reverse("pair_statistics"), {"match_type": "competitivo"})
        link = f'?p1={self.a.public_id}&amp;p2={self.b.public_id}&amp;match_type=competitivo'
        self.assertContains(response, link)
        followed = self.client.get(reverse("pair_statistics"),
                                   {"p1": self.a.public_id, "p2": self.b.public_id})
        self.assertEqual(followed.status_code, 200)

    def test_best_and_worst_pairs_ranking(self):
        row = lambda name, played, wins: {'name': name, 'played': played, 'wins': wins,
                                          'pct': pair_stats._pct(wins, played)}
        pairs = [row('a', 10, 9), row('b', 5, 1), row('c', 4, 4), row('d', 6, 3),
                 row('e', 8, 2), row('f', 3, 2), row('g', 1, 0), row('h', 7, 5)]
        best, worst = pair_stats.best_and_worst_pairs(pairs)
        self.assertEqual([r['name'] for r in best], ['c', 'a', 'h'])
        self.assertEqual([r['name'] for r in worst], ['b', 'e', 'd'])  # 'g' no llega al mínimo

        # Con pocas parejas se reparten sin repetir: 3 parejas -> 2 mejores y 1 peor
        best, worst = pair_stats.best_and_worst_pairs(pairs[:3])
        self.assertEqual(([r['name'] for r in best], [r['name'] for r in worst]), (['c', 'a'], ['b']))

    def test_pair_last_games(self):
        # Cinco partidos más de A+B: la tabla muestra solo los cinco más recientes
        own, rival = self.club.own_team, Team.objects.get(club=self.club, name="Rival")
        for day in range(1, 6):
            m = Match.objects.create(club=self.club, local=own, visiting=rival,
                                     start_date=datetime.date(2026, 1, day), draft_mode=False)
            Game.objects.create(match=m, n_game=1, score=3, winner='Visitante', draft_mode=False,
                                player_1_local=self.b, player_2_local=self.a)
        response = self.client.get(reverse("pair_statistics"), {"p1": self.a.public_id, "p2": self.b.public_id})
        games = response.context["last_games"]
        self.assertEqual([g["date"] for g in games], [datetime.date(2026, 1, d) for d in (5, 4, 3, 2, 1)])
        self.assertTrue(all(g["local"] and not g["won"] and g["rival"] == rival for g in games))
        self.assertContains(response, "Últimos 5 partidos")

    def test_pair_last_games_sets_and_side(self):
        m = Match.objects.get(start_date=datetime.date(2024, 11, 1))
        Result.objects.create(game=m.games.get(n_game=1), set1_local=6, set1_visiting=3,
                              set2_local=6, set2_visiting=4)
        response = self.client.get(reverse("pair_statistics"), {"p1": self.b.public_id, "p2": self.a.public_id})
        games = response.context["last_games"]
        self.assertEqual([(g["date"], g["n_game"], g["local"], g["won"]) for g in games], [
            (datetime.date(2025, 10, 1), 1, True, True),
            (datetime.date(2024, 11, 1), 1, False, False),
            (datetime.date(2024, 10, 1), 2, True, True),
            (datetime.date(2024, 10, 1), 1, True, True),
        ])
        self.assertEqual(games[1]["sets"], "3-6 4-6")

    def test_pair_view_rejects_other_club_players(self):
        other = create_club("Club B", "Madrid", User.objects.create_user("b", password="x"))
        foreign = Player.objects.create(club=other, name="X", last_name="Y")
        response = self.client.get(reverse("pair_statistics"), {"p1": self.a.public_id, "p2": foreign.public_id})
        self.assertEqual(response.status_code, 404)

    def test_team_statistics_chart_only_current_players(self):
        response = self.client.get(reverse("team_statistics"))
        names = [row["player"] for row in response.context["column_chart_data"]]
        self.assertNotIn("C CSON", names)
        self.assertIn("A ASON", names)
        self.assertEqual(len(response.context["top_local_players"]), 2)

    def test_team_statistics_chart_script_is_not_cut(self):
        # Un </script> dentro del script de los datos lo cerraba antes de tiempo y no se pintaba ningún gráfico.
        html = self.client.get(reverse("team_statistics")).content.decode()
        script = html[html.index("const teamData"):]
        script = script[:script.index("</script>")]
        self.assertIn("column_chart_data:", script)
        self.assertTrue(script.rstrip().endswith("};"))

    def test_player_streak_follows_match_date(self):
        """Un partido anterior en fecha pero creado después no cuenta como el último (antes se ordenaba por id)."""
        own, rival = self.club.own_team, Team.objects.get(club=self.club, name="Rival")
        m = Match.objects.create(club=self.club, local=own, visiting=rival,
                                 start_date=datetime.date(2025, 9, 1), draft_mode=False)
        Game.objects.create(match=m, n_game=1, score=3, winner='Visitante', draft_mode=False,
                            player_1_local=self.a, player_2_local=self.b)
        d = self.client.get(reverse("player_statistics"),
                            {"player": self.a.public_id, "season": "2025-2026"}).context["d"]
        self.assertEqual((d["streak_type"], d["streak_len"]), ("V", 2))

    def test_pair_last_games_with_competitive_filter(self):
        response = self.client.get(reverse("pair_statistics"),
                                   {"p1": self.a.public_id, "p2": self.b.public_id, "match_type": "competitivo"})
        self.assertEqual(len(response.context["last_games"]), 4)

    def test_player_season_games_table(self):
        response = self.client.get(reverse("player_statistics"), {"player": self.a.public_id, "season": "2024-2025"})
        games = response.context["d"]["games"]
        # Del más reciente al más antiguo: visitante (1 nov) y luego los 2 partidos en casa (1 oct)
        self.assertEqual(
            [(g["date"], g["n_game"], g["local"], g["won"], g["points"]) for g in games],
            [
                (datetime.date(2024, 11, 1), 1, False, False, 0),
                (datetime.date(2024, 10, 1), 1, True, True, 3),
                (datetime.date(2024, 10, 1), 2, True, True, 3),
            ],
        )
        self.assertEqual(games[0]["partner"], self.b)
        self.assertEqual(games[0]["rival"].name, "Rival")

        # Cada fila enlaza a su partido en la sección de partidos
        match_id = games[0]["match_public_id"]
        self.assertContains(response, f'{reverse("call_for_match", args=[match_id])}#partido-1')
        self.assertContains(self.client.get(reverse("call_for_match", args=[match_id])), 'id="partido-1"')

    def test_player_season_games_show_sets_from_player_side(self):
        m = Match.objects.get(start_date=datetime.date(2024, 11, 1))
        game = m.games.get(n_game=1)  # A+B de visitantes, pierden
        Result.objects.create(game=game, set1_local=6, set1_visiting=3, set2_local=6, set2_visiting=4)
        response = self.client.get(reverse("player_statistics"), {"player": self.a.public_id, "season": "2024-2025"})
        self.assertEqual(response.context["d"]["games"][0]["sets"], "3-6 4-6")

    def test_player_season_games_empty_and_only_selected_season(self):
        response = self.client.get(reverse("player_statistics"), {"player": self.d.public_id, "season": "2025-2026"})
        self.assertEqual([g["n_game"] for g in response.context["d"]["games"]], [2])
        self.assertIsNone(self.client.get(reverse("player_statistics"), {"player": self.d.public_id}).context["d"])

        e = Player.objects.create(club=self.club, name="E", last_name="Eson")
        response = self.client.get(reverse("player_statistics"), {"player": e.public_id, "season": "2025-2026"})
        self.assertEqual(response.context["d"]["games"], [])
        self.assertContains(response, "No jugó ningún partido esta temporada.")


class MatchTypeFilterTests(TestCase):
    """
    Un enfrentamiento (A+B gana, C+D... no juega), un reto (C+D gana) y un play off
    (A+B pierde), todos como locales.
    """

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        own = self.club.own_team
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        mk = lambda n: Player.objects.create(club=self.club, name=n, last_name=f"{n}son")
        self.a, self.b, self.c, self.d = mk("A"), mk("B"), mk("C"), mk("D")

        def match(date, match_type, p1, p2, won):
            m = Match.objects.create(club=self.club, local=own, visiting=rival, start_date=date, draft_mode=False,
                                     match_type=match_type, result="Victoria Local" if won else "Victoria Visitante")
            Game.objects.create(match=m, n_game=1, score=3, winner='Local' if won else 'Visitante', draft_mode=False,
                                player_1_local=p1, player_2_local=p2)

        match(datetime.date(2025, 10, 1), Match.ENFRENTAMIENTO, self.a, self.b, True)
        match(datetime.date(2025, 10, 8), Match.ENFRENTAMIENTO, self.a, self.b, True)
        match(datetime.date(2025, 10, 15), Match.RETO, self.c, self.d, True)
        match(datetime.date(2025, 10, 22), Match.PLAYOFF, self.a, self.b, False)
        self.client.force_login(self.user)

    def test_existing_matches_default_to_enfrentamiento(self):
        m = Match.objects.create(club=self.club, local=self.club.own_team,
                                 visiting=Team.objects.get(name="Rival"), start_date=datetime.date(2025, 11, 1))
        self.assertEqual(m.match_type, Match.ENFRENTAMIENTO)

    def test_team_statistics_filter_by_type(self):
        response = self.client.get(reverse("team_statistics"))
        self.assertEqual(response.context["total_matches"], 4)
        self.assertEqual(response.context["min_games_pair"], 2)
        self.assertEqual([r["name"] for r in response.context["top_local_pairs"]], ["A ASON / B BSON"])

        response = self.client.get(reverse("team_statistics"), {"match_type": Match.RETO})
        self.assertEqual((response.context["total_matches"], response.context["won_matches"]), (1, 1))
        # En retos y play off no hay mínimo de partidos por pareja
        self.assertEqual(response.context["min_games_pair"], 1)
        self.assertEqual([r["name"] for r in response.context["top_local_pairs"]], ["C CSON / D DSON"])

        response = self.client.get(reverse("team_statistics"), {"match_type": Match.ENFRENTAMIENTO})
        self.assertEqual(response.context["total_matches"], 2)
        self.assertEqual(response.context["min_games_pair"], 2)

    def test_filter_links_keep_other_parameters(self):
        response = self.client.get(reverse("player_statistics"), {"player": self.a.public_id, "match_type": Match.PLAYOFF})
        self.assertEqual((response.context["s"]["played"], response.context["s"]["wins"]), (1, 0))
        links = {o["label"]: o["url"] for o in response.context["match_types"]}
        self.assertEqual(links["Todos"], f"{reverse('player_statistics')}?player={self.a.public_id}")
        types = {o["label"]: o["url"] for o in response.context["competitive_types"]}
        self.assertIn(f"player={self.a.public_id}", types["Retos"])
        self.assertIn("match_type=reto", types["Retos"])

    def test_pair_statistics_filter_by_type(self):
        response = self.client.get(reverse("pair_statistics"))
        pairs = [(r["p1"].name, r["p2"].name) for r in response.context["best_pairs"] + response.context["worst_pairs"]]
        self.assertEqual(pairs, [("A", "B")])  # C+D solo tiene 1 partido

        response = self.client.get(reverse("pair_statistics"), {"match_type": Match.RETO})
        pairs = [(r["p1"].name, r["p2"].name) for r in response.context["best_pairs"] + response.context["worst_pairs"]]
        self.assertEqual(pairs, [("C", "D")])

        response = self.client.get(reverse("pair_statistics"),
                                   {"p1": self.a.public_id, "p2": self.b.public_id, "match_type": Match.ENFRENTAMIENTO})
        self.assertEqual(response.context["s"]["played"], 2)
        self.assertEqual(len(response.context["last_games"]), 2)

    def test_unknown_type_shows_everything(self):
        response = self.client.get(reverse("team_statistics"), {"match_type": "otro"})
        self.assertEqual(response.context["total_matches"], 4)
        self.assertIsNone(response.context["selected_match_type"])

    def test_friendly_matches_have_their_own_filter(self):
        Match.objects.create(club=self.club, local=self.club.own_team, visiting=Team.objects.get(name="Rival"),
                             start_date=datetime.date(2025, 11, 5), draft_mode=False,
                             match_type=Match.AMISTOSO, result="Victoria Local")
        self.assertEqual(self.client.get(reverse("team_statistics")).context["total_matches"], 5)
        response = self.client.get(reverse("team_statistics"), {"match_type": Match.AMISTOSO})
        self.assertEqual(response.context["total_matches"], 1)
        self.assertEqual([o["label"] for o in response.context["match_types"] if o["active"]], ["Amistosos"])
        self.assertEqual(response.context["competitive_types"], [])
        response = self.client.get(reverse("team_statistics"), {"match_type": Match.ENFRENTAMIENTO})
        self.assertEqual(response.context["total_matches"], 2)

    def test_competitive_groups_every_competitive_type(self):
        Match.objects.create(club=self.club, local=self.club.own_team, visiting=Team.objects.get(name="Rival"),
                             start_date=datetime.date(2025, 11, 5), draft_mode=False,
                             match_type=Match.AMISTOSO, result="Victoria Local")
        response = self.client.get(reverse("team_statistics"), {"match_type": "competitivo"})
        self.assertEqual(response.context["total_matches"], 4)
        self.assertEqual([o["label"] for o in response.context["match_types"] if o["active"]], ["Competitivos"])
        self.assertEqual([o["label"] for o in response.context["competitive_types"]],
                         ["Todos los partidos", "Enfrentamientos", "Retos", "Play offs"])
        self.assertContains(response, 'id="competitive-type"')

        # Un tipo concreto sigue dentro de Competitivos, con el selector en ese tipo
        response = self.client.get(reverse("team_statistics"), {"match_type": Match.RETO})
        self.assertEqual([o["label"] for o in response.context["match_types"] if o["active"]], ["Competitivos"])
        self.assertEqual([o["label"] for o in response.context["competitive_types"] if o["active"]], ["Retos"])

        response = self.client.get(reverse("pair_statistics"), {"match_type": "competitivo"})
        pairs = [(r["p1"].name, r["p2"].name) for r in response.context["best_pairs"] + response.context["worst_pairs"]]
        self.assertEqual(pairs, [("A", "B")])

    def test_competitive_selector_keeps_other_parameters(self):
        response = self.client.get(reverse("player_statistics"), {"player": self.a.public_id, "match_type": "competitivo"})
        self.assertEqual(response.context["match_type_keep"], [("player", self.a.public_id)])
        self.assertContains(response, f'<input type="hidden" name="player" value="{self.a.public_id}">', html=True)
        self.assertContains(response, '<option value="reto" >')

    def test_all_hides_competitive_selector(self):
        response = self.client.get(reverse("team_statistics"))
        self.assertEqual(response.context["competitive_types"], [])
        self.assertNotContains(response, 'id="competitive-type"')


class SeasonFilterTests(TestCase):
    """Cinco temporadas con un partido cada una (2021-2022 ... 2025-2026)."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        self.a = Player.objects.create(club=self.club, name="A", last_name="Ason")
        for year in range(2021, 2026):
            m = Match.objects.create(club=self.club, local=self.club.own_team, visiting=rival,
                                     start_date=datetime.date(year, 10, 1), draft_mode=False,
                                     match_type=Match.AMISTOSO if year == 2021 else Match.ENFRENTAMIENTO,
                                     result="Victoria Local")
            Game.objects.create(match=m, n_game=1, score=3, winner='Local', draft_mode=False, player_1_local=self.a)
        self.client.force_login(self.user)

    def test_all_plus_last_three_and_search_with_every_season(self):
        response = self.client.get(reverse("team_statistics"))
        self.assertTrue(response.context["season_all"]["active"])
        self.assertEqual([c["label"] for c in response.context["season_chips"]], ["2025-2026", "2024-2025", "2023-2024"])
        self.assertEqual(response.context["season_search"],
                         ["2025-2026", "2024-2025", "2023-2024", "2022-2023", "2021-2022"])
        self.assertContains(response, 'id="season-search"')

    def test_older_season_from_search_shows_as_active_chip(self):
        response = self.client.get(reverse("team_statistics"), {"season": "2021-2022"})
        self.assertEqual(response.context["total_matches"], 1)
        self.assertFalse(response.context["season_all"]["active"])
        self.assertEqual([(c["label"], c["active"]) for c in response.context["season_chips"]],
                         [("2025-2026", False), ("2024-2025", False), ("2023-2024", False), ("2021-2022", True)])

    def test_season_links_and_search_keep_match_type(self):
        url = reverse("player_statistics")
        response = self.client.get(url, {"player": self.a.public_id, "season": "2021-2022", "match_type": Match.AMISTOSO})
        self.assertEqual(response.context["s"]["played"], 1)
        self.assertEqual(response.context["season_all"]["url"],
                         f"{url}?player={self.a.public_id}&match_type=amistoso#temporadas")
        self.assertIn("match_type=amistoso", response.context["season_chips"][0]["url"])
        self.assertEqual(response.context["season_keep"],
                         [("player", self.a.public_id), ("match_type", Match.AMISTOSO)])
        # Cambiar el tipo de partido conserva la temporada
        links = {o["label"]: o["url"] for o in response.context["match_types"]}
        self.assertIn("season=2021-2022", links["Competitivos"])

    def test_unknown_season_shows_all(self):
        response = self.client.get(reverse("team_statistics"), {"season": "1999-2000"})
        self.assertIsNone(response.context["selected_season"])
        self.assertEqual(response.context["total_matches"], 5)

    def test_no_search_with_three_seasons_or_fewer(self):
        Match.objects.filter(start_date__year__lt=2023).delete()
        response = self.client.get(reverse("team_statistics"))
        self.assertEqual(response.context["season_search"], [])
        self.assertNotContains(response, 'id="season-search"')

    def test_warnings_all_uses_explicit_value(self):
        response = self.client.get(reverse("warnings_statistics"))
        self.assertFalse(response.context["season_all"]["active"])
        self.assertTrue(response.context["season_all"]["url"].endswith("?season=all"))
        response = self.client.get(reverse("warnings_statistics"), {"season": "all"})
        self.assertTrue(response.context["season_all"]["active"])


class AffinityScopeTests(TestCase):
    """A juega con B (sigue en el equipo), C (ya no está) y D (eliminado)."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        own = self.club.own_team
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        mk = lambda n, **kw: Player.objects.create(club=self.club, name=n, last_name=f"{n}son", **kw)
        self.a, b, c, d = mk("A"), mk("B"), mk("C", in_team=False), mk("D")
        for i, partner in enumerate((b, c, d)):
            m = Match.objects.create(club=self.club, local=own, visiting=rival, draft_mode=False,
                                     start_date=datetime.date(2025, 10, 1 + i), result="Victoria Local")
            Game.objects.create(match=m, n_game=1, score=3, winner='Local', draft_mode=False,
                                player_1_local=self.a, player_2_local=partner)
        d.delete()
        self.client.force_login(self.user)

    def test_affinity_marks_partners_not_in_team(self):
        response = self.client.get(reverse("player_statistics"), {"player": self.a.public_id})
        rows = {r["name"]: r["in_team"] for r in response.context["chart_affinity"]}
        self.assertEqual(rows, {"B BSON": True, "C CSON": False, "D DSON": False})
        self.assertContains(response, 'data-scope="team" aria-pressed="true"')


class DrawStatisticsTests(TestCase):
    """Una eliminatoria empatada a puntos (6-6) cuenta como empate, no como derrota."""

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        own = self.club.own_team
        rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        for day, result in ((1, "Victoria Local"), (8, "EMPATE"), (15, "Victoria Visitante")):
            Match.objects.create(club=self.club, local=own, visiting=rival, draft_mode=False,
                                 start_date=datetime.date(2025, 10, day), result=result)
        self.client.force_login(self.user)

    def test_team_statistics_count_draws(self):
        response = self.client.get(reverse("team_statistics"))
        self.assertEqual(response.context["total_matches"], 3)
        self.assertEqual(response.context["won_matches"], 1)
        self.assertEqual(response.context["drawn_matches"], 1)
        self.assertEqual(response.context["lost_matches"], 1)
        self.assertEqual(response.context["percentage_drawn"], 33.33)
        self.assertEqual(response.context["dicc_line_chart"], {"2025-2026": {"won": 1, "drawn": 1, "lost": 1}})
        self.assertContains(response, "Empates")
