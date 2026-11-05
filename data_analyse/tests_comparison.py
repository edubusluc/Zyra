"""Fase 6: situaciones de set comunes, bloque «Local y visitante», tendencias con muestra y compañeros."""
from django.test import SimpleTestCase

from data_analyse import comparison
from data_analyse.views import summarize_by_season


def _situation(wins, losses):
    """Situación de set con el formato de data_analyse.sets.set_stats."""
    total = wins + losses
    return {'wins': wins, 'losses': losses, 'total': total, 'pct': round(100 * wins / total) if total else None}


class SetSituationTests(SimpleTestCase):
    """Todas las vistas usan las mismas situaciones, con nombre literal y solo las que tienen casos."""

    def stats(self, **kw):
        """set_stats mínimo para las pruebas."""
        base = {key: _situation(0, 0) for key in ('first_set', 'comeback', 'tiebreak', 'third')}
        base.update(sets_won=0, sets_lost=0, bagels_for=0)
        base.update(kw)
        return base

    def test_literal_names_and_order(self):
        rows = comparison.set_situation_rows(self.stats(
            first_set=_situation(3, 1), comeback=_situation(1, 1), tiebreak=_situation(2, 0),
            third=_situation(1, 2), sets_won=10, sets_lost=6, bagels_for=2))
        self.assertEqual([str(label) for label, _hint, _r in rows],
                         ["Tras ganar el 1.er set", "Tras perder el 1.er set", "Tie-breaks", "Set decisivo", "Roscos a favor"])
        self.assertEqual(rows[-1][2], {'wins': 2, 'losses': 14, 'total': 16, 'pct': 12, 'unit': 'sets'})
        self.assertEqual([r['unit'] for _l, _h, r in rows], ['games', 'games', 'sets', 'games', 'sets'])

    def test_rows_without_cases_are_left_out(self):
        rows = comparison.set_situation_rows(self.stats(tiebreak=_situation(1, 1)))
        self.assertEqual([str(label) for label, _hint, _r in rows], ["Tie-breaks"])
        self.assertEqual(comparison.set_situation_rows(self.stats()), [])


class VenueSplitTests(SimpleTestCase):
    """El bloque Local y visitante lleva su unidad y sus bases."""

    def test_rows_and_percentages(self):
        venue = comparison.venue_split({'won': 5, 'lost': 2}, {'won': 0, 'lost': 0}, 'matches')
        self.assertEqual(venue['unit'], 'matches')
        local, visiting = venue['rows']
        self.assertEqual((local['total'], local['pct']), (7, 71))
        self.assertEqual((visiting['total'], visiting['pct']), (0, None))

    def test_draws_count_in_the_base(self):
        row = comparison.venue_split({'won': 1, 'lost': 1, 'drawn': 2}, {}, 'matches')['rows'][0]
        self.assertEqual((row['total'], row['pct']), (4, 25))


class TrendTests(SimpleTestCase):
    """Sin evolución ni cambio de % por debajo de la muestra mínima."""

    def log(self, **played):
        """Partidos (todos ganados salvo el último de cada temporada) por temporada."""
        out = []
        for season, n in played.items():
            out += [{'season': season.replace('_', '-'), 'won': i < n - 1, 'points': 1} for i in range(n)]
        return out

    def test_delta_needs_both_seasons_with_sample(self):
        rows = summarize_by_season(self.log(**{'2023_2024': 6, '2024_2025': 1, '2025_2026': 7}), {}, {})
        self.assertEqual([r['delta'] for r in rows], [None, None, None])
        rows = summarize_by_season(self.log(**{'2023_2024': 6, '2024_2025': 8}), {}, {})
        self.assertIsNotNone(rows[1]['delta'])
        self.assertEqual([r['reliable'] for r in rows], [True, True])

    def test_trend_requires_two_valid_seasons(self):
        rows = summarize_by_season(self.log(**{'2023_2024': 3, '2024_2025': 1, '2025_2026': 9}), {}, {})
        self.assertIsNone(comparison.trend(rows))
        rows = summarize_by_season(self.log(**{'2023_2024': 5, '2024_2025': 1, '2025_2026': 9}), {}, {})
        trend = comparison.trend(rows)
        self.assertEqual((trend['labels'], trend['played']), (['2023-2024', '2025-2026'], [5, 9]))


class PartnerRowsTests(SimpleTestCase):
    """Compañeros con su % real; la afinidad suavizada solo desempata."""

    def partner(self, name, games, wins, affinity=50, in_team=True):
        """Fila como las de degree_of_affinity."""
        return {'name': name, 'public_id': name, 'games': games, 'wins': wins, 'losses': games - wins,
                'affinity': affinity, 'in_team': in_team}

    def test_usual_partner_first_and_real_percentage(self):
        rows = comparison.partner_rows([self.partner('Nuevo', 1, 1, 62), self.partner('Habitual', 3, 2, 54),
                                        self.partner('Baja', 9, 9, 90, in_team=False)])
        self.assertEqual([r['name'] for r in rows], ['Habitual', 'Nuevo'])
        self.assertEqual([r['pct'] for r in rows], [67, 100])

    def test_best_and_worst_only_with_sample(self):
        rows = comparison.partner_rows([self.partner('A', 6, 5), self.partner('B', 5, 1), self.partner('C', 5, 3),
                                        self.partner('D', 2, 0)])
        flags = {r['name']: (r.get('best'), r.get('worst')) for r in rows}
        self.assertEqual(flags['A'], (True, None))
        self.assertEqual(flags['B'], (None, True))
        self.assertEqual(flags['D'], (None, None))



class VisibleBaseTests(SimpleTestCase):
    """Cada barra con % enseña, en texto visible, de dónde sale (no solo en el title)."""

    def render(self, template, **ctx):
        """Renderiza una plantilla incluida con el contexto dado."""
        from django.template.loader import render_to_string
        return render_to_string(template, ctx)

    def test_set_bar_shows_n_of_m_with_unit(self):
        html = self.render('includes/stat_bar_row.html', label='Tie-breaks', desc='x',
                           r=dict(_situation(2, 1), unit='sets'))
        self.assertIn('st-bar-base">2 de 3 sets<', html)
        html = self.render('includes/stat_bar_row.html', label='Set decisivo', desc='x',
                           r=dict(_situation(1, 0), unit='games'))
        self.assertIn('1 de 1 partido<', html)

    def test_game_number_row_shows_balance_and_games(self):
        r = {'n': 1, 'value': 3, 'played': 3, 'wins': 2, 'losses': 1, 'pct': 67}
        self.assertIn('2V – 1D · 3 partidos', self.render('includes/game_number_row.html', r=r))
        empty = {'n': 2, 'value': 2, 'played': 0, 'wins': 0, 'losses': 0, 'pct': None}
        self.assertIn('Sin partidos todavía', self.render('includes/game_number_row.html', r=empty))
