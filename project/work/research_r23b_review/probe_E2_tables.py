"""Probe E2: the delivered block tables and the leave-one-origin-year-out table, recomputed with own code."""
import numpy as np
import pandas as pd

from _common import ROOT, FINAL, EVAL, Report

R = Report('E2 block tables and leave-one-year-out')
rd = dict(float_precision='round_trip', low_memory=False)
native = pd.read_csv(FINAL / 'native_forecasts.csv', **rd)
actual = pd.read_csv(ROOT / 'output/research_r14b/attribution/actual_component_targets.csv', **rd); actual.index = pd.PeriodIndex(actual.iloc[:, 0], freq='M')
W = {'core': 'weight_core', 'food': 'weight_food', 'fuel': 'weight_fuel', 'administered': 'weight_administered', 'alcohol_tobacco': 'weight_alc'}

# ---- block_error_table.csv: RMS and bias of cumulative weighted errors (h0 + h1..H), own loop
BT = pd.read_csv(EVAL / 'block_error_table.csv', **rd); worst = 0.; cells = 0
for model in ['STATE_FAST_R15', 'PRESS_JOINT_R23B']:
    g = native[native.model.eq(model)]; rows = []
    for origin, z in g.groupby('origin'):
        z = z.set_index('h').sort_index(); t = pd.Period(origin, 'M'); cum = {k: 0. for k in [*W, 'wedge', 'h0', 'total']}
        for h in range(13):
            r = z.loc[h]; total = r.mm_forecast - r.mm_actual
            if h == 0:
                cum['h0'] += total
            else:
                parts = {b: r[w] * (r['value_' + b] - actual[b].get(t + h, np.nan)) for b, w in W.items()}
                for b, v in parts.items():
                    cum[b] += v
                cum['wedge'] += total - sum(parts.values())
            cum['total'] += total
            if h in (3, 6, 12):
                rows.append(dict(origin=origin, H=h, **cum))
    mine = pd.DataFrame(rows)
    for H in (3, 6, 12):
        for sample, keep in [('full', mine.origin >= '0'), ('origins_2024plus', mine.origin >= '2024-01')]:
            for part in [*W, 'wedge', 'h0', 'total']:
                v = mine[(mine.H == H) & keep][part].dropna().to_numpy(); t_ = BT[(BT.model == model) & (BT.H == H) & (BT['sample'] == sample) & (BT.block == part)].iloc[0]; cells += 1
                worst = max(worst, abs(np.sqrt(np.mean(v ** 2)) - t_.rms), abs(v.mean() - t_.bias)); assert len(v) == t_.n
R.check(f'block_error_table.csv: {cells} cells (2 models x 3 horizons x 2 samples x 8 parts) equal own cumulation', worst < 1e-12, f'max abs diff={worst:.3e}')
fast12 = BT[(BT.model == 'STATE_FAST_R15') & (BT.H == 12)].pivot(index='block', columns='sample', values='rms').round(3)
print('   FAST, H=12, RMS of cumulative weighted error (pp of headline):'); print(fast12.to_string().replace('\n', '\n   '))

# ---- block_benchmarks.csv: model / zero-change / seasonal-naive on identical origins, own code
import r17_common as c
BB = pd.read_csv(EVAL / 'block_benchmarks.csv', **rd); published = c.publication_dates(actual.index)
clock = {o: pd.Timestamp(v).tz_convert('Europe/Prague').tz_localize(None) for o, v in native[native.h.eq(0)].drop_duplicates('origin').set_index('origin').as_of_utc.items()}
log = lambda v: 100 * np.log1p(np.asarray(v, float) / 100); worst = 0.; cells = 0
for block in ['core', 'food', 'administered']:
    for model in ['STATE_FAST_R15', 'PRESS_ULC_R23B']:
        rec = []
        for origin, z in native[native.model.eq(model) & native.h.gt(0)].groupby('origin'):
            t = pd.Period(origin, 'M'); z = z.set_index('h').sort_index(); known = actual[block][(actual.index < t) & (published <= clock[origin]).to_numpy()].dropna(); naive = []
            for h in range(1, 13):
                same = known[known.index.month == (t + h).month]; naive.append(same.iloc[-3:].mean() if len(same) >= 3 else np.nan)
            truth = log(actual[block].reindex(pd.period_range(t + 1, t + 12, freq='M'))); own = log(z['value_' + block].reindex(range(1, 13))); naive = log(naive)
            for H in (3, 6, 12):
                rec.append(dict(origin=origin, H=H, f=own[:H].sum(), s=naive[:H].sum(), a=truth[:H].sum()))
        rec = pd.DataFrame(rec); rec = rec[np.isfinite(rec[['f', 's', 'a']]).all(axis=1)]
        for H in (3, 6, 12):
            for sample, keep in [('full', rec.origin >= '0'), ('origins_2024plus', rec.origin >= '2024-01')]:
                z = rec[(rec.H == H) & keep]; t_ = BB[(BB.model == model) & (BB.block == block) & (BB.H == H) & (BB['sample'] == sample)].iloc[0]; cells += 1; rm = lambda e: float(np.sqrt(np.mean(np.square(e))))
                worst = max(worst, abs(rm(z.f - z.a) - t_.model_rmse), abs(rm(z.a) - t_.zero_rmse), abs(rm(z.s - z.a) - t_.seasonal_rmse)); assert len(z) == t_.n
R.check(f'block_benchmarks.csv: {cells} cells (3 blocks x 2 models x 3 horizons x 2 samples): model, zero-change and seasonal-naive RMSE equal own code', worst < 1e-12, f'max abs diff={worst:.3e}')

# ---- leave_one_origin_year_out.csv
L = pd.read_csv(EVAL / 'leave_one_origin_year_out.csv', **rd); P = pd.read_csv(EVAL / 'primary_rows.csv', **rd); worst = 0.; cells = 0
for model in L.model.unique():
    for h in (3, 6, 12):
        a = P[(P.model == model) & (P.h == h)].set_index('origin'); f = P[(P.model == 'STATE_FAST_R15') & (P.h == h)].set_index('origin')
        for year in sorted(set(a.index.str[:4])):
            keep = ~a.index.str.startswith(year); e = (a.yy_exante - a.yy_actual)[keep]; b = (f.yy_exante - f.yy_actual)[keep]
            t_ = L[(L.model == model) & (L.h == h) & (L.omitted_year == int(year))].iloc[0]; cells += 1
            worst = max(worst, abs(np.sqrt((e ** 2).mean()) - np.sqrt((b ** 2).mean()) - t_.rmse_delta)); assert len(e) == t_.n
R.check(f'leave_one_origin_year_out.csv: {cells} cells at h3/h6/h12 equal own RMSE deltas against FAST', worst < 1e-12, f'max abs diff={worst:.3e}')
piv = L[L.h.eq(6)].pivot(index='omitted_year', columns='model', values='rmse_delta').round(3); piv.columns = [c_[6:-5] for c_ in piv.columns]
print('   headline h6 RMSE minus FAST, leaving out one origin year:'); print(piv.to_string().replace('\n', '\n   '))
R.done()
