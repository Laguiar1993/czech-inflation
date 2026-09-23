"""Semantic checks for the dashboard's financial meaning, not its markup."""
import json
import tempfile
from pathlib import Path
import unittest
from tools.inflation_dashboard_r32 import build


class DashboardTests(unittest.TestCase):
    def test_modified_frozen_export_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            path.write_text('{"value": 1}', encoding='utf8')
            expected = build.digest(path)
            (path.parent / 'manifest.json').write_text(json.dumps({'outputs': {'data.json': expected}}))
            build.verify_export(path)
            path.write_text('{"value": 2}', encoding='utf8')
            with self.assertRaises(ValueError):
                build.verify_export(path)

    def test_contribution_change_includes_residual_and_reconciles(self):
        monitor = dict(history=dict(months=['2026-06', '2026-07'],
            contributions={'food': [-.2, -.5], 'rents': [.9, 1.1]},
            residual=[.1, .2], headline=[.8, .8]),
            blocks={'food': {'label': 'Food'}, 'rents': {'label': 'Rents'}})
        rows = build.contribution_rows(monitor, 1)
        self.assertAlmostEqual(sum(r['value'] for r in rows), 0.)
        self.assertAlmostEqual(next(r['value'] for r in rows if r['id'] == 'residual'), .1)
        self.assertAlmostEqual(next(r['value'] for r in rows if r['id'] == 'food'), -.3)

    def test_partial_quarter_is_not_a_quarter_forecast(self):
        points = [['2026-07', 1.], ['2026-08', 2.]]
        self.assertIsNone(build.quarter_average(points, '2026Q3'))
        self.assertEqual(build.quarter_average(points + [['2026-09', 6.]], '2026Q3'), 3.)

    def test_breadth_is_weighted_and_equality_is_not_acceleration(self):
        groups = [{'weight_permille': 600, 'd3_yy': .1},
                  {'weight_permille': 300, 'd3_yy': -.1},
                  {'weight_permille': 100, 'd3_yy': 0}]
        self.assertEqual(build.weighted_breadth(groups), 60.)

    def test_missing_group_cannot_be_silently_dropped(self):
        with self.assertRaises(ValueError):
            build.weighted_breadth([{'weight_permille': 1000, 'd3_yy': None}])

    def test_current_view_does_not_invent_a_live_forecast(self):
        data = build.assemble()
        self.assertEqual(data['live']['status'], 'unavailable')
        self.assertIsNone(data['live']['point'])
        self.assertEqual(data['vintages']['model_origin'], '2026-07')
        self.assertEqual(data['vintages']['groups'], '2026-07')
        self.assertEqual(data['vintages']['headline'], '2026-08')
        self.assertEqual(data['replay']['reportsByClock']['report'][-1]['score']['n'], 0)

    def test_archived_nowcast_components_reconcile(self):
        run = build.assemble()['last_r31c_run']
        self.assertEqual(run['period'], '2026-07')
        self.assertAlmostEqual(sum(v for k, v in run.items() if k.startswith('contrib_')), run['HARD_BASE'])

    def test_scorecard_uses_accepted_r31c_input_lane(self):
        rows = build.assemble()['scores']['nowcast']
        base = next(r for r in rows if r['model'] == 'HARD_BASE' and r['sample'] == 'all')
        self.assertEqual(base['source'], 'C123')
        self.assertEqual(base['n'], 90)
        self.assertAlmostEqual(base['rmse'], .4159, places=4)

    def test_snapshot_level_and_change_account_for_headline(self):
        data = build.assemble()
        history = data['monitor']['history']
        for lag in (0, 1, 3):
            expected = history['headline'][-1] - (history['headline'][-1-lag] if lag else 0.)
            self.assertAlmostEqual(sum(r['value'] for r in data['drivers'][str(lag)]), expected)


if __name__ == '__main__':
    unittest.main()
