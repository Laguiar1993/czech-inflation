"""H. Remaining ways the conclusion could be wrong.

1. horizon alignment: forecast_food_rates index k is month t+k (k=0 is the origin month). Checked on stored output:
   the calendar month of the baseline's long-horizon seasonal must match the month of target t+h.
2. untested fallback paths of candidates_at (insufficient history; missing drift) - do they behave as the spec says?
3. era masks of tools/path_diagnostics/standard.py against the reviewer's own, on every origin string
4. timezone handling: clocks given as UTC strings, Prague-aware stamps or naive Prague wall time give the same drifts
5. non-overlapping block t-statistics of the h12 loss difference under all twelve block alignments
6. food-block supports: which origins enter food_block_scores.csv, and whether any NaN was dropped silently
7. bias: the candidate's full-sample bias against the baseline's (the promotion rule only looks at 2024+)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import probe_common as pc
from models.food_path_r14 import load_inputs
from models.food_drift_r24 import long_food_rates, candidates_at, median_annual_drift, LONG_HISTORY
from tools.path_diagnostics import standard

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60)
levels, available, _ = load_inputs(); long_rates, long_published = long_food_rates(levels, available, ROOT / LONG_HISTORY); clk = pc.clocks()

print('1. horizon / calendar alignment on stored output')
rates = pd.read_csv(pc.R24 / 'food_log_rates.csv', float_precision='round_trip')
base = rates[rates.model.eq('FOOD_STABLE_PIPELINE_R14B')].pivot(index='origin', columns='h', values='log_rate')
# at long horizons the deviation has decayed, so base[h] - base[h'] ~ s(month(t+h)) - s(month(t+h')). Compare the stored h12 rate of origin o with
# the stored h11 rate of origin o+1 and h10 of o+2: all three target the SAME calendar month t+12, so they should be close if the index is month t+h.
o = list(base.index); same_target = []; shifted = []
for i in range(len(o) - 2):
    same_target.append(abs(base.loc[o[i], 12] - base.loc[o[i + 1], 11])); shifted.append(abs(base.loc[o[i], 12] - base.loc[o[i + 1], 12]))
print('   mean |rate(o,h12) - rate(o+1,h11)| (same target month)  = %.4f' % np.mean(same_target))
print('   mean |rate(o,h12) - rate(o+1,h12)| (adjacent target months) = %.4f   -> index k is month t+k only if the first is much smaller' % np.mean(shifted))
fast = pd.read_csv(pc.R24 / 'native_forecasts.csv', low_memory=False); fast = fast[fast.model.eq(pc.FAST)]
ok = all(str(pd.Period(r.origin, 'M') + int(r.h)) == str(r.target) for r in fast.itertuples())
print('   native rows: target == origin + h for every FAST row:', ok)

print('\n2. fallback paths')
early = candidates_at(levels, available, long_rates, long_published, '2018-06', pd.Timestamp('2018-07-09T23:59:00+02:00'))
print('   origin 2018-06 (35 complete months at most): status =', early['status'], '| paths empty:', early['paths'] == {}, '| drifts empty:', early['drifts'] == {})
blank = long_rates.copy(); blank[:] = np.nan
missing = candidates_at(levels, available, blank, long_published, '2024-06', clk['2024-06'])
print('   all long rates missing at 2024-06: status =', missing['status'], '| paths empty:', missing['paths'] == {}, '(run.py then copies the FAST frame and sets food_fallback_used=True)')

print('\n3. era masks')
origins = np.array(sorted(clk)); mine = {name: pc.era_mask(origins, name) for name in pc.ERAS}
theirs = {name: np.asarray(rule(origins)) for name, rule in standard.ERAS.items()}
print('   identical on all 90 origins:', all((mine[k] == theirs[k]).all() for k in pc.ERAS), '| sizes:', {k: int(v.sum()) for k, v in theirs.items()},
      '| eras partition the sample:', bool(((theirs['origins_2019_2021'].astype(int) + theirs['origins_2022_2023'] + theirs['origins_2024plus']) == 1).all()))

print('\n4. clock representations at 2024-06 (UTC string, Prague-aware, naive Prague wall time)')
utc = pd.Timestamp('2024-07-09T21:59:00+00:00')
for label, c in [('UTC aware', utc), ('Prague aware', utc.tz_convert('Europe/Prague')), ('naive Prague wall time', utc.tz_convert('Europe/Prague').tz_localize(None))]:
    print(f'   {label:<24} mu_long = {median_annual_drift(long_rates, long_published, c)!r}')
edge = long_published[pd.Period('2024-06', 'M')]
print('   stamp of 2024-06 food:', edge, '| drift with clock exactly at the stamp uses it (<=):',
      median_annual_drift(long_rates, long_published, edge) != median_annual_drift(long_rates, long_published, edge - pd.Timedelta(seconds=1)))

print('\n5. non-overlapping 12-origin block means of d = e_cand^2 - e_FAST^2 at h12, every alignment')
prim = pd.read_csv(pc.EVAL / 'primary_rows.csv', low_memory=False); prim = prim[prim.h.eq(12)].assign(e=lambda z: z.yy_exante - z.yy_actual)
e = prim.pivot(index='origin', columns='model', values='e'); d = (e['FOOD_NORM_SHIFT_R24'] ** 2 - e[pc.FAST] ** 2).to_numpy()
ts = []
for start in range(12):
    blocks = np.array([d[i:i + 12].mean() for i in range(start, len(d) - 11, 12)])
    t = blocks.mean() / (blocks.std(ddof=1) / np.sqrt(len(blocks))); ts.append(t)
    print(f'   offset {start:>2}: {len(blocks)} blocks, all negative: {bool((blocks < 0).all())}, t = {t:.2f}')
print('   t range %.2f .. %.2f ; two-sided 5%% critical value with 4-5 df is 2.57-2.78' % (min(ts), max(ts)))

print('\n6. food-block support')
scores = pd.read_csv(pc.EVAL / 'food_block_scores.csv'); pairs = pd.read_csv(HERE / 'out_D_food_block_pairs.csv')
for H in (3, 6, 12):
    mine_n = pairs[(pairs.H == H) & (pairs.model == pc.FAST)].origin.nunique(); theirs_n = int(scores[(scores.H == H) & (scores['sample'] == 'full') & (scores.model == pc.FAST)].n.iloc[0])
    print(f'   H={H}: reviewer (realised finite) n={mine_n}, evaluator (also needs a seasonal-naive path) n={theirs_n}')

print('\n7. bias, forecast minus actual')
food = pd.read_csv(HERE / 'out_D_food_block_own.csv'); head = pd.read_csv(HERE / 'out_D_headline_own.csv')
f = food[food.H.eq(12) & food.model.isin([pc.FAST, 'FOOD_NORM_SHIFT_R24'])].pivot(index='sample', columns='model', values='own_bias')
y = head[head.h.eq(12) & head.model.isin([pc.FAST, 'FOOD_NORM_SHIFT_R24'])].pivot(index='sample', columns='model', values='own_bias')
print('   food block h12 (log points):'); print(f.round(3).to_string()); print('   headline h12 (pp):'); print(y.round(3).to_string())
