"""Probe C: reconstruction from the saved outputs only, all 90 origins and all six candidates."""
import json
import numpy as np
import pandas as pd

from _common import ROOT, FINAL, EVAL, Report

R = Report('C reconstruction from saved outputs')
MODELS = ['PRESS_ULC_R23B', 'PRESS_DOMESTIC_R23B', 'PRESS_MOMENTUM_R23B', 'PRESS_JOINT_R23B', 'PRESS_SIGNED_R23B', 'PRESS_LEVELS_R23B']
CONTROLS = ['STATE_FAST_R15', 'STABLE_LOCAL_CORE_R14B', 'DAMPED_P95_Q001_R16', 'CORE_FEEDBACK_R21']
GRID = [0.3, 1.0, 3.0, 10.0, 30.0]
rd = dict(float_precision='round_trip', low_memory=False)
fits = {json.loads(l)['origin']: json.loads(l) for l in (FINAL / 'fits.jsonl').open()}
X = pd.read_csv(FINAL / 'features.csv', index_col=0, **rd)
Y = pd.read_csv(FINAL / 'band_targets.csv', index_col=0, **rd); Y.columns = Y.columns.astype(int)
K = pd.read_csv(FINAL / 'coefficient_contributions.csv', **rd)
IV = pd.read_csv(FINAL / 'inner_validation.csv', **rd)
ST = pd.read_csv(FINAL / 'status.csv', **rd)
native = pd.read_csv(FINAL / 'native_forecasts.csv', **rd)
forecasts = pd.read_csv(FINAL / 'forecasts.csv', **rd)
states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
manifest = json.loads((FINAL / 'manifest.json').read_text())
R.check('manifest roster = 4 controls + 6 declared candidates', manifest['controls'] == CONTROLS and manifest['models'] == MODELS and manifest['origin_count'] == 90)
R.check('fits.jsonl: 90 origins, all estimated, every candidate and both bands present',
        len(fits) == 90 and all(f['status'] == 'estimated' and set(f['fits']) == set(MODELS) and all(set(f['fits'][m]) == {'1', '2'} for m in MODELS) for f in fits.values()))


def band_means_to_months(bands):
    h = np.arange(1, 13); basis = np.column_stack([np.interp(h, [2, 5, 8, 11], np.eye(4)[j]) for j in range(4)])
    means = np.vstack([basis[3 * k:3 * k + 3].mean(axis=0) for k in range(4)])
    return basis @ np.linalg.solve(means, np.asarray(bands, float))


# ---- 1. coefficients x scaled current features = contributions = prediction
w = dict(contrib=0., pred=0., csv_coef=0., csv_contrib=0.); bad = []
kk = K.set_index(['origin', 'model', 'band', 'feature'])
R.check('coefficient_contributions.csv has one row per origin-model-band-feature and nothing else',
        kk.index.is_unique and len(K) == 90 * 2 * sum(len(fits['2019-02']['fits'][m]['1']['columns']) for m in MODELS))
for o, f in fits.items():
    for m in MODELS:
        for b in ('1', '2'):
            z = f['fits'][m][b]; cols = z['columns']
            now = X.loc[o, cols].to_numpy(float); scale = np.array([z['scale'][c] for c in cols]); beta = np.array(z['coefficients'])
            mine = beta * now / scale
            w['contrib'] = max(w['contrib'], np.abs(mine - np.array(z['contributions'])).max())
            w['pred'] = max(w['pred'], abs(mine.sum() - z['prediction']))
            for j, c in enumerate(cols):
                row = kk.loc[(o, m, int(b), c)]
                w['csv_coef'] = max(w['csv_coef'], abs(row.coefficient - beta[j])); w['csv_contrib'] = max(w['csv_contrib'], abs(row.band_log_core_correction - z['contributions'][j]))
                if bool(row.applied) != z['applied'] or row.alpha != z['alpha'] or row.kind != z['kind']:
                    bad.append((o, m, b, c))
R.check('coefficient x (current feature / saved training RMS scale) = contribution', w['contrib'] < 1e-15, f"max abs diff={w['contrib']:.3e}")
R.check('sum of contributions = band prediction', w['pred'] < 1e-15, f"max abs diff={w['pred']:.3e}")
R.check('coefficient_contributions.csv mirrors fits.jsonl (coefficient, contribution, applied, alpha, kind)', w['csv_coef'] == 0 and w['csv_contrib'] == 0 and not bad, f"{w['csv_coef']:.1e} {w['csv_contrib']:.1e} {bad[:3]}")

# ---- 2. selection from saved validation scores
ivm = IV.groupby(['origin', 'model', 'band', 'alpha']).agg(score=('loss', 'mean'), zero=('zero_loss', 'mean'), n=('loss', 'size'))
w2 = dict(score=0., zero=0., zero_y=0.); bad = []; applied_count = {m: [0, 0] for m in MODELS}; margins = []
for o, f in fits.items():
    for m in MODELS:
        for bi, b in enumerate(('1', '2')):
            s = f['selection'][m][b]; z = f['fits'][m][b]
            scores = {a: s['scores'][str(a)] for a in GRID}
            for a in GRID:
                w2['score'] = max(w2['score'], abs(ivm.loc[(o, m, int(b), a), 'score'] - scores[a]))
                w2['zero'] = max(w2['zero'], abs(ivm.loc[(o, m, int(b), a), 'zero'] - s['zero_loss']))
            vo = sorted({r['validation_origin'] for r in s['validation']})
            w2['zero_y'] = max(w2['zero_y'], abs(float(np.mean(Y.loc[vo, int(b)].to_numpy() ** 2)) - s['zero_loss']))
            low = min(scores.values()); best = max(a for a in GRID if scores[a] == low)
            expect = best if scores[best] < s['zero_loss'] else None
            margins.append(scores[best] / s['zero_loss'])
            if expect != s['alpha'] or z['applied'] != (expect is not None) or z['alpha'] != (expect if expect is not None else 3.0):
                bad.append((o, m, b, expect, s['alpha']))
            if s['status'] != ('nested_selected' if expect is not None else 'no_correction_validated'):
                bad.append((o, m, b, s['status']))
            applied_count[m][bi] += expect is not None
            row = ST[(ST.origin == o) & (ST.model == m)].iloc[0]
            sa = row[f'band{b}_alpha']
            if row[f'band{b}_status'] != s['status'] or not ((pd.isna(sa) and s['alpha'] is None) or sa == s['alpha']) or row[f'n_train_{b}'] != f['n_train'][b]:
                bad.append((o, m, b, 'status.csv'))
R.check('saved scores = mean of the per-fold losses in inner_validation.csv', w2['score'] < 1e-15, f"max abs diff={w2['score']:.3e}")
R.check('zero_loss = mean squared validation label (inner_validation.csv and band_targets.csv)', w2['zero'] < 1e-15 and w2['zero_y'] < 1e-15, f"{w2['zero']:.1e} {w2['zero_y']:.1e}")
R.check('selected alpha = argmin of saved scores, tie to larger alpha, applied only if strictly below zero_loss; status.csv agrees', not bad, str(bad[:4]))
print('   bands applied out of 90 origins (band1, band2):', {m: tuple(v) for m, v in applied_count.items()})
mg = np.array(margins); print(f'   best-score / zero-loss ratio: min {mg.min():.3f}, median {np.median(mg):.3f}, max {mg.max():.3f}; within 1% of the threshold: {int((np.abs(mg - 1) < .01).sum())} of {len(mg)} cells')

# ---- 3. paths
w3 = dict(path=0., mean=0., far=0.); near_nonzero = 0
for o, f in fits.items():
    for m in MODELS:
        c = [f['fits'][m][b]['prediction'] if f['selection'][m][b]['alpha'] is not None else 0. for b in ('1', '2')]
        path = np.array(f['paths'][m]); mine = band_means_to_months([*c, 0., 0.])
        w3['path'] = max(w3['path'], np.abs(path - mine).max())
        w3['mean'] = max(w3['mean'], np.abs(path.reshape(4, 3).mean(axis=1) - np.array([*c, 0., 0.])).max())
        if c == [0., 0.]:
            w3['far'] = max(w3['far'], np.abs(path).max())
        near_nonzero += (c[0] == 0.) and np.abs(path[:3]).max() > 0
R.check('paths = monthly_correction([c1, c2, 0, 0]) with unapplied bands entered as exactly 0', w3['path'] < 1e-15, f"max abs diff={w3['path']:.3e}")
R.check('band means of the saved path = [c1, c2, 0, 0]', w3['mean'] < 1e-15, f"max abs diff={w3['mean']:.3e}")
R.check('both bands unapplied -> path identically zero', w3['far'] == 0.)
print(f'   origin-model cells where band 1 is NOT applied yet months h1-h3 carry a non-zero (mean-zero) correction from band 2: {near_nonzero}')

# ---- 4. native forecasts
nat = native.set_index(['model', 'origin', 'h']).sort_index()
R.check('native_forecasts.csv: 10 models x 90 origins x 13 horizons, unique keys', len(native) == 10 * 90 * 13 and nat.index.is_unique and set(native.model) == set(CONTROLS + MODELS))
R.check('forecasts.csv: same 11,700 keys', len(forecasts) == 11700 and not forecasts.duplicated(['model', 'origin', 'h']).any() and set(forecasts.model) == set(CONTROLS + MODELS))
src = pd.read_csv(ROOT / 'output/research_r21/path_anchor/native_forecasts.csv', **rd)
src = src[src.model.isin(CONTROLS)].set_index(['model', 'origin', 'h']).sort_index()
def same_frame(a, b):
    cols = [c for c in a.columns if c in b.columns]; a = a[cols]; b = b[cols].reindex(a.index); diff = []
    for c in cols:
        x, y = a[c], b[c]
        if not ((x == y) | (x.isna() & y.isna())).all():
            diff.append(c)
    return diff
control_diff = {m: same_frame(nat.loc[m], src.loc[m]) for m in CONTROLS}
R.check('control rows are carried over from the R21 native file unchanged (every shared column, NaN = NaN)', not any(control_diff.values()), str(control_diff))
print('   columns only in the R23B native file:', sorted(set(native.columns) - set(src.reset_index().columns)), '; only in the R21 file:', sorted(set(src.reset_index().columns) - set(native.columns)))
fast = nat.loc['STATE_FAST_R15']
w4 = dict(core=0., state=0., mm=0., cc=0.); changed_cols = set(); h0_diff = 0
frozen = [c for c in native.columns if c not in ('model', 'origin', 'h', 'value_core', 'contribution_core', 'mm_forecast', 'yy_exante', 'yy_conditional', 'cumulative_log_forecast', 'core_model_status', 'core_fallback_used')]
for m in MODELS:
    own = nat.loc[m]
    for col in frozen:
        a, b = own[col], fast[col]
        if not ((a == b) | (a.isna() & b.isna())).all():
            changed_cols.add(col)
    z = own.xs(0, level='h'); zf = fast.xs(0, level='h')
    for col in ['value_core', 'contribution_core', 'mm_forecast']:
        h0_diff += int((~((z[col] == zf[col]) | (z[col].isna() & zf[col].isna()))).sum())
    for o in fits:
        base = np.array([states[o]['forecasts_log']['fast'][str(h)] for h in range(1, 13)])
        want = 100 * np.expm1((base + np.array(fits[o]['paths'][m])) / 100)
        got = own.loc[o].loc[1:12]
        w4['core'] = max(w4['core'], np.abs(got.value_core.to_numpy() - want).max())
        w4['state'] = max(w4['state'], np.abs(100 * np.log1p(fast.loc[o].loc[1:12].value_core.to_numpy() / 100) - base).max())
        ff = fast.loc[o].loc[1:12]
        w4['mm'] = max(w4['mm'], np.abs(got.mm_forecast.to_numpy() - (ff.mm_forecast.to_numpy() + ff.weight_core.to_numpy() * (want - ff.value_core.to_numpy()))).max())
        w4['cc'] = max(w4['cc'], np.abs(got.contribution_core.to_numpy() - got.weight_core.to_numpy() * got.value_core.to_numpy()).max())
R.check('exported core h1-12 = 100*expm1((saved FAST log rate + path)/100)', w4['core'] < 1e-13, f"max abs diff={w4['core']:.3e}")
R.check('native FAST core equals states.json FAST log rates', w4['state'] < 1e-10, f"max abs diff={w4['state']:.3e}")
R.check('h0 rows (core, contribution, mm_forecast) identical to FAST for every candidate', h0_diff == 0, f'differing cells={h0_diff}')
R.check('every noncore value, every contribution except core, every weight, every target/actual column identical to FAST', not changed_cols, str(sorted(changed_cols)))
R.check('mm_forecast = FAST mm_forecast + weight_core x (new core - FAST core); contribution_core = weight x value', w4['mm'] < 1e-13 and w4['cc'] < 1e-15, f"{w4['mm']:.1e} {w4['cc']:.1e}")
# identical-to-FAST when no band is applied?
noband = [(o, m) for o in fits for m in MODELS if all(fits[o]['selection'][m][b]['alpha'] is None for b in ('1', '2'))]
drift = max((np.abs(nat.loc[m].loc[o].loc[1:12].value_core.to_numpy() - fast.loc[o].loc[1:12].value_core.to_numpy()).max() for o, m in noband), default=0.)
print(f'   origin-model cells with no band applied: {len(noband)}; their core differs from FAST by at most {drift:.2e} (states.json log rates re-exponentiated, not the FAST value copied)')

# ---- 5. headline annual rate recomputed from the monthly path
headline = pd.read_csv(ROOT / 'output/independent_path_frozen_inputs.csv', **rd).set_index('period')['headline_mm'] if 'period' in pd.read_csv(ROOT / 'output/independent_path_frozen_inputs.csv', nrows=1).columns else None
if headline is None:
    raw_in = pd.read_csv(ROOT / 'output/independent_path_frozen_inputs.csv', **rd); headline = raw_in.set_index(raw_in.columns[0])['headline_mm']
headline.index = pd.PeriodIndex(headline.index, freq='M'); worst_yy = 0.; worst_cum = 0.
fc = forecasts.set_index(['model', 'origin', 'h']).sort_index()
for m in MODELS + ['STATE_FAST_R15']:
    for o in fits:
        t = pd.Period(o, 'M'); mm = nat.loc[m].loc[o].mm_forecast
        for h in range(13):
            window = pd.period_range(t + h - 11, t + h, freq='M')
            vals = np.array([headline[p] if p < t else mm.loc[(p - t).n] for p in window], float)
            yy = 100 * np.expm1(np.log1p(vals / 100).sum())
            worst_yy = max(worst_yy, abs(yy - fc.loc[(m, o, h), 'yy_exante']))
R.check('forecasts.csv yy_exante = twelve-month compounding of known history, FAST h0 and the candidate monthly path', worst_yy < 1e-10, f'max abs diff={worst_yy:.3e}')

# ---- 6. primary rows
P = pd.read_csv(EVAL / 'primary_rows.csv', **rd)
support = pd.read_csv(ROOT / 'output/research_r17/attribution/primary_support.csv')
keys = set(map(tuple, support[['origin', 'h']].to_numpy()))
per_model = P.groupby('model').size()
R.check('primary_rows.csv: 969 keys for each of the 10 models, identical key set = R17 primary support', per_model.eq(969).all() and len(per_model) == 10 and all(set(map(tuple, g[['origin', 'h']].to_numpy())) == keys for _, g in P.groupby('model')))
R.check('primary rows have finite forecast and outcome for every model (headline and cumulative core)', np.isfinite(P[['yy_exante', 'yy_actual', 'core_cumulative_log_forecast', 'core_cumulative_log_actual']]).all().all())
counts = {h: int((support.h == h).sum()) for h in (3, 6, 12)}; recent = {h: int(((support.h == h) & (support.origin >= '2024-01')).sum()) for h in (3, 6, 12)}
print('   support sizes h3/h6/h12:', counts, ' origins from 2024:', recent)
pf = P.merge(forecasts[['model', 'origin', 'h', 'yy_exante']], on=['model', 'origin', 'h'], suffixes=('', '_f'))
R.check('primary_rows yy_exante identical to forecasts.csv', (pf.yy_exante == pf.yy_exante_f).all())
# cumulative core in primary rows against native
pn = P.merge(native[['model', 'origin', 'h', 'value_core']], on=['model', 'origin', 'h'])
R.check('primary_rows core_mm_forecast identical to native value_core', (pn.core_mm_forecast == pn.value_core).all())
cum = native[native.h.gt(0)].sort_values(['model', 'origin', 'h']).assign(lc=lambda d: 100 * np.log1p(d.value_core / 100))
cum['mine'] = cum.groupby(['model', 'origin']).lc.cumsum()
pc = P.merge(cum[['model', 'origin', 'h', 'mine']], on=['model', 'origin', 'h'])
R.check('primary_rows cumulative log core = sum over h1..h of native log core', (pc.core_cumulative_log_forecast - pc.mine).abs().max() < 1e-12, f'max abs diff={(pc.core_cumulative_log_forecast - pc.mine).abs().max():.3e}')
# cumulative applied correction identity at h3/h6/h12
fastc = cum[cum.model.eq('STATE_FAST_R15')].set_index(['origin', 'h']).mine; worst_id = 0.
for m in MODELS:
    own = cum[cum.model.eq(m)].set_index(['origin', 'h']).mine
    for o, f in fits.items():
        c = [f['fits'][m][b]['prediction'] if f['selection'][m][b]['alpha'] is not None else 0. for b in ('1', '2')]
        for h, want in [(3, 3 * c[0]), (6, 3 * (c[0] + c[1])), (9, 3 * (c[0] + c[1])), (12, 3 * (c[0] + c[1]))]:
            worst_id = max(worst_id, abs(own[(o, h)] - fastc[(o, h)] - want))
R.check('cumulative log core minus FAST = 3*c1 at h3 and 3*(c1+c2) at h6, h9 and h12', worst_id < 1e-12, f'max abs diff={worst_id:.3e}')
R.done()
