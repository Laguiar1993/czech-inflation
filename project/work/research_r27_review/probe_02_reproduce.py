"""Probe 2: independent reproduction of the R27 headline numbers from the exported files.

Block cumulative log changes are recomputed from value_food in native_forecasts.csv and the realised block
rates; the assembled headline rates are recomputed from mm_forecast and the frozen headline history; the CNB
pair RMSE from cnb_pairs.csv (with the pair forecasts checked against the recompounded quarterly means); the
bootstrap intervals with the reviewer's own copy of the circular scheme and with other seeds and block lengths.
Nothing from tools/research_r27/evaluate.py or tools/path_diagnostics is imported.
"""
import json

import numpy as np
import pandas as pd

import probe_common as pc

OUT = pc.HERE / 'probe_02_reproduce'
OUT.mkdir(exist_ok=True)
native = pc.load_native(); forecasts = pc.load_forecasts(); actual = pc.load_actual(); support = pc.load_support(); headline = pc.load_headline()
MODELS = [pc.FAST, pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE, *pc.FIXED]
findings = {}

# 1. block scores ----------------------------------------------------------------------------------------------
paths = pc.food_log_paths(native, MODELS)
table = pc.cumulative_table(paths, pc.actual_food_log(actual), support)
table.to_csv(OUT / 'food_cumulative_table_own.csv', index=False)
own = pc.score_table(table, MODELS)
theirs = pd.read_csv(pc.EVAL / 'food_family_scores.csv')
merged = own.merge(theirs, on=['H', 'sample', 'name'], suffixes=('_own', '_theirs'))
merged['rmse_diff'] = (merged.rmse_own - merged.rmse_theirs).abs(); merged['n_diff'] = merged.n_own - merged.n_theirs
merged.to_csv(OUT / 'block_scores_compare.csv', index=False)
findings['block_scores'] = dict(cells=len(merged), max_abs_rmse_diff=float(merged.rmse_diff.max()), n_mismatch=int((merged.n_diff != 0).sum()))
ratio = own.pivot_table(index='name', columns=['H', 'sample'], values='rmse')
ratio_to_base = ratio.div(ratio.loc[pc.BASELINE], axis=1)
ratio_to_base.to_csv(OUT / 'block_ratio_to_baseline_own.csv')
findings['candidate_ratio_to_baseline'] = {f'h{H}_{s}': float(ratio_to_base.loc[pc.CANDIDATE, (H, s)]) for H in (3, 6, 12) for s in pc.ERAS}
findings['ppi_candidate_ratio_to_baseline'] = {f'h{H}_{s}': float(ratio_to_base.loc[pc.PPI_CANDIDATE, (H, s)]) for H in (3, 6, 12) for s in pc.ERAS}
findings['all_twelve_cells_below_baseline'] = bool((ratio_to_base.loc[pc.CANDIDATE] < 1).all())

# 2. assembled headline ---------------------------------------------------------------------------------------
recomp = []
for (o, m), g in native[native.model.isin([pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE])].groupby(['origin', 'model']):
    path = g.set_index('h').mm_forecast.to_dict()
    for h in (6, 12):
        recomp.append(dict(origin=o, model=m, h=h, yy_own=pc.compound_yy(headline, path[0], path, o, h)))
recomp = pd.DataFrame(recomp)
chk = recomp.merge(forecasts[['origin', 'model', 'h', 'yy_exante', 'yy_actual']], on=['origin', 'model', 'h'])
chk['diff'] = (chk.yy_own - chk.yy_exante).abs()
findings['yy_exante_recompounded_max_abs_diff'] = float(chk['diff'].max())
# own yy_actual from the headline history
def yy_actual_of(o, h):
    t = pd.Period(o, 'M') + h; w = headline.reindex(pd.period_range(t - 11, t, freq='M'))
    return float(100 * np.expm1(np.log1p(w / 100).sum())) if w.notna().all() else np.nan
chk['yy_actual_own'] = [yy_actual_of(o, h) for o, h in zip(chk.origin, chk.h)]
findings['yy_actual_max_abs_diff'] = float((chk.yy_actual_own - chk.yy_actual).abs().max())
chk = chk[[(o, h) in support for o, h in zip(chk.origin, chk.h)]]
cells = []
for h in (6, 12):
    g = chk[chk.h == h].pivot(index='origin', columns='model', values='yy_own'); truth = chk[chk.h == h].drop_duplicates('origin').set_index('origin').yy_actual_own
    for era in pc.ERAS:
        z = g[pc.era_mask(g.index, era)].dropna(); t = truth.reindex(z.index)
        cells.append(dict(h=h, sample=era, n=len(z), **{m: pc.rmse(z[m] - t) for m in (pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE)}))
cells = pd.DataFrame(cells); cells.to_csv(OUT / 'assembled_headline_own.csv', index=False)
verdict = json.loads((pc.EVAL / 'rule_verdicts.json').read_text())
theirs_cells = verdict[pc.CANDIDATE]['assembled']['cells']
findings['assembled'] = {f'{r["sample"]}_h{r["h"]}': dict(n=int(r['n']), baseline_own=r[pc.BASELINE], candidate_own=r[pc.CANDIDATE], baseline_theirs=theirs_cells[f'{r["sample"]}_h{r["h"]}']['baseline'],
                                                        candidate_theirs=theirs_cells[f'{r["sample"]}_h{r["h"]}']['candidate']) for _, r in cells.iterrows()}
findings['assembled_max_abs_diff'] = float(max(abs(v['baseline_own'] - v['baseline_theirs']) + abs(v['candidate_own'] - v['candidate_theirs']) for v in findings['assembled'].values()))

# 3. CNB pairs from 2024 ----------------------------------------------------------------------------------------
pairs = pd.read_csv(pc.EVAL / 'cnb_pairs.csv')
recent = pairs[(pairs.clock == 'report') & (pairs.report_date >= '2024-01-01')]
findings['cnb_pairs_2024plus'] = {m: dict(n=int((recent.model == m).sum()), rmse_from_error=pc.rmse(recent[recent.model == m].error),
                                          rmse_from_forecast_minus_realised=pc.rmse(recent[recent.model == m].forecast - recent[recent.model == m].realised))
                                  for m in (pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE, pc.FAST)}
# check the pair forecasts against the quarterly mean of the recompounded annual rates for that origin
fc = forecasts[forecasts.model.isin([pc.BASELINE, pc.CANDIDATE])].copy(); fc['target'] = pd.PeriodIndex(fc.target, freq='M')
fc['quarter'] = fc.target.dt.asfreq('Q').astype(str).str.replace('Q', 'Q')
qm = fc.groupby(['origin', 'model', 'quarter']).yy_exante.agg(['mean', 'size']).reset_index()
qm['quarter'] = qm.quarter.str.replace('Q', 'Q')
r2 = recent[recent.model.isin([pc.BASELINE, pc.CANDIDATE])].merge(qm, on=['origin', 'model', 'quarter'], how='left')
findings['cnb_pair_forecast_vs_quarter_mean'] = dict(n=len(r2), matched=int(r2['mean'].notna().sum()), max_abs_diff=float((r2.forecast - r2['mean']).abs().max()),
                                                     months_per_quarter=r2['size'].dropna().unique().tolist())
r2.to_csv(OUT / 'cnb_pairs_check.csv', index=False)
by_ahead = recent[recent.model.isin([pc.BASELINE, pc.CANDIDATE])].groupby(['quarters_ahead', 'model']).error.apply(lambda e: pc.rmse(e)).unstack()
by_ahead['n'] = recent[recent.model == pc.BASELINE].groupby('quarters_ahead').size()
by_ahead.to_csv(OUT / 'cnb_pairs_by_quarters_ahead.csv')
findings['cnb_pairs_by_quarters_ahead'] = by_ahead.round(4).to_dict()
# per-pair gain
pv = recent[recent.model.isin([pc.BASELINE, pc.CANDIDATE])].pivot_table(index=['report_date', 'quarter'], columns='model', values='error')
pv['dsq'] = pv[pc.CANDIDATE] ** 2 - pv[pc.BASELINE] ** 2
pv.sort_values('dsq').to_csv(OUT / 'cnb_pairs_loss_differences.csv')
findings['cnb_pairs_gain_concentration'] = dict(n_pairs=len(pv), pairs_improved=int((pv.dsq < 0).sum()), total_dsq=float(pv.dsq.sum()),
                                                top3_share=float(pv.dsq.sort_values().iloc[:3].sum() / pv.dsq.sum()) if pv.dsq.sum() < 0 else np.nan,
                                                top3=[f'{i[0]} {i[1]}: {v:.3f}' for i, v in pv.dsq.sort_values().iloc[:3].items()])

# 4. bootstrap intervals -------------------------------------------------------------------------------------------
boot = {}
for H in (6, 12):
    w = table[table.H == H].dropna(subset=[pc.CANDIDATE, pc.BASELINE, 'actual']).sort_values('origin')
    d = ((w[pc.CANDIDATE] - w.actual) ** 2 - (w[pc.BASELINE] - w.actual) ** 2).to_numpy()
    ordinal = pd.PeriodIndex(w.origin, freq='M').asi8
    contiguous = bool(np.all(np.diff(ordinal) == 1))
    own = pc.circular_block_bootstrap(d)
    theirs = verdict[pc.CANDIDATE][f'interval_h{H}']
    seeds = [pc.circular_block_bootstrap(d, seed=s) for s in range(200)]
    blocks = {b: pc.circular_block_bootstrap(d, block=b) for b in (3, 6, 9, 12, 18, 24)}
    # stationary bootstrap (geometric block lengths, mean 12)
    rng = np.random.default_rng(7); n = len(d); means = []
    for _ in range(2000):
        idx = []; i = rng.integers(0, n)
        while len(idx) < n:
            idx.append(i % n); i = rng.integers(0, n) if rng.random() < 1 / 12 else i + 1
        means.append(d[np.array(idx[:n])].mean())
    stat = dict(ci_low=float(np.quantile(means, .025)), ci_high=float(np.quantile(means, .975)))
    boot[f'h{H}'] = dict(n=len(d), contiguous_origins=contiguous, first=w.origin.iloc[0], last=w.origin.iloc[-1], own=own, theirs={k: theirs[k] for k in ('n', 'block', 'mean_loss_difference', 'ci_low', 'ci_high', 'status')},
                         ci_high_max_over_200_seeds=float(max(s['ci_high'] for s in seeds)), seeds_with_ci_high_below_zero=int(sum(s['ci_high'] < 0 for s in seeds)),
                         by_block={b: (round(v['ci_low'], 3), round(v['ci_high'], 3)) for b, v in blocks.items()}, stationary_mean12=stat,
                         origins_improved=int((d < 0).sum()), lag1_autocorr_of_loss_difference=float(pd.Series(d).autocorr(1)))
    pd.DataFrame(dict(origin=w.origin, loss_difference=d)).to_csv(OUT / f'loss_difference_h{H}.csv', index=False)
findings['bootstrap'] = boot

# 5. needed vs applied at h3/h6, full and 2024+ ----------------------------------------------------------------
phase = {}
for H in (3, 6):
    for era in ('full', 'origins_2024plus'):
        w = table[table.H == H]; w = w[pc.era_mask(w.origin, era)].dropna(subset=[pc.CANDIDATE, pc.BASELINE, 'actual'])
        needed = w.actual - w[pc.BASELINE]; applied = w[pc.CANDIDATE] - w[pc.BASELINE]
        phase[f'h{H}_{era}'] = dict(n=len(w), correlation=float(needed.corr(applied)), sign_agreement=float((np.sign(needed) == np.sign(applied)).mean()),
                                    theirs=verdict[pc.CANDIDATE]['phase'][f'{era}_h{H}']['correlation'])
findings['phase'] = phase

# 6. gain concentration at h6 ---------------------------------------------------------------------------------------
w = table[table.H == 6].dropna(subset=[pc.CANDIDATE, pc.BASELINE, 'actual']).copy()
w['dsq'] = (w[pc.CANDIDATE] - w.actual) ** 2 - (w[pc.BASELINE] - w.actual) ** 2
w = w.sort_values('dsq')
findings['h6_concentration'] = dict(n=len(w), gaining=int((w.dsq < 0).sum()), total=float(w.dsq.sum()), top5=w.origin.iloc[:5].tolist(), top5_share=float(w.dsq.iloc[:5].sum() / w.dsq.sum()),
                                   worst5=w.origin.iloc[-5:].tolist(), worst5_sum=float(w.dsq.iloc[-5:].sum()))

(OUT / 'findings.json').write_text(json.dumps(findings, indent=1, default=str), encoding='utf-8')
print(json.dumps(findings, indent=1, default=str))
