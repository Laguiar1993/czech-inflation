"""Probe 8: everything else that could make the promotion wrong.
  a. CNB lead test verdicts, candidate against baseline (evaluation/cnb_lead_summary.csv).
  b. Interaction with the R24 drift: the same corrections applied to FAST's food block (no drift shift), and the
     era bias of the baseline against the mean correction applied.
  c. One-off months: which realised food months carry the gain; the score with origins whose h1-6 window holds
     the largest monthly food surprises removed.
  d. Stability of the estimated relation: coefficients and R2 by origin year (ecm_audit.csv).
  e. Bias after correction by era.
"""
import json

import numpy as np
import pandas as pd

import probe_common as pc

OUT = pc.HERE / 'probe_08_other'
OUT.mkdir(exist_ok=True)
native = pc.load_native(); actual = pc.load_actual(); support = pc.load_support(); audit = pc.load_audit()
paths = pc.food_log_paths(native, [pc.FAST, pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE]); truth = pc.actual_food_log(actual)
findings = {}

# a. CNB lead summary --------------------------------------------------------------------------------------------------
lead = pd.read_csv(pc.EVAL / 'cnb_lead_summary.csv')
sel = lead[lead.model.isin([pc.FAST, pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE]) & lead.scope.eq('first_call_episodes')]
cols = ['model', 'clock', 'threshold', 'sample', 'mature_calls', 'material_gains', 'material_losses', 'joint_successes', 'mean_abs_error_gain']
sel[cols].to_csv(OUT / 'cnb_lead_first_call_episodes.csv', index=False)
findings['cnb_lead'] = {f'{r.model}|{r.clock}|{r.threshold}|{r["sample"]}': dict(mature=int(r.mature_calls), gains=int(r.material_gains), losses=int(r.material_losses), joint=int(r.joint_successes),
                                                                                mean_abs_error_gain=round(float(r.mean_abs_error_gain), 3) if np.isfinite(r.mean_abs_error_gain) else None)
                        for _, r in sel.iterrows() if r.clock == 'report' and r.threshold == 0.3}

# b. the same corrections on FAST's food block ---------------------------------------------------------------------------
corr = paths[pc.CANDIDATE] - paths[pc.BASELINE]
on_fast = paths[pc.FAST] + corr
table = pc.cumulative_table({pc.FAST: paths[pc.FAST], 'FAST_PLUS_ECM': on_fast, pc.BASELINE: paths[pc.BASELINE], pc.CANDIDATE: paths[pc.CANDIDATE]}, truth, support)
sc = pc.score_table(table, [pc.FAST, 'FAST_PLUS_ECM', pc.BASELINE, pc.CANDIDATE]); sc.to_csv(OUT / 'ecm_on_fast_scores.csv', index=False)
piv = sc.pivot_table(index='name', columns=['H', 'sample'], values='rmse')
findings['ecm_on_fast_ratio'] = {f'h{H}_{s}': dict(on_fast=round(float(piv.loc['FAST_PLUS_ECM', (H, s)] / piv.loc[pc.FAST, (H, s)]), 4), on_r24=round(float(piv.loc[pc.CANDIDATE, (H, s)] / piv.loc[pc.BASELINE, (H, s)]), 4))
                                 for H in (3, 6, 12) for s in pc.ERAS}
bias = sc.pivot_table(index='name', columns=['H', 'sample'], values='bias')
findings['bias_h6_h12'] = {f'h{H}_{s}': dict(fast=round(float(bias.loc[pc.FAST, (H, s)]), 3), baseline=round(float(bias.loc[pc.BASELINE, (H, s)]), 3), candidate=round(float(bias.loc[pc.CANDIDATE, (H, s)]), 3))
                           for H in (6, 12) for s in pc.ERAS}
cum6 = audit[audit.model == pc.CANDIDATE].set_index('origin').cumulative_correction_h6
findings['mean_correction_h6_by_era'] = {s: round(float(cum6[pc.era_mask(cum6.index, s)].mean()), 3) for s in pc.ERAS}
# variance decomposition of the h6 gain: bias part vs. variance part, per era
dec = {}
w = table[table.H == 6].dropna()
for s in pc.ERAS:
    z = w[pc.era_mask(w.origin, s)]; eb = z[pc.BASELINE] - z.actual; ec = z[pc.CANDIDATE] - z.actual
    dec[s] = dict(mse_baseline=round(float((eb ** 2).mean()), 3), mse_candidate=round(float((ec ** 2).mean()), 3), bias2_baseline=round(float(eb.mean() ** 2), 3), bias2_candidate=round(float(ec.mean() ** 2), 3),
                  var_baseline=round(float(eb.var(ddof=0)), 3), var_candidate=round(float(ec.var(ddof=0)), 3))
findings['h6_mse_decomposition'] = dec

# c. one-off months ------------------------------------------------------------------------------------------------------
# monthly food surprise against the baseline at h1 (the same month appears in six origins' h1-6 windows)
sur = []
for o in paths[pc.BASELINE].index:
    t = pd.Period(o, 'M') + 1
    if t in truth.index:
        sur.append(dict(month=str(t), surprise=truth[t] - paths[pc.BASELINE].loc[o, 1]))
sur = pd.DataFrame(sur).set_index('month').surprise
big = sur.abs().sort_values(ascending=False)
findings['largest_monthly_food_surprises_h1'] = {m: round(float(sur[m]), 2) for m in big.index[:8]}
w = table[table.H == 6].dropna().copy(); w['dsq'] = (w[pc.CANDIDATE] - w.actual) ** 2 - (w[pc.BASELINE] - w.actual) ** 2
month_gain = {}
for m in big.index[:8]:
    p = pd.Period(m, 'M'); origins_touching = [o for o in w.origin if pd.Period(o, 'M') + 1 <= p <= pd.Period(o, 'M') + 6]
    month_gain[m] = dict(origins=len(origins_touching), share_of_h6_gain=round(float(w[w.origin.isin(origins_touching)].dsq.sum() / w.dsq.sum()), 3))
findings['h6_gain_share_of_origins_touching_big_months'] = month_gain
top3 = [pd.Period(m, 'M') for m in big.index[:3]]
touch = [o for o in w.origin if any(pd.Period(o, 'M') + 1 <= p <= pd.Period(o, 'M') + 6 for p in top3)]
z = w[~w.origin.isin(touch)]
findings['h6_without_origins_touching_top3_surprise_months'] = dict(removed=len(touch), remaining=len(z), ratio=round(pc.rmse(z[pc.CANDIDATE] - z.actual) / pc.rmse(z[pc.BASELINE] - z.actual), 4), months=[str(p) for p in top3])
# the same at h3
w3 = table[table.H == 3].dropna().copy(); touch3 = [o for o in w3.origin if any(pd.Period(o, 'M') + 1 <= p <= pd.Period(o, 'M') + 3 for p in top3)]; z3 = w3[~w3.origin.isin(touch3)]
findings['h3_without_origins_touching_top3_surprise_months'] = dict(removed=len(touch3), remaining=len(z3), ratio=round(pc.rmse(z3[pc.CANDIDATE] - z3.actual) / pc.rmse(z3[pc.BASELINE] - z3.actual), 4))

# d. stability of the relation -----------------------------------------------------------------------------------------
a = audit[audit.model == pc.CANDIDATE].copy(); a['year'] = a.origin.str[:4]
stab = a.groupby('year').agg(coef_ppi=('coef_food_ppi', 'mean'), coef_agri=('coef_agri4', 'mean'), trend=('trend_per_month', 'mean'), r2=('r2', 'mean'), gap_sd=('gap_sd', 'mean'), n=('n', 'mean'), alpha_raw=('speed_alpha_raw', 'mean'), gap_last_mean=('gap_last', 'mean')).round(3)
stab.to_csv(OUT / 'relation_by_year.csv')
findings['relation_by_year'] = stab.to_dict('index')
# gap_last sign by era vs. the direction the baseline needed at h6
w = table[table.H == 6].dropna().copy(); w['gap'] = w.origin.map(audit[audit.model == pc.CANDIDATE].set_index('origin').gap_last)
findings['gap_sign_by_year'] = {y: dict(n=len(g), positive_gap_share=round(float((g.gap > 0).mean()), 2), mean_gap=round(float(g.gap.mean()), 2), mean_needed=round(float((g.actual - g[pc.BASELINE]).mean()), 2)) for y, g in w.groupby(w.origin.str[:4])}

# e. the two declared candidates disagree by era: which one would the rule promote?
piv2 = pc.score_table(pc.cumulative_table({pc.BASELINE: paths[pc.BASELINE], pc.CANDIDATE: paths[pc.CANDIDATE], pc.PPI_CANDIDATE: paths[pc.PPI_CANDIDATE]}, truth, support), [pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE]).pivot_table(index='name', columns=['H', 'sample'], values='rmse')
findings['cand_vs_ppi_candidate'] = {f'h{H}_{s}': dict(cand=round(float(piv2.loc[pc.CANDIDATE, (H, s)] / piv2.loc[pc.BASELINE, (H, s)]), 4), ppi=round(float(piv2.loc[pc.PPI_CANDIDATE, (H, s)] / piv2.loc[pc.BASELINE, (H, s)]), 4)) for H in (3, 6, 12) for s in pc.ERAS}

(OUT / 'findings.json').write_text(json.dumps(findings, indent=1, default=str), encoding='utf-8')
print(json.dumps(findings, indent=1, default=str))
