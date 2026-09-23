"""Probe 9: small remaining checks.
  a. ZERO benchmark recomputed (RMS of the realised cumulative change) against evaluation/food_family_scores.csv.
  b. h0 and h7-12 food values and every other block identical between candidate and baseline in native_forecasts.csv.
  c. The specificity condition as declared: what the interval test says when the grid contains the estimator's own constant.
  d. The declared "expectations" of the specification against the outcome.
"""
import json

import numpy as np
import pandas as pd

import probe_common as pc

OUT = pc.HERE / 'probe_09_misc'
OUT.mkdir(exist_ok=True)
native = pc.load_native(); actual = pc.load_actual(); support = pc.load_support()
findings = {}

# a. ZERO
paths = pc.food_log_paths(native, [pc.BASELINE, pc.CANDIDATE]); truth = pc.actual_food_log(actual)
table = pc.cumulative_table(paths, truth, support)
theirs = pd.read_csv(pc.EVAL / 'food_family_scores.csv'); z = theirs[theirs.name == 'ZERO'].set_index(['H', 'sample']).rmse
zero = {}
for H in (3, 6, 12):
    w = table[table.H == H].dropna()
    for s in pc.ERAS:
        g = w[pc.era_mask(w.origin, s)]
        zero[f'h{H}_{s}'] = dict(own=round(pc.rmse(g.actual), 4), theirs=round(float(z.loc[(H, s)]), 4))
findings['zero_benchmark'] = zero
findings['zero_max_abs_diff'] = max(abs(v['own'] - v['theirs']) for v in zero.values())

# b. untouched parts
b = native[native.model == pc.BASELINE].set_index(['origin', 'h']); c = native[native.model == pc.CANDIDATE].set_index(['origin', 'h']).reindex(b.index)
cols = ['value_core', 'value_administered', 'value_alcohol_tobacco', 'value_fuel', 'value_wedge', 'weight_food', 'weight_core', 'h0_exante']
findings['other_blocks_max_abs_diff'] = {col: float((b[col] - c[col]).abs().max()) for col in cols}
h0 = b.index.get_level_values('h') == 0; late = b.index.get_level_values('h') >= 7
findings['food_h0_max_abs_diff'] = float((b.value_food[h0].fillna(0) - c.value_food[h0].fillna(0)).abs().max())
findings['food_h7_12_max_abs_diff'] = float((b.value_food[late] - c.value_food[late]).abs().max())
findings['mm_forecast_identity'] = float((c.mm_forecast - b.mm_forecast - b.weight_food * (c.value_food - b.value_food)).abs().max())

# c. condition 3 with the estimator's own constant in the grid: the estimator is a constant, so the loss difference is exactly zero
findings['estimator_vs_fixed_025'] = dict(max_abs_path_diff=float((paths[pc.CANDIDATE] - pc.food_log_paths(native, ['FOOD_ECM_A015_R27'])['FOOD_ECM_A015_R27']).abs().max().max()),
                                          note='A025 is not in the declared grid; probe 4 shows the estimator equals a fixed -0.25 at every origin (zero loss difference, no interval)')

# d. expectations
audit = pc.load_audit(); a = audit[audit.model == pc.CANDIDATE]
findings['expectations'] = dict(alpha_negative_share=float((a.alpha < 0).mean()), alpha_median=float(a.alpha.median()), expected_median='between -0.03 and -0.10',
                                gap_seasonal_share_raw_median=float(a.gap_seasonal_share_raw.median()), expected_raw='above 0.25', centred_median=float(a.gap_seasonal_share_centred.median()),
                                h12_full_change_pct=round(100 * (7.124 / 7.466 - 1), 1), expected_h12='within +/-2%',
                                h6_2019_21_change_pct=round(100 * (3.773 / 4.030 - 1), 1), expected_2019_21='within +3% of baseline, most likely to fail')
(OUT / 'findings.json').write_text(json.dumps(findings, indent=1, default=str), encoding='utf-8')
print(json.dumps(findings, indent=1, default=str))
