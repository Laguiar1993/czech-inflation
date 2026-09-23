"""B3. Could the 2026 download of the long CZSO file leak, and do rounding / representation / start date matter?

1. splice audit: which months come from which source; overlap identity CZSO vs model series 2015-02..2025-12
2. one-decimal rounding of the base index: Monte Carlo (index + U(-0.05, 0.05)) on mu_long at five origins
3. representation: the same median from CZSO's own published year-on-year index (casz_kod 'C'), which is
   rounded independently of the base index
4. the wording 'from January 1996': first twelve-month change ENDING 1996-01 (uses 1995-02.. rates) versus
   the code's reading (first monthly rate 1996-01, so first change ends 1996-12)
5. post-hoc sensitivity of the 'norm' to the start year (NOT for selection)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_common as pc

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60)
levels = pc.load_levels(); available = pc.load_available(); clk = pc.clocks()
rates, stamps = pc.own_long_rates(levels, available)
idx = pc.load_long_index('Z'); yy = pc.load_long_index('C')
ORIGINS = ['2019-02', '2021-12', '2022-06', '2024-06', '2026-07']

print('1. splice')
print('   CZSO base index: %s..%s, n=%d, min %.1f max %.1f, decimals: %s' % (idx.index.min(), idx.index.max(), len(idx), idx.min(), idx.max(), sorted({len(str(v).split(".")[1]) for v in idx.to_numpy()})))
old = (100 * np.log(idx)).diff().dropna(); own = levels.food.diff().dropna()
both = old.index.intersection(own.index)
print('   overlap %s..%s (n=%d): max |CZSO rate - model rate| = %.2e log points' % (both.min(), both.max(), len(both), (old[both] - own[both]).abs().max()))
print('   months taken from CZSO: %s..%s ; from the model series: %s..%s' % (rates.index.min(), '2015-01', '2015-02', rates.index.max()))
print('   latest CZSO-sourced month 2015-01 is stamped %s -> before every origin clock (first clock %s)' % (stamps[pd.Period('2015-01', 'M')], min(clk.values())))
print('   model series after the CZSO file ends (2026-01..): %d months, all from pipeline_log_levels.csv with recorded stamps' % (rates.index > idx.index.max()).sum())
lead = pd.Series({m: (stamps[m] - (m + 1).to_timestamp().tz_localize('UTC')).days for m in rates.index if m >= pd.Period('2015-02', 'M')})
print('   recorded food stamps: day-of-following-month range %d..%d' % (lead.min() + 1, lead.max() + 1))

print('\n2. rounding Monte Carlo (2000 draws, every index level perturbed by U(-0.05,0.05), model-series months included since they are the same rounded index)')
rng = np.random.default_rng(5)
full_idx = pd.concat([idx, pd.Series(100 * np.exp((levels.food - levels.food[pd.Period('2025-12', 'M')]) / 100) * idx[pd.Period('2025-12', 'M')] / 100, index=levels.index)[lambda s: s.index > idx.index.max()]])
for origin in ORIGINS:
    clock = clk[origin]; months = [m for m in rates.index if m >= pd.Period('1996-01', 'M') and stamps[m] <= clock]
    last = max(months); span = pd.period_range('1995-12', last, freq='M'); base = full_idx[span].to_numpy()
    point = np.median(100 * np.log(base[12:] / base[:-12])) / 12
    draws = np.empty(2000)
    for b in range(2000):
        z = base + rng.uniform(-.05, .05, len(base)); draws[b] = np.median(100 * np.log(z[12:] / z[:-12])) / 12
    own_value, n = pc.own_median_drift(rates, stamps, clock)
    print(f'   {origin}: mu_long {12 * own_value:.4f} a year (level-ratio recomputation {12 * point:.4f}, windows {n}); rounding MC 95% [{12 * np.quantile(draws, .025):.4f}, {12 * np.quantile(draws, .975):.4f}], sd {12 * draws.std():.4f}')

print('\n3. same median from the published year-on-year index (casz C), available through 2025-12')
for origin in ORIGINS:
    clock = clk[origin]; last = max(m for m in rates.index if stamps[m] <= clock)
    usable = yy[(yy.index >= pd.Period('1996-12', 'M')) & (yy.index <= min(last, yy.index.max()))]
    alt = np.median(100 * np.log(usable / 100)) / 12; own_value, _ = pc.own_median_drift(rates, stamps, clock)
    print(f'   {origin}: from y/y index {12 * alt:.4f} (n={len(usable)}, through {usable.index.max()}) vs mu_long {12 * own_value:.4f}; gap {12 * (alt - own_value):+.4f} a year')

print('\n4. wording: first change ending 1996-01 (start 1995-02) versus the code (start 1996-01)')
for origin in ORIGINS:
    a, na = pc.own_median_drift(rates, stamps, clk[origin], start='1995-02'); b, nb = pc.own_median_drift(rates, stamps, clk[origin], start='1996-01')
    print(f'   {origin}: start 1995-02 -> {12 * a:.4f} (n={na}); start 1996-01 -> {12 * b:.4f} (n={nb}); gap {12 * (a - b):+.4f} a year')

print('\n5. POST-HOC (not for selection): the long-run median by start year, log points a year')
rows = []
for origin in ORIGINS:
    rows.append(dict(origin=origin, **{s: 12 * pc.own_median_drift(rates, stamps, clk[origin], start=s + '-01')[0] for s in ['1996', '1998', '2000', '2002', '2005', '2010']},
                     mean_from_1996=12 * rates[[m for m in rates.index if m >= pd.Period('1996-01', 'M') and stamps[m] <= clk[origin]]].mean()))
print(pd.DataFrame(rows).round(3).to_string(index=False))
