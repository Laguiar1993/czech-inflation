"""Hash-consistent archive mutants; no network, model fitting, or X-13 process."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import analysis, build
from . import test_inputs


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the official-format byte fixture, including real source validation.
        # These are synthetic observations/adjustments, not another model run.
        test_inputs.InputsTests.setUpClass()
        cls.source = test_inputs.InputsTests()
        cls.source.setUp()
        cls.addClassCleanup(cls.source.tearDown)
        cls.source.write_capture()
        cls.inp = cls.source.prepare()
        cls.start = datetime.now(timezone.utc).isoformat()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='momentum_r35_archive_', dir=build.ROOT/'work')
        self.addCleanup(temp.cleanup)
        self.out = Path(temp.name)
        self.levels = self.inp['levels'].copy()
        n = len(self.levels)
        self.sa = pd.DataFrame({g: 100*np.exp((.001+j*.00001)*np.arange(n))
                                for j, g in enumerate(self.levels)}, index=self.levels.index)
        self.endpoints = {g: self.sa[g].iloc[:-1].copy() for g in self.sa}
        self.diag = {}
        for g in self.sa:
            full = self.adjustment(g, 'full', self.levels[g], self.sa[g])
            full['endpoint_check'] = self.adjustment(g, 'previous_endpoint',
                                                     self.levels[g].iloc[:-1], self.endpoints[g])
            self.diag[g] = full
        self.recalculate()
        self.seal()

    def adjustment(self, group, sample, observed, adjusted, status='ok'):
        folder = self.out/'x13'/sample/group
        folder.mkdir(parents=True, exist_ok=True)
        diag = dict(schema='momentum_r35_x13/v1', name=group, status=status,
                    method='synthetic archived D11 fixture', quality_flags=[],
                    created_at_utc=self.start,
                    input=dict(n=len(observed), start=str(observed.index[0]), end=str(observed.index[-1])))
        observed.to_csv(folder/'input.csv', index_label='month', float_format='%.17g')
        if status == 'ok':
            self.write_d11(folder/'series.d11', adjusted)
        build.dump(folder/'diagnostics.json', diag)
        return diag

    @staticmethod
    def write_d11(path, series):
        text = 'date series.d11\n-------------------\n'
        text += ''.join(f'{p.year:04}{p.month:02} {v:.17g}\n' for p, v in series.items())
        path.write_text(text, encoding='ascii')

    def recalculate(self):
        self.data = build.clean(analysis.assemble(self.levels, self.sa, self.inp['weights'],
                                                 self.inp['metadata'], self.diag, self.endpoints))
        self.data.update(schema='category-momentum-r35/v1', mode='current_analysis',
                         as_of=self.start, completed_at=datetime.now(timezone.utc).isoformat(),
                         prepared=self.source.output.relative_to(build.ROOT).as_posix(),
                         provenance=copy.deepcopy(self.inp['provenance']), diagnostics=self.diag)

    def seal(self):
        self.levels.to_csv(self.out/'observed_levels.csv', index_label='month')
        self.sa.to_csv(self.out/'adjusted_levels.csv', index_label='month')
        self.seal_json()

    def seal_json(self):
        build.dump(self.out/'momentum.json', self.data)
        build.dump(self.out/'manifest.json', dict(schema='category-momentum-r35/manifest-v1',
            inputs={p.relative_to(build.ROOT).as_posix(): build.sha(p)
                    for p in self.source.output.iterdir() if p.is_file()},
            code={p.relative_to(build.ROOT).as_posix(): build.sha(p)
                  for p in build.HERE.iterdir() if p.is_file()},
            outputs={p.relative_to(self.out).as_posix(): build.sha(p)
                     for p in self.out.rglob('*') if p.is_file() and p != self.out/'manifest.json'}))

    def rejects(self, pattern):
        self.seal()
        with self.assertRaisesRegex(ValueError, pattern):
            build.load(self.out)

    def test_valid_complete_archive_loads(self):
        result = build.load(self.out)
        self.assertEqual(result['month'], '2026-08')
        self.assertEqual(len(result['rows']), 9)
        self.assertEqual(len(result['groups']), 37)

    def test_valid_partial_archive_with_unavailable_adjustment_loads(self):
        g = 'actual_rent'
        self.sa[g] = np.nan
        self.endpoints.pop(g)
        self.diag[g] = self.adjustment(g, 'full', self.levels[g], None, status='unavailable')
        self.recalculate(); self.seal()
        result = build.load(self.out)
        row = next(r for r in result['rows'] if r['id'] == g)
        self.assertIsNone(row['m3'])

    def test_future_or_noncanonical_month_rejects(self):
        for month in ('2099-08', '2026-08-01', '2026-07'):
            with self.subTest(month=month):
                self.data['month'] = month
                self.rejects('month')

    def test_missing_or_duplicate_category_rejects(self):
        rows = copy.deepcopy(self.data['rows'])
        for changed in ([], rows[:-1], rows[:-1]+[rows[0]]):
            with self.subTest(count=len(changed)):
                self.data['rows'] = changed
                self.rejects('rows|roster|categor')

    def test_missing_group_rejects(self):
        self.data['groups'].pop('actual_rent')
        self.rejects('groups|roster')

    def test_missing_diagnostic_rejects(self):
        self.diag.pop('actual_rent')
        self.rejects('diagnostic|roster')

    def test_wrong_provenance_rejects(self):
        self.data['provenance']['through'] = '2099-08'
        self.rejects('provenance')

    def test_wrong_mode_rejects(self):
        self.data['mode'] = 'forecast'
        self.rejects('mode')

    def test_wrong_observed_values_rejects_even_with_matching_summary(self):
        self.levels.iloc[-1, 0] += 2
        self.recalculate()
        self.rejects('observed|prepared')

    def test_missing_adjusted_month_rejects(self):
        self.sa = self.sa.drop(self.sa.index[-10])
        self.rejects('calendar|month|alignment')

    def test_duplicate_adjusted_month_rejects(self):
        self.sa.index = pd.PeriodIndex(list(self.sa.index[:-1])+[self.sa.index[-2]], freq='M')
        self.rejects('calendar|month|alignment')

    def test_day_labels_cannot_be_silently_coerced_to_months(self):
        self.sa.index = [str(p)+'-01' for p in self.sa.index]
        self.rejects('calendar|month')

    def test_adjusted_column_roster_rejects(self):
        self.sa = self.sa.drop(columns='actual_rent')
        self.rejects('column|roster|alignment')

    def test_partial_nan_adjustment_rejects(self):
        self.sa.iloc[-1, 0] = np.nan
        self.rejects('adjust|status|positive|finite')

    def test_unavailable_status_with_usable_values_rejects(self):
        self.diag['actual_rent']['status'] = 'unavailable'
        self.rejects('status|diagnostic|unavailable')

    def test_ok_status_with_absent_values_rejects(self):
        self.sa['actual_rent'] = np.nan
        self.rejects('status|adjust|finite')

    def test_unknown_status_rejects(self):
        self.diag['actual_rent']['status'] = 'maybe'
        self.rejects('status|diagnostic')

    def test_no_usable_categories_rejects(self):
        for g in self.sa:
            self.sa[g] = np.nan
            self.diag[g] = self.adjustment(g, 'full', self.levels[g], None, status='unavailable')
        self.endpoints = {}
        self.recalculate()
        self.rejects('usable')

    def test_changed_latest_result_rejects(self):
        self.data['rows'][0]['m3'] += 1
        self.rejects('rows|result|momentum')

    def test_changed_history_calendar_rejects(self):
        self.data['histories']['food'][-1]['month'] = '2099-08'
        self.rejects('histor|month')

    def test_changed_adjusted_panel_rejects_even_with_matching_summary(self):
        self.sa.iloc[-1, 0] *= 1.1
        self.recalculate()
        self.rejects('D11|adjust')

    def test_endpoint_wrong_calendar_rejects(self):
        path = self.out/'x13/previous_endpoint/actual_rent/series.d11'
        self.write_d11(path, self.endpoints['actual_rent'].iloc[:-1])
        self.rejects('D11|calendar|endpoint')

    def test_wrong_adjustment_input_rejects(self):
        s = self.levels.actual_rent.copy(); s.iloc[-1] += 3
        s.to_csv(self.out/'x13/full/actual_rent/input.csv', index_label='month')
        self.rejects('input|observed')

    def test_unpinned_adjusted_evidence_rejects(self):
        p = self.out/'manifest.json'
        m = json.loads(p.read_bytes()); m['outputs'].pop('adjusted_levels.csv')
        build.dump(p, m)
        with self.assertRaisesRegex(ValueError, 'adjusted_levels|required'):
            build.load(self.out)


if __name__ == '__main__':
    unittest.main()
