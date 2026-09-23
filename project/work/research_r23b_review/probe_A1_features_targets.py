"""Probe A1: features and targets rebuilt with independent code and compared with the delivered files.

Nothing from data.cost_pressure_r23b / data.cost_gaps_r23 is used for the *computation*; only
`load_inputs` is used to obtain the frozen source series. Writes nothing outside this folder.
"""
import json
import numpy as np
import pandas as pd

from _common import ROOT, FINAL, Report

from data.cost_pressure_r23b import load_inputs

R = Report('A1 features and targets (independent rebuild)')
core, core_dates, raw, fx, _ = load_inputs()
states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
saved = pd.read_csv(FINAL / 'features.csv', index_col=0, float_precision='round_trip')
clocks = pd.read_csv(FINAL / 'feature_clocks.csv', index_col=0).iloc[:, 0].map(pd.Timestamp)
prov = pd.read_csv(FINAL / 'feature_provenance.csv')
R.check('199 feature rows, 7 columns in the declared order', saved.shape == (199, 7) and list(saved.columns) == ['ulc_sameq', 'tightening', 'import_mom', 'ppi_mom', 'fx_news', 'import_gap', 'ppi_gap'])
R.check('feature origins equal the 199 saved states, in chronological order', list(saved.index) == list(states) and list(saved.index) == sorted(saved.index))


def prague(value):
    t = pd.Timestamp(value)
    return t.tz_convert('Europe/Prague').tz_localize(None) if t.tzinfo else t


# ---- clocks: evaluated origins use the native decision clock, earlier ones the saved state clock
native = pd.read_csv(ROOT / 'output/research_r21/path_anchor/native_forecasts.csv', low_memory=False)
fastn = native[native.model.eq('STATE_FAST_R15')]
outer = fastn[fastn.h.eq(0)].set_index('origin').as_of_utc
R.check('90 evaluated origins 2019-02..2026-07', len(outer) == 90 and outer.index.min() == '2019-02' and outer.index.max() == '2026-07')
bad = []
for o, st in states.items():
    expect = prague(outer[o]) if o in outer.index else prague(st['as_of'])
    if expect != clocks[o]:
        bad.append(o)
R.check('feature clock = native as_of_utc (Prague) for evaluated origins, state as_of otherwise', not bad, str(bad[:5]))
gap = pd.Series({o: (prague(outer[o]) - prague(states[o]['as_of'])).total_seconds() for o in outer.index})
R.check('evaluated-origin decision clock identical to the saved FAST state clock', (gap == 0).all(), f'max abs difference seconds={gap.abs().max()}')
# clock is strictly before the release of month t and after the release of t-1
rel_t = core_dates.reindex(pd.PeriodIndex(saved.index, freq='M')); rel_p = core_dates.reindex(pd.PeriodIndex(saved.index, freq='M') - 1)
R.check('every clock is before the release of core month t', (clocks.to_numpy() < rel_t.to_numpy()).all())
after = clocks.to_numpy() >= rel_p.to_numpy()
R.check('every clock is at or after the release of core month t-1', after.all(), f'violations={[saved.index[i] for i in np.where(~after)[0]][:8]}')


def own_features(origin, clock, seasonal):
    t = pd.Period(origin, 'M'); edge = t - 1; out = {}; refs = {}
    # seasonally adjusted monthly log core and its strict chain
    sa = {}
    for m, v in core.items():
        if m <= edge and pd.notna(core_dates.get(m)) and core_dates[m] <= clock and np.isfinite(v) and v > -100:
            sa[m] = 100 * np.log1p(v / 100) - seasonal[str(m.month)]
    level = {}; total = 0.
    for m in pd.period_range(core.index.min(), edge, freq='M'):
        if m not in sa:
            break
        total += sa[m]; level[m] = total
    # --- ULC same quarter
    u = raw[17]
    pubq = [q for q in u.values.index if pd.notna(u.available.get(q)) and u.available[q] <= clock and np.isfinite(u.values[q]) and u.values[q] > 0]
    done = [q for q in pubq if q.asfreq('M', 'end') <= edge]
    out['ulc_sameq'] = np.nan; refs['ulc_sameq'] = None
    if done:
        ref = max(done); refs['ulc_sameq'] = str(ref)
        def rel(q):
            months = pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M')
            if q not in pubq or any(m not in level for m in months):
                return np.nan
            return 100 * np.log(u.values[q]) - np.mean([level[m] for m in months])
        four = [rel(ref - 12), rel(ref - 8), rel(ref - 4), rel(ref)]
        if np.isfinite(four).all():
            out['ulc_sameq'] = four[3] - float(np.median(four[:3]))
    # --- six-month momentum differentials
    for name, n in [('import_mom', 26), ('ppi_mom', 47)]:
        r = raw[n]; out[name] = np.nan; refs[name] = None
        seen = [m for m in r.values.index if m <= edge and pd.notna(r.available.get(m)) and r.available[m] <= clock and np.isfinite(r.values[m])]
        if not seen:
            continue
        ref = max(seen); refs[name] = str(ref); window = list(pd.period_range(ref - 5, ref, freq='M'))
        if any(m not in sa for m in window):
            continue
        core6 = sum(sa[m] for m in window)
        if n == 26:
            if any(m not in seen or not r.values[m] > -100 for m in window):
                continue
            up = sum(100 * np.log1p(r.values[m] / 100) for m in window)
        else:
            # strict reading of the text: all six monthly changes published => months ref-6..ref published and positive
            need = list(pd.period_range(ref - 6, ref, freq='M'))
            if any(m not in seen or not r.values[m] > 0 for m in need):
                continue
            up = sum(100 * np.log(r.values[b] / r.values[a]) for a, b in zip(need[:-1], need[1:]))
        out[name] = up - core6
    return out, refs


worst = {}; ref_bad = []
provenance = prov.set_index(['origin', 'feature']).reference
for o in saved.index:
    mine, refs = own_features(o, clocks[o], states[o]['seasonal'])
    for k, v in mine.items():
        s = saved.loc[o, k]
        if np.isnan(v) != np.isnan(s):
            worst[k] = np.inf; print('   missingness differs', o, k, v, s)
        elif np.isfinite(v):
            worst[k] = max(worst.get(k, 0.), abs(v - s))
        saved_ref = provenance.get((o, k))
        if (refs[k] or None) != (saved_ref if isinstance(saved_ref, str) else None):
            ref_bad.append((o, k, refs[k], saved_ref))
for k in ['ulc_sameq', 'import_mom', 'ppi_mom']:
    R.check(f'{k}: independent rebuild equals features.csv on all 199 origins', worst.get(k, 0.) < 1e-9, f'max abs diff={worst.get(k, 0.):.3e}; finite={int(saved[k].notna().sum())}')
R.check('reference quarter/month in feature_provenance.csv equals the independently chosen one', not ref_bad, str(ref_bad[:5]))

# ---- R23 features reused unchanged
r23 = pd.read_csv(ROOT / 'output/research_r23/final/features.csv', index_col=0, float_precision='round_trip')
for k in ['tightening', 'fx_news', 'import_gap', 'ppi_gap']:
    same = (saved[k].isna() == r23[k].isna()).all() and np.array_equal(saved[k].dropna().to_numpy(), r23[k].dropna().to_numpy())
    R.check(f'{k}: bit-identical to the sealed R23 final features', same)
r23clock = pd.read_csv(ROOT / 'output/research_r23/final/feature_clocks.csv', index_col=0).iloc[:, 0].map(pd.Timestamp)
R.check('R23B feature clocks identical to R23 clocks', r23clock.equals(clocks))

# ---- reference-quarter timing facts worth reporting
ulc_ref = prov[prov.feature.eq('ulc_sameq')].set_index('origin').reference
lagq = pd.Series({o: (pd.Period(o, 'M') - 1).asfreq('Q').ordinal - pd.Period(q, 'Q').ordinal for o, q in ulc_ref.dropna().items()})
print('   ULC reference-quarter lag behind the quarter of t-1 (quarters): ', lagq.value_counts().sort_index().to_dict())
imp_ref = prov[prov.feature.eq('import_mom')].set_index('origin').reference
lagm = pd.Series({o: (pd.Period(o, 'M') - pd.Period(m, 'M')).n for o, m in imp_ref.dropna().items()})
print('   import reference month lag behind origin t (months): ', lagm.value_counts().sort_index().to_dict())
ppi_ref = prov[prov.feature.eq('ppi_mom')].set_index('origin').reference
lagp = pd.Series({o: (pd.Period(o, 'M') - pd.Period(m, 'M')).n for o, m in ppi_ref.dropna().items()})
print('   PPI reference month lag behind origin t (months): ', lagp.value_counts().sort_index().to_dict())
R.check('import_mom and import_gap share one reference month (fx_news anchor unchanged)',
        (prov[prov.feature.eq('import_mom')].set_index('origin').reference.dropna() == prov[prov.feature.eq('import_gap')].set_index('origin').reference.reindex(imp_ref.dropna().index)).all())

# ---- targets and release maturity
y = pd.read_csv(FINAL / 'band_targets.csv', index_col=0, float_precision='round_trip'); y.columns = y.columns.astype(int)
a = pd.read_csv(FINAL / 'target_available.csv', index_col=0); a.columns = a.columns.astype(int)
worst_y = 0.; bad_a = []
for o, st in states.items():
    t = pd.Period(o, 'M')
    for b in (1, 2):
        through = pd.period_range(t + 1, t + 3 * b, freq='M'); months = through[-3:]
        vals = core.reindex(through); rel = core_dates.reindex(through)
        complete = vals.notna().all() and (vals > -100).all() and rel.notna().all()
        if complete:
            fast = np.array([st['forecasts_log']['fast'][str(h)] for h in range(3 * b - 2, 3 * b + 1)])
            mine = float(np.mean(100 * np.log1p(core.reindex(months).to_numpy() / 100) - fast))
            worst_y = max(worst_y, abs(mine - y.loc[o, b]))
            if pd.Timestamp(a.loc[o, b]) != rel.max():
                bad_a.append((o, b))
        elif not (np.isnan(y.loc[o, b]) and pd.isna(a.loc[o, b])):
            bad_a.append((o, b, 'should be missing'))
R.check('band targets: mean(realised log core - saved FAST log rate) over h1-3 and h4-6, all 199 origins', worst_y < 1e-12, f'max abs diff={worst_y:.3e}')
R.check('target_available = last release among h1..h3b (all releases needed), missing when incomplete', not bad_a, str(bad_a[:5]))
print('   finite labels: band1', int(y[1].notna().sum()), 'band2', int(y[2].notna().sum()), '; last finite band1', y[1].dropna().index.max(), 'band2', y[2].dropna().index.max())
R.done()
