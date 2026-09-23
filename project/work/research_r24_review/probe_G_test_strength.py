"""G. How much would tests/test_food_drift_r24.py (and the run's own assertion) catch?

In-memory mutants of models/food_drift_r24.py are built from its source text (no file is edited). Each mutant
is pushed into the test module's namespace and every test function is called directly. The run's assertion
(baseline_path vs value_food of STATE_FAST_R15) is replayed for the mutant at three origins as well.

A mutant that SURVIVES marks behaviour the suite does not pin down. The frozen outputs themselves were checked
against these behaviours independently in probes AC, B1 and B2, so survival is a test-gap finding, not a bug.
"""
import importlib
import inspect
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import probe_common as pc
import models.food_drift_r24 as real
tests = importlib.import_module('tests.test_food_drift_r24')
from models.food_path_r14 import load_inputs

SOURCE = (ROOT / 'models/food_drift_r24.py').read_text(encoding='utf-8')
MUTANTS = {
    'M0 unchanged (control)': [],
    'M1 horizon off-by-one: baseline rates [0:12] and refit [0:12] instead of [1:13]': [("[BASELINE_MODELS[0]])[1:13]", "[BASELINE_MODELS[0]])[0:12]"), ("np.asarray(refit['log_rates'])[1:13]", "np.asarray(refit['log_rates'])[0:12]")],
    'M2 mu_robust ignores the training window (allowed dropped)': [("median_annual_drift(long_rates, long_published, as_of, allowed=fit['training_dates'])", "median_annual_drift(long_rates, long_published, as_of)")],
    'M3 refit moves the food centre the wrong way': [("centre[:, food] += shift", "centre[:, food] -= shift")],
    'M4 publication stamps ignored in the drift': [("usable = rates.notna() & stamp.notna() & (stamp <= clock) & (rates.index >= start)", "usable = rates.notna() & stamp.notna() & (rates.index >= start)")],
    'M5 long history starts 2005 instead of 1996': [("LONG_START = pd.Period('1996-01', 'M')", "LONG_START = pd.Period('2005-01', 'M')")],
    'M6 mu_window taken as the plain window mean of calendar means of ALL THREE series': [("mu_window, _ = decompose(np.asarray(fit['seasonal_means'])[:, food])", "mu_window = float(np.asarray(fit['seasonal_means']).mean())")],
    'M7 simple rate conversion dropped (log rate written as the simple rate)': [("float(100 * np.expm1(values[h - 1] / 100))", "float(values[h - 1])")],
    'M8 median replaced by the mean of twelve-month changes': [("float(annual.median() / 12)", "float(annual.mean() / 12)")],
}
NAMES = ['MODELS', 'median_annual_drift', 'decompose', 'long_food_rates', 'refit_forecast', 'candidates_at', 'LONG_HISTORY']
levels, available, _ = load_inputs()
native = pd.read_csv(pc.NATIVE_R21, float_precision='round_trip'); native = native[native.model.eq(pc.FAST)]
clk = pc.clocks()


def build(replacements):
    text = SOURCE
    for a, b in replacements:
        assert text.count(a) == 1, ('mutation anchor not unique', a)
        text = text.replace(a, b)
    module = types.ModuleType('mutant'); module.__dict__['__name__'] = 'mutant'
    exec(compile(text, 'mutant_food_drift_r24', 'exec'), module.__dict__)
    return module


def run_tests(module):
    saved = {n: getattr(tests, n) for n in NAMES}
    for n in NAMES:
        setattr(tests, n, getattr(module, n))
    failures = []
    try:
        rates, published = module.long_food_rates(levels, available, ROOT / module.LONG_HISTORY)
        fixture = (levels, available, rates, published)
        for name, fn in inspect.getmembers(tests, inspect.isfunction):
            if not name.startswith('test_'):
                continue
            params = list(inspect.signature(fn).parameters)
            cases = [('2019-02', '2019-03-10T23:59:00+01:00'), ('2024-06', '2024-07-09T23:59:00+02:00')] if 'origin' in params else [None]
            for case in cases:
                kwargs = {}
                if 'real' in params:
                    kwargs['real'] = fixture
                if case:
                    kwargs.update(origin=case[0], clock=case[1])
                try:
                    fn(**kwargs)
                except Exception as error:      # noqa: BLE001 - any failure counts as the mutant being caught
                    failures.append(f'{name}{"" if not case else "[" + case[0] + "]"}: {type(error).__name__}')
    finally:
        for n, v in saved.items():
            setattr(tests, n, v)
    return failures


def run_assertion(module):
    """The check in tools/research_r24/run.py line 47, replayed for a mutant."""
    rates, published = module.long_food_rates(levels, available, ROOT / module.LONG_HISTORY)
    for origin in ['2019-02', '2022-06', '2024-06']:
        result = module.candidates_at(levels, available, rates, published, origin, clk[origin])
        base = native[native.origin.eq(origin) & native.h.gt(0)].sort_values('h').value_food.to_numpy()
        try:
            np.testing.assert_allclose([result['baseline_path'][h] for h in range(1, 13)], base, atol=1e-9, rtol=0)
        except AssertionError:
            return 'fails'
    return 'passes'


rows = []
for label, replacements in MUTANTS.items():
    module = build(replacements); failures = run_tests(module)
    rows.append(dict(mutant=label, tests_failed=len(failures), caught_by_tests=bool(failures), run_assertion=run_assertion(module), which='; '.join(failures)))
out = pd.DataFrame(rows); out.to_csv(HERE / 'out_G_test_strength.csv', index=False)
pd.set_option('display.width', 300); pd.set_option('display.max_colwidth', 120)
for r in out.itertuples():
    print(f'{r.mutant}\n    caught by tests: {r.caught_by_tests} ({r.tests_failed} failing)   run.py baseline assertion: {r.run_assertion}\n    {r.which}')
