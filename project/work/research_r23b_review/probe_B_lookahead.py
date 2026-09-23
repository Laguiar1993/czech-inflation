"""Probe B: look-ahead. Real origins, real inputs, 1e12 poison on everything not yet knowable.

B1  features_at on poisoned inputs must be bit-identical (all 199 origins; four named ones printed).
B2  training.csv / inner_validation.csv / fits.jsonl: every outer and inner label matured and released, per band.
B3  run_origin on labels and features poisoned beyond the outer clock reproduces fits.jsonl exactly;
    per-fold poison beyond each fold's own clock reproduces that fold's saved losses.
"""
import copy
import json
from types import SimpleNamespace
import numpy as np
import pandas as pd

from _common import ROOT, FINAL, Report

from data.cost_pressure_r23b import load_inputs, features_at, COLUMNS
from models.cost_pressure_r23b import run_origin, choose, FAMILIES, GRID

R = Report('B look-ahead')
core, core_dates, raw, fx, _ = load_inputs()
states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
clocks = pd.read_csv(FINAL / 'feature_clocks.csv', index_col=0).iloc[:, 0].map(pd.Timestamp)
saved = pd.read_csv(FINAL / 'features.csv', index_col=0, float_precision='round_trip')
POISON = 1e12
NAMED = ['2019-02', '2021-06', '2023-01', '2026-07']


def poisoned_inputs(origin, clock):
    t = pd.Period(origin, 'M'); edge = t - 1; counts = {}
    pc = core.copy(); late = core_dates.isna() | (core_dates > clock) | (pc.index > edge); pc[late.to_numpy()] = POISON; counts['core'] = int(late.sum())
    pf = fx.copy(); latef = pf.index > t; pf[latef] = POISON; counts['fx'] = int(latef.sum())
    praw = {}
    for n in (11, 17, 26, 47):
        r = raw[n]; v = r.values.copy().astype(float)
        end_month = v.index.asfreq('M', 'end') if v.index.freqstr.startswith('Q') else v.index
        late = (r.available.isna() | (r.available > clock)).to_numpy() | (end_month > edge)
        v[late] = POISON; counts[n] = int(late.sum())
        praw[n] = SimpleNamespace(values=v, available=r.available.copy(), kind=r.kind, source=r.source)
    return pc, praw, pf, counts


mismatch = []; saved_mismatch = []; contaminated_when_clock_moves = 0
for origin, state in states.items():
    clock = clocks[origin]
    clean, _ = features_at(core, core_dates, raw, fx, pd.Period(origin, 'M'), clock, state['seasonal'])
    pc, praw, pf, counts = poisoned_inputs(origin, clock)
    dirty, _ = features_at(pc, core_dates, praw, pf, pd.Period(origin, 'M'), clock, state['seasonal'])
    same = np.array_equal(clean.to_numpy(), dirty.to_numpy(), equal_nan=True)
    if not same:
        mismatch.append(origin)
    if not np.array_equal(clean.to_numpy(), saved.loc[origin, COLUMNS].to_numpy(float), equal_nan=True):
        saved_mismatch.append(origin)
    if origin in NAMED:
        print(f'   {origin} clock {clock}: poisoned cells {counts}; bit-identical={same}; features={np.round(clean.to_numpy(), 4).tolist()}')
    # the poison is live: the same poisoned inputs read 75 days later must contaminate something
    if origin <= '2026-04':
        later, _ = features_at(pc, core_dates, praw, pf, pd.Period(origin, 'M') + 3, clock + pd.Timedelta(days=92), state['seasonal'])
        contaminated_when_clock_moves += bool((later.abs() > 1e6).any() or later.isna().sum() > clean.isna().sum())
R.check('B1 features bit-identical under 1e12 poison of every unpublished/future source cell, all 199 origins', not mismatch, str(mismatch[:5]))
R.check('B1 features_at on the frozen inputs reproduces features.csv bit for bit, all 199 origins', not saved_mismatch, str(saved_mismatch[:5]))
R.check('B1 poison is live: moving origin and clock three months forward over the same poisoned inputs contaminates the features',
        contaminated_when_clock_moves >= 190, f'{contaminated_when_clock_moves} of {sum(o <= "2026-04" for o in states)} origins')

# ---------------- B2: saved audit files
cd = core_dates.copy()
tr = pd.read_csv(FINAL / 'training.csv'); iv = pd.read_csv(FINAL / 'inner_validation.csv')
tr['p_s'] = pd.PeriodIndex(tr.training_origin, freq='M'); tr['p_o'] = pd.PeriodIndex(tr.origin, freq='M'); tr['p_lt'] = pd.PeriodIndex(tr.last_target, freq='M')
ok_target = np.array([l == s + 3 * b for l, s, b in zip(tr['p_lt'], tr['p_s'], tr['band'])])
R.check('B2 training.csv: last_target = training origin + 3*band', ok_target.all())
R.check('B2 training.csv: last target month <= origin-1 for every outer row (band-specific maturity)', np.array([l <= o - 1 for l, o in zip(tr['p_lt'], tr['p_o'])]).all())
R.check('B2 training.csv: label release <= decision clock for every outer row', (pd.to_datetime(tr.target_available) <= pd.to_datetime(tr.as_of)).all())
R.check('B2 training.csv: recorded release equals the calendar release of the last target month', (pd.to_datetime(tr.target_available).to_numpy() == cd.reindex(pd.PeriodIndex(tr['p_lt'])).to_numpy()).all())
R.check('B2 training.csv: as_of equals the origin clock in feature_clocks.csv', (pd.to_datetime(tr.as_of).to_numpy() == clocks.reindex(tr.origin).to_numpy()).all())
R.check('B2 training.csv: only quarter-end training origins, 24..40 rows per origin-band, no duplicates',
        tr['p_s'].dt.month.isin([3, 6, 9, 12]).all() and tr.groupby(['origin', 'band']).size().between(24, 40).all() and not tr.duplicated(['origin', 'band', 'training_origin']).any())
slack = pd.Series([(o - 1 - l).n for l, o in zip(tr['p_lt'], tr['p_o'])]); newest = tr.assign(slack=slack).groupby(['origin', 'band']).slack.min()
print('   months between the newest outer label\'s last target and t-1, by band:', {int(b): g.value_counts().sort_index().to_dict() for b, g in newest.groupby(level='band')})
# does the release criterion ever bind beyond the month criterion?
print('   smallest gap (days) between decision clock and newest used label release:', (pd.to_datetime(tr.as_of) - pd.to_datetime(tr.target_available)).min())

iv['v'] = pd.PeriodIndex(iv.validation_origin, freq='M'); iv['o'] = pd.PeriodIndex(iv.origin, freq='M')
iv['ltt'] = pd.PeriodIndex(iv.last_training_target, freq='M'); iv['lto'] = pd.PeriodIndex(iv.last_training_origin, freq='M'); iv['vt'] = pd.PeriodIndex(iv.validation_target, freq='M')
outer_sets = {k: set(g.training_origin) for k, g in tr.groupby(['origin', 'band'])}
R.check('B2 inner_validation.csv: every validation origin is one of that origin-band\'s outer training rows',
        all(v in outer_sets[(o, b)] for o, b, v in zip(iv.origin, iv.band, iv.validation_origin)))
R.check('B2 inner: validation label matured at the OUTER clock (target month <= t-1 and released)',
        np.array([vt <= o - 1 for vt, o in zip(iv.vt, iv.o)]).all() and (pd.to_datetime(iv.validation_available).to_numpy() <= clocks.reindex(iv.origin).to_numpy()).all())
R.check('B2 inner: last inner training target = last inner origin + 3*band and <= validation origin - 1',
        np.array([ltt == lto + 3 * b and ltt <= v - 1 for ltt, lto, b, v in zip(iv.ltt, iv.lto, iv.band, iv.v)]).all())
R.check('B2 inner: newest inner label release <= the validation origin\'s own clock', (pd.to_datetime(iv.max_training_release) <= pd.to_datetime(iv.validation_clock)).all())
R.check('B2 inner: validation clock equals that origin\'s clock in feature_clocks.csv', (pd.to_datetime(iv.validation_clock).to_numpy() == clocks.reindex(iv.validation_origin).to_numpy()).all())
R.check('B2 inner: 16..40 inner rows, exactly 8 folds x 5 penalties per origin-model-band', iv.n_train.between(16, 40).all() and iv.groupby(['origin', 'model', 'band']).size().eq(40).all())
R.check('B2 inner: validation label release strictly after the validation origin\'s own clock (genuinely out of sample)', (pd.to_datetime(iv.validation_available) > pd.to_datetime(iv.validation_clock)).all())

# ---------------- B3: poison the labels and features the model must not see, then re-run the real code
X = saved.copy(); X.index = pd.PeriodIndex(X.index, freq='M')
Y = pd.read_csv(FINAL / 'band_targets.csv', index_col=0, float_precision='round_trip'); Y.index = pd.PeriodIndex(Y.index, freq='M'); Y.columns = Y.columns.astype(int)
A = pd.read_csv(FINAL / 'target_available.csv', index_col=0); A.index = pd.PeriodIndex(A.index, freq='M'); A.columns = A.columns.astype(int); A = A.apply(pd.to_datetime)
C = clocks.copy(); C.index = pd.PeriodIndex(C.index, freq='M')
fits = {json.loads(l)['origin']: json.loads(l) for l in (FINAL / 'fits.jsonl').open()}
as_of = {o: f['as_of'] for o, f in fits.items()}
for origin in NAMED + ['2020-03', '2024-12']:
    t = pd.Period(origin, 'M'); clock = C[t]
    yp = Y.copy(); n_poison = 0
    for b in (1, 2):
        hidden = ((A[b].isna()) | (A[b] > clock) | (np.array([s + 3 * b > t - 1 for s in Y.index]))) & Y[b].notna()
        yp.loc[hidden, b] = 1e8; n_poison += int(hidden.sum())
    xp = X.copy(); xp.loc[xp.index > t] = xp.loc[xp.index > t].where(xp.loc[xp.index > t].isna(), POISON)
    again = json.loads(json.dumps(run_origin(xp, yp, A, C, t, as_of[origin])))
    ref = {k: fits[origin][k] for k in again}
    R.check(f'B3 {origin}: run_origin with {n_poison} unmatured labels and all later feature rows poisoned equals fits.jsonl exactly', again == ref)

checked = 0; worst = 0.
for origin in NAMED:
    t = pd.Period(origin, 'M'); clock = C[t]
    for model in ['PRESS_JOINT_R23B', 'PRESS_SIGNED_R23B', 'PRESS_LEVELS_R23B']:
        columns, kind = FAMILIES[model]
        for b in (1, 2):
            savedv = fits[origin]['selection'][model][str(b)]['validation']
            for v in sorted({r['validation_origin'] for r in savedv}):
                pv = pd.Period(v, 'M'); yp = Y.copy()
                hidden = ((A[b].isna()) | (A[b] > C[pv]) | (np.array([s + 3 * b > pv - 1 for s in Y.index]))) & Y[b].notna()
                hidden[pv] = False                                   # the fold's own label is the score target
                yp.loc[hidden, b] = 1e8
                res = choose(X, yp, A, C, t, clock, b, columns, kind)
                for r in res['validation']:
                    if r['validation_origin'] == v:
                        want = next(z for z in savedv if z['validation_origin'] == v and z['alpha'] == r['alpha'])
                        worst = max(worst, abs(want['loss'] - r['loss'])); checked += 1
R.check('B3 per-fold: poisoning every label not matured at the fold\'s own clock leaves that fold\'s saved losses unchanged', worst == 0., f'{checked} fold-penalty losses, max abs diff={worst:.3e}')
R.done()
