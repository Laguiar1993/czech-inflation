"""Probe 4: the adjustment speed. Extended fixed-speed grid on the candidate's own gap (trend + food_ppi + agri4),
same correction formula, h1-6, plus the unclipped estimator. Block cumulative-log RMSE at h3/h6/h12 by era on
the primary support; era-balanced score; paired bootstrap of the declared -0.25 against every other speed.
"""
import json

import numpy as np
import pandas as pd

import probe_common as pc

OUT = pc.HERE / 'probe_04_speed'
OUT.mkdir(exist_ok=True)
levels = pc.load_levels(); available = pc.load_available(); native = pc.load_native(); actual = pc.load_actual(); support = pc.load_support(); clocks = pc.clocks(native)
base = pc.food_log_paths(native, [pc.BASELINE])[pc.BASELINE]; truth = pc.actual_food_log(actual)
GRID = [-.02, -.05, -.10, -.15, -.20, -.25, -.30, -.35, -.40, -.50, -.60, -.75, -.90, -1.0]


def name_of(a):
    return f'A{abs(a):.2f}'.replace('.', '')


gaps = {}
for o, clock in clocks.items():
    t = pd.Period(o, 'M'); L = t - 1
    pub = pc.published_before(levels, available, o, clock)
    gap, info = pc.own_gap(pub, L, ('food_ppi', 'agri4'))
    _, raw, _ = pc.own_speed(pub, gap, clip=None)
    gaps[o] = dict(L=L, gap_last=float(gap.loc[L]), alpha_raw=raw)
paths = {pc.BASELINE: base}
for a in GRID:
    paths[name_of(a)] = pd.DataFrame({o: base.loc[o] + pd.Series([pc.own_correction(a, g['gap_last'], g['L'], o)[h] for h in range(1, 13)], index=base.columns) for o, g in gaps.items()}).T.sort_index()
paths['RAW'] = pd.DataFrame({o: base.loc[o] + pd.Series([pc.own_correction(g['alpha_raw'], g['gap_last'], g['L'], o)[h] for h in range(1, 13)], index=base.columns) for o, g in gaps.items()}).T.sort_index()
# the cumulative h6 multiplier of the formula: sum_{k=1..6} a (1+a)^k, with L = t-1
mult = {name_of(a): float(sum(a * (1 + a) ** k for k in range(1, 7))) for a in GRID}
mult3 = {name_of(a): float(sum(a * (1 + a) ** k for k in range(1, 4))) for a in GRID}
names = list(paths)
table = pc.cumulative_table(paths, truth, support); table.to_csv(OUT / 'cumulative_table_speeds.csv', index=False)
scores = pc.score_table(table, names); scores.to_csv(OUT / 'speed_scores.csv', index=False)
piv = scores.pivot_table(index='name', columns=['H', 'sample'], values='rmse'); ratio = piv.div(piv.loc[pc.BASELINE], axis=1)
ratio = ratio.reindex([pc.BASELINE, *[name_of(a) for a in GRID], 'RAW'])
ratio.to_csv(OUT / 'speed_ratio_to_baseline.csv')
findings = dict(reproduction_A025_equals_candidate=float((paths['A025'] - pc.food_log_paths(native, [pc.CANDIDATE])[pc.CANDIDATE]).abs().max().max()),
                alpha_raw=dict(min=float(min(g['alpha_raw'] for g in gaps.values())), median=float(np.median([g['alpha_raw'] for g in gaps.values()])), max=float(max(g['alpha_raw'] for g in gaps.values()))),
                cumulative_multiplier_h6=mult, cumulative_multiplier_h3=mult3)
findings['ratio_to_baseline'] = {n: {f'h{H}_{s}': round(float(ratio.loc[n, (H, s)]), 4) for H in (3, 6, 12) for s in pc.ERAS} for n in ratio.index if n != pc.BASELINE}
findings['era_balanced'] = {n: round(float(ratio.loc[n].mean()), 4) for n in ratio.index if n != pc.BASELINE}
findings['all_twelve_pass'] = {n: bool((ratio.loc[n] < 1 + 1e-12).all()) for n in ratio.index if n != pc.BASELINE}
best = {}
for H in (3, 6, 12):
    for s in pc.ERAS:
        col = ratio.loc[[name_of(a) for a in GRID], (H, s)]
        best[f'h{H}_{s}'] = dict(best=col.idxmin(), ratio=round(float(col.min()), 4), at_A025=round(float(ratio.loc['A025', (H, s)]), 4))
findings['best_fixed_speed_per_cell'] = best
findings['best_era_balanced'] = min(((n, v) for n, v in findings['era_balanced'].items() if n != 'RAW'), key=lambda kv: kv[1])
# paired bootstrap of -0.25 against each other speed, h6 and h12 full sample (the declared condition 3 reading uses h6)
dist = {}
for H in (6, 12):
    w = table[table.H == H].dropna().sort_values('origin')
    for n in names:
        if n in (pc.BASELINE, 'A025'):
            continue
        d = ((w['A025'] - w.actual) ** 2 - (w[n] - w.actual) ** 2).to_numpy(); b = pc.circular_block_bootstrap(d)
        dist[f'h{H}_A025_minus_{n}'] = dict(mean=round(b['mean'], 3), ci=[round(b['ci_low'], 3), round(b['ci_high'], 3)], excludes_zero=bool(b['ci_high'] < 0 or b['ci_low'] > 0))
findings['A025_vs_other_speeds'] = dist
# the range of speeds not distinguishable from -0.25 at h6 full sample
findings['speeds_indistinguishable_from_A025_h6'] = [n for n in names if n not in (pc.BASELINE, 'A025') and not dist[f'h6_A025_minus_{n}']['excludes_zero']]
# in-era optimum by year of origin (stability): best fixed speed per origin year at h6
yr = {}
w6 = table[table.H == 6].dropna()
for year, g in w6.groupby(w6.origin.str[:4]):
    r = {n: pc.rmse(g[n] - g.actual) for n in [name_of(a) for a in GRID]}
    yr[year] = dict(n=len(g), best=min(r, key=r.get), baseline=round(pc.rmse(g[pc.BASELINE] - g.actual), 3), A025=round(r['A025'], 3), best_rmse=round(min(r.values()), 3))
findings['best_speed_by_origin_year_h6'] = yr
(OUT / 'findings.json').write_text(json.dumps(findings, indent=1, default=str), encoding='utf-8')
print(json.dumps(findings, indent=1, default=str))
