import copy
import unittest
from tools.inflation_dashboard_r33 import analysis

class AnalysisTests(unittest.TestCase):
    def test_release_briefing_uses_matching_detailed_months(self):
        data=analysis.assemble()
        b=data['briefings']['1']
        self.assertEqual((b['from_month'],b['to_month']),('2026-06','2026-07'))
        self.assertAlmostEqual(b['headline_change'],.2)
        self.assertAlmostEqual(sum(r['value'] for r in b['drivers']),.2)

    def test_housing_split_does_not_double_count_rents(self):
        data=analysis.assemble()
        rows=data['pressure_rows']
        self.assertNotIn('rents',[r['id'] for r in rows])
        self.assertIn('actual_rent',[r['id'] for r in rows])
        self.assertIn('imputed_rent',[r['id'] for r in rows])
        self.assertAlmostEqual(sum(r['weight'] for r in rows),1000,places=5)

    def test_gap_parts_reconcile_and_residual_is_not_called_food(self):
        row=dict(quarter='2026Q4',gap=-.3,model=2.,cnb=2.3,
                 parts=dict(core=.1,food_alc_tobacco=-.2,fuel=.1,administered=0.,unexplained=-.3),complete=True)
        result=analysis.explain_gap(row)
        self.assertTrue(result['residual_dominant'])
        self.assertIn('residual',result['summary'].lower())
        self.assertAlmostEqual(sum(r['value'] for r in result['parts']),row['gap'])

    def test_gap_inconsistency_is_rejected(self):
        with self.assertRaises(ValueError):
            analysis.explain_gap(dict(quarter='2026Q4',gap=-.3,parts={'core':-.2},complete=True))

    def test_zero_scenario_exactly_preserves_archived_path(self):
        rows=[dict(month='2026-09',model_mm=.2,implied_yy_model=2.5,forecast_kind='rebased')]
        self.assertEqual(analysis.scenario_path(rows,0,0,0)[0]['scenario_yy'],2.5)

    def test_energy_scenario_starts_in_january_and_compounds(self):
        rows=[dict(month='2026-12',model_mm=.1,implied_yy_model=2.,forecast_kind='rebased'),
              dict(month='2027-01',model_mm=.2,implied_yy_model=2.1,forecast_kind='rebased')]
        result=analysis.scenario_path(rows,0,0,.3)
        self.assertEqual(result[0]['scenario_yy'],2.)
        self.assertAlmostEqual(result[1]['scenario_yy'],102.1*1.005/1.002-100)

    def test_scenario_shock_leaves_annual_window_after_twelve_months(self):
        rows=[dict(month=analysis.month_offset('2026-09',i),model_mm=0.,implied_yy_model=2.,forecast_kind='rebased') for i in range(15)]
        result=analysis.scenario_path(rows,.1,0,0)
        self.assertGreater(result[11]['scenario_yy'],2.)
        self.assertAlmostEqual(result[14]['scenario_yy'],2.)

    def test_model_horizon_not_extended_with_seasonal_fallback(self):
        rows=[dict(month='2026-09',model_mm=0.,implied_yy_model=2.,forecast_kind='rebased'),
              dict(month='2026-10',model_mm=0.,implied_yy_model=2.,forecast_kind='seasonal_scenario')]
        self.assertEqual(len(analysis.scenario_path(rows,0,0,0)),1)

    def test_broad_definitions_distinguished_from_czso_totals(self):
        d=analysis.assemble()
        self.assertEqual(d['source_issues'],[])
        self.assertEqual(d['broad_definitions']['concepts']['services'],'Nontradables excluding regulated prices')
        self.assertEqual(d['official_release']['cnb_august']['core'],3.0)

    def test_gap_clock_kept_separate(self):
        data=analysis.assemble()
        for clock,reports in data['replay']['reportsByClock'].items():
            for r in reports:
                for model,rows in r['gaps'].items():
                    self.assertEqual(data['gap_explanations'][clock][r['id']][model],[analysis.explain_gap(x) for x in rows])

    def test_historical_run_is_not_current_news(self):
        data=analysis.assemble()
        self.assertEqual(data['revision']['status'],'unavailable')
        self.assertIsNone(data['revision'].get('delta'))
        self.assertEqual(data['watch'][0]['next_release'],'2026-10-06')
        self.assertTrue(all(r.get('next_release') is None for r in data['watch'][1:]))

if __name__=='__main__':
    unittest.main()
