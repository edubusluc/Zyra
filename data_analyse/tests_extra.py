"""Tests de las estadísticas de sets, número de partido, récords, ranking SNP y apuntado/alineado."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from call.models import Call
from core.services import create_club
from data_analyse import pairs as pair_stats
from data_analyse import records
from data_analyse.sets import best_and_worst_number, by_game_number, own_sets, set_stats
from match.models import Game, Match, Result
from players.models import Player, SnpScoreHistory
from team.models import Team

User = get_user_model()


class SetStatsUnitTests(TestCase):
    """Reglas de sets de pádel aplicadas a listas de partidos ya preparadas."""

    def test_rules(self):
        games = [
            {'won': True, 'sets': [(6, 4), (6, 0)]},              # rosco dado, cierra tras ganar el 1.º
            {'won': True, 'sets': [(4, 6), (7, 6), (6, 3)]},      # remontada con tie-break y tercer set
            {'won': False, 'sets': [(7, 5), (3, 6), (8, 10)]},    # ventaja perdida, super tie-break perdido
            {'won': False, 'sets': [(0, 6), (6, 7)]},             # rosco recibido, tie-break perdido
            {'won': True, 'sets': []},                            # sin resultado: no cuenta
        ]
        st = set_stats(games)
        self.assertEqual(st['played'], 4)
        self.assertEqual((st['sets_won'], st['sets_lost']), (5, 5))
        self.assertEqual(st['third'], {'wins': 1, 'losses': 1, 'total': 2, 'pct': 50})
        self.assertEqual(st['third_share'], 50)
        self.assertEqual(st['super_tb'], {'wins': 0, 'losses': 1, 'total': 1, 'pct': 0})
        self.assertEqual(st['tiebreak'], {'wins': 1, 'losses': 1, 'total': 2, 'pct': 50})
        self.assertEqual(st['close'], {'wins': 2, 'losses': 1, 'total': 3, 'pct': 67})
        self.assertEqual(st['comeback'], {'wins': 1, 'losses': 1, 'total': 2, 'pct': 50})
        self.assertEqual(st['first_set'], {'wins': 1, 'losses': 1, 'total': 2, 'pct': 50})
        self.assertEqual((st['bagels_for'], st['bagels_against']), (1, 1))
        # El super tie-break no suma juegos
        self.assertEqual((st['games_won'], st['games_lost']), (6 + 6 + 4 + 7 + 6 + 7 + 3 + 0 + 6, 4 + 0 + 6 + 6 + 3 + 5 + 6 + 6 + 7))

    def test_empty(self):
        st = set_stats([])
        self.assertEqual(st['played'], 0)
        self.assertIsNone(st['third']['pct'])

    def test_own_sets_view_and_legacy_third_set(self):
        r = Result(set1_local=6, set1_visiting=3, set2_local=6, set2_visiting=4, set3_local=0, set3_visiting=0)
        self.assertEqual(own_sets(r, True), [(6, 3), (6, 4)])
        self.assertEqual(own_sets(r, False), [(3, 6), (4, 6)])
        self.assertEqual(own_sets(None, True), [])

    def test_by_game_number(self):
        games = [{'n_game': 1, 'won': True}, {'n_game': 1, 'won': False}, {'n_game': 3, 'won': True},
                 {'n_game': 3, 'won': True}, {'n_game': None, 'won': True}]
        rows = by_game_number(games)
        self.assertEqual([r['n'] for r in rows], [1, 2, 3, 4, 5])
        self.assertEqual((rows[0]['played'], rows[0]['wins'], rows[0]['pct'], rows[0]['points'], rows[0]['stake']),
                         (2, 1, 50, 3, 6))
        self.assertEqual((rows[2]['value'], rows[2]['points']), (2, 4))
        self.assertIsNone(rows[1]['pct'])
        best, worst = best_and_worst_number(rows)
        self.assertEqual((best['n'], worst['n']), (3, 1))


class ClubDataMixin:
    """
    Club con dos enfrentamientos cerrados (2025-2026) y resultados set a set:
      10/10 local     A+B gana 6-4 6-0 (partido 1), C+D pierde 6-7 7-5 8-10 (partido 2) → empate 3-3
      01/11 visitante A+B gana 4-6 6-3 6-2 (partido 1), C+D gana 6-1 6-1 (partido 3) → victoria 5-0
    """

    def setUp(self):
        self.user = User.objects.create_user("admin", password="pass-12345")
        self.club = create_club("Club A", "Sevilla", self.user)
        own = self.club.own_team
        self.rival = Team.objects.create(club=self.club, name="Rival", location="X", in_group=True)
        mk = lambda n, snp: Player.objects.create(club=self.club, name=n, last_name=f"{n}son", snp_score=snp)  # noqa: E731
        self.a, self.b, self.c, self.d = mk("A", 40), mk("B", 30), mk("C", 20), mk("D", None)
        self.e = mk("E", 10)  # se apunta pero no juega

        def match(date, own_local, games, result):
            m = Match.objects.create(
                club=self.club, local=own if own_local else self.rival, visiting=self.rival if own_local else own,
                start_date=date, draft_mode=False, result=result,
            )
            side = 'local' if own_local else 'visiting'
            for n, p1, p2, won, sets in games:
                winner = ('Local' if own_local else 'Visitante') if won else ('Visitante' if own_local else 'Local')
                g = Game.objects.create(match=m, n_game=n, score=3 if n < 3 else 2, winner=winner, draft_mode=False,
                                        **{f'player_1_{side}': p1, f'player_2_{side}': p2})
                values = {}
                for i, (own_games, rival_games) in enumerate(sets, start=1):
                    loc, vis = (own_games, rival_games) if own_local else (rival_games, own_games)
                    values[f'set{i}_local'], values[f'set{i}_visiting'] = loc, vis
                Result.objects.bulk_create([Result(game=g, draft_mode=False, **values)])
            call = Call.objects.create(match=m, draft_mode=False)
            call.players.set([self.a, self.b, self.c, self.d, self.e])
            return m

        self.m1 = match(datetime.date(2025, 10, 10), True, [
            (1, self.a, self.b, True, [(6, 4), (6, 0)]),
            (2, self.c, self.d, False, [(6, 7), (7, 5), (8, 10)]),
        ], "EMPATE")
        self.m2 = match(datetime.date(2025, 11, 1), False, [
            (1, self.a, self.b, True, [(4, 6), (6, 3), (6, 2)]),
            (3, self.c, self.d, True, [(6, 1), (6, 1)]),
        ], "Victoria Visitante")
        self.client.login(username="admin", password="pass-12345")


class ClubSetsTests(ClubDataMixin, TestCase):

    def test_club_log_has_sets_and_game_number(self):
        log = pair_stats.club_game_log(self.club)
        self.assertEqual([g['n_game'] for g in log], [1, 2, 1, 3])
        # El segundo enfrentamiento es como visitante: los sets se ven desde el club
        self.assertEqual(log[2]['sets'], [(4, 6), (6, 3), (6, 2)])
        st = set_stats(log)
        self.assertEqual(st['third'], {'wins': 1, 'losses': 1, 'total': 2, 'pct': 50})
        self.assertEqual(st['super_tb']['total'], 1)
        self.assertEqual(st['comeback']['wins'], 1)

    def test_records(self):
        rec = records.team_records(self.club)
        self.assertEqual(rec['biggest_win']['own'], 5)
        self.assertEqual(rec['biggest_win']['rival'], 0)
        self.assertNotIn('worst_defeat', rec)
        self.assertNotIn('win_streak', rec)
        self.assertEqual(rec['unbeaten']['n'], 2)
        self.assertEqual(rec['game_streak']['n'], 2)
        self.assertEqual(rec['top_player']['n'], 2)  # A y B: 2 victorias; desempata el nombre
        self.assertEqual(rec['top_player']['name'], self.a.full_name)
        self.assertEqual(rec['top_pair']['n'], 2)

    def test_snp_ranking(self):
        season = "2025-2026"
        for day, score in ((1, 35), (8, 40)):
            SnpScoreHistory.objects.create(player=self.a, season=season, date=datetime.date(2025, 10, day), score=score)
        SnpScoreHistory.objects.create(player=self.b, season=season, date=datetime.date(2025, 10, 1), score=30)
        snp = records.snp_ranking(self.club, season)
        self.assertEqual([r['player'] for r in snp['rows']], [self.a, self.b, self.c, self.e])  # D sin puntos
        self.assertEqual(snp['rows'][0]['delta'], 5)
        self.assertEqual(snp['rows'][1]['delta'], 0)
        self.assertIsNone(snp['rows'][2]['delta'])
        self.assertEqual(snp['riser']['player'], self.a)
        self.assertEqual(snp['chart'], {'labels': ['01/10', '08/10'], 'average': [32.5, 40.0]})

    def test_team_page_shows_new_sections(self):
        response = self.client.get(reverse('team_statistics'))
        self.assertContains(response, "Por número de partido")
        self.assertContains(response, "Set decisivo")
        self.assertContains(response, "Récords del equipo")
        self.assertContains(response, "Ranking SNP del equipo")
        self.assertEqual(response.context['records']['biggest_win']['own'], 5)

    def test_player_page_clutch_and_lineup_rate(self):
        response = self.client.get(reverse('player_statistics'), {'player': self.c.public_id})
        self.assertContains(response, "Sets clutch")
        self.assertEqual(response.context['clutch']['tiebreak']['total'], 1)
        self.assertEqual(response.context['lineup_rate'], {'signed': 2, 'aligned': 2, 'benched': 0, 'pct': 100})
        rows = response.context['game_numbers']
        self.assertEqual((rows[1]['played'], rows[2]['wins']), (1, 1))

        response = self.client.get(reverse('player_statistics'), {'player': self.e.public_id})
        self.assertEqual(response.context['lineup_rate'], {'signed': 2, 'aligned': 0, 'benched': 2, 'pct': 0})

    def test_pair_page_sets(self):
        response = self.client.get(reverse('pair_statistics'), {'p1': self.a.public_id, 'p2': self.b.public_id})
        self.assertContains(response, "Sets de la pareja")
        st = response.context['pair_sets']
        self.assertEqual((st['played'], st['comeback']['wins'], st['bagels_for']), (2, 1, 1))
