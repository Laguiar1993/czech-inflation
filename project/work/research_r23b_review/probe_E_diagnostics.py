"""Probe E: the tools/path_diagnostics package against own calculations on the delivered data."""
import json
import numpy as np
import pandas as pd

from _common import ROOT, FINAL, EVAL, Report

from tools.path_diagnostics import gates, bootstrap, attribution, benchmarks, lead_baselines

R = Report('E diagnostics package')
rd = dict(float_precision='round_trip', low_memory=False)

# ------------------------------------------------------------------ E1 seasonal share
x = pd.read_csv(FINAL / 'features.csv', index_col=0, **rd); prov = pd.read_csv(FINAL / 'feature_provenance.csv')
G = pd.read_csv(EVAL / 'gate_feature_seasonality.csv', **rd); worst = 0.
for feature in x.columns:
    ref = prov[prov.feature.eq(feature)].set_index('origin').reference.reindex(x.index)
    label = ref.map(lambda s: np.nan if not isinstance(s, str) else (int(s[-1]) if 'Q' in s else int(s[5:7])))
    for scope, keep in [('all_origins', np.ones(len(x), bool)), ('quarter_end_origins', np.array([int(o[5:7]) % 3 == 0 for o in x.index]))]:
        v = x[feature][keep]; l = label[keep]; ok = v.notna() & l.notna(); v = v[ok].to_numpy(); l = l[ok].to_numpy()
        dummies = (l[:, None] == np.unique(l)[None, :]).astype(float)                  # R2 of a regression on period dummies
        fitted = dummies @ np.linalg.lstsq(dummies, v, rcond=None)[0]; r2 = 1 - ((v - fitted) ** 2).sum() / ((v - v.mean()) ** 2).sum()
        theirs = G[(G.feature == feature) & (G.scope == scope)].iloc[0]
        worst = max(worst, abs(r2 - theirs.seasonal_variance_share)); assert theirs.n == len(v)
R.check('E1 seasonal share = R2 of a period-of-year dummy regression, all 7 features x 2 scopes equal gate_feature_seasonality.csv', worst < 1e-12, f'max abs diff={worst:.3e}')
print('   max share:', G.seasonal_variance_share.max().round(4), 'for', G.loc[G.seasonal_variance_share.idxmax(), ['feature', 'scope']].tolist(), '(declared limit 0.25)')
# The same gate on the R23 ulc_gap, to show that the gate has power on the defect it was written for
r23x = pd.read_csv(ROOT / 'output/research_r23/final/features.csv', index_col=0, **rd); r23p = pd.read_csv(ROOT / 'output/research_r23/final/feature_provenance.csv')
lab = r23p[r23p.feature.eq('ulc_gap')].set_index('origin').reference.reindex(r23x.index).map(lambda s: float(s[-1]) if isinstance(s, str) else np.nan)
print('   gate applied to the sealed R23 ulc_gap (expected about 0.44):', round(gates.seasonal_share(r23x.ulc_gap, lab), 4))
# the gate labels by the reference period; by origin month instead:
for feature in ['ulc_sameq', 'import_mom', 'ppi_mom', 'fx_news']:
    lab2 = pd.Series([int(o[5:7]) for o in x.index], index=x.index)
    print(f'   {feature}: share explained by ORIGIN calendar month (12 groups, n={int(x[feature].notna().sum())}) = {gates.seasonal_share(x[feature], lab2):.4f}; chance level about {11 / (x[feature].notna().sum() - 1):.4f}')

# coefficient gates recomputed
K = pd.read_csv(FINAL / 'coefficient_contributions.csv', **rd); CG = pd.read_csv(EVAL / 'gate_coefficient_signs.csv', **rd); worst = 0.
for (m, b, f), g in K.groupby(['model', 'band', 'feature']):
    theirs = CG[(CG.model == m) & (CG.band == b) & (CG.feature == f)].iloc[0]
    mine = float((g.coefficient.abs() < 1e-10).mean()) if g.kind.iloc[0] == 'positive' else float((g.coefficient < -1e-10).mean())
    worst = max(worst, abs(mine - theirs.share))
R.check('E1 coefficient gates (on-bound share for the signed fit, negative share otherwise) equal gate_coefficient_signs.csv', worst < 1e-15)
applied_only = K[K.applied & K.kind.eq('ridge')].groupby(['model', 'band', 'feature']).coefficient.apply(lambda c: float((c < -1e-10).mean()))
print('   note: shares above pool applied fits and unapplied diagnostic fits (alpha fixed at 3). Wrong-sign share among APPLIED fits only, joint model:')
print(applied_only.loc['PRESS_JOINT_R23B'].round(3).to_string().replace('\n', '\n   '))

# ------------------------------------------------------------------ E2 circular bootstrap
R.check('E2 block rule 12 / 6 / none', [bootstrap.block_length(n) for n in (19, 23, 24, 47, 48, 88)] == [None, None, 6, 6, 12, 12])
worst_inc = 0.
for n, block in [(75, 12), (88, 12), (25, 6), (28, 6)]:                       # the supports that occur in the delivered table
    rng = np.random.default_rng(11); draws = 400000
    starts = rng.integers(0, n, size=(draws, int(np.ceil(n / block)))); index = ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    inclusion = np.bincount(index.ravel(), minlength=n) / index.size * n; worst_inc = max(worst_inc, np.abs(inclusion - 1).max())
R.check('E2 the index rule gives every origin the same inclusion probability, also when n is not a multiple of the block (400,000 draws)', worst_inc < .01, f'max relative deviation={worst_inc:.4f}')
n = 75; block = 12; draws = 2000; rng = np.random.default_rng(1509)
starts = rng.integers(0, n, size=(draws, int(np.ceil(n / block)))); index = ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
inclusion = np.bincount(index.ravel(), minlength=n) / index.size
print(f'   at the delivered 2,000 draws and seed the realised inclusion still varies by up to {np.abs(inclusion * n - 1).max():.1%} between origins (Monte Carlo noise, not bias)')
values = np.arange(n, dtype=float); out = bootstrap.circular_block_bootstrap(values, origins=pd.period_range('2019-05', periods=n, freq='M').astype(str))
R.check('E2 function reproduces from its declared index rule', abs(out['bootstrap_mean'] - values[index].mean(axis=1).mean()) < 1e-12 and abs(out['ci_low'] - np.quantile(values[index].mean(axis=1), .025)) < 1e-12)
gap = bootstrap.circular_block_bootstrap(np.arange(30.), origins=[*pd.period_range('2019-05', periods=15, freq='M').astype(str), *pd.period_range('2020-09', periods=15, freq='M').astype(str)])
R.check('E2 non-contiguous origins are refused', gap['status'] == 'noncontiguous_origins' and np.isnan(gap['ci_low']))
unsorted = bootstrap.circular_block_bootstrap(np.arange(30.), origins=list(pd.period_range('2019-05', periods=30, freq='M').astype(str))[::-1])
R.check('E2 reversed (unsorted) origins are refused rather than resampled as if contiguous', unsorted['status'] == 'noncontiguous_origins')
B = pd.read_csv(EVAL / 'primary_support_circular_bootstrap.csv', **rd); P = pd.read_csv(EVAL / 'primary_rows.csv', **rd)
R.check('E2 delivered bootstrap table: block 12 iff n>=48, 6 iff 24<=n<48, no interval below 24; all supports contiguous',
        ((B.block == 12) == (B.n >= 48)).all() and ((B.block == 6) == ((B.n >= 24) & (B.n < 48))).all() and (B.block.isna() == (B.n < 24)).all()
        and (B.ci_low.isna() == (B.n < 24)).all() and not B.status.eq('noncontiguous_origins').any())
worst = 0.; worst_ci = 0.; outside = 0
for r in B[B.h.isin([3, 6, 12])].itertuples():
    col = ('yy_exante', 'yy_actual') if r.metric == 'headline_yy' else ('core_cumulative_log_forecast', 'core_cumulative_log_actual')
    g = P[(P.h == r.h) & ((P.origin >= '2024-01') if r.sample == 'origins_2024plus' else True)]
    e = g.pivot(index='origin', columns='model', values=col[0]).sub(g.drop_duplicates('origin').set_index('origin')[col[1]], axis=0)
    d = (e[r.model] ** 2 - e['STATE_FAST_R15'] ** 2).to_numpy(); worst = max(worst, abs(d.mean() - r.mean_loss_difference))
    if r.n >= 24:
        rng = np.random.default_rng(99); b = 12 if r.n >= 48 else 6                # own seed: intervals must agree up to Monte Carlo error
        st = rng.integers(0, r.n, size=(4000, int(np.ceil(r.n / b)))); ix = ((st[:, :, None] + np.arange(b)) % r.n).reshape(4000, -1)[:, :r.n]
        mine = np.quantile(d[ix].mean(axis=1), [.025, .975]); width = r.ci_high - r.ci_low
        worst_ci = max(worst_ci, max(abs(mine[0] - r.ci_low), abs(mine[1] - r.ci_high)) / width)
        outside += not (r.ci_low <= r.mean_loss_difference <= r.ci_high)
R.check('E2 mean loss differences at h3/h6/h12 equal own MSE differences on the primary support', worst < 1e-12, f'max abs diff={worst:.3e}')
R.check('E2 intervals agree with an own-seed replication within 15% of the interval width; no point estimate outside its own interval', worst_ci < .15 and outside == 0, f'max endpoint gap / width={worst_ci:.3f}; outside={outside}')

# ------------------------------------------------------------------ E3 monthly block errors
native = pd.read_csv(FINAL / 'native_forecasts.csv', **rd)
actual = pd.read_csv(ROOT / 'output/research_r14b/attribution/actual_component_targets.csv', **rd); actual.index = pd.PeriodIndex(actual.iloc[:, 0], freq='M')
monthly = attribution.monthly_block_errors(native, actual); parts = ['e_' + p for p in attribution.PARTS]
done = monthly[monthly.e_total.notna() & monthly[parts].notna().all(axis=1)]
R.check('E3 monthly parts (h0, five blocks, wedge) sum to the headline monthly error', (done[parts].sum(axis=1) - done.e_total).abs().max() < 1e-12)
h0 = monthly[monthly.h.eq(0)]
R.check('E3 h0 is its own bucket: at h0 every block and the wedge are zero and e_h0 = e_total; zero elsewhere', (h0[[p for p in parts if p != 'e_h0']] == 0).all().all() and (h0.e_h0 == h0.e_total).all() and (monthly[monthly.h.gt(0)].e_h0 == 0).all())
own = native.merge(actual[['core', 'food']].rename(columns=lambda c: 'a_' + c), left_on=pd.PeriodIndex(native.target, freq='M'), right_index=True, how='left') if False else None
chk = native[native.h.gt(0)].copy(); tg = pd.PeriodIndex(chk.target, freq='M')
for blk, wcol in attribution.BLOCKS.items():
    chk['mine_' + blk] = chk[wcol].to_numpy() * (chk['value_' + blk].to_numpy() - actual[blk].reindex(tg).to_numpy())
mm = monthly.merge(chk[['origin', 'model', 'h', *['mine_' + b for b in attribution.BLOCKS]]], on=['origin', 'model', 'h'])
R.check('E3 block error = weight x (forecast - realised block rate) on every h>0 row', max((mm['e_' + b] - mm['mine_' + b]).abs().max() for b in attribution.BLOCKS) < 1e-15)
cum = monthly.sort_values(['model', 'origin', 'h']); worstc = 0.
for p in [*attribution.PARTS, 'total']:
    mine = cum.groupby(['model', 'origin'])['e_' + p].transform(lambda s: np.cumsum(s.to_numpy()))
    both = mine.notna() & cum['c_' + p].notna(); worstc = max(worstc, (mine[both] - cum.loc[both, 'c_' + p]).abs().max())
    assert (mine.isna() == cum['c_' + p].isna()).all()
R.check('E3 cumulative parts = running sums from h0, a missing month propagates', worstc < 1e-12)
wedge = monthly[monthly.h.gt(0)].e_wedge.dropna()
print(f'   wedge (residual) monthly error: mean {wedge.mean():+.4f}, RMS {np.sqrt((wedge ** 2).mean()):.4f} pp; block table is of the cumulative price-LEVEL error, h0 included at every H')
# how close is the "sum of monthly errors" to the annual-rate error it is said to approximate?
F = pd.read_csv(FINAL / 'forecasts.csv', **rd); j = monthly.merge(F[['origin', 'model', 'h', 'yy_exante', 'yy_actual']], on=['origin', 'model', 'h'])
j = j[j.model.eq('STATE_FAST_R15') & j.yy_actual.notna() & j.c_total.notna()]; j['approx'] = np.where(j.h.eq(12), j.c_total - j.c_h0, j.c_total); j['err'] = j.yy_exante - j.yy_actual
for h in (6, 12):
    z = j[j.h.eq(h)]; print(f'   FAST h{h}: RMS annual-rate error {np.sqrt((z.err ** 2).mean()):.3f} against RMS of summed monthly errors {np.sqrt((z.approx ** 2).mean()):.3f}; RMS gap {np.sqrt(((z.err - z.approx) ** 2).mean()):.3f}; correlation {z.err.corr(z.approx):.4f}')

# ------------------------------------------------------------------ E4 quarter attribution
fast = monthly[monthly.model.eq('STATE_FAST_R15') & monthly.origin.eq('2022-04')].set_index('h')
qa = attribution.quarter_attribution(monthly, 'STATE_FAST_R15', '2022-04', '2022Q2')          # April (h0), May (h1), June (h2)
cols = ['c_' + p for p in attribution.PARTS]
R.check('E4 quarter fully inside the path: mean of the three cumulative rows', np.allclose(qa[cols].to_numpy(float), fast.loc[[0, 1, 2], cols].to_numpy(float).mean(axis=0), atol=1e-15))
qb = attribution.quarter_attribution(monthly, 'STATE_FAST_R15', '2022-05', '2022Q2')          # April is history, May h0, June h1
fb = monthly[monthly.model.eq('STATE_FAST_R15') & monthly.origin.eq('2022-05')].set_index('h')
R.check('E4 months before the origin contribute zero', np.allclose(qb[cols].to_numpy(float), (fb.loc[[0, 1], cols].to_numpy(float).sum(axis=0)) / 3, atol=1e-15))
qc = attribution.quarter_attribution(monthly, 'STATE_FAST_R15', '2022-04', '2023Q2')          # h12, h13, h14 -> beyond the path
R.check('E4 quarter beyond h12 returns None', qc is None)
qd = attribution.quarter_attribution(monthly, 'STATE_FAST_R15', '2022-06', '2023Q2')          # h10, h11, h12
fd = monthly[monthly.model.eq('STATE_FAST_R15') & monthly.origin.eq('2022-06')].set_index('h'); rows = fd.loc[[10, 11, 12], cols].to_numpy(float).copy(); rows[2, 0] = 0.
R.check('E4 the h0 contribution is dropped at h12 only, and c_total is the sum of the parts', np.allclose(qd[cols].to_numpy(float), rows.mean(axis=0), atol=1e-15) and abs(qd['c_total'] - rows.mean(axis=0).sum()) < 1e-15)
CA = pd.read_csv(EVAL / 'cnb_call_attribution.csv', **rd); ok = CA.approx_error.notna()
print(f'   call attribution: {int(ok.sum())} of {len(CA)} calls attributed; model_error vs approx_error correlation {CA.model_error[ok].corr(CA.approx_error[ok]):.4f}, RMS gap {np.sqrt(((CA.model_error - CA.approx_error)[ok] ** 2).mean()):.3f} pp, RMS error {np.sqrt((CA.model_error[ok] ** 2).mean()):.3f} pp')

# ------------------------------------------------------------------ E5 seasonal naive
import r17_common as c
published = c.publication_dates(actual.index); clocks = native[native.h.eq(0)].drop_duplicates('origin').set_index('origin').as_of_utc; bad = []
for origin in ['2019-02', '2021-06', '2023-01', '2026-07']:
    t = pd.Period(origin, 'M'); clock = pd.Timestamp(clocks[origin]).tz_convert('Europe/Prague').tz_localize(None)
    for block in attribution.BLOCKS:
        clean = benchmarks.seasonal_naive_path(actual[block], published, origin, clocks[origin])
        dirty_series = actual[block].copy(); dirty_series[(dirty_series.index >= t) | (published > clock).to_numpy() | published.isna().to_numpy()] = 1e12
        dirty = benchmarks.seasonal_naive_path(dirty_series, published, origin, clocks[origin])
        mine = {}
        for h in range(1, 13):
            same = [actual[block][p] for p in actual.index if p < t and p.month == (t + h).month and published[p] <= clock and np.isfinite(actual[block][p])]
            mine[h] = float(np.mean(same[-3:])) if len(same) >= 3 else np.nan
        if clean != dirty or any(not (np.isclose(clean[h], mine[h]) or (np.isnan(clean[h]) and np.isnan(mine[h]))) for h in mine):
            bad.append((origin, block))
R.check('E5 seasonal naive: own rebuild equal, and unchanged when every month at or after the origin or unpublished at the clock is poisoned', not bad, str(bad))

# ------------------------------------------------------------------ E6 lead baselines, own rebuild for the report clock at 0.30
cnb = pd.read_csv(ROOT / 'data/cnb_mpr_cpi_quarterly.csv'); CL = pd.read_csv(EVAL / 'cnb_clocks.csv'); LS = pd.read_csv(EVAL / 'cnb_lead_summary.csv', **rd); LP = pd.read_csv(EVAL / 'cnb_lead_pairs.csv', **rd)
inp = pd.read_csv(ROOT / 'output/independent_path_frozen_inputs.csv', **rd); inp.index = pd.PeriodIndex(inp.iloc[:, 0], freq='M')
yy = 100 * np.expm1(np.log1p(inp.headline_mm / 100).rolling(12).sum())
fc = cnb[cnb.is_forecast.astype(str).str.lower().eq('true')]; cnbf = {(r.report_date, r.quarter): float(r.value) for r in fc.itertuples()}
reports = sorted(cnb.report_date.unique()); nxt = dict(zip(reports, reports[1:])); position = {d: i for i, d in enumerate(reports)}
origin_at = CL[CL.clock.eq('report')].set_index('report_date').origin
rows = []
for report in reports:
    o = pd.Period(origin_at[report], 'M'); last = yy[o - 1]
    for q in sorted(k[1] for k in cnbf if k[0] == report):
        Q = pd.Period(q, 'Q'); months = pd.period_range(Q.asfreq('M', 'start'), Q.asfreq('M', 'end'), freq='M')
        realised = float(np.mean([yy.get(m, np.nan) for m in months])); realised = realised if np.isfinite(realised) else np.nan
        for model, constant in [('CONST_2', 2.), ('RW_YY', last)]:
            value = float(np.mean([yy[m] if m < o else constant for m in months]))
            old = cnbf[(report, q)]; new = cnbf.get((nxt.get(report), q), np.nan); dev = value - old
            future = report in nxt and Q > pd.Period(nxt[report], 'Q'); eligible = bool(future and np.isfinite(new))
            rows.append(dict(model=model, report_date=report, quarter=q, forecast=value, old=old, new=new, dev=dev, call=abs(dev) >= .30 - 1e-12, eligible=eligible, realised=realised))
mine = pd.DataFrame(rows)
theirs = LP[(LP.clock == 'report') & (LP.threshold == .3) & LP.model.isin(['CONST_2', 'RW_YY'])]
both = mine.merge(theirs, on=['model', 'report_date', 'quarter'], suffixes=('', '_t'))
R.check('E6 CONST_2 and RW_YY quarter values equal the delivered ones on every report-clock pair', len(both) == len(mine) == len(theirs) and (both.forecast - both.forecast_t).abs().max() < 1e-12, f'pairs={len(mine)}, max abs diff={(both.forecast - both.forecast_t).abs().max():.3e}')
R.check('E6 call, eligibility and realised flags equal', (both.call == both.call_t).all() and (both.eligible == both.revision_eligible).all() and ((both.realised - both.realised_t).abs().fillna(0).max() < 1e-12) and (both.realised.isna() == both.realised_t.isna()).all())
mine = mine.sort_values(['model', 'quarter', 'report_date']).reset_index(drop=True); mine['start'] = False
for _, g in mine.groupby(['model', 'quarter']):
    prev = None; sign = None
    for i, r in g.iterrows():
        if r.call:
            mine.loc[i, 'start'] = prev is None or position[r.report_date] != prev + 1 or np.sign(r.dev) != sign
            prev = position[r.report_date]; sign = np.sign(r.dev)
        else:
            prev = None; sign = None
bad = []
for model, g in mine.groupby('model'):
    s = g[g.start]; e = s[s.eligible]; calls = e[e.call]; mature = calls[calls.realised.notna()]
    rev = calls.new - calls.old; agree = (rev != 0) & (np.sign(rev) == np.sign(calls.dev)); gain = (calls.old - calls.forecast).abs() - (calls.new - calls.forecast).abs()
    confirmed = agree & (gain >= .15 - 1e-12); absgain = (mature.old - mature.realised).abs() - (mature.forecast - mature.realised).abs()
    own = dict(considered_pairs=len(s), all_calls=int(s.call.sum()), calls_without_eligible_revision=int((s.call & ~s.eligible).sum()), n_pairs=len(e), n_reports=e.report_date.nunique(),
               n_target_quarters=e.quarter.nunique(), calls=len(calls), revision_direction_matches=int(agree.sum()), revision_confirmations=int(confirmed.sum()), mature_calls=len(mature),
               material_gains=int((absgain >= .15 - 1e-12).sum()), material_losses=int((absgain <= -.15 + 1e-12).sum()),
               joint_successes=int((confirmed.reindex(mature.index) & (absgain >= .15 - 1e-12)).sum()), unconfirmed_calls=int((~confirmed).sum()), mean_abs_error_gain=float(absgain.mean()))
    t = LS[(LS.model == model) & (LS.clock == 'report') & (LS.threshold == .3) & (LS['sample'] == 'full') & (LS.scope == 'first_call_episodes')].iloc[0]
    diff = {k: (v, t[k]) for k, v in own.items() if abs(v - t[k]) > 1e-12}
    print(f'   {model}: ' + ', '.join(f'{k}={v}' if not isinstance(v, float) else f'{k}={v:.4f}' for k, v in own.items()))
    if diff:
        bad.append((model, diff))
R.check('E6 CONST_2 and RW_YY first-call-episode summary rows (report clock, 0.30, full) equal cnb_lead_summary.csv on all 15 columns', not bad, str(bad))
# ---- E7 the whole lead table, every model, both clocks, both thresholds, from cnb_quarter_projections.csv and own rules
QP = pd.read_csv(EVAL / 'cnb_quarter_projections.csv', **rd); QP = QP[QP.model.ne('cnb')]
FC = pd.read_csv(FINAL / 'forecasts.csv', **rd); paths = {(m, o_): dict(zip(g.target, g.yy_exante)) for (m, o_), g in FC.groupby(['model', 'origin'])}
worst_q = 0.
for r in QP[QP.model.isin(['STATE_FAST_R15', 'PRESS_JOINT_R23B', 'PRESS_ULC_R23B'])].itertuples():
    Q = pd.Period(r.quarter, 'Q'); o_ = pd.Period(r.origin, 'M'); months = pd.period_range(Q.asfreq('M', 'start'), Q.asfreq('M', 'end'), freq='M')
    vals = [yy.get(mth, np.nan) if mth < o_ else paths[(r.model, r.origin)].get(str(mth), np.nan) for mth in months]
    mine_q = float(np.mean(vals)) if np.isfinite(vals).all() else np.nan
    if not (np.isnan(mine_q) and np.isnan(r.forecast)):
        worst_q = max(worst_q, abs(mine_q - r.forecast))
R.check('E7 model quarter values (FAST, joint, ULC) = mean of known history before the origin and the same-origin annual path', worst_q < 1e-12, f'max abs diff={worst_q:.3e}')
every = pd.concat([QP[['model', 'clock', 'report_date', 'quarter', 'forecast', 'realised']], LP[LP.is_baseline & LP.threshold.eq(.3)][['model', 'clock', 'report_date', 'quarter', 'forecast', 'realised']]], ignore_index=True)
bad7 = []; n_rows = 0
for threshold in (.3, .5):
    z = every.copy(); z['old'] = [cnbf.get((d, q), np.nan) for d, q in zip(z.report_date, z.quarter)]; z['new'] = [cnbf.get((nxt.get(d), q), np.nan) for d, q in zip(z.report_date, z.quarter)]
    z['dev'] = z.forecast - z.old; z['call'] = z.dev.abs() >= threshold - 1e-12
    z['eligible'] = np.array([d in nxt and pd.Period(q, 'Q') > pd.Period(nxt[d], 'Q') for d, q in zip(z.report_date, z.quarter)], dtype=bool) & np.isfinite(z[['old', 'new', 'forecast']].to_numpy(float)).all(axis=1)
    z = z.sort_values(['model', 'clock', 'quarter', 'report_date']).reset_index(drop=True); start = np.zeros(len(z), bool)
    for _, g in z.groupby(['model', 'clock', 'quarter']):
        prev = None; sign = None
        for i, r in g.iterrows():
            if r.call:
                start[i] = prev is None or position[r.report_date] != prev + 1 or np.sign(r.dev) != sign; prev = position[r.report_date]; sign = np.sign(r.dev)
            else:
                prev = None; sign = None
    z['start'] = start
    for (model, clock), g in z.groupby(['model', 'clock']):
        for sample, s_ in [('full', g), ('reports_2024plus', g[g.report_date >= '2024-01-01'])]:
            for scope, w_ in [('all_pairs', s_), ('first_call_episodes', s_[s_.start])]:
                e_ = w_[w_.eligible]; calls = e_[e_.call]; mature = calls[calls.realised.notna()]
                rev = calls.new - calls.old; agree = (rev != 0) & (np.sign(rev) == np.sign(calls.dev)); gain = (calls.old - calls.forecast).abs() - (calls.new - calls.forecast).abs(); conf = agree & (gain >= .15 - 1e-12)
                ag = (mature.old - mature.realised).abs() - (mature.forecast - mature.realised).abs()
                own = dict(considered_pairs=len(w_), all_calls=int(w_.call.sum()), n_pairs=len(e_), calls=len(calls), revision_direction_matches=int(agree.sum()), revision_confirmations=int(conf.sum()), mature_calls=len(mature),
                           material_gains=int((ag >= .15 - 1e-12).sum()), material_losses=int((ag <= -.15 + 1e-12).sum()), joint_successes=int((conf.reindex(mature.index) & (ag >= .15 - 1e-12)).sum()))
                t_ = LS[(LS.model == model) & (LS.clock == clock) & (LS.threshold == threshold) & (LS['sample'] == sample) & (LS.scope == scope)].iloc[0]; n_rows += 1
                if any(own[k] != t_[k] for k in own):
                    bad7.append((model, clock, threshold, sample, scope, {k: (own[k], t_[k]) for k in own if own[k] != t_[k]}))
R.check(f'E7 all {n_rows} rows of cnb_lead_summary.csv (14 models x 2 clocks x 2 thresholds x 2 samples x 2 scopes) reproduce with own call, eligibility, episode and outcome rules', not bad7 and n_rows == len(LS), str(bad7[:3]))
# clock honesty of the base rates: the last known annual rate must be published at the snapshot clock
late = []
for r in CL[CL.origin.notna()].itertuples():
    o = pd.Period(r.origin, 'M'); stamp = pd.Timestamp(r.as_of_utc).tz_convert('Europe/Prague').tz_localize(None)
    if not published.get(o - 1, pd.NaT) <= stamp:
        late.append((r.clock, r.report_date))
R.check('E6 base rates use only annual rates published at the snapshot clock (month origin-1 released before as_of)', not late, str(late))
R.done()
