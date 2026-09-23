"""B1. Recompute mu_window, mu_robust and mu_long at EVERY origin with the reviewer's own code, straight from the
CSV inputs and using only observations stamped at or before the origin's clock; compare with drift_audit.csv.

No R24/R14B model code is imported here.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_common as pc

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 50); pd.set_option('display.max_rows', 500)

levels = pc.load_levels(); available = pc.load_available()
long_rates, long_stamps = pc.own_long_rates(levels, available)
audit = pd.read_csv(pc.R24 / 'drift_audit.csv').set_index('origin')
clk = pc.clocks()

print('Spliced history', long_rates.index.min(), '..', long_rates.index.max(), 'n', len(long_rates))
print('Stamps monotone non-decreasing:', bool(long_stamps.is_monotonic_increasing))
rows = []
for origin in sorted(clk):
    assert pd.Timestamp(audit.loc[origin, 'as_of']) == clk[origin]
    d = pc.own_drifts(levels, available, long_rates, long_stamps, origin, clk[origin])
    # latest food month stamped at or before the clock, and the first month after it
    usable = long_stamps[long_stamps <= clk[origin]].index.max()
    rows.append(dict(origin=origin, clock=str(clk[origin]), latest_food_month_published=str(usable),
                     own_mu_window=d['mu_window'], own_mu_robust=d['mu_robust'], own_mu_long=d['mu_long'],
                     audit_mu_window=audit.loc[origin, 'mu_window'], audit_mu_robust=audit.loc[origin, 'mu_robust'], audit_mu_long=audit.loc[origin, 'mu_long'],
                     own_n_train=d['n_train'], audit_n_train=int(audit.loc[origin, 'n_train']), own_train_start=d['train_start'], own_train_end=d['train_end'],
                     audit_train_start=audit.loc[origin, 'train_start'], audit_train_end=audit.loc[origin, 'train_end'],
                     n_windows_robust=d['n_windows_robust'], n_windows_long=d['n_windows_long'], plain_window_mean=d['plain_window_mean']))
out = pd.DataFrame(rows)
for k in ('mu_window', 'mu_robust', 'mu_long'):
    out['diff_' + k] = out['own_' + k] - out['audit_' + k]
out.to_csv(pc.HERE / 'out_B1_own_drifts.csv', index=False)

print('\nOrigins:', len(out))
print('max |own - audit|   mu_window %.3e   mu_robust %.3e   mu_long %.3e' % tuple(out[['diff_mu_window', 'diff_mu_robust', 'diff_mu_long']].abs().max()))
print('training window identical (n, start, end):', bool((out.own_n_train == out.audit_n_train).all() and (out.own_train_start == out.audit_train_start).all() and (out.own_train_end == out.audit_train_end).all()))
lag = pd.PeriodIndex(out.origin, freq='M').asi8 - pd.PeriodIndex(out.latest_food_month_published, freq='M').asi8
print('origin minus latest published food month (months):', dict(pd.Series(lag).value_counts()))
print('min windows used  robust %d  long %d  (rule: >= 12)' % (out.n_windows_robust.min(), out.n_windows_long.min()))
show = ['2019-02', '2020-06', '2021-12', '2022-06', '2023-03', '2024-06', '2025-07', '2026-07']
cols = ['origin', 'clock', 'latest_food_month_published', 'own_mu_window', 'audit_mu_window', 'own_mu_robust', 'audit_mu_robust', 'own_mu_long', 'audit_mu_long', 'own_n_train', 'n_windows_robust', 'n_windows_long']
print(out[out.origin.isin(show)][cols].to_string(index=False))
print('\nmean of calendar means (spec mu_window) versus plain window mean, annualised pct: max abs gap %.3f' % (12 * (out.own_mu_window - out.plain_window_mean)).abs().max())
