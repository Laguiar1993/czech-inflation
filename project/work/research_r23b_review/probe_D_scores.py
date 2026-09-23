"""Probe D: headline and cumulative-core RMSE, and needed-versus-applied, recomputed with own code.

Outcomes are NOT taken from the evaluator's columns alone: annual headline outcomes are rebuilt from
output/independent_path_frozen_inputs.csv and cumulative core outcomes from the CNB core fixture.
"""
import json
import numpy as np
import pandas as pd

from _common import ROOT, FINAL, EVAL, Report

R = Report('D scores recomputed')
rd = dict(float_precision='round_trip', low_memory=False)
P = pd.read_csv(EVAL / 'primary_rows.csv', **rd)
S = pd.read_csv(EVAL / 'same_support_scoreboard.csv', **rd)
MODELS = ['PRESS_ULC_R23B', 'PRESS_DOMESTIC_R23B', 'PRESS_MOMENTUM_R23B', 'PRESS_JOINT_R23B', 'PRESS_SIGNED_R23B', 'PRESS_LEVELS_R23B']
ROSTER = ['STATE_FAST_R15', 'STABLE_LOCAL_CORE_R14B', 'DAMPED_P95_Q001_R16', 'CORE_FEEDBACK_R21', *MODELS]

# own outcomes
inp = pd.read_csv(ROOT / 'output/independent_path_frozen_inputs.csv', **rd); inp.index = pd.PeriodIndex(inp.iloc[:, 0], freq='M')
lh = np.log1p(inp.headline_mm / 100); yy = {p: 100 * np.expm1(lh.loc[p - 11:p].sum()) for p in lh.index[11:] if lh.loc[p - 11:p].notna().all() and len(lh.loc[p - 11:p]) == 12}
corefile = pd.read_csv(ROOT / 'tests/fixtures/cleanup/cnb_core_mm.csv', **rd); corefile.index = pd.PeriodIndex(corefile.iloc[:, 0], freq='M'); lc = 100 * np.log1p(corefile['core'] / 100)
t = pd.PeriodIndex(P.origin, freq='M'); tg = pd.PeriodIndex(P.target, freq='M')
R.check('target = origin + h on every primary row', all(a + int(h) == b for a, h, b in zip(t, P.h, tg)))
own_yy = np.array([yy.get(p, np.nan) for p in tg])
R.check('yy_actual in primary rows = own twelve-month compounding of frozen headline m/m', np.nanmax(np.abs(own_yy - P.yy_actual.to_numpy())) < 1e-10 and np.isfinite(own_yy).all(), f'max abs diff={np.nanmax(np.abs(own_yy - P.yy_actual.to_numpy())):.3e}')
own_core = np.array([lc.loc[o + 1:o + int(h)].sum() if len(lc.loc[o + 1:o + int(h)]) == int(h) else np.nan for o, h in zip(t, P.h)])
R.check('core_cumulative_log_actual = own sum of realised log core over h1..h', np.nanmax(np.abs(own_core - P.core_cumulative_log_actual.to_numpy())) < 1e-10 and np.isfinite(own_core).all(), f'max abs diff={np.nanmax(np.abs(own_core - P.core_cumulative_log_actual.to_numpy())):.3e}')
P = P.assign(e_yy=P.yy_exante - own_yy, e_core=P.core_cumulative_log_forecast - own_core)

rows = []; worst = 0.; count = 0
for metric, col in [('headline_yy', 'e_yy'), ('core_cumulative_log', 'e_core')]:
    for h in (3, 6, 12):
        for sample, keep in [('full', P.origin >= '0'), ('origins_2024plus', P.origin >= '2024-01')]:
            for m in ROSTER:
                e = P.loc[(P.model == m) & (P.h == h) & keep, col].to_numpy()
                mine = dict(n=len(e), rmse=float(np.sqrt(np.mean(e ** 2))), mae=float(np.mean(np.abs(e))), bias=float(np.mean(e)))
                theirs = S[(S.metric == metric) & (S.h == h) & (S['sample'] == sample) & (S.model == m)].iloc[0]
                d = max(abs(mine[k] - theirs[k]) for k in ('rmse', 'mae', 'bias')); worst = max(worst, d); count += 1
                if mine['n'] != theirs.n:
                    worst = np.inf
                rows.append(dict(metric=metric, h=h, sample=sample, model=m, **mine))
R.check(f'{count} cells (2 metrics x h3/h6/h12 x 2 samples x 10 models): n, RMSE, MAE, bias equal same_support_scoreboard.csv', worst < 1e-12, f'max abs diff={worst:.3e}')
T = pd.DataFrame(rows)
T.to_csv(ROOT / 'work/research_r23b_review/probe_D_scores.recomputed.csv', index=False)
for metric in ('headline_yy', 'core_cumulative_log'):
    for sample in ('full', 'origins_2024plus'):
        z = T[(T.metric == metric) & (T['sample'] == sample)].pivot(index='model', columns='h', values='rmse').reindex(ROSTER)
        fast = z.loc['STATE_FAST_R15']; n = T[(T.metric == metric) & (T['sample'] == sample) & (T.model == 'STATE_FAST_R15')].set_index('h').n.to_dict()
        print(f'\n   {metric} RMSE, {sample}, n={n}  (value, then difference from FAST)')
        for m in ROSTER:
            print('   {:24s}'.format(m) + '  '.join(f'h{h}: {z.loc[m, h]:.4f} ({z.loc[m, h] - fast[h]:+.4f})' for h in (3, 6, 12)))

# declared "what would count" criteria 1 and 2 (h6, both samples)
print()
for m in MODELS:
    g = T[(T.model == m) & (T.h == 6)].set_index(['metric', 'sample']).rmse; f = T[(T.model == 'STATE_FAST_R15') & (T.h == 6)].set_index(['metric', 'sample']).rmse
    print(f'   {m:24s} h6 at-or-below FAST: ' + ', '.join(f'{k[0][:8]}/{k[1][:4]}={"yes" if g[k] <= f[k] else "NO"}' for k in g.index))

# ---- needed versus applied, from forecast_core_outcomes.csv
F = pd.read_csv(EVAL / 'forecast_core_outcomes.csv', **rd); NA = pd.read_csv(EVAL / 'needed_vs_applied.csv', **rd)
fast = F[F.model.eq('STATE_FAST_R15')].set_index(['origin', 'h']); worst = 0.; out = []
for h in (3, 6, 12):
    for m in MODELS + ['CORE_FEEDBACK_R21']:
        own = F[F.model.eq(m)].set_index(['origin', 'h'])
        base = fast.xs(h, level='h'); mine = own.xs(h, level='h')
        needed = (base.core_cumulative_log_actual - base.core_cumulative_log_forecast); applied = mine.core_cumulative_log_forecast - base.core_cumulative_log_forecast
        ok = needed.notna() & applied.notna()
        for sample, keep in [('full', ok), ('origins_2024plus', ok & (needed.index >= '2024-01'))]:
            a, b = needed[keep].to_numpy(), applied[keep].to_numpy()
            corr = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 and b.std() > 1e-12 else np.nan
            act = np.abs(b) > 1e-12
            theirs = NA[(NA.model == m) & (NA.h == h) & (NA['sample'] == sample)].iloc[0]
            for k, v in [('correlation', corr), ('mean_needed', a.mean()), ('mean_applied', b.mean()), ('sign_agreement', float(np.mean(np.sign(a[act]) == np.sign(b[act]))) if act.any() else np.nan)]:
                if not (np.isnan(v) and np.isnan(theirs[k])):
                    worst = max(worst, abs(v - theirs[k]))
            if len(a) != theirs.n or int(act.sum()) != theirs.n_active:
                worst = np.inf
            # correlation on the active rows only, and with a sign-only summary, as sensitivity
            corr_active = float(np.corrcoef(a[act], b[act])[0, 1]) if act.sum() > 2 else np.nan
            out.append(dict(model=m, h=h, sample=sample, n=len(a), n_active=int(act.sum()), correlation=corr, correlation_active_only=corr_active,
                            mse_gain_vs_fast=float(np.mean(a ** 2) - np.mean((a - b) ** 2))))
R.check('needed-versus-applied (n, n_active, correlation, means, sign agreement) equals needed_vs_applied.csv at h3/h6/h12, both samples, 7 models', worst < 1e-12, f'max abs diff={worst:.3e}')
O = pd.DataFrame(out); O.to_csv(ROOT / 'work/research_r23b_review/probe_D_needed_applied.recomputed.csv', index=False)
print(O[O.h.eq(6)].round(4).to_string(index=False))
# is the needed-vs-applied support the primary support?
sup = pd.read_csv(ROOT / 'output/research_r17/attribution/primary_support.csv')
print('\n   needed-vs-applied h6 origins:', int(O[(O.h == 6) & (O['sample'] == 'full')].n.iloc[0]), 'against primary-support h6 origins:', int((sup.h == 6).sum()))
R.done()
