"""F. Robustness of the economic story, from frozen outputs only (no model is fitted here).

1. per-origin h12 squared-loss differences (candidate minus FAST) on the primary support; concentration
2. decomposition d = 2*e_FAST*delta + delta^2 and the sign of delta = direction the candidate moved the path
3. is the 2019-21 gain distinguishable from noise?
4. how much do mu_long / mu_robust / mu_window move over time
5. POST-HOC SENSITIVITY, NOT FOR SELECTION: a plain constant drift instead of mu_long (grid 0..5 log points a
   year), re-scored on the food block (h12) and on the assembled headline (h12, fixed support)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_common as pc

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 500)
prim = pd.read_csv(pc.EVAL / 'primary_rows.csv', low_memory=False, float_precision='round_trip')
prim['e'] = prim.yy_exante - prim.yy_actual
h12 = prim[prim.h.eq(12)]
err = h12.pivot(index='origin', columns='model', values='e'); fc = h12.pivot(index='origin', columns='model', values='yy_exante')
audit = pd.read_csv(pc.R24 / 'drift_audit.csv', float_precision='round_trip').set_index('origin')
C = 'FOOD_NORM_SHIFT_R24'

# ---------------------------------------------------------------- 1, 2
d = (err[C] ** 2 - err[pc.FAST] ** 2).rename('d'); delta = (fc[C] - fc[pc.FAST]).rename('delta')
table = pd.concat([err[pc.FAST].rename('e_fast'), err[C].rename('e_cand'), delta, d], axis=1)
table['drift_gap_annual_pct'] = (audit.mu_long_annual_pct - audit.mu_window_annual_pct).reindex(table.index)
table['year'] = table.index.str[:4]; table['era'] = [pc.era(o) for o in table.index]
table.to_csv(pc.HERE / 'out_F_per_origin_h12.csv')
total = d.sum()
print('=' * 30, '1. concentration of the full-sample h12 headline gain,', C)
print('n = %d, sum d = %.3f, mean d = %.4f (stored mean_loss_difference -0.664419)' % (len(d), total, d.mean()))
print('origins improved: %d of %d (%.0f%%); worsened: %d' % ((d < 0).sum(), len(d), 100 * (d < 0).mean(), (d > 0).sum()))
top = d.sort_values().head(5)
print('five largest improvements:'); print(table.loc[top.index, ['e_fast', 'e_cand', 'delta', 'd']].round(3).to_string())
print('share of total improvement from the top 5 origins: %.1f%%; top 10: %.1f%%; top 20: %.1f%%' % (100 * top.sum() / total, 100 * d.sort_values().head(10).sum() / total, 100 * d.sort_values().head(20).sum() / total))
print('five largest deteriorations:'); print(table.loc[d.sort_values().tail(5).index, ['e_fast', 'e_cand', 'delta', 'd']].round(3).to_string())
by_year = table.groupby('year').agg(n=('d', 'size'), sum_d=('d', 'sum'), mean_d=('d', 'mean'), improved=('d', lambda x: int((x < 0).sum())), mean_delta=('delta', 'mean'), mean_e_fast=('e_fast', 'mean'),
                                     rmse_fast=('e_fast', lambda x: np.sqrt((x ** 2).mean())), rmse_cand=('e_cand', lambda x: np.sqrt((x ** 2).mean())))
by_year['share_of_total_pct'] = 100 * by_year.sum_d / total
print('\nby origin year:'); print(by_year.round(3).to_string())
by_era = table.groupby('era').agg(n=('d', 'size'), sum_d=('d', 'sum'), improved=('d', lambda x: int((x < 0).sum())), mean_delta=('delta', 'mean'), rmse_fast=('e_fast', lambda x: np.sqrt((x ** 2).mean())), rmse_cand=('e_cand', lambda x: np.sqrt((x ** 2).mean())))
by_era['share_of_total_pct'] = 100 * by_era.sum_d / total; by_era['rmse_change_pct'] = 100 * (by_era.rmse_cand / by_era.rmse_fast - 1)
print('\nby era:'); print(by_era.round(3).to_string())
print('\n2. decomposition: sum of 2*e_fast*delta = %.3f, sum of delta^2 = %.3f  (gain comes from moving against the FAST error, cost is delta^2)' % ((2 * table.e_fast * table.delta).sum(), (table.delta ** 2).sum()))
print('correlation(delta, e_fast) = %.3f ; sign(delta) opposite to sign(e_fast) at %d of %d origins' % (table.delta.corr(table.e_fast), (np.sign(table.delta) != np.sign(table.e_fast)).sum(), len(table)))
print('delta by era (pp of annual headline at h12): ' + ', '.join(f'{k} mean {v:+.3f}' for k, v in table.groupby('era').delta.mean().items()))

# ---------------------------------------------------------------- 3
print('\n' + '=' * 30, '3. is the 2019-21 gain real?')


def circ(x, block, draws=20000, seed=77):
    rng = np.random.default_rng(seed); n = len(x); k = int(np.ceil(n / block)); s = rng.integers(0, n, size=(draws, k))
    idx = ((s[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    return x[idx].mean(axis=1)


for name in pc.ERAS[1:]:
    x = table[table.era.eq(name)].d.to_numpy()
    for block in (6, 12):
        m = circ(x, block)
        print(f'headline h12 {name:<18} n={len(x):>2} mean d {x.mean():+.4f}  circular block {block:>2}: 95% [{np.quantile(m, .025):+.4f}, {np.quantile(m, .975):+.4f}]  P(d<0)={np.mean(m < 0):.3f}')
pairs = pd.read_csv(pc.HERE / 'out_D_food_block_pairs.csv')
f12 = pairs[pairs.H.eq(12)].assign(e=lambda z: z.forecast - z.actual).pivot(index='origin', columns='model', values='e')
for name in pc.ERAS:
    z = f12[pc.era_mask(f12.index, name)]; x = (z[C] ** 2 - z[pc.FAST] ** 2).to_numpy()
    m = circ(x, 12 if len(x) >= 48 else 6)
    print(f'food block h12 {name:<18} n={len(x):>2} mean d {x.mean():+.3f}  improved {int((x < 0).sum()):>2}/{len(x)}  95% [{np.quantile(m, .025):+.3f}, {np.quantile(m, .975):+.3f}]  P(d<0)={np.mean(m < 0):.3f}')
early = table[table.era.eq('origins_2019_2021')]
print('2019-21 origins: FAST h12 headline errors all negative? %s (mean %.2f, max %.2f); delta > 0 at %d of %d origins -> any upward nudge gains here' % (bool((early.e_fast < 0).all()), early.e_fast.mean(), early.e_fast.max(), (early.delta > 0).sum(), len(early)))
for lo, hi in [('2019-05', '2020-04'), ('2020-05', '2021-04'), ('2021-05', '2021-12')]:
    z = early[(early.index >= lo) & (early.index <= hi)]
    print(f'   origins {lo}..{hi}: n={len(z):>2}  mean delta {z.delta.mean():+.3f}  mean e_fast {z.e_fast.mean():+.3f}  sum d {z.d.sum():+.3f}  improved {int((z.d < 0).sum())}/{len(z)}')

# ---------------------------------------------------------------- 4
print('\n' + '=' * 30, '4. drift estimates over time, log points a year')
a = audit[['mu_window_annual_pct', 'mu_robust_annual_pct', 'mu_long_annual_pct']].copy(); a['year'] = a.index.str[:4]
print(a.groupby('year').agg(['min', 'max']).round(2).to_string())
print('mu_long over all 90 origins: min %.3f max %.3f mean %.3f sd %.3f' % (a.mu_long_annual_pct.min(), a.mu_long_annual_pct.max(), a.mu_long_annual_pct.mean(), a.mu_long_annual_pct.std()))
print('mu_window: min %.3f max %.3f ; mu_robust: min %.3f max %.3f' % (a.mu_window_annual_pct.min(), a.mu_window_annual_pct.max(), a.mu_robust_annual_pct.min(), a.mu_robust_annual_pct.max()))

# ---------------------------------------------------------------- 5
print('\n' + '=' * 30, '5. POST-HOC SENSITIVITY (must not be used for selection): constant drift instead of mu_long')
native = pd.read_csv(pc.R24 / 'native_forecasts.csv', low_memory=False, float_precision='round_trip')
fast = native[native.model.eq(pc.FAST)].sort_values(['origin', 'h'])
rates = pd.read_csv(pc.R24 / 'food_log_rates.csv', float_precision='round_trip')
base = rates[rates.model.eq('FOOD_STABLE_PIPELINE_R14B')].pivot(index='origin', columns='h', values='log_rate')
actual = pd.read_csv(pc.ACTUAL, float_precision='round_trip'); actual.index = pd.PeriodIndex(actual.period, freq='M')
head = pd.read_csv(pc.HEADLINE); head.index = pd.PeriodIndex(head.period, freq='M'); head = head.headline_mm
support = pd.read_csv(pc.ROOT / 'output/research_r17/attribution/primary_support.csv'); support12 = set(support[support.h.eq(12)].origin)
truth_yy = h12.drop_duplicates('origin').set_index('origin').yy_actual


def score(drift_by_origin):
    """drift_by_origin: Series origin -> monthly log-point drift replacing mu_window. Returns per-origin food and headline h12 errors."""
    out = {}
    for origin, g in fast.groupby('origin'):
        t = pd.Period(origin, 'M'); g = g.set_index('h')
        logs = base.loc[origin].to_numpy() - audit.loc[origin, 'mu_window'] + drift_by_origin[origin]
        value = 100 * np.expm1(logs / 100)
        truth = 100 * np.log1p(actual.food.reindex(pd.period_range(t + 1, t + 12, freq='M')).to_numpy(float) / 100)
        food_e = logs.sum() - truth.sum()
        mm = g.mm_forecast.to_dict()
        for h in range(1, 13):
            mm[h] = mm[h] + g.loc[h, 'weight_food'] * (value[h - 1] - g.loc[h, 'value_food'])
        yy_e = np.nan
        if origin in support12:
            yy_e = 100 * np.expm1(np.log1p(np.array([mm[h] for h in range(1, 13)]) / 100).sum()) - truth_yy[origin]
        out[origin] = (food_e, yy_e)
    return pd.DataFrame(out, index=['food_e', 'yy_e']).T


def summarise(label, frame):
    row = dict(drift=label)
    for name in pc.ERAS:
        z = frame[pc.era_mask(frame.index, name)]
        row['food12_' + name.replace('origins_', '')] = np.sqrt((z.food_e.dropna() ** 2).mean()); row['yy12_' + name.replace('origins_', '')] = np.sqrt((z.yy_e.dropna() ** 2).mean())
    return row


check = score(audit.mu_long); base_check = score(audit.mu_window)
print('machinery check: mu_long reproduces NORM_SHIFT headline h12 errors, max gap %.2e; mu_window reproduces FAST, max gap %.2e' % ((check.yy_e.dropna() - err[C]).abs().max(), (base_check.yy_e.dropna() - err[pc.FAST]).abs().max()))
rows = [summarise('mu_window (baseline)', base_check), summarise('mu_robust (declared)', score(audit.mu_robust)), summarise('mu_long (declared)', check)]
for annual in (0., 1., 1.5, 2., 2.5, 2.6, 3., 3.5, 4., 5., 6.):
    rows.append(summarise(f'constant {annual:.1f} a year', score(pd.Series(annual / 12, index=audit.index))))
grid = pd.DataFrame(rows).set_index('drift'); grid.to_csv(pc.HERE / 'out_F_constant_drift_grid.csv')
print(grid.round(3).to_string())
fine = pd.DataFrame([summarise(x, score(pd.Series(x / 12, index=audit.index))) for x in np.arange(0, 8.01, .25)]).set_index('drift')
print('\nex-post best constant (log points a year) by column:'); print(fine.idxmin().to_string())
print('\nrange of constants that beat the baseline on BOTH full-sample h12 headline and 2024+ h12 headline: ',
      [float(x) for x in fine.index[(fine.yy12_full <= grid.loc['mu_window (baseline)', 'yy12_full']) & (fine.yy12_2024plus <= grid.loc['mu_window (baseline)', 'yy12_2024plus'])]])
