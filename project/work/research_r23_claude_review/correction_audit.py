"""Claude review of R23, probe 2: what the fitted R23 corrections actually consisted of.

Read-only. Writes nothing. Reads only the delivered `output/research_r23/final` files.

Run from the repository root:
    python work/research_r23_claude_review/correction_audit.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
final = ROOT / 'output/research_r23/final'; ev = final / 'evaluation'
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60); pd.set_option('display.max_rows', 300)
c = pd.read_csv(final / 'coefficient_contributions.csv')
fits = [json.loads(line) for line in (final / 'fits.jsonl').read_text().splitlines()]

print('1. Share of (origin, band) cells where a sign-restricted coefficient sits exactly on its zero bound:')
for m in ['GAP_DOMESTIC_R23', 'GAP_IMPORTED_R23', 'GAP_JOINT_R23']:
    z = c[c.model.eq(m) & c.feature.ne('intercept')]
    print(f'   {m:18s}', z.groupby('feature').coefficient.apply(lambda s: (s.abs() < 1e-10).mean()).round(3).to_dict())
z = c[c.model.eq('GAP_FREE_R23') & c.feature.ne('intercept')]
print('   Unrestricted ridge, share of cells with a NEGATIVE coefficient:',
      z.groupby('feature').coefficient.apply(lambda s: (s < 0).mean()).round(3).to_dict())

print('\n2. Mean absolute 12-month cumulative log-core contribution, by term (pp):')
for m in ['GAP_CALIBRATION_R23', 'GAP_DOMESTIC_R23', 'GAP_IMPORTED_R23', 'GAP_JOINT_R23']:
    t = (c[c.model.eq(m)].groupby(['origin', 'feature']).monthly_log_core_correction.sum() * 3).unstack('feature')
    print(f'   {m:20s}', t.abs().mean().round(3).to_dict())

comp = pd.read_csv(ev / 'component_outcomes.csv')
f = comp[comp.model.eq('STATE_FAST_R15') & comp.block.eq('core') & comp.h.eq(12)].set_index('origin')
need = (f.cumulative_log_actual - f.cumulative_log_forecast).rename('needed')
t = pd.concat([need] + [pd.Series({x['origin']: float(np.sum(x['paths'][m])) for x in fits}, name=m)
                        for m in ['GAP_CALIBRATION_R23', 'GAP_JOINT_R23', 'GAP_FREE_R23']], axis=1).dropna()
print(f'\n3. Correction FAST needed (realised minus FAST, 12-month log core) against the correction applied, {len(t)} matured origins:')
for lab, a, b in [('2019-02..2020-12', '2019-02', '2020-12'), ('2021-01..2022-04', '2021-01', '2022-04'),
                  ('2022-05..2023-08', '2022-05', '2023-08'), ('2023-09..2025-07', '2023-09', '2025-07')]:
    z = t[(t.index >= a) & (t.index <= b)]
    print(f'   {lab}: n={len(z):2d}  needed {z.needed.mean():6.2f} | calibration {z.GAP_CALIBRATION_R23.mean():5.2f} | joint {z.GAP_JOINT_R23.mean():5.2f} | free {z.GAP_FREE_R23.mean():5.2f}')
print('   correlation(needed, applied):', {m: round(float(t.needed.corr(t[m])), 2) for m in t.columns[1:]})

prov = pd.read_csv(final / 'feature_provenance.csv')
refq = prov[prov.feature.eq('ulc_gap')].set_index('origin').reference.str[-1].astype(float)
j = c[c.model.eq('GAP_JOINT_R23')]
u = (j[j.feature.eq('ulc_gap')].groupby('origin').monthly_log_core_correction.sum() * 3).rename('ulc')
tot = (j.groupby('origin').monthly_log_core_correction.sum() * 3).rename('total')
z = pd.concat([u, tot, refq.rename('refq')], axis=1).dropna(); z = z[z.index >= '2024-01']
m = z.groupby('refq').ulc.transform('mean')
print(f'\n4. Joint candidate, origins from 2024-01 (n={len(z)}): ULC term / total absolute correction = {z.ulc.abs().sum() / z.total.abs().sum():.2f};')
print(f'   share of the ULC term\'s variance explained by the reference quarter-of-year = {1 - ((z.ulc - m) ** 2).sum() / ((z.ulc - z.ulc.mean()) ** 2).sum():.3f};')
print('   mean ULC term by reference quarter:', z.groupby('refq').ulc.mean().round(3).to_dict())

L = pd.read_csv(ev / 'cnb_lead_pairs.csv')
k = L[L.report_date.eq('2024-08-08') & L.quarter.eq('2025Q2') & L.clock.eq('report') & L.threshold.eq(.3) & L.model.isin(['STATE_FAST_R15', 'GAP_JOINT_R23'])]
print('\n5. The August 2024 -> 2025Q2 case (the only joint success that FAST does not also score):')
print(k[['model', 'forecast', 'cnb_current', 'cnb_next', 'realised', 'revision_distance_gain', 'revision_confirmed', 'joint_success']].round(4).to_string(index=False))
o = '2024-06'
print('   snapshot origin 2024-06; joint 12-month contributions:',
      (j[j.origin.eq(o)].groupby('feature').monthly_log_core_correction.sum() * 3).round(4).to_dict())
print('   ulc_gap reading used:', prov[prov.origin.eq(o) & prov.feature.eq('ulc_gap')][['reference', 'value']].round(2).to_dict('records'))

b = pd.read_csv(ev / 'primary_support_bootstrap.csv'); b = b[b.h.eq(12) & b['sample'].eq('origins_2024plus')]
b['mean_outside_own_interval'] = (b.mean_loss_difference < b.ci_low) | (b.mean_loss_difference > b.ci_high)
print('\n6. Recent-sample h12 bootstrap rows (n=19, block 12, 8 block starts): point estimate outside its own interval?')
print(b[['model', 'mean_loss_difference', 'ci_low', 'ci_high', 'bootstrap_probability_improvement', 'mean_outside_own_interval']].round(4).to_string(index=False))
