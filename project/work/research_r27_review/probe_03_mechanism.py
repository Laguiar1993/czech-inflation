"""Probe 3: what is the mechanism? Controls with no upstream information, scored exactly like the candidate.

Variants (all: same window rule, same calendar-month centring unless stated, same speed rule clipped to
[-0.25, 0], same decay formula, same h1-6 activation, on the same R24 baseline food log rates):
  CAND      trend + food_ppi + agri4            (the declared FOOD_ECM_R27; reproduced here from scratch)
  PPI       trend + food_ppi                    (the declared FOOD_ECM_PPI_R27)
  AGRI      trend + agri4
  TREND     trend only: the own-level residual of retail food on a constant and a trend
  CONST     constant only: retail food minus its window mean
  MARGIN    food - food_ppi minus its window mean, centred by calendar month (no trend, coefficient fixed at 1)
  MARGIN_NC the same without the calendar-month centring
  MARGIN_T  food - food_ppi on a constant and a trend (coefficient fixed at 1, trend free)
The reviewer's implementation of the mechanics is in probe_common.py and reproduces ecm_audit.csv to 1e-15 (probe 1).
"""
import json

import numpy as np
import pandas as pd

import probe_common as pc

OUT = pc.HERE / 'probe_03_mechanism'
OUT.mkdir(exist_ok=True)
levels = pc.load_levels(); available = pc.load_available(); native = pc.load_native(); actual = pc.load_actual(); support = pc.load_support(); clocks = pc.clocks(native)
base_paths = pc.food_log_paths(native, [pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE])
truth = pc.actual_food_log(actual)

VARIANTS = {
    'CAND': dict(regressors=('food_ppi', 'agri4'), trend=True, centre=True),
    'PPI': dict(regressors=('food_ppi',), trend=True, centre=True),
    'AGRI': dict(regressors=('agri4',), trend=True, centre=True),
    'TREND': dict(regressors=(), trend=True, centre=True),
    'CONST': dict(regressors=(), trend=False, centre=True),
    'MARGIN': dict(margin=True, trend=False, centre=True),
    'MARGIN_NC': dict(margin=True, trend=False, centre=False),
    'MARGIN_T': dict(margin=True, trend=True, centre=True),
}


def margin_gap(published, last, trend, centre, window=pc.WINDOW, min_window=pc.MIN_WINDOW):
    frame = published.loc[:last, ['food', 'food_ppi']].dropna().iloc[-window:]
    if len(frame) < min_window:
        return None, {}
    m = frame.food - frame.food_ppi; n = len(frame)
    X = np.column_stack([np.ones(n), np.arange(n, dtype=float)]) if trend else np.ones((n, 1))
    beta = np.linalg.lstsq(X, m.to_numpy(float), rcond=None)[0]
    resid = pd.Series(m.to_numpy(float) - X @ beta, index=frame.index)
    return (pc.month_centre(resid) if centre else resid), dict(n=n, beta=beta)


def run_variant(name, spec, clip=(-.25, 0.)):
    rows = []; paths = {}
    for o, clock in clocks.items():
        t = pd.Period(o, 'M'); L = t - 1
        pub = pc.published_before(levels, available, o, clock)
        if spec.get('margin'):
            gap, info = margin_gap(pub, L, spec['trend'], spec['centre'])
        else:
            gap, info = pc.own_gap(pub, L, spec['regressors'], trend=spec['trend'], centre=spec['centre'])
        alpha, raw, npairs = pc.own_speed(pub, gap, clip=clip)
        corr = pc.own_correction(alpha, float(gap.loc[L]), L, o)
        base = base_paths[pc.BASELINE].loc[o]
        paths[o] = base + pd.Series([corr[h] for h in range(1, 13)], index=base.index)
        rows.append(dict(origin=o, variant=name, gap_last=float(gap.loc[L]), alpha_raw=raw, alpha=alpha, cum6=sum(corr[h] for h in range(1, 7)), n_window=info['n']))
    return pd.DataFrame(rows), pd.DataFrame(paths).T.sort_index()


audits = []; all_paths = {pc.BASELINE: base_paths[pc.BASELINE]}
for name, spec in VARIANTS.items():
    a, p = run_variant(name, spec); audits.append(a); all_paths[name] = p
audit = pd.concat(audits, ignore_index=True); audit.to_csv(OUT / 'variant_audit.csv', index=False)
findings = {}
# reproduction of the declared candidates from scratch
findings['reproduction'] = dict(CAND_vs_FOOD_ECM_R27_max_abs_diff=float((all_paths['CAND'] - base_paths[pc.CANDIDATE]).abs().max().max()),
                                PPI_vs_FOOD_ECM_PPI_R27_max_abs_diff=float((all_paths['PPI'] - base_paths[pc.PPI_CANDIDATE]).abs().max().max()))
table = pc.cumulative_table(all_paths, truth, support); table.to_csv(OUT / 'cumulative_table_variants.csv', index=False)
names = list(all_paths)
scores = pc.score_table(table, names); scores.to_csv(OUT / 'variant_scores.csv', index=False)
piv = scores.pivot_table(index='name', columns=['H', 'sample'], values='rmse'); ratio = piv.div(piv.loc[pc.BASELINE], axis=1)
ratio.to_csv(OUT / 'variant_ratio_to_baseline.csv')
findings['ratio_to_baseline'] = {n: {f'h{H}_{s}': round(float(ratio.loc[n, (H, s)]), 4) for H in (3, 6, 12) for s in pc.ERAS} for n in names if n != pc.BASELINE}
findings['all_twelve_cells_pass'] = {n: bool((ratio.loc[n] < 1 + 1e-12).all()) for n in names if n != pc.BASELINE}
findings['era_balanced_score'] = {n: float(ratio.loc[n].mean()) for n in names if n != pc.BASELINE}

# speed audit per variant
g = audit.groupby('variant')
findings['alpha_raw'] = {n: dict(min=float(x.alpha_raw.min()), median=float(x.alpha_raw.median()), max=float(x.alpha_raw.max()), share_clipped_at_minus_025=float((x.alpha_raw <= -.25).mean()),
                                  share_wrong_sign=float((x.alpha_raw >= 0).mean())) for n, x in g}
# how alike are the corrections?
cum = audit.pivot(index='origin', columns='variant', values='cum6'); gl = audit.pivot(index='origin', columns='variant', values='gap_last')
findings['cum6_correlation_with_CAND'] = {n: float(cum['CAND'].corr(cum[n])) for n in cum.columns}
findings['gap_last_correlation_with_CAND'] = {n: float(gl['CAND'].corr(gl[n])) for n in gl.columns}
findings['cum6_correlation_matrix'] = cum.corr().round(3).to_dict()
findings['cum6_median_abs'] = {n: float(cum[n].abs().median()) for n in cum.columns}
findings['cum6_mean_by_era'] = {n: {era: float(cum.loc[pc.era_mask(cum.index, era), n].mean()) for era in pc.ERAS} for n in cum.columns}

# is the candidate distinguishable from each control? paired squared-loss difference, h6 and h12 full sample, circular block bootstrap
dist = {}
for H in (6, 12):
    w = table[table.H == H].dropna().sort_values('origin')
    for n in names:
        if n in (pc.BASELINE, 'CAND'):
            continue
        d = ((w['CAND'] - w.actual) ** 2 - (w[n] - w.actual) ** 2).to_numpy()
        b = pc.circular_block_bootstrap(d)
        dist[f'h{H}_CAND_minus_{n}'] = dict(mean=round(b['mean'], 3), ci=[round(b['ci_low'], 3), round(b['ci_high'], 3)], candidate_better_share=float((d < 0).mean()))
findings['candidate_vs_controls_loss_difference'] = dist
# and each control against the baseline
base_int = {}
for H in (6, 12):
    w = table[table.H == H].dropna().sort_values('origin')
    for n in names:
        if n == pc.BASELINE:
            continue
        d = ((w[n] - w.actual) ** 2 - (w[pc.BASELINE] - w.actual) ** 2).to_numpy(); b = pc.circular_block_bootstrap(d)
        base_int[f'h{H}_{n}'] = dict(mean=round(b['mean'], 3), ci=[round(b['ci_low'], 3), round(b['ci_high'], 3)], improved_share=float((d < 0).mean()))
findings['controls_vs_baseline_loss_difference'] = base_int

# what does the trend-only gap look like against the candidate's gap over time (a few origins)
sample = gl.loc[['2019-06', '2020-06', '2021-06', '2021-12', '2022-06', '2023-03', '2024-06', '2025-06', '2026-06']].round(3)
findings['gap_last_examples'] = sample.to_dict('index')

(OUT / 'findings.json').write_text(json.dumps(findings, indent=1, default=str), encoding='utf-8')
print(json.dumps(findings, indent=1, default=str))
