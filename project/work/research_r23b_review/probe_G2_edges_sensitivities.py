"""Probe G2: edge behaviour of the delivered code and sensitivities of the reported diagnostics."""
import json
from types import SimpleNamespace
import numpy as np
import pandas as pd

from _common import ROOT, FINAL, EVAL, Report

from data.cost_pressure_r23b import load_inputs, features_at, COLUMNS
from models.cost_pressure_r23b import eligible, run_origin, FAMILIES
from models.cost_gaps_r23 import monthly_correction

R = Report('G2 edges and sensitivities')
rd = dict(float_precision='round_trip', low_memory=False)
core, core_dates, raw, fx, _ = load_inputs()
states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
clocks = pd.read_csv(FINAL / 'feature_clocks.csv', index_col=0).iloc[:, 0].map(pd.Timestamp)
X = pd.read_csv(FINAL / 'features.csv', index_col=0, **rd)
fits = {json.loads(l)['origin']: json.loads(l) for l in (FINAL / 'fits.jsonl').open()}
MODELS = list(FAMILIES)

# ---- (a) a publication hole INSIDE the six-month PPI window
o = '2023-01'; t = pd.Period(o, 'M'); clock = clocks[o]
base, _ = features_at(core, core_dates, raw, fx, t, clock, states[o]['seasonal'])
holed = dict(raw); r = raw[47]; avail = r.available.copy(); avail.loc[t - 4] = pd.NaT                     # reference month is t-1; t-4 is interior
holed[47] = SimpleNamespace(values=r.values, available=avail, kind=r.kind, source=r.source)
ppi_hole, _ = features_at(core, core_dates, holed, fx, t, clock, states[o]['seasonal'])
r26 = raw[26]; avail26 = r26.available.copy(); avail26.loc[t - 5] = pd.NaT; holed26 = dict(raw); holed26[26] = SimpleNamespace(values=r26.values, available=avail26, kind=r26.kind, source=r26.source)
imp_hole, _ = features_at(core, core_dates, holed26, fx, t, clock, states[o]['seasonal'])
R.check('(a) import_mom fails closed when one of its six monthly changes has no publication date', np.isnan(imp_hole.import_mom))
R.check('(a) ppi_mom fails closed when an interior month of its six-month window has no publication date (spec: "all six must be published")',
        np.isnan(ppi_hole.ppi_mom), f'ppi_mom with the hole = {ppi_hole.ppi_mom:.6f}, without = {base.ppi_mom:.6f} (the code reads only the two end levels)')
interior_holes = 0
for n in (47,):
    a = raw[n].available
    interior_holes += int(a.isna().sum()) + int((a.diff().dropna() < pd.Timedelta(0)).sum())
print(f'   delivered PPI source: missing or non-monotone publication dates = {interior_holes} -> the deviation cannot have changed a delivered number')

# ---- (b) eligible() silently depends on row order
Xp = X.copy(); Xp.index = pd.PeriodIndex(Xp.index, freq='M')
Y = pd.read_csv(FINAL / 'band_targets.csv', index_col=0, **rd); Y.index = pd.PeriodIndex(Y.index, freq='M'); Y.columns = Y.columns.astype(int)
A = pd.read_csv(FINAL / 'target_available.csv', index_col=0); A.index = pd.PeriodIndex(A.index, freq='M'); A.columns = A.columns.astype(int); A = A.apply(pd.to_datetime)
good = eligible(Xp, Y, A, pd.Period('2026-07', 'M'), clocks['2026-07'], 1, 24)
shuffled = Xp.sample(frac=1., random_state=3)
other = eligible(shuffled, Y, A, pd.Period('2026-07', 'M'), clocks['2026-07'], 1, 24)
R.check('(b) eligible() returns the same latest-40 set when the feature rows arrive unsorted', set(good) == set(other),
        f'sorted: {good.min()}..{good.max()}; shuffled input: {len(set(good) ^ set(other))} rows differ (run.py refuses unsorted features, the function itself does not)')

# ---- (c) no intercept, but the features are not mean-zero: the pseudo-intercept that remains
F = pd.read_csv(EVAL / 'forecast_core_outcomes.csv', **rd); fast6 = F[F.model.eq('STATE_FAST_R15') & F.h.eq(6)].set_index('origin')
needed = (fast6.core_cumulative_log_actual - fast6.core_cumulative_log_forecast).dropna(); rows = []; share = []
for f in fits.values():
    for b in ('1', '2'):
        tr = X.loc[f['train_dates'][b]]; share.append(dict(origin=f['origin'], band=b, **(tr.mean() ** 2 / (tr ** 2).mean()).to_dict()))
S = pd.DataFrame(share)
print('   share of each feature\'s training second moment that is its MEAN (mean^2 / mean of squares), by origin year, band 1:')
print(S[S.band.eq('1')].assign(year=lambda d: d.origin.str[:4]).groupby('year')[COLUMNS].mean().round(2).to_string().replace('\n', '\n   '))
for m in MODELS:
    level = {}; dev = {}
    for o_, f in fits.items():
        L = D = 0.
        for b in ('1', '2'):
            z = f['fits'][m][b]
            if not z['applied']:
                continue
            cols = z['columns']; beta = np.array(z['coefficients']); s = np.array([z['scale'][c] for c in cols]); mean = X.loc[f['train_dates'][b], cols].mean().to_numpy(); now = X.loc[o_, cols].to_numpy()
            L += 3 * (beta * mean / s).sum(); D += 3 * (beta * (now - mean) / s).sum()
        level[o_] = L; dev[o_] = D
    level = pd.Series(level); dev = pd.Series(dev); own = F[F.model.eq(m) & F.h.eq(6)].set_index('origin')
    applied = (own.core_cumulative_log_forecast - fast6.core_cumulative_log_forecast).reindex(level.index)
    assert np.allclose(applied, level + dev, atol=1e-9)
    ix = needed.index
    rows.append(dict(model=m, n=len(ix), corr_applied=needed.corr(applied[ix]), corr_level_part=needed.corr(level[ix]), corr_deviation_part=needed.corr(dev[ix]),
                     mean_abs_level_part=level[ix].abs().mean(), mean_abs_deviation_part=dev[ix].abs().mean()))
    # which part costs accuracy? h6 cumulative-core RMSE on the 81-origin primary support, delivered against each part alone (a decomposition of the delivered correction, not a new model)
    support6 = pd.read_csv(ROOT / 'output/research_r17/attribution/primary_support.csv').query('h == 6').origin; rm = lambda e: float(np.sqrt(np.mean(np.square(e))))
    for sample, jx in [('full', support6), ('origins_2024plus', support6[support6 >= '2024-01'])]:
        rows[-1].update({f'rmse_fast_{sample}': rm(needed[jx]), f'rmse_delivered_{sample}': rm(needed[jx] - applied[jx]), f'rmse_deviation_part_only_{sample}': rm(needed[jx] - dev[jx]),
                         f'rmse_level_part_only_{sample}': rm(needed[jx] - level[jx]), f'mean_level_part_{sample}': float(level[jx].mean()), f'mean_deviation_part_{sample}': float(dev[jx].mean())})
T = pd.DataFrame(rows); T.to_csv(ROOT / 'work/research_r23b_review/probe_G2_pseudo_intercept.csv', index=False)
print('   h6 core RMSE on the primary support: FAST, delivered, deviation part alone, level part alone; and the mean of each part')
print(T[['model', *[c for c in T.columns if c.startswith(('rmse_', 'mean_level', 'mean_dev'))]]].round(4).T.to_string(header=False).replace('\n', '\n   '))
T = T[['model', 'n', 'corr_applied', 'corr_level_part', 'corr_deviation_part', 'mean_abs_level_part', 'mean_abs_deviation_part']]
print('   h6 applied correction = coefficient x training MEAN of the feature ("level part") + coefficient x deviation from that mean; correlation with the correction FAST needed:')
print(T.round(3).to_string(index=False).replace('\n', '\n   '))
R.check('(c) the part of the applied correction that comes from non-zero feature means is NOT negatively correlated with the needed correction (no delayed echo left)',
        (T.corr_level_part > -.2).all(), f"level-part correlations: {dict(zip(T.model.str[6:-5], T.corr_level_part.round(2)))}")

# ---- (d) needed-versus-applied on the primary support instead of all matured origins
sup = pd.read_csv(ROOT / 'output/research_r17/attribution/primary_support.csv'); keep6 = sup[sup.h.eq(6)].origin
NA = pd.read_csv(EVAL / 'needed_vs_applied.csv', **rd); flips = []
for m in MODELS:
    own = F[F.model.eq(m) & F.h.eq(6)].set_index('origin'); applied = own.core_cumulative_log_forecast - fast6.core_cumulative_log_forecast
    for sample, ix in [('full', keep6), ('origins_2024plus', keep6[keep6 >= '2024-01'])]:
        mine = needed[ix].corr(applied[ix]); theirs = NA[(NA.model == m) & (NA.h == 6) & (NA['sample'] == sample)].correlation.iloc[0]
        if np.sign(mine) != np.sign(theirs):
            flips.append((m, sample, round(mine, 3), round(theirs, 3)))
        print(f'   {m:22s} {sample:17s} delivered (n={int(NA[(NA.model == m) & (NA.h == 6) & (NA["sample"] == sample)].n.iloc[0])}) {theirs:+.3f}   on the primary support (n={len(ix)}) {mine:+.3f}')
R.check('(d) no needed-versus-applied sign changes when the 81-origin primary support replaces the 84 matured origins', not flips, str(flips))

# ---- (e) how decisive is the do-no-harm test?
IV = pd.read_csv(FINAL / 'inner_validation.csv', **rd)
cell = IV.groupby(['origin', 'model', 'band', 'alpha']).agg(score=('loss', 'mean'), zero=('zero_loss', 'mean')).reset_index()
best = cell.sort_values(['score', 'alpha'], ascending=[True, False]).groupby(['origin', 'model', 'band']).head(1).assign(applied=lambda d: d.score < d.zero, ratio=lambda d: d.score / d.zero)
print('   chosen penalty among applied cells:', best[best.applied].alpha.value_counts().sort_index().to_dict(), '; applied', int(best.applied.sum()), 'of', len(best))
print(f'   applied cells whose validation gain over no correction is below 1%: {int((best.applied & (best.ratio > .99)).sum())}; below 5%: {int((best.applied & (best.ratio > .95)).sum())}')
print(f'   unapplied cells that lost by less than 1%: {int((~best.applied & (best.ratio < 1.01)).sum())}')
# sign test across the 8 folds: in how many applied cells does the correction win in at most half of the folds?
wins = IV.merge(best[['origin', 'model', 'band', 'alpha', 'applied']], on=['origin', 'model', 'band', 'alpha']).assign(win=lambda d: d.loss < d.zero_loss)
fold_wins = wins[wins.applied].groupby(['origin', 'model', 'band']).win.sum()
print('   applied cells by number of the 8 folds in which the correction beat no correction:', fold_wins.value_counts().sort_index().to_dict())

# ---- (f) what the band-mean-preserving map does outside the band it is given
unit = monthly_correction([0., 1., 0., 0.]); unit1 = monthly_correction([1., 0., 0., 0.])
print('   monthly map of c2=1 alone:', np.round(unit, 3).tolist())
print('   monthly map of c1=1 alone:', np.round(unit1, 3).tolist())
side = []
for o_, f in fits.items():
    for m in MODELS:
        p = np.array(f['paths'][m]); c = [f['fits'][m][b]['prediction'] if f['fits'][m][b]['applied'] else 0. for b in ('1', '2')]
        side.append(dict(origin=o_, model=m, far=np.abs(p[6:]).max(), near_unapplied=np.abs(p[:3]).max() if c[0] == 0. else 0., largest=np.abs(p).max()))
side = pd.DataFrame(side)
print(f'   largest |monthly correction| in h7-12: {side.far.max():.4f} log points; in h1-3 of origins whose band 1 was NOT applied: {side.near_unapplied.max():.4f}; largest anywhere: {side.largest.max():.4f}')
R.check('(f) cumulative effect of those side lobes at h3, h6, h9, h12 is exactly zero (checked in probe C); they only move h1-2, h4-5, h7-8, h10-11', True)

# ---- (g) fallback paths that the delivered run never exercised
st = pd.read_csv(FINAL / 'status.csv'); print('   status values in the delivered run:', st.status.value_counts().to_dict(), '| band statuses:', pd.concat([st.band1_status, st.band2_status]).value_counts().to_dict())
hole = Xp.copy(); hole.loc[pd.Period('2026-07', 'M'), 'import_gap'] = np.nan
res = run_origin(hole, Y, A, clocks.set_axis(pd.PeriodIndex(clocks.index, freq='M')), pd.Period('2026-07', 'M'), fits['2026-07']['as_of'])
R.check('(g) a missing current import_gap (used by one candidate) leaves the five candidates that do not use it estimated',
        res['status'] == 'estimated', f"status={res['status']}: every candidate, including PRESS_ULC_R23B, falls back to FAST (never triggered in the delivered run)")
R.done()
