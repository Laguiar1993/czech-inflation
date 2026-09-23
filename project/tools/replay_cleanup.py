"""Replay a given code tree offline. No live loaders, refresh or original output writes.

python replay_cleanup.py TREE INPUTS OUTPUT [--tests]
All model fitting, X13, warm/cold forests, horizons and bands remain production code.
This is a refactor equivalence experiment on frozen inputs, not vintage certification.
"""
from pathlib import Path
import sys, os, json, hashlib, platform, importlib.metadata
import numpy as np
import pandas as pd

tree, inputs, out = map(lambda p:Path(p).resolve(), sys.argv[1:4])
out.mkdir(parents=True, exist_ok=True)
for name, expected in json.loads((inputs/'MANIFEST.json').read_text()).items():
    assert hashlib.sha256((inputs/name).read_bytes()).hexdigest()==expected, name
sys.path.insert(0, str(tree))
import requests
def offline(*args, **kwargs):
    raise AssertionError('Live network is forbidden in the frozen cleanup replay')
requests.sessions.Session.request = offline
import cz_struct as S

def read(name):
    a = pd.read_csv(inputs/name, index_col=0)
    a.index = pd.PeriodIndex(a.index, freq='M')
    return a
y = read('target_headline_cpi_mm.csv').iloc[:,0]
comp = read('component_food_fuel_mm.csv')
core = read('cnb_core_mm.csv').iloc[:,0].rename('core')
reg = read('cnb_regulated_mm.csv').iloc[:,0].rename('reg')
f = read('core_features.csv'); st = read('smooth_features.csv')
ff = read('food_block_features.csv')
ext = read('headline_extended_and_states.csv').headline_mm_extended
slow = read('slow_block_features_h6h12.csv')
alc = read('alcohol_tobacco.csv').iloc[:,0]
weekly = pd.read_csv(inputs/'fuel_weekly.csv', index_col=0)
weekly.index = pd.to_datetime(weekly.index)
# Preserve the pre-existing wedge's availability index exactly.
w = S.W
wedge = (y-w['food']*comp.food-w['fuel']*comp.fuel-w['core']*core-w['administered']*reg).rename('wedge')
S.load_all = lambda:(y.copy(), comp.copy(), core.copy(), reg.copy(), f.copy(), st.copy(), ff.copy(), wedge.copy())
S.load_alc_tobacco_mm = lambda:alc.copy()
S.la.load_headline_cpi_mm = lambda:y.copy()
S.la.load_component_targets = lambda:comp.copy()
S.la.fetch_cnb_core_inflation_mm_live = lambda:core.copy()
S.la.fetch_cnb_regulated_prices_mm_live = lambda:reg.copy()
S.la.load_headline_cpi_mm_extended = lambda:ext.copy()
S.la.fetch_weekly_fuels_live = lambda:weekly.copy()
# The baseline imports these from the research driver; candidate re-exports them.
import backtest_h0_enriched as enriched
enriched.load_m3_yoy = lambda:slow.m3_yoy.copy()
enriched.load_housing_channel = lambda:slow[['hpi_yoy','constr_ppi_yoy']].copy()
try:
    import data.struct_inputs as loaders
    loaders.load_m3_yoy = enriched.load_m3_yoy
    loaders.load_housing_channel = enriched.load_housing_channel
except ModuleNotFoundError:
    pass
if '--tests' in sys.argv:
    import pytest
    raise SystemExit(pytest.main([str(tree/'test_live_parity.py'), str(tree/'test_p0_regressions.py'), str(tree/'test_struct_acceptance.py'), '-q', '-p', 'no:cacheprovider']))
S.OUT = str(out)
S._X13_CACHE.clear()
bt = S.main()
versions = {p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','statsmodels','scikit-learn','quantile-forest','duckdb']}
(out/'runtime.json').write_text(json.dumps({'python':platform.python_version(), 'libraries':versions}, indent=2))
assert len(bt)==90, bt.shape
print('Completed 90 origins,',len(bt.columns),'columns')
expected = inputs/'expected_backtest.csv'
if expected.exists():
    actual = out/'cz_struct_backtest.csv'
    if actual.read_bytes() == expected.read_bytes():
        print('Frozen reference: byte-identical')
    else:
        # v2.5: a later spec may ADD columns (release-eve checkpoint). The
        # reference's own columns must still reproduce exactly; new columns
        # are reported, never silently accepted as identity.
        e = pd.read_csv(expected, index_col=0); a = pd.read_csv(actual, index_col=0)
        shared = [c for c in e.columns if c in a.columns]
        missing = [c for c in e.columns if c not in a.columns]
        if missing or not e.index.equals(a.index):
            raise AssertionError(f'Replay lost reference columns/rows: {missing}')
        bad = []
        for c in shared:
            ea, aa = e[c], a[c]
            if pd.api.types.is_numeric_dtype(ea) and pd.api.types.is_numeric_dtype(aa):
                if not np.allclose(ea.fillna(-9e9), aa.fillna(-9e9), rtol=0, atol=1e-12):
                    bad.append(c)
            elif not ea.astype(str).equals(aa.astype(str)):
                bad.append(c)
        if bad:
            raise AssertionError(f'Replay differs from the frozen reference in {bad}. '
                                 'Inspect matrices, runtime and per-column differences before adopting it.')
        new = [c for c in a.columns if c not in e.columns]
        print(f'Frozen reference: identical on all {len(shared)} reference columns; '
              f'{len(new)} new column(s) not covered by the reference: {new}')
