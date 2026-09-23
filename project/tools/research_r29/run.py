"""R29: phase-conditioned core persistence, weights from the EU panel, applied to the Czech FAST core on the roster frame.

Run from the repository root into a directory that does not exist yet:
    python -m tools.research_r29.run --output output/research_r29/final [--frame-run output/research_r27/final --frame-model FOOD_ECM_R27]

Panel rows (FAST deviation, realised deviation, norm; per country, quarterly origin and band) are the frozen R25
output; this round adds each row's upstream phase from the frozen PPI panel and estimates two weights per band.
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
from data.cost_gaps_r23 import load_inputs as load_r23_inputs
from data.ppi_panel_r29 import load as load_ppi, SNAPSHOT
from models.cost_gaps_r23 import monthly_correction
from models.panel_persistence_r25 import BANDS, MIN_PANEL_ROWS, lambda_at
from models.core_phase_r29 import MODELS, FIXED_FADING, TARGET_LOG_PER_MONTH, band_corrections, fixed_name, lambda_phase_at, phase_at

SPEC = 'docs/implementation/R29_CORE_PHASE_SPEC_2026-09-18.md'
R25 = 'output/research_r25/final'
CODE = ['models/core_phase_r29.py', 'models/panel_persistence_r25.py', 'models/cost_gaps_r23.py', 'data/ppi_panel_r29.py', 'data/cost_gaps_r23.py', 'r17_common.py', 'tools/research_r29/run.py']
PANEL_CLOCK_DAYS = 24     # R25's panel clock: day 24 of the origin month


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--frame-run', default='output/research_r27/final'); ap.add_argument('--frame-model', default='FOOD_ECM_R27'); ap.add_argument('--limit', type=int)
    args = ap.parse_args(); out = args.output; out.mkdir(parents=True, exist_ok=False); start = time.perf_counter()
    ppi, ppi_published, ppi_manifest = load_ppi()
    core, dates, raw, fx, r23_hashes = load_r23_inputs(); cz_ppi = raw[47]
    native_path = f'{args.frame_run}/native_forecasts.csv'
    hashes = {name: c.sha(ROOT / name) for name in [*CODE, SPEC, native_path, f'{args.frame_run}/manifest.json', f'{R25}/panel_rows.csv', f'{R25}/czech_rows.csv',
                                                   f'{R25}/czech_norm.csv', f'{R25}/manifest.json', SNAPSHOT + '/manifest.json', SNAPSHOT + '/ppi_index.csv', 'output/research_r15/states.json']}
    hashes.update(r23_hashes)
    panel = c.read(f'{R25}/panel_rows.csv'); panel['origin'] = pd.PeriodIndex(panel.origin, freq='M'); panel['label_end'] = pd.PeriodIndex(panel.label_end, freq='M')
    phases = []
    for (geo, origin), _ in panel.groupby(['geo', 'origin']):
        clock = origin.to_timestamp() + pd.Timedelta(days=PANEL_CLOCK_DAYS - 1)
        phase, d = phase_at(ppi[geo], ppi_published, origin, clock)
        phases.append(dict(geo=geo, origin=origin, phase=phase, **{k: v for k, v in d.items() if k != 'phase'}))
    phases = pd.DataFrame(phases); panel = panel.merge(phases[['geo', 'origin', 'phase', 'momentum', 'change', 'last_month']], on=['geo', 'origin'], how='left')
    print(f'R29 panel: {len(panel)} rows, phase known for {panel.phase.notna().mean():.1%}; building share {(panel.phase.eq("building")).sum() / max(panel.phase.notna().sum(), 1):.2f}, {time.perf_counter() - start:.1f}s', flush=True)
    own = c.read(f'{R25}/czech_rows.csv'); own['origin'] = pd.PeriodIndex(own.origin, freq='M'); own = own.set_index(['origin', 'band'])
    norms = c.read(f'{R25}/czech_norm.csv').set_index('origin').mu_cz
    states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
    native = c.read(native_path); controls = ['STATE_FAST_R15', args.frame_model] if args.frame_model != 'STATE_FAST_R15' else ['STATE_FAST_R15']
    native = native[native.model.isin(controls)].copy()
    clocks = native[native.model.eq(args.frame_model) & native.h.eq(0)].set_index('origin').as_of_utc.to_dict()
    origins = sorted(clocks); origins = origins[:args.limit] if args.limit else origins; native = native[native.origin.isin(origins)]
    fixed = {fixed_name(fd): fd for fd in FIXED_FADING}; all_models = [*MODELS, *fixed]
    results = [native]; audit = []; weight_rows = []
    with (out / 'fits.jsonl').open('w', encoding='utf-8') as log:
        for i, origin in enumerate(origins):
            t = pd.Period(origin, 'M'); state = states[origin]; clock = pd.Timestamp(clocks[origin])
            frame = native[native.model.eq(args.frame_model) & native.origin.eq(origin)].sort_values('h')
            if len(frame) != 13 or frame.h.duplicated().any():
                raise ValueError('Invalid frame support at ' + origin)
            baseline = np.array([state['forecasts_log']['fast'][str(h)] for h in range(1, 13)])
            np.testing.assert_allclose(100 * np.log1p(frame[frame.h.gt(0)].value_core.to_numpy() / 100), baseline, atol=1e-10, rtol=0)
            f_cz = np.array([float(own.loc[(t, b), 'f']) for b in BANDS]); mu_own = float(norms.get(origin, np.nan))
            cz_phase, cz_diag = phase_at(cz_ppi.values, cz_ppi.available, origin, clock)
            lam_phase = {ph: [lambda_phase_at(panel, b, t, ph, MIN_PANEL_ROWS) for b in BANDS] for ph in ('building', 'fading')}
            lam_single = [lambda_at(panel[panel.phase.notna()], b, t, MIN_PANEL_ROWS) for b in BANDS]
            status = 'estimated' if cz_phase is not None and np.isfinite(f_cz).all() else ('no_czech_phase' if cz_phase is None else 'missing_czech_state')
            chosen = {}
            if status == 'estimated':
                used = [d['lam'] for d in lam_phase[cz_phase]]
                chosen['CORE_PHASE_TARGET_R29'] = (used, TARGET_LOG_PER_MONTH)
                chosen['CORE_PHASE_OWN_R29'] = (used, mu_own) if np.isfinite(mu_own) else None
                chosen['CORE_SINGLE_TARGET_R29'] = ([d['lam'] for d in lam_single], TARGET_LOG_PER_MONTH)
                for name, fd in fixed.items():
                    chosen[name] = ([1.] * 4 if cz_phase == 'building' else [fd] * 4, TARGET_LOG_PER_MONTH)
            record = dict(origin=origin, as_of=clocks[origin], status=status, czech_phase=cz_phase, czech_phase_diagnostics=cz_diag, mu_own=mu_own, f_cz=f_cz.tolist(),
                          lambda_building=[d['lam'] for d in lam_phase['building']], lambda_fading=[d['lam'] for d in lam_phase['fading']], lambda_single=[d['lam'] for d in lam_single],
                          n_building=[d['n'] for d in lam_phase['building']], n_fading=[d['n'] for d in lam_phase['fading']], corrections={})
            for b in BANDS:
                weight_rows.append(dict(origin=origin, band=b, czech_phase=cz_phase, lambda_building=lam_phase['building'][b - 1]['lam'], n_building=lam_phase['building'][b - 1]['n'],
                                        lambda_fading=lam_phase['fading'][b - 1]['lam'], n_fading=lam_phase['fading'][b - 1]['n'], lambda_single=lam_single[b - 1]['lam'], n_single=lam_single[b - 1]['n'],
                                        f_cz=f_cz[b - 1], mu_own=mu_own, mu_target=TARGET_LOG_PER_MONTH))
            for model in all_models:
                spec = chosen.get(model)
                if spec is not None:
                    lam, mu = spec; path = monthly_correction(band_corrections(f_cz, mu, lam)); rates_new = 100 * np.expm1((baseline + path) / 100)
                    if not np.isfinite(rates_new).all():
                        raise ArithmeticError('Nonfinite monthly core forecast')
                    rows = c.replace_block(frame, 'core', dict(zip(range(1, 13), rates_new))); record['corrections'][model] = path.tolist(); fallback = False
                else:
                    rows = frame.copy(); fallback = True
                rows['model'] = model; rows['core_model_status'] = status if not fallback else 'fallback_' + status; rows['core_fallback_used'] = fallback; results.append(rows)
            audit.append(dict(origin=origin, as_of=clocks[origin], status=status, czech_phase=cz_phase, **{'cz_' + k: v for k, v in cz_diag.items() if k != 'phase'}, mu_own=mu_own))
            log.write(json.dumps(record, allow_nan=True, default=str) + '\n')
            if i % 10 == 0 or i == len(origins) - 1:
                print(f'R29 {i + 1}/{len(origins)} {origin}: phase={cz_phase} lam_b={np.round(record["lambda_building"], 2).tolist()} lam_f={np.round(record["lambda_fading"], 2).tolist()}, {time.perf_counter() - start:.1f}s', flush=True)
    combined = pd.concat(results, ignore_index=True); combined.to_csv(out / 'native_forecasts.csv', index=False)
    c.compound(combined).to_csv(out / 'forecasts.csv', index=False)
    pd.DataFrame(audit).to_csv(out / 'phase_audit.csv', index=False); pd.DataFrame(weight_rows).to_csv(out / 'lambda_audit.csv', index=False)
    panel.assign(origin=panel.origin.astype(str), label_end=panel.label_end.astype(str)).to_csv(out / 'panel_rows_with_phase.csv', index=False)
    c.finish(out, hashes, controls=controls, models=all_models, origin_count=len(origins), frame_run=args.frame_run, frame_model=args.frame_model,
             panel_members=list(ppi.columns), ppi_panel_last=str(ppi.index.max()),
             notes='R29 phase-conditioned core persistence on the roster frame; only the core block of h1-12 changes; weights from the R25 panel rows split by the PPI-momentum phase.')
    m = json.loads((out / 'manifest.json').read_text()); m['outputs']['fits.jsonl'] = c.sha(out / 'fits.jsonl'); c.dump(out / 'manifest.json', m)
    print('Completed R29', out, flush=True)


if __name__ == '__main__':
    main()
