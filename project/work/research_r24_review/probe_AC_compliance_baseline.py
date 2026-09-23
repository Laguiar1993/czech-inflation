"""A + C. Specification compliance of the stored paths, block replacement, and baseline reproduction.

Own arithmetic on the stored CSVs only; no model code is imported.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_common as pc

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60)
r24 = pd.read_csv(pc.R24 / 'native_forecasts.csv', low_memory=False, float_precision='round_trip')
r21 = pd.read_csv(pc.NATIVE_R21, low_memory=False, float_precision='round_trip')
rates = pd.read_csv(pc.R24 / 'food_log_rates.csv', float_precision='round_trip')
audit = pd.read_csv(pc.R24 / 'drift_audit.csv', float_precision='round_trip').set_index('origin')
origins = sorted(r24.origin.unique())
print('origins', len(origins), origins[0], origins[-1])

# ---- C: the run's reproduction of the frozen food path against STATE_FAST_R15 in the R21 anchor file
base = rates[rates.model.eq('FOOD_STABLE_PIPELINE_R14B')].pivot(index='origin', columns='h', values='log_rate')
fast21 = r21[r21.model.eq(pc.FAST) & r21.h.between(1, 12)].pivot(index='origin', columns='h', values='value_food')
assert list(base.index) == origins and list(fast21.index) == origins and base.shape == (90, 12)
gap = (100 * np.expm1(base / 100) - fast21).abs()
print('\n[C] baseline reproduction: max |100*expm1(log rate) - value_food(STATE_FAST_R15, R21)| over 90 origins x 12 horizons = %.3e' % gap.to_numpy().max())
print('[C] worst origin:', gap.max(axis=1).idxmax(), ' non-finite cells:', int((~np.isfinite(gap.to_numpy())).sum()))

# controls in the R24 file are the R21 rows, untouched (all shared columns, NaN-aware)
shared = [col for col in r21.columns if col in r24.columns]
for m in ['STATE_FAST_R15', 'STABLE_LOCAL_CORE_R14B', 'DAMPED_P95_Q001_R16']:
    a = r24[r24.model.eq(m)].sort_values(['origin', 'h']).reset_index(drop=True)[shared]
    b = r21[r21.model.eq(m)].sort_values(['origin', 'h']).reset_index(drop=True)[shared]
    diff = [col for col in shared if not a[col].equals(b[col])]
    print(f'[C] control {m}: rows {len(a)} vs {len(b)}; columns that differ from the R21 file: {diff}')
print('[C] columns only in R24 file:', [col for col in r24.columns if col not in r21.columns], ' only in R21 file:', [col for col in r21.columns if col not in r24.columns])

# ---- A1: shift formulas, in log rates, from the stored audit and stored log rates
worst = {}
for name, const in [('FOOD_ZERO_DRIFT_R24', lambda a: -a.mu_window), ('FOOD_ROBUST_WINDOW_R24', lambda a: a.mu_robust - a.mu_window), ('FOOD_NORM_SHIFT_R24', lambda a: a.mu_long - a.mu_window)]:
    own = rates[rates.model.eq(name)].pivot(index='origin', columns='h', values='log_rate')
    expected = base.add(const(audit).reindex(base.index), axis=0)
    worst[name] = float((own - expected).abs().to_numpy().max())
print('\n[A1] max |stored candidate log rate - (baseline log rate + declared constant)|:', worst)
refit = rates[rates.model.eq('FOOD_NORM_REFIT_R24')].pivot(index='origin', columns='h', values='log_rate')
shift = rates[rates.model.eq('FOOD_NORM_SHIFT_R24')].pivot(index='origin', columns='h', values='log_rate')
d = refit - shift
print('[A1] refit minus shift log rates: mean |d| by horizon (log points a month):', d.abs().mean().round(4).to_dict())
print('[A1] refit minus shift, cumulative over h1..12: mean %.3f, min %.3f, max %.3f log points' % (d.sum(axis=1).mean(), d.sum(axis=1).min(), d.sum(axis=1).max()))

# ---- A2: only the food block of h1..12 changes
fast = r24[r24.model.eq(pc.FAST)].sort_values(['origin', 'h']).reset_index(drop=True)
allowed_change = {'model', 'value_food', 'contribution_food', 'mm_forecast', 'food_model_status', 'food_fallback_used', 'yy_exante', 'yy_conditional', 'cumulative_log_forecast'}
for name in pc.CANDIDATES:
    cand = r24[r24.model.eq(name)].sort_values(['origin', 'h']).reset_index(drop=True)
    assert (cand.origin == fast.origin).all() and (cand.h == fast.h).all()
    changed = [col for col in r24.columns if not cand[col].equals(fast[col])]
    unexpected = [col for col in changed if col not in allowed_change]
    h0 = cand.h.eq(0)
    h0_changed = [col for col in r24.columns if col not in ('model', 'food_model_status', 'food_fallback_used') and not cand.loc[h0, col].equals(fast.loc[h0, col])]
    fut = cand.h.gt(0)
    own_rate = rates[rates.model.eq(name)].sort_values(['origin', 'h']).log_rate.to_numpy()
    v_gap = np.abs(cand.loc[fut, 'value_food'].to_numpy() - 100 * np.expm1(own_rate / 100)).max()
    mm_gap = np.abs((cand.loc[fut, 'mm_forecast'] - fast.loc[fut, 'mm_forecast']) - fast.loc[fut, 'weight_food'] * (cand.loc[fut, 'value_food'] - fast.loc[fut, 'value_food'])).max()
    c_gap = np.abs(cand.loc[fut, 'contribution_food'] - cand.loc[fut, 'weight_food'] * cand.loc[fut, 'value_food']).max()
    parts = ['contribution_core', 'contribution_food', 'contribution_administered', 'contribution_alcohol_tobacco', 'contribution_fuel', 'contribution_wedge']
    sum_gap = np.abs(cand.loc[fut, parts].sum(axis=1) - cand.loc[fut, 'mm_forecast']).max()
    print(f'\n[A2] {name}: changed columns {changed}')
    print(f'     unexpected changed columns: {unexpected}; h0 columns changed: {h0_changed}')
    print(f'     max |value_food - 100*expm1(log rate)| = {v_gap:.2e}; max |d mm_forecast - weight_food*d value_food| = {mm_gap:.2e}')
    print(f'     max |contribution_food - weight_food*value_food| = {c_gap:.2e}; max |sum of six contributions - mm_forecast| = {sum_gap:.2e}')
    print(f'     status values: {sorted(cand.food_model_status.astype(str).unique())}; fallback used anywhere: {bool(cand.food_fallback_used.astype(str).str.lower().eq("true").any())}')
    print(f'     stale derived columns in native rows h>0: yy_exante all NaN = {bool(cand.loc[fut, "yy_exante"].isna().all())}, cumulative_log_forecast all NaN = {bool(cand.loc[fut, "cumulative_log_forecast"].isna().all())}')

# ---- A3: the refit's recorded window equals the baseline's, and how often its stability contraction binds
fits = [json.loads(line) for line in (pc.R24 / 'fits.jsonl').read_text(encoding='utf-8').splitlines()]
print('\n[A3] refit contraction < 1 at', sum(f['refit']['contraction'] < 1 for f in fits), 'of', len(fits), 'origins; max spectral radius %.4f' % max(f['refit']['spectral_radius'] for f in fits))
print('[A3] n_train range', audit.n_train.min(), audit.n_train.max(), '; first window', audit.train_start.iloc[0], audit.train_end.iloc[0], '; last window', audit.train_start.iloc[-1], audit.train_end.iloc[-1])
