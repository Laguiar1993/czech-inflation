"""F2. POST-HOC SENSITIVITY - NOT FOR SELECTION.

How discriminating is the promotion rule? Replace mu_long by a plain constant c (log points a year) in the shift
formula  s_c + c/12 + d_h  and evaluate the four declared conditions for every c on a grid. Also shows what was
already implied, before any R24 fit, by the numbers printed in the specification itself (the 2024+ bias of the
baseline and its window drift): for a constant shift the 2024+ RMSE falls if and only if |bias + shift| < |bias|.

Uses only frozen outputs (food_log_rates.csv, drift_audit.csv, native_forecasts.csv) and realised data.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_common as pc

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 200)
native = pd.read_csv(pc.R24 / 'native_forecasts.csv', low_memory=False, float_precision='round_trip')
fast = {o: g.set_index('h') for o, g in native[native.model.eq(pc.FAST)].groupby('origin')}
rates = pd.read_csv(pc.R24 / 'food_log_rates.csv', float_precision='round_trip')
base = rates[rates.model.eq('FOOD_STABLE_PIPELINE_R14B')].pivot(index='origin', columns='h', values='log_rate')
audit = pd.read_csv(pc.R24 / 'drift_audit.csv', float_precision='round_trip').set_index('origin')
actual = pd.read_csv(pc.ACTUAL, float_precision='round_trip'); actual.index = pd.PeriodIndex(actual.period, freq='M')
prim = pd.read_csv(pc.EVAL / 'primary_rows.csv', low_memory=False, float_precision='round_trip')
truth_yy = prim[prim.h.eq(12)].drop_duplicates('origin').set_index('origin').yy_actual
origins = list(base.index)
truth = {o: 100 * np.log1p(actual.food.reindex(pd.period_range(pd.Period(o, 'M') + 1, pd.Period(o, 'M') + 12, freq='M')).to_numpy(float) / 100) for o in origins}


def evaluate(drift):
    """drift: Series origin -> monthly log points. Returns the rule's ingredients."""
    rec = []
    for o in origins:
        logs = base.loc[o].to_numpy() - audit.loc[o, 'mu_window'] + drift[o]; g = fast[o]
        value = 100 * np.expm1(logs / 100); row = dict(origin=o)
        for H in (3, 6, 12):
            row[f'e{H}'] = logs[:H].sum() - truth[o][:H].sum()
        if o in truth_yy.index:
            mm = [g.loc[h, 'mm_forecast'] + g.loc[h, 'weight_food'] * (value[h - 1] - g.loc[h, 'value_food']) for h in range(1, 13)]
            row['yy'] = 100 * np.expm1(np.log1p(np.array(mm) / 100).sum()) - truth_yy[o]
        rec.append(row)
    z = pd.DataFrame(rec).set_index('origin'); late = z.index >= '2024-01'
    rmse = lambda x: float(np.sqrt((x.dropna() ** 2).mean()))
    return dict(f3=rmse(z.e3), f6=rmse(z.e6), f12=rmse(z.e12), f12_2024=rmse(z.e12[late]), bias12_2024=float(z.e12[late].dropna().mean()), yy12=rmse(z.yy), yy12_2024=rmse(z.yy[late]))


ref = evaluate(audit.mu_window); declared = evaluate(audit.mu_long)
print('machinery check against the reviewer\'s D scores: baseline', {k: round(v, 3) for k, v in ref.items()})
print('                                              mu_long ', {k: round(v, 3) for k, v in declared.items()})


def rule(s):
    c1 = s['f12'] <= ref['f12'] and s['f12_2024'] <= ref['f12_2024']; c2 = s['f3'] <= 1.02 * ref['f3'] and s['f6'] <= 1.02 * ref['f6']
    c3 = s['yy12'] <= ref['yy12'] and s['yy12_2024'] <= ref['yy12_2024']; c4 = abs(s['bias12_2024']) < abs(ref['bias12_2024'])
    return c1, c2, c3, c4


rows = []
for c in np.round(np.arange(0, 8.01, .25), 2):
    s = evaluate(pd.Series(c / 12, index=origins)); c1, c2, c3, c4 = rule(s)
    rows.append(dict(constant_annual=c, **{k: round(v, 3) for k, v in s.items()}, c1=c1, c2=c2, c3=c3, c4=c4, passes_all=c1 and c2 and c3 and c4))
grid = pd.DataFrame(rows); grid.to_csv(pc.HERE / 'out_F2_rule_vs_constant.csv', index=False)
print('\n' + grid.to_string(index=False))
ok = grid[grid.passes_all].constant_annual
print('\nConstants (log points a year) for which ALL FOUR declared conditions hold: %.2f .. %.2f  (mu_long ranged %.2f .. %.2f over the 90 origins)' % (ok.min(), ok.max(), 12 * audit.mu_long.min(), 12 * audit.mu_long.max()))

print('\nWhat the specification\'s own table implied before any fit (2024+ origins, h12):')
late = audit[audit.index.isin([o for o in origins if o >= '2024-01' and np.isfinite(truth[o]).all()])]
b = ref['bias12_2024']; w = 12 * late.mu_window.mean()
print('   baseline bias %+.2f log points over twelve months; mean window drift at those 19 origins %.2f a year' % (b, w))
print('   a constant shift changes the bias one for one and leaves the error variance alone, so conditions 1 (2024+ leg) and 4 are one condition:')
print('   they hold for any drift between %.2f and %.2f a year; the bias-zeroing drift is %.2f; mu_long at those origins averaged %.2f' % (w - 2 * b, w, w - b, 12 * late.mu_long.mean()))
sd = np.sqrt(ref['f12_2024'] ** 2 - b ** 2)
print('   predicted 2024+ h12 food RMSE of NORM_SHIFT from the spec table alone: sqrt(%.2f^2 + %.2f^2) = %.2f ; realised %.2f' % (sd, b + 12 * late.mu_long.mean() - w, np.hypot(sd, b + 12 * late.mu_long.mean() - w), declared['f12_2024']))
