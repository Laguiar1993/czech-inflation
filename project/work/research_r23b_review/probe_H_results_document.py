"""Probe H: every number and checkable statement in R23B_RESULTS_2026-09-17.md against own recomputation.

Scores come from probe D's own recomputation (probe_D_scores.recomputed.csv, built from primary_rows.csv with
outcomes rebuilt from the frozen headline and core series), not from the evaluator's scoreboard.
"""
import re
import numpy as np
import pandas as pd

from _common import ROOT, FINAL, EVAL, HERE, Report

R = Report('H results document cross-check')
rd = dict(float_precision='round_trip', low_memory=False)
doc = (ROOT / 'R23B_RESULTS_2026-09-17.md').read_text(encoding='utf-8').splitlines()
line = lambda n: doc[n - 1]
T = pd.read_csv(HERE / 'probe_D_scores.recomputed.csv', **rd)
NAMES = {'FAST': 'STATE_FAST_R15', 'Labour cost pressure': 'PRESS_ULC_R23B', 'Domestic pressure': 'PRESS_DOMESTIC_R23B', 'Imported momentum': 'PRESS_MOMENTUM_R23B',
         'Joint, free': 'PRESS_JOINT_R23B', 'Joint, signed': 'PRESS_SIGNED_R23B', 'R23 level gaps, repaired': 'PRESS_LEVELS_R23B'}
CELLS = [('headline_yy', 6, 'full'), ('headline_yy', 12, 'full'), ('headline_yy', 6, 'origins_2024plus'), ('headline_yy', 12, 'origins_2024plus'),
         ('core_cumulative_log', 6, 'full'), ('core_cumulative_log', 6, 'origins_2024plus')]
bad = []; n = 0
for i, text in enumerate(doc, 1):
    parts = [p.strip().strip('*') for p in text.strip().strip('|').split('|')]
    if parts and parts[0] in NAMES and len(parts) == 7:
        for (metric, h, sample), shown in zip(CELLS, parts[1:]):
            mine = T[(T.metric == metric) & (T.h == h) & (T['sample'] == sample) & (T.model == NAMES[parts[0]])].rmse.iloc[0]; n += 1
            if abs(round(mine, 3) - float(shown)) > 5e-4 + 1e-12:
                bad.append((i, parts[0], metric, h, sample, shown, round(mine, 4)))
R.check(f'score table (lines 39-45): all {n} cells equal own RMSE at three decimals', n == 42 and not bad, str(bad))

# ---- gates table (lines 23-29, 31)
G = pd.read_csv(EVAL / 'gate_feature_seasonality.csv', **rd); C = pd.read_csv(EVAL / 'gate_coefficient_signs.csv', **rd)
free = C[C.test.eq('negative_unrestricted')]; signed = C[C.test.eq('on_zero_bound')]
rng = lambda s: (round(100 * s.min()), round(100 * s.max()))
R.check('line 23: seasonal share 0.1% for the labour-cost gap, at most 6.6% for any feature', round(100 * G[G.feature.eq('ulc_sameq')].seasonal_variance_share.max(), 1) == .1 and round(100 * G.seasonal_variance_share.max(), 1) == 6.6,
        f"ulc {G[G.feature.eq('ulc_sameq')].seasonal_variance_share.round(4).tolist()}, max {G.seasonal_variance_share.max():.4f}")
R.check('line 24: labour-cost gap positive in 93-100% of unrestricted fits', rng(1 - free[free.feature.eq('ulc_sameq')].share) == (93, 100), str(rng(1 - free[free.feature.eq('ulc_sameq')].share)))
R.check('line 25: producer-price momentum positive in 100% of unrestricted fits', (free[free.feature.eq('ppi_mom')].share == 0).all())
imp = free[free.feature.eq('import_mom')]
R.check('line 26: import momentum negative in 47-50% (h1-3) and 76-100% (h4-6)', rng(imp[imp.band.eq(1)].share) == (47, 50) and rng(imp[imp.band.eq(2)].share) == (76, 100), f'{rng(imp[imp.band.eq(1)].share)} {rng(imp[imp.band.eq(2)].share)}')
R.check('line 27: koruna news negative in 71-100%', rng(free[free.feature.eq('fx_news')].share) == (71, 100), str(rng(free[free.feature.eq('fx_news')].share)))
tg = free[free.feature.eq('tightening')]
R.check('line 28: tightening negative in 61-64%, 18% in the joint near band', rng(tg[~(tg.model.eq('PRESS_JOINT_R23B') & tg.band.eq(1))].share) == (61, 64) and round(100 * tg[tg.model.eq('PRESS_JOINT_R23B') & tg.band.eq(1)].share.iloc[0]) == 18)
R.check('line 29: validation applied a correction at 50-79% of origins', rng(C.applied_share) == (50, 79), str(rng(C.applied_share)))
R.check('line 31: signed bounds bind for koruna news 71-100% and import momentum 50-100%', rng(signed[signed.feature.eq('fx_news')].share) == (71, 100) and rng(signed[signed.feature.eq('import_mom')].share) == (50, 100))
print('   line 31 "two of five channels carry the declared sign robustly": wrong-sign ranges by feature over the unrestricted candidates:',
      {f: rng(g.share) for f, g in free.groupby('feature')})

# ---- line 49
NA = pd.read_csv(EVAL / 'needed_vs_applied.csv', **rd); u = NA[NA.model.eq('PRESS_ULC_R23B')].set_index(['h', 'sample'])
core = T[(T.metric == 'core_cumulative_log') & (T['sample'] == 'full')].pivot(index='model', columns='h', values='rmse')
gain = {h: 100 * (1 - core.loc['PRESS_ULC_R23B', h] / core.loc['STATE_FAST_R15', h]) for h in (3, 6)}
R.check('line 49: labour-cost candidate improves full-sample core by 4% at h3 and 7% at h6', round(gain[3]) == 4 and round(gain[6]) == 7, f'{gain[3]:.2f}% {gain[6]:.2f}%')
cor = [u.loc[(h, 'full'), 'correlation'] for h in (3, 6, 12)]
R.check('line 49: needed-against-applied +0.33, +0.42, +0.43 at h3, h6, h12', [round(c, 2) for c in cor] == [.33, .42, .43], str([round(c, 4) for c in cor]))
R.check('line 49: from 2024 at h6 applied +0.14 against needed +0.06, correlation 0.15',
        round(u.loc[(6, 'origins_2024plus'), 'mean_applied'], 2) == .14 and round(u.loc[(6, 'origins_2024plus'), 'mean_needed'], 2) == .06 and round(u.loc[(6, 'origins_2024plus'), 'correlation'], 2) == .15)
B = pd.read_csv(EVAL / 'primary_support_circular_bootstrap.csv', **rd)
b = B[B.model.eq('PRESS_ULC_R23B') & B['sample'].eq('origins_2024plus') & B.h.isin([3, 6, 12])][['metric', 'h', 'n', 'block', 'mean_loss_difference', 'ci_low', 'ci_high', 'bootstrap_probability_improvement', 'status']]
print(b.round(4).to_string(index=False).replace('\n', '\n   '))
ok = all((b[(b.metric == m) & (b.h == h)].ci_low.iloc[0] > 0) for m in ('headline_yy', 'core_cumulative_log') for h in (3, 6))
R.check('line 49: 2024+ circular-bootstrap intervals exclude zero on the wrong side at h3 and h6 (both metrics)', ok)
everyone = B[B['sample'].eq('origins_2024plus') & B.h.isin([3, 6]) & B.model.str.startswith('PRESS')]
print('   the same statement for every candidate (ci_low > 0), 2024+:')
print(everyone.assign(excludes_zero_worse=everyone.ci_low > 0, excludes_zero_better=everyone.ci_high < 0).pivot_table(index='model', columns=['metric', 'h'], values='excludes_zero_worse', aggfunc='first').to_string().replace('\n', '\n   '))

# ---- lines 50-51
hl = T[(T.metric == 'headline_yy') & (T.h == 6)].pivot(index='model', columns='sample', values='rmse'); f = hl.loc['STATE_FAST_R15']
at_or_below = [m for m in hl.index if m.startswith('PRESS') and (hl.loc[m] <= f).all()]
R.check('line 50: imported momentum is the ONLY candidate at or below FAST on headline h6 in both samples', at_or_below == ['PRESS_MOMENTUM_R23B'], str(at_or_below))
c6 = T[(T.metric == 'core_cumulative_log') & (T.h == 6)].pivot(index='model', columns='sample', values='rmse')
R.check('line 50: its core h6 is worse in both samples (1.784 v 1.758; 0.430 v 0.394)', [round(v, 3) for v in (c6.loc['PRESS_MOMENTUM_R23B', 'full'], c6.loc['STATE_FAST_R15', 'full'], c6.loc['PRESS_MOMENTUM_R23B', 'origins_2024plus'], c6.loc['STATE_FAST_R15', 'origins_2024plus'])] == [1.784, 1.758, .430, .394])
recent = T[(T['sample'] == 'origins_2024plus') & T.model.str.startswith('PRESS')].pivot_table(index='model', columns=['metric', 'h'], values='rmse')
R.check('line 51: the repaired level-gap control is the worst candidate from 2024 (h6 and h12 headline, h6 core)', all(recent[c].idxmax() == 'PRESS_LEVELS_R23B' for c in [('headline_yy', 6), ('headline_yy', 12), ('core_cumulative_log', 6)]),
        str({c: recent[c].idxmax() for c in recent.columns}))
full_core = T[(T.metric == 'core_cumulative_log') & (T['sample'] == 'full') & (T.h == 6)].set_index('model').rmse
four = {m: dict(headline_full=hl.loc[m, 'full'] <= f['full'], headline_2024=hl.loc[m, 'origins_2024plus'] <= f['origins_2024plus'], core_full=c6.loc[m, 'full'] <= c6.loc['STATE_FAST_R15', 'full'],
                core_2024=c6.loc[m, 'origins_2024plus'] <= c6.loc['STATE_FAST_R15', 'origins_2024plus'], corr_positive=NA[(NA.model == m) & (NA.h == 6) & (NA['sample'] == 'full')].correlation.iloc[0] > 0) for m in hl.index if m.startswith('PRESS')}
R.check('line 47: no candidate meets all four declared conditions', not any(all(v.values()) for v in four.values()))
print(pd.DataFrame(four).T.to_string().replace('\n', '\n   '))

# ---- lead table lines 61-66 and line 68
LS = pd.read_csv(EVAL / 'cnb_lead_summary.csv', **rd); LP = pd.read_csv(EVAL / 'cnb_lead_pairs.csv', **rd); CLU = pd.read_csv(EVAL / 'cnb_lead_report_clusters.csv', **rd)
sel = LS[(LS.clock == 'report') & (LS.threshold == .3) & (LS['sample'] == 'full') & (LS.scope == 'first_call_episodes')].set_index('model')
want = {'STATE_FAST_R15': (19, 4, 13, 2), 'PRESS_JOINT_R23B': (20, 6, 13, 3), 'CONST_2': (19, 6, 12, 3), 'RW_YY': (25, 7, 17, 6), 'PREV_CNB': (19, 3, 15, 1), 'CNB_MOMENTUM': (19, 6, 11, 1)}
got = {m: tuple(int(sel.loc[m, c]) for c in ['mature_calls', 'material_gains', 'material_losses', 'joint_successes']) for m in want}
R.check('lines 61-66: lead table counts (already reproduced with own rules in probe E7)', got == want, str({m: got[m] for m in want if got[m] != want[m]}))
first = LP[(LP.clock == 'report') & (LP.threshold == .3) & LP.episode_start & LP.call & LP.revision_eligible & LP.realised.notna()]
succ = first[first.joint_success]
print('   joint successes by model and report (report clock, 0.30):')
print(succ.groupby(['model', 'report_date']).size().unstack(fill_value=0).to_string().replace('\n', '\n   '))
# the same successes rebuilt with own rules from the CNB file, the clocks and the frozen headline series (no delivered lead file)
cnb = pd.read_csv(ROOT / 'data/cnb_mpr_cpi_quarterly.csv'); CL = pd.read_csv(EVAL / 'cnb_clocks.csv'); inp = pd.read_csv(ROOT / 'output/independent_path_frozen_inputs.csv', **rd); inp.index = pd.PeriodIndex(inp.iloc[:, 0], freq='M')
yy = 100 * np.expm1(np.log1p(inp.headline_mm / 100).rolling(12).sum()); fcst = {(r.report_date, r.quarter): float(r.value) for r in cnb[cnb.is_forecast.astype(str).str.lower().eq('true')].itertuples()}
reports = sorted(cnb.report_date.unique()); nxt = dict(zip(reports, reports[1:])); pos = {d: i for i, d in enumerate(reports)}; origin_at = CL[CL.clock.eq('report')].set_index('report_date').origin; own_rows = []
for report in reports:
    o_ = pd.Period(origin_at[report], 'M')
    for q in sorted(k[1] for k in fcst if k[0] == report):
        Q = pd.Period(q, 'Q'); months = pd.period_range(Q.asfreq('M', 'start'), Q.asfreq('M', 'end'), freq='M'); realised = np.mean([yy.get(m_, np.nan) for m_ in months])
        for model, constant in [('CONST_2', 2.), ('RW_YY', yy[o_ - 1])]:
            value = float(np.mean([yy[m_] if m_ < o_ else constant for m_ in months])); old_, new_ = fcst[(report, q)], fcst.get((nxt.get(report), q), np.nan)
            own_rows.append(dict(model=model, report_date=report, quarter=q, forecast=value, old=old_, new=new_, dev=value - old_, call=abs(value - old_) >= .3 - 1e-12,
                                 eligible=bool(report in nxt and Q > pd.Period(nxt[report], 'Q') and np.isfinite(new_)), realised=realised))
own = pd.DataFrame(own_rows).sort_values(['model', 'quarter', 'report_date']).reset_index(drop=True); own['start'] = False
for _, g in own.groupby(['model', 'quarter']):
    prev = None; sign = None
    for i_, r_ in g.iterrows():
        if r_.call:
            own.loc[i_, 'start'] = prev is None or pos[r_.report_date] != prev + 1 or np.sign(r_.dev) != sign; prev = pos[r_.report_date]; sign = np.sign(r_.dev)
        else:
            prev = None; sign = None
z = own[own.start & own.eligible & own.realised.notna()].copy(); rev = z.new - z.old
z['joint'] = (rev != 0) & (np.sign(rev) == np.sign(z.dev)) & (((z.old - z.forecast).abs() - (z.new - z.forecast).abs()) >= .15 - 1e-12) & (((z.old - z.realised).abs() - (z.forecast - z.realised).abs()) >= .15 - 1e-12)
print('   own rebuild, joint successes by report:', {m_: g_[g_.joint].groupby('report_date').size().to_dict() for m_, g_ in z.groupby('model')})
for row_ in z[z.joint & z.model.eq('RW_YY')][['report_date', 'quarter', 'forecast', 'old', 'new', 'realised']].round(3).itertuples(index=False):
    print('     RW_YY joint success:', tuple(row_))
rw = succ[succ.model.eq('RW_YY')].report_date.unique(); c2 = succ[succ.model.eq('CONST_2')].report_date.unique()
assert sorted(rw) == sorted(z[z.joint & z.model.eq('RW_YY')].report_date.unique()) and sorted(c2) == sorted(z[z.joint & z.model.eq('CONST_2')].report_date.unique())
R.check('line 68: the random walk\'s six joint successes all come from two 2022 reports', len(rw) == 2 and all(d.startswith('2022') for d in rw), str(sorted(rw)))
print('   constant-2% joint successes come from reports:', sorted(c2), '(the sentence on line 68 reads as covering both base rates)')
R.check('line 68: "a constant 2% forecast scores as many joint successes as any model"', sel.loc['CONST_2', 'joint_successes'] >= sel.loc[[m for m in sel.index if m.startswith(('PRESS', 'STATE', 'STABLE', 'DAMPED', 'CORE'))], 'joint_successes'].max(),
        f"CONST_2 {int(sel.loc['CONST_2', 'joint_successes'])}; models max {int(sel.loc[[m for m in sel.index if m.startswith(('PRESS', 'STATE', 'STABLE', 'DAMPED', 'CORE'))], 'joint_successes'].max())}")
fc = CLU[(CLU.model == 'STATE_FAST_R15') & (CLU.clock == 'report') & (CLU.threshold == .3)].iloc[0]; mine = first[first.model.eq('STATE_FAST_R15')]
R.check('line 68: FAST\'s 19 episodes come from 13 reports, losses from 9 and gains from 3', (len(mine), mine.report_date.nunique(), mine[mine.material_loss].report_date.nunique(), mine[mine.material_gain].report_date.nunique()) == (19, 13, 9, 3)
        and (fc.episodes, fc.reports, fc.loss_reports, fc.gain_reports) == (19, 13, 9, 3))

# ---- line 72: a dominant-block label on every call?
CA = pd.read_csv(EVAL / 'cnb_call_attribution.csv', **rd); models_only = LP[~LP.is_baseline]
print(f'   model calls in cnb_lead_pairs.csv: {int(models_only.call.sum())}; first calls: {int((models_only.call & models_only.episode_start).sum())}; '
      f'first calls that are revision-eligible and matured: {int((models_only.call & models_only.episode_start & models_only.revision_eligible & models_only.realised.notna()).sum())}; rows with a block label: {int(CA.dominant_block.notna().sum())}')
R.check('line 72: "a dominant-block label on every call"', int(CA.dominant_block.notna().sum()) == int(models_only.call.sum()),
        f'{int(CA.dominant_block.notna().sum())} labelled of {int(models_only.call.sum())} calls: only matured, revision-eligible FIRST calls are labelled')

# ---- line 16 wording
tr = pd.read_csv(FINAL / 'training.csv'); age = pd.Series([(pd.Period(o, 'M') - pd.Period(s, 'M')).n for o, s in zip(tr.origin, tr.training_origin)])
newest = tr.assign(age=age).groupby(['origin', 'band']).age.min()
print(f'   line 16 "no correction is learned from labels more than a year old": label origins used are {age.min()} to {age.max()} months before the decision origin; '
      f'{(age > 12).mean():.0%} of training rows are older than 12 months. What is true: the NEWEST label is {newest.min()}-{newest.max()} months old (R23: 13-15).')
R.check('line 16: "no correction is learned from labels more than a year old" (as written)', (age <= 12).all(), f'{(age > 12).mean():.0%} of the training labels are more than a year old; the statement holds only for the newest label')

# ---- tests (lines 72, 76)
count = lambda p: len(re.findall(r'^def test_', (ROOT / p).read_text(encoding='utf-8'), flags=re.M))
n_new = count('tests/test_cost_pressure_r23b.py') + count('tests/test_path_diagnostics.py'); n_all = n_new + count('tests/test_cost_gaps_r23.py')
R.check('lines 72 and 76: 20 new tests, 29 targeted tests', (n_new, n_all) == (20, 29), f'{n_new} new, {n_all} in the three files (29 passed in F_pytest_output.txt)')
R.done()
