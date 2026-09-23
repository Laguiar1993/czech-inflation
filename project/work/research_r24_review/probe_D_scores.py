"""D. Independent re-scoring. Nothing from the evaluator or tools.path_diagnostics is imported.

 (i)   food-block cumulative log RMSE / bias, h3/h6/h12 by era, baseline + candidates + zero change, from
       native_forecasts.csv and the realised block rates; compared with food_block_scores.csv
 (ii)  headline annual-rate RMSE h3/6/9/12 by era from evaluation/primary_rows.csv, compared with
       same_support_scoreboard.csv; plus an independent re-compounding of yy_exante and yy_actual from the
       native monthly paths and the headline history
 (iii) leave-one-origin-year-out h12 RMSE deltas
 (iv)  own circular block bootstrap (block 12, 20000 draws, own seed) of the full-sample h12 squared-loss
       difference against FAST, with block 6 / 18 / 24, a stationary bootstrap, a non-overlapping-block
       check and a Diebold-Mariano / Newey-West statistic as sensitivity
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_common as pc

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 500)
SEED = 24091717
native = pd.read_csv(pc.R24 / 'native_forecasts.csv', low_memory=False, float_precision='round_trip')
actual = pd.read_csv(pc.ACTUAL, float_precision='round_trip'); actual.index = pd.PeriodIndex(actual.period, freq='M')
models = [pc.FAST, *pc.CANDIDATES]

# ------------------------------------------------------------------ (i) food block
print('=' * 30, '(i) food block, cumulative log change h1..H')
rec = []
for (model, origin), g in native[native.model.isin(models) & native.h.gt(0)].groupby(['model', 'origin']):
    g = g.sort_values('h'); assert list(g.h) == list(range(1, 13))
    t = pd.Period(origin, 'M')
    truth = actual.food.reindex(pd.period_range(t + 1, t + 12, freq='M')).to_numpy(float)
    f = 100 * np.log1p(g.value_food.to_numpy(float) / 100); a = 100 * np.log1p(truth / 100)
    for H in (3, 6, 12):
        rec.append(dict(model=model, origin=origin, H=H, forecast=f[:H].sum(), actual=a[:H].sum()))   # NaN in truth propagates
blk = pd.DataFrame(rec); blk = blk[np.isfinite(blk.actual) & np.isfinite(blk.forecast)]
rows = []
for (model, H), g in blk.groupby(['model', 'H']):
    for sample in pc.ERAS:
        z = g[pc.era_mask(g.origin, sample)]; e = z.forecast - z.actual
        rows.append(dict(model=model, H=H, sample=sample, n=len(z), own_rmse=np.sqrt((e ** 2).mean()), own_bias=e.mean(), own_zero_rmse=np.sqrt((z.actual ** 2).mean()),
                         own_corr=z.forecast.corr(z.actual)))
own = pd.DataFrame(rows)
theirs = pd.read_csv(pc.EVAL / 'food_block_scores.csv')
cmp = own.merge(theirs[['model', 'H', 'sample', 'n', 'model_rmse', 'model_bias', 'zero_rmse', 'forecast_actual_correlation']], on=['model', 'H', 'sample'], suffixes=('', '_theirs'))
for a_, b_ in [('own_rmse', 'model_rmse'), ('own_bias', 'model_bias'), ('own_zero_rmse', 'zero_rmse'), ('own_corr', 'forecast_actual_correlation')]:
    print(f'max |{a_} - {b_}| = {(cmp[a_] - cmp[b_]).abs().max():.3e}')
print('n identical:', bool((cmp.n == cmp.n_theirs).all()), ' rows compared:', len(cmp))
piv = own.pivot_table(index=['sample', 'H'], columns='model', values='own_rmse')[models].round(3)
piv['zero_change'] = own[own.model.eq(pc.FAST)].set_index(['sample', 'H']).own_zero_rmse.round(3)
print('\nOwn food-block RMSE:'); print(piv.to_string())
print('\nOwn food-block bias:'); print(own.pivot_table(index=['sample', 'H'], columns='model', values='own_bias')[models].round(3).to_string())
print('\nCandidate RMSE relative to baseline, pct:'); print((100 * (piv[pc.CANDIDATES].div(piv[pc.FAST], axis=0) - 1)).round(2).to_string())
own.to_csv(pc.HERE / 'out_D_food_block_own.csv', index=False); blk.to_csv(pc.HERE / 'out_D_food_block_pairs.csv', index=False)

# ------------------------------------------------------------------ (ii) headline
print('\n' + '=' * 30, '(ii) headline annual rate on the fixed primary support')
prim = pd.read_csv(pc.EVAL / 'primary_rows.csv', low_memory=False, float_precision='round_trip')
support = pd.read_csv(pc.ROOT / 'output/research_r17/attribution/primary_support.csv')
keys = prim[prim.model.eq(pc.FAST)][['origin', 'h']]
print('primary keys per model:', prim.groupby('model').size().unique(), ' support file rows:', len(support), ' identical key set:', set(map(tuple, keys.to_numpy())) == set(map(tuple, support.to_numpy())))
print('non-finite yy_exante / yy_actual in primary rows:', int((~np.isfinite(prim.yy_exante)).sum()), int((~np.isfinite(prim.yy_actual)).sum()))

# independent compounding from the native monthly path and the headline history
head = pd.read_csv(pc.HEADLINE); head.index = pd.PeriodIndex(head.period, freq='M'); head = head.headline_mm
worst_f = worst_a = 0.
for (model, origin), g in native[native.model.isin(models)].groupby(['model', 'origin']):
    t = pd.Period(origin, 'M'); path = g.set_index('h').mm_forecast.to_dict()
    mine = {}
    for h in range(13):
        window = pd.period_range(t + h - 11, t + h, freq='M')
        vals = np.array([head.get(m, np.nan) if m < t else path[m.ordinal - t.ordinal] for m in window], float)
        mine[h] = 100 * np.expm1(np.log1p(vals / 100).sum())
    sub = prim[prim.model.eq(model) & prim.origin.eq(origin)]
    for r in sub.itertuples():
        worst_f = max(worst_f, abs(mine[r.h] - r.yy_exante))
        truth = head.reindex(pd.period_range(t + r.h - 11, t + r.h, freq='M')).to_numpy(float)
        worst_a = max(worst_a, abs(100 * np.expm1(np.log1p(truth / 100).sum()) - r.yy_actual))
print('independent compounding: max |own yy_exante - primary_rows| = %.3e ; max |own yy_actual - primary_rows| = %.3e' % (worst_f, worst_a))

prim['e'] = prim.yy_exante - prim.yy_actual; rows = []
for (model, h), g in prim[prim.h.isin([3, 6, 9, 12])].groupby(['model', 'h']):
    for sample in pc.ERAS:
        z = g[pc.era_mask(g.origin, sample)]
        rows.append(dict(model=model, h=h, sample=sample, n=len(z), own_rmse=np.sqrt((z.e ** 2).mean()), own_bias=z.e.mean(), own_mae=z.e.abs().mean()))
hown = pd.DataFrame(rows)
theirs = pd.read_csv(pc.EVAL / 'same_support_scoreboard.csv'); theirs = theirs[theirs.metric.eq('headline_yy')]
cmp = hown.merge(theirs, on=['model', 'h', 'sample'], suffixes=('', '_theirs'))
print('rows compared', len(cmp), ' max |rmse diff| %.3e  max |bias diff| %.3e  max |mae diff| %.3e  n identical %s' % ((cmp.own_rmse - cmp.rmse).abs().max(), (cmp.own_bias - cmp.bias).abs().max(), (cmp.own_mae - cmp.mae).abs().max(), bool((cmp.n == cmp.n_theirs).all())))
order = [pc.FAST, 'STABLE_LOCAL_CORE_R14B', 'DAMPED_P95_Q001_R16', *pc.CANDIDATES]
print('\nOwn headline RMSE:'); print(hown.pivot_table(index=['sample', 'h'], columns='model', values='own_rmse')[order].round(4).to_string())
print('\nn:'); print(hown[hown.model.eq(pc.FAST)].pivot_table(index='sample', columns='h', values='n').to_string())
hown.to_csv(pc.HERE / 'out_D_headline_own.csv', index=False)

# ------------------------------------------------------------------ (iii) leave one origin year out
print('\n' + '=' * 30, '(iii) leave-one-origin-year-out, h12 RMSE delta against FAST')
h12 = prim[prim.h.eq(12)].pivot(index='origin', columns='model', values='e'); years = sorted(set(h12.index.str[:4])); rows = []
for year in years:
    z = h12[~h12.index.str.startswith(year)]
    rows.append(dict(omitted_year=year, n=len(z), **{m: np.sqrt((z[m] ** 2).mean()) - np.sqrt((z[pc.FAST] ** 2).mean()) for m in pc.CANDIDATES}))
loo = pd.DataFrame(rows); print(loo.round(4).to_string(index=False))
theirs = pd.read_csv(pc.EVAL / 'leave_one_origin_year_out.csv'); theirs = theirs[theirs.h.eq(12)].pivot(index='omitted_year', columns='model', values='rmse_delta')
print('max |own - stored| = %.3e' % np.abs(loo.set_index('omitted_year')[pc.CANDIDATES].to_numpy() - theirs[pc.CANDIDATES].to_numpy()).max())
# harsher: drop a whole era, or keep one era only
for label, keep in [('drop 2019-21', h12.index > '2021-12'), ('drop 2022-23', (h12.index <= '2021-12') | (h12.index >= '2024-01')), ('drop 2024+', h12.index <= '2023-12'), ('drop 2021+2022 origins', ~(h12.index.str.startswith('2021') | h12.index.str.startswith('2022')))]:
    z = h12[keep]
    print(f'  {label:<24} n={len(z):>2}  ' + '  '.join(f'{m[5:-4]} {np.sqrt((z[m] ** 2).mean()) - np.sqrt((z[pc.FAST] ** 2).mean()):+.4f}' for m in pc.CANDIDATES))

# ------------------------------------------------------------------ (iv) bootstrap
print('\n' + '=' * 30, '(iv) own bootstraps of the mean h12 squared-loss difference against FAST (full sample)')


def circular(d, block, draws, rng):
    n = len(d); k = int(np.ceil(n / block)); starts = rng.integers(0, n, size=(draws, k))
    idx = ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    return d[idx].mean(axis=1)


def moving(d, block, draws, rng):
    n = len(d); k = int(np.ceil(n / block)); starts = rng.integers(0, n - block + 1, size=(draws, k))
    idx = (starts[:, :, None] + np.arange(block)).reshape(draws, -1)[:, :n]
    return d[idx].mean(axis=1)


def stationary(d, mean_block, draws, rng):
    n = len(d); p = 1 / mean_block; out = np.empty(draws)
    for b in range(draws):
        idx = np.empty(n, int); idx[0] = rng.integers(n); jump = rng.random(n) < p; fresh = rng.integers(0, n, size=n)
        for i in range(1, n):
            idx[i] = fresh[i] if jump[i] else (idx[i - 1] + 1) % n
        out[b] = d[idx].mean()
    return out


def newey_west_t(d, lag):
    n = len(d); u = d - d.mean(); s = (u @ u) / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (u[k:] @ u[:-k]) / n
    return d.mean() / np.sqrt(s / n) if s > 0 else np.nan


rows = []
sq = h12 ** 2; origins12 = h12.index
assert np.all(np.diff(pd.PeriodIndex(origins12, freq='M').asi8) == 1), 'origins must be consecutive'
for m in pc.CANDIDATES:
    d = (sq[m] - sq[pc.FAST]).to_numpy(float); rng = np.random.default_rng(SEED)
    for method, fn, params in [('circular', circular, (6, 12, 18, 24)), ('moving', moving, (12,)), ('stationary', stationary, (6, 12, 18))]:
        for b in params:
            draws = fn(d, b, 20000 if method != 'stationary' else 5000, rng)
            rows.append(dict(model=m, method=method, block=b, n=len(d), mean=d.mean(), ci_low=np.quantile(draws, .025), ci_high=np.quantile(draws, .975),
                             ci90_high=np.quantile(draws, .95), p_improve=(draws < 0).mean(), excludes_zero=bool(np.quantile(draws, .975) < 0)))
    for lag in (11, 17, 23):
        rows.append(dict(model=m, method='DM Newey-West t', block=lag, n=len(d), mean=d.mean(), ci_low=np.nan, ci_high=np.nan, ci90_high=np.nan, p_improve=np.nan, excludes_zero=np.nan, t=newey_west_t(d, lag)))
boot = pd.DataFrame(rows); boot.to_csv(pc.HERE / 'out_D_bootstrap_own.csv', index=False)
print(boot.round(4).to_string(index=False))
stored = pd.read_csv(pc.EVAL / 'primary_support_circular_bootstrap.csv')
print('\nStored interval (seed 1509, 2000 draws, block 12):'); print(stored[stored.metric.eq('headline_yy') & stored.h.eq(12) & stored['sample'].eq('full') & stored.model.isin(pc.CANDIDATES)][['model', 'n', 'block', 'mean_loss_difference', 'ci_low', 'ci_high']].round(4).to_string(index=False))

# seed stability of the declared scheme and the number of independent blocks
d = (sq['FOOD_NORM_SHIFT_R24'] - sq[pc.FAST]).to_numpy(float)
highs = [np.quantile(circular(d, 12, 2000, np.random.default_rng(s)), .975) for s in range(200)]
print('\nNORM_SHIFT, declared scheme across 200 seeds: upper 97.5%% bound min %.3f median %.3f max %.3f; share of seeds with bound < 0: %.2f' % (min(highs), np.median(highs), max(highs), np.mean(np.array(highs) < 0)))
print('non-overlapping 12-month blocks of the 75 origins (block means of the loss difference):')
for i in range(0, len(d), 12):
    print('   %s..%s  n=%2d  mean d = %+8.3f' % (origins12[i], origins12[min(i + 11, len(d) - 1)], len(d[i:i + 12]), d[i:i + 12].mean()))
blocks = np.array([d[i:i + 12].mean() for i in range(0, len(d) - 11, 12)])
print('   t-statistic on the %d complete non-overlapping block means: %.2f (df=%d)' % (len(blocks), blocks.mean() / (blocks.std(ddof=1) / np.sqrt(len(blocks))), len(blocks) - 1))
ac = [np.corrcoef(d[k:], d[:-k])[0, 1] for k in (1, 3, 6, 12)]
print('   autocorrelation of the loss difference at lags 1/3/6/12: ' + ', '.join(f'{x:.2f}' for x in ac))
