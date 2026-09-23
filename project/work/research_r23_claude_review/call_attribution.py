"""Claude review of R23, probe 3: why the CNB disagreement calls fail, and where path error sits.

Read-only. Writes nothing. Reads only the delivered `output/research_r23/final` files.

For a frozen origin o and target month T = o+h, the annual-rate error is approximately the sum
of the monthly headline errors over the forecast months o..T (known history cancels). Each
monthly error = sum over blocks of weight x (forecast - actual) + the reconciliation residual.
The h0 month is the independent nowcast and is kept as its own bucket.

Run from the repository root:
    python work/research_r23_claude_review/call_attribution.py [MODEL]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
final = ROOT / 'output/research_r23/final'; ev = final / 'evaluation'
pd.set_option('display.width', 320); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 400)
MODEL = sys.argv[1] if len(sys.argv) > 1 else 'STATE_FAST_R15'
W = {'core': 'weight_core', 'food': 'weight_food', 'fuel': 'weight_fuel', 'administered': 'weight_administered', 'alcohol_tobacco': 'weight_alc'}
nat_all = pd.read_csv(final / 'native_forecasts.csv'); comp_all = pd.read_csv(ev / 'component_outcomes.csv')
nat = nat_all[nat_all.model.eq(MODEL)]; comp = comp_all[comp_all.model.eq(MODEL)]

m = nat[['origin', 'h', 'target', 'mm_forecast', 'mm_actual', *W.values()]].copy()
for b, w in W.items():
    z = comp[comp.block.eq(b)][['origin', 'h', 'mm_forecast', 'mm_actual']].rename(columns={'mm_forecast': 'f', 'mm_actual': 'a'})
    m = m.merge(z, on=['origin', 'h'], how='left'); m['e_' + b] = np.where(m.h.eq(0), 0., m[w] * (m.f - m.a)); m = m.drop(columns=['f', 'a'])
m['e_total'] = m.mm_forecast - m.mm_actual
m['e_h0'] = np.where(m.h.eq(0), m.e_total, 0.)
m['e_wedge'] = np.where(m.h.eq(0), 0., m.e_total - m[['e_' + b for b in W]].sum(axis=1))
cols = ['e_h0', *['e_' + b for b in W], 'e_wedge', 'e_total']
m = m.sort_values(['origin', 'h']); m[['c' + c[1:] for c in cols]] = m.groupby('origin')[cols].cumsum()

print(f'1. {MODEL}: RMS of the cumulative weighted block error over h1..H (pp of headline), by era')
for H in (6, 12):
    z = m[m.h.eq(H)].dropna(subset=['c_total'])
    for lab, w in [('full', z), ('origins 2024+', z[z.origin >= '2024-01'])]:
        print(f'   H={H:2d} {lab:14s} n={len(w):2d}', {b: round(float(np.sqrt((w["c_" + b] ** 2).mean())), 2) for b in W},
              '| bias', {b: round(float(w['c_' + b].mean()), 2) for b in W})

L = pd.read_csv(ev / 'cnb_lead_pairs.csv'); ck = pd.read_csv(ev / 'cnb_clocks.csv')
L = L[L.model.eq(MODEL) & L.clock.eq('report') & L.threshold.eq(.3) & L.call & L.revision_eligible & L.episode_start & L.realised.notna()]
L = L.merge(ck[ck.clock.eq('report')][['report_date', 'origin']], on='report_date'); rows = []
for r in L.itertuples():
    q = pd.Period(r.quarter, 'Q'); months = [str(p) for p in pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M')]
    a = m[m.origin.eq(r.origin) & m.target.isin(months)][['c' + c[1:] for c in cols]].mean()
    rows.append(dict(report=r.report_date, quarter=r.quarter, origin=r.origin, dev_vs_cnb=r.deviation, model_err=r.forecast - r.realised,
                     cnb_err=r.cnb_current - r.realised, outcome='GAIN' if r.material_gain else 'LOSS' if r.material_loss else '~',
                     approx=a.c_total, h0=a.c_h0, core=a.c_core, food=a.c_food, fuel=a.c_fuel, admin=a.c_administered, alc=a.c_alcohol_tobacco, wedge=a.c_wedge))
T = pd.DataFrame(rows)
print(f'\n2. {MODEL}: every matured first-call episode (report clock, .30pp), error attribution in pp of annual CPI')
print(T.round(2).to_string(index=False))
print('   approximation check: corr(model_err, approx) = %.3f, mean abs gap = %.2f' % (T.model_err.corr(T.approx), (T.model_err - T.approx).abs().mean()))
parts = ['h0', 'core', 'food', 'fuel', 'admin', 'alc', 'wedge']
for lab, z in [('losses, all', T[T.outcome.eq('LOSS')]), ('losses, reports from 2023', T[T.outcome.eq('LOSS') & (T.report >= '2023-01-01')]),
               ('losses, reports from 2025', T[T.outcome.eq('LOSS') & (T.report >= '2025-01-01')]), ('gains', T[T.outcome.eq('GAIN')])]:
    if len(z):
        p = z[parts].mul(np.sign(z.model_err), axis=0)
        print(f'   {lab:26s} n={len(z):2d} mean contribution in the direction of the miss:', p.mean().round(2).to_dict())

P = pd.read_csv(ev / 'cnb_quarter_projections.csv'); P = P[P.clock.eq('report')]
cn = P[P.model.eq('cnb')][['report_date', 'quarter', 'forecast']].rename(columns={'forecast': 'cnb'})
z = P[P.model.eq(MODEL)].merge(cn, on=['report_date', 'quarter']); z['gap'] = z.forecast - z.cnb; z = z[np.isfinite(z.gap)]; z['year'] = z.report_date.str[:4]
print(f'\n3. {MODEL}: mean (model - CNB) by report year and quarters ahead, and share of gaps above zero')
print(z.pivot_table(index='year', columns='quarters_ahead', values='gap', aggfunc='mean').round(2).to_string())
print(z.pivot_table(index='year', columns='quarters_ahead', values='gap', aggfunc=lambda s: (s > 0).mean()).round(2).to_string())

print(f'   matured first calls: {len(T)} episodes from {T.report.nunique()} reports; losses from {T[T.outcome.eq("LOSS")].report.nunique()}, gains from {T[T.outcome.eq("GAIN")].report.nunique()};',
      f'upward calls {int((T.dev_vs_cnb > 0).sum())}, downward {int((T.dev_vs_cnb < 0).sum())} (matured only)')

# Does the gap three to four quarters ahead carry information about the next CNB revision or CNB's eventual error?
reports = sorted(cn.report_date.unique()); nxt = dict(zip(reports, reports[1:])); prv = dict(zip(reports[1:], reports))
cnb = cn.set_index(['report_date', 'quarter']).cnb; g = z.set_index(['report_date', 'quarters_ahead']).gap; rows = []
for r in z[z.quarters_ahead.isin([3, 4])].itertuples():
    new = cnb.get((nxt.get(r.report_date), r.quarter), np.nan)
    if not np.isfinite(new): continue
    hist = []; d = r.report_date
    for _ in range(4):                       # same-horizon gap at up to four earlier reports, known at the time
        d = prv.get(d)
        if d is None: break
        if np.isfinite(g.get((d, r.quarters_ahead), np.nan)): hist.append(g.get((d, r.quarters_ahead)))
    rows.append(dict(report=r.report_date, gap=r.gap, gap_less_trailing_mean=r.gap - np.mean(hist) if len(hist) >= 2 else np.nan,
                     revision=new - r.cnb, cnb_error=r.realised - r.cnb))
D = pd.DataFrame(rows)
print(f'\n3b. {MODEL}: gap three to four quarters ahead against the next CNB revision and CNB\'s eventual error (EXPLORATORY, small n)')
for lab, w in [('all reports', D), ('reports from 2023', D[D.report >= '2023-01-01'])]:
    for f in ['gap', 'gap_less_trailing_mean']:
        k = w[[f, 'revision', 'cnb_error']].dropna()
        hit = (np.sign(k[f]) == np.sign(k.cnb_error)).mean()
        print(f'   {lab:18s} {f:24s} n={len(k):2d} corr with revision {k[f].corr(k.revision):5.2f} | corr with CNB error {k[f].corr(k.cnb_error):5.2f} | sign hit on CNB error {hit:4.2f}')

print('\n4. Snapshot timing against the CNB information cutoff')
for mode in ('report', 'cutoff'):
    k = ck[ck.clock.eq(mode)].copy(); snap = pd.to_datetime(k['as_of_utc']).dt.tz_convert('Europe/Prague').dt.tz_localize(None).dt.normalize()
    knew = pd.to_datetime(k.cutoff_date) >= snap + pd.Timedelta(days=1)
    print(f'   {mode:6s} clock: {len(k)} rounds; CNB cutoff falls on or after the release of our h0 month in {int(knew.sum())};',
          f'median days from our snapshot to the CNB cutoff = {(pd.to_datetime(k.cutoff_date) - snap).dt.days.median():.0f}')

print('\n5. Food block of the shared path: cumulative log change forecast against a zero-change forecast')
f = comp_all[comp_all.model.eq('STATE_FAST_R15') & comp_all.block.eq('food')]
for H in (3, 6, 12):
    z = f[f.h.eq(H)].dropna(subset=['cumulative_log_forecast', 'cumulative_log_actual']); e = z.cumulative_log_forecast - z.cumulative_log_actual
    for lab, k in [('full', z.index), ('origins 2024+', z.index[z.origin >= '2024-01'])]:
        print(f'   h{H:<2d} {lab:14s} n={len(k):2d} model RMSE {np.sqrt((e[k] ** 2).mean()):5.2f} | zero-change RMSE {np.sqrt((z.cumulative_log_actual[k] ** 2).mean()):5.2f}',
              f'| bias {e[k].mean():5.2f} | corr(forecast, actual) {z.cumulative_log_forecast[k].corr(z.cumulative_log_actual[k]):5.2f}')
