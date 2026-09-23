"""R25: panel-estimated persistence of the FAST core trend, applied to the saved Czech FAST path.

Run from the repository root into a directory that does not exist yet:
    python -m tools.research_r25.run --output output/research_r25/final
"""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from data.cost_gaps_r23 import local
from data.hicp_panel_r25 import load as load_panel, SNAPSHOT
from models.cost_gaps_r23 import monthly_correction
from models.panel_persistence_r25 import (BANDS, MIN_PANEL_ROWS, MIN_OWN_ROWS, robust_norm, adjusted_band_means, country_rows,
                                          lambda_at, two_regime_at, czech_correction)

CONTROLS = ['STATE_FAST_R15', 'STABLE_LOCAL_CORE_R14B', 'DAMPED_P95_Q001_R16']
MODELS = ['CORE_PANEL_SHRINK_R25', 'CORE_PANEL_STATE_R25', 'CORE_OWN_SHRINK_R25', 'CORE_PANEL_SHRINK_FOODNORM_R25']
NATIVE = 'output/research_r21/path_anchor/native_forecasts.csv'
FOOD = 'output/research_r24/final/native_forecasts.csv'
SPEC = 'docs/implementation/R25_PANEL_PERSISTENCE_SPEC_2026-09-17.md'
CORE = 'tests/fixtures/cleanup/cnb_core_mm.csv'
CODE = ['models/panel_persistence_r25.py', 'models/core_trend_residual_r15.py', 'models/cost_gaps_r23.py', 'data/hicp_panel_r25.py', 'r17_common.py', 'tools/research_r25/run.py']


def czech_rows(core, dates, states):
    """The same row definition for Czechia, from the saved R15 states (control candidate and the norm audit)."""
    logs = 100 * np.log1p(core / 100); rows = []; norms = {}
    for origin, state in states.items():
        s = pd.Period(origin, 'M'); clock = local(state['as_of']); seasonal = {int(k): float(v) for k, v in state['seasonal'].items()}
        known = logs.loc[logs.index < s]; known = known[(dates.reindex(known.index) <= clock).to_numpy()]
        mu = robust_norm(known); norms[s] = mu; months = pd.period_range(s + 1, s + 12, freq='M')
        f = adjusted_band_means({s + int(h): float(v) for h, v in state['forecasts_log']['fast'].items()}, seasonal, months)
        r = adjusted_band_means(logs.to_dict(), seasonal, months)
        for b in BANDS:
            rows.append(dict(geo='CZ', origin=s, band=b, label_end=s + 3 * b, f=float(f[b - 1]), r=float(r[b - 1]), mu=mu))
    return pd.DataFrame(rows), pd.Series(norms)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); ap.add_argument('--limit', type=int)
    args = ap.parse_args(); out = args.output; out.mkdir(parents=True, exist_ok=False); start = time.perf_counter()
    rates, published, panel_manifest = load_panel()
    hashes = {name: c.sha(ROOT / name) for name in [*CODE, SPEC, NATIVE, FOOD, CORE, 'data/release_calendar_cz_cpi.csv', 'output/research_r15/states.json',
                                                   SNAPSHOT + '/manifest.json', SNAPSHOT + '/hicp_core_index.csv']}
    hashes.update(c.preserved_hashes())
    origins_q = pd.period_range('1999-03', rates.index.max(), freq='Q').asfreq('M', 'end')
    panel = pd.DataFrame([row for geo in rates.columns for row in country_rows(rates[geo], published, geo, origins_q)])
    print(f'R25 panel: {panel.geo.nunique()} countries, {panel.origin.nunique()} quarterly origins, {len(panel)} rows, {time.perf_counter() - start:.1f}s', flush=True)
    core = c.monthly(CORE, 'core'); dates = c.publication_dates(core.index); states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
    own, norms = czech_rows(core, dates, states); own_q = own[own.origin.dt.month % 3 == 0]
    panel.assign(origin=panel.origin.astype(str), label_end=panel.label_end.astype(str)).to_csv(out / 'panel_rows.csv', index=False)
    own.assign(origin=own.origin.astype(str), label_end=own.label_end.astype(str)).to_csv(out / 'czech_rows.csv', index=False)
    native = c.read(NATIVE); native = native[native.model.isin(CONTROLS)].copy()
    food = c.read(FOOD); food = food[food.model.eq('FOOD_NORM_SHIFT_R24') & food.h.gt(0)].set_index(['origin', 'h']).value_food
    clocks = native[native.model.eq(c.FAST) & native.h.eq(0)].set_index('origin').as_of_utc.to_dict()
    origins = sorted(clocks); origins = origins[:args.limit] if args.limit else origins; native = native[native.origin.isin(origins)]
    results = [native]; audit = []; statuses = []
    with (out / 'fits.jsonl').open('w', encoding='utf-8') as log:
        for i, origin in enumerate(origins):
            t = pd.Period(origin, 'M'); state = states[origin]; base = native[native.model.eq(c.FAST) & native.origin.eq(origin)].sort_values('h')
            if len(base) != 13 or base.h.duplicated().any():
                raise ValueError('Invalid baseline support')
            baseline = np.array([state['forecasts_log']['fast'][str(h)] for h in range(1, 13)])
            np.testing.assert_allclose(100 * np.log1p(base[base.h.gt(0)].value_core.to_numpy() / 100), baseline, atol=1e-10, rtol=0)
            mine = own[own.origin.eq(t)].set_index('band'); f_cz = mine.f.reindex(BANDS).to_numpy(); mu_cz = float(norms[t])
            record = dict(origin=origin, as_of=clocks[origin], mu_cz=mu_cz, f_cz=f_cz.tolist(), lambdas={}, corrections={}, status='estimated')
            if not np.isfinite(mu_cz) or not np.isfinite(f_cz).all():
                record['status'] = 'missing_czech_norm_or_state'
            single = [lambda_at(panel, b, t, MIN_PANEL_ROWS) for b in BANDS]; regime = [two_regime_at(panel, b, t, MIN_PANEL_ROWS) for b in BANDS]
            control = [lambda_at(own_q, b, t, MIN_OWN_ROWS) for b in BANDS]
            chosen = {'CORE_PANEL_SHRINK_R25': [s['lam'] for s in single],
                      'CORE_PANEL_STATE_R25': [(r['lam_small'] if abs(f_cz[k] - mu_cz) <= r['threshold'] else r['lam_large']) if r['status'] == 'estimated' else 1.
                                               for k, r in enumerate(regime)],
                      'CORE_OWN_SHRINK_R25': [s['lam'] for s in control]}
            chosen['CORE_PANEL_SHRINK_FOODNORM_R25'] = chosen['CORE_PANEL_SHRINK_R25']
            for b in BANDS:
                audit.append(dict(origin=origin, band=b, f_cz=f_cz[b - 1], mu_cz=mu_cz, deviation=f_cz[b - 1] - mu_cz, panel_lambda=single[b - 1]['lam'], panel_n=single[b - 1]['n'],
                                  panel_status=single[b - 1]['status'], regime_threshold=regime[b - 1]['threshold'], regime_lambda_small=regime[b - 1]['lam_small'],
                                  regime_lambda_large=regime[b - 1]['lam_large'], regime_used=chosen['CORE_PANEL_STATE_R25'][b - 1], own_lambda=control[b - 1]['lam'],
                                  own_n=control[b - 1]['n'], own_status=control[b - 1]['status']))
            for model in MODELS:
                if record['status'] == 'estimated':
                    bands = czech_correction(f_cz, mu_cz, chosen[model]); path = monthly_correction(bands)
                    rates_new = 100 * np.expm1((baseline + path) / 100)
                    if not np.isfinite(rates_new).all():
                        raise ArithmeticError('Nonfinite monthly core forecast')
                    frame = c.replace_block(base, 'core', dict(zip(range(1, 13), rates_new)))
                    if model.endswith('FOODNORM_R25'):
                        frame = c.replace_block(frame, 'food', {h: float(food[(origin, h)]) for h in range(1, 13)})
                    record['lambdas'][model] = [float(v) for v in chosen[model]]; record['corrections'][model] = path.tolist()
                else:
                    frame = base.copy()
                frame['model'] = model; frame['core_model_status'] = record['status']; frame['core_fallback_used'] = record['status'] != 'estimated'
                results.append(frame); statuses.append(dict(origin=origin, model=model, status=record['status']))
            log.write(json.dumps(record, allow_nan=False) + '\n')
            if i % 10 == 0 or i == len(origins) - 1:
                print(f'R25 {i + 1}/{len(origins)} {origin}: lambda={np.round(chosen["CORE_PANEL_SHRINK_R25"], 3).tolist()} n={[s["n"] for s in single]}, {time.perf_counter() - start:.1f}s', flush=True)
    combined = pd.concat(results, ignore_index=True); combined.to_csv(out / 'native_forecasts.csv', index=False)
    c.compound(combined).to_csv(out / 'forecasts.csv', index=False)
    pd.DataFrame(audit).to_csv(out / 'lambda_audit.csv', index=False); pd.DataFrame(statuses).to_csv(out / 'status.csv', index=False)
    norms.rename('mu_cz').rename_axis('origin').to_frame().assign(annual_pct=lambda d: 12 * d.mu_cz).to_csv(out / 'czech_norm.csv')
    c.finish(out, hashes, controls=CONTROLS, models=MODELS, origin_count=len(origins), panel_members=list(rates.columns), panel_last=str(rates.index.max()),
             notes='Four frozen R25 candidates: panel-estimated persistence of the FAST core trend around a robust norm; h0 and noncore unchanged except the declared food combination.')
    m = json.loads((out / 'manifest.json').read_text()); m['outputs']['fits.jsonl'] = c.sha(out / 'fits.jsonl'); c.dump(out / 'manifest.json', m)
    print('Completed R25', out, flush=True)


if __name__ == '__main__':
    main()
