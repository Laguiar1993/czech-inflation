"""Claude review of R23, probe 1: what the five R23 features actually measure.

Read-only. Writes nothing. Uses the R23 loaders, publication masks and origin clocks.
Part A is a measurement audit. Part B is EXPLORATORY in-sample description (about 60
overlapping quarterly rows, one inflation cycle): it motivates hypotheses, it is not evidence
of forecast skill and must not be used to select a model.

Run from the repository root:
    python work/research_r23_claude_review/feature_checks.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data.cost_gaps_r23 import load_inputs, visible, chain, relative_gap, local  # noqa: E402
from tools.research_r23.run import targets  # noqa: E402

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 300)
core, core_dates, raw, fx, _ = load_inputs()
states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
native = pd.read_csv(ROOT / 'output/research_r21/path_anchor/native_forecasts.csv')
outer = native[native.model.eq('STATE_FAST_R15') & native.h.eq(0)].set_index('origin').as_of_utc.to_dict()


def measures(origin, asof, seasonal):
    t = pd.Period(origin, 'M'); edge = t - 1; clock = local(asof)
    obs = visible(core, core_dates, edge, clock)
    logs = 100 * np.log1p(obs.where(obs > -100) / 100)
    logs -= np.array([seasonal.get(p.month, seasonal.get(str(p.month), np.nan)) for p in logs.index])
    level = chain(logs); out = {}
    q = raw[17]
    qv = visible(q.values, q.available, edge.asfreq('Q'), clock).where(lambda x: x > 0)
    cq = level.groupby(level.index.asfreq('Q')).agg(['mean', 'count']); cq = cq['mean'].where(cq['count'].eq(3))
    done = pd.PeriodIndex([p for p in qv.dropna().index if p.asfreq('M', 'end') <= edge], freq='Q')
    ref = done.max() if len(done) else None
    rel = 100 * np.log(qv) - cq.reindex(qv.index)
    out['ulc_gap_r23'] = relative_gap(rel, ref, 12)                      # exactly the R23 definition
    if ref is not None:
        same = rel.reindex([ref - 12, ref - 8, ref - 4, ref])             # same quarter of the three previous years
        out['ulc_gap_sameq'] = float(same.iloc[-1] - same.iloc[:-1].median()) if same.notna().all() else np.nan
        out['ulc_gap_ma4'] = relative_gap(rel.rolling(4).mean(), ref, 12)   # four-quarter average of the real-cost ratio
        out['ulc_real_yoy'] = float(rel.get(ref, np.nan) - rel.get(ref - 4, np.nan))
        out['ulc_refq'] = ref.quarter
    for name, n in [('imp', 26), ('ppi', 47)]:
        r = raw[n]; v = visible(r.values, r.available, edge, clock); rf = v.last_valid_index()
        up = chain(100 * np.log1p(v.where(v > -100) / 100)) if n == 26 else 100 * np.log(v.where(v > 0))
        relm = up - level.reindex(up.index)
        out[name + '_gap_r23'] = relative_gap(relm, rf, 36)               # exactly the R23 definition
        if rf is not None:
            g = lambda s, k: float(s.get(rf, np.nan) - s.get(rf - k, np.nan))
            out[name + '_rel_mom6'] = g(relm, 6)                          # upstream minus core, six-month momentum
            out[name + '_mom12'] = g(up, 12)
            out[name + '_accel6'] = g(up, 6) - float(up.get(rf - 6, np.nan) - up.get(rf - 12, np.nan))
    e = level.last_valid_index()
    if e is not None:
        out['core_mom12'] = float(level.get(e, np.nan) - level.get(e - 12, np.nan))
    return out


X = pd.DataFrame.from_dict({pd.Period(o, 'M'): measures(o, outer.get(o, s['as_of']), s['seasonal']) for o, s in states.items()},
                           orient='index').sort_index()
saved = pd.read_csv(ROOT / 'output/research_r23/final/features.csv', index_col=0)
saved.index = pd.PeriodIndex(saved.index, freq='M')
for mine, theirs in [('ulc_gap_r23', 'ulc_gap'), ('imp_gap_r23', 'import_gap'), ('ppi_gap_r23', 'ppi_gap')]:
    np.testing.assert_allclose(X[mine].to_numpy(float), saved[theirs].reindex(X.index).to_numpy(float), atol=1e-9, equal_nan=True)
print('A0. This probe rebuilds the delivered ulc_gap, import_gap and ppi_gap exactly (199 origins).')

print('\nA1. ULC source: Bloomberg LCTQCZI, field seasonality_and_transformation =',
      pd.read_csv(ROOT / 'data/market_snapshots/20260911_bloomberg_full_refresh/raw/nominal_ulc_quarterly_bdp.csv').seasonality_and_transformation.iloc[0])
ulc = ['ulc_gap_r23', 'ulc_gap_sameq', 'ulc_gap_ma4', 'ulc_real_yoy']
print('\nA2. Mean of each ULC measure by the reference quarter-of-year it is read from (199 origins):')
print(X.groupby('ulc_refq')[ulc].mean().round(2).to_string())
print('\nA3. Share of variance explained by quarter-of-year alone (0 = no seasonal contamination):')
for c_ in ulc:
    z = X[[c_, 'ulc_refq']].dropna(); m = z.groupby('ulc_refq')[c_].transform('mean')
    print(f'    {c_:14s} {1 - ((z[c_] - m) ** 2).sum() / ((z[c_] - z[c_].mean()) ** 2).sum():.3f}')

Y, _, _ = targets(core, core_dates, states)
Y.columns = ['h1_3', 'h4_6', 'h7_9', 'h10_12']; Y['cum12'] = 3 * Y.sum(axis=1)
Q = X[X.index.month % 3 == 0].join(Y, how='inner').dropna(subset=['cum12'])
print(f'\nB. EXPLORATORY, in-sample: correlation with the R23 targets (realised minus FAST, log core) on {len(Q)} quarter-end origins.')
print('   A positive number means: when the measure is high, FAST subsequently under-predicts core.')
rows = []
for f in [c_ for c_ in X.columns if c_ != 'ulc_refq']:
    for samp, z in [('all', Q), ('origins<=2019', Q[Q.index <= '2019-12']), ('origins>=2020', Q[Q.index >= '2020-01'])]:
        z = z[[f, *Y.columns]].dropna()
        if len(z) >= 10:
            rows.append(dict(measure=f, sample=samp, n=len(z), **{k: z[f].corr(z[k]) for k in Y.columns}))
print(pd.DataFrame(rows).set_index(['measure', 'sample']).round(2).to_string())
