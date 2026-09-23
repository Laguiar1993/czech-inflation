"""R23B: frozen cost-pressure corrections for h1-6 around the saved FAST core path.

Run from the repository root into a directory that does not exist yet:
    python -m tools.research_r23b.run --output output/research_r23b/final
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
from data.cost_pressure_r23b import load_inputs, features_at, COLUMNS
from models.cost_pressure_r23b import run_origin, FAMILIES, BANDS

CONTROLS = ['STATE_FAST_R15', 'STABLE_LOCAL_CORE_R14B', 'DAMPED_P95_Q001_R16', 'CORE_FEEDBACK_R21']
MODELS = list(FAMILIES)
NATIVE = 'output/research_r21/path_anchor/native_forecasts.csv'
SPEC = 'docs/implementation/R23B_MEASUREMENT_REPAIR_SPEC_2026-09-17.md'


def targets(core, dates, states):
    """Band means of realised minus saved FAST log core, and the release that matures each band."""
    values = {}; releases = {}; audit = []
    for origin, state in states.items():
        t = pd.Period(origin, 'M'); row = {}; when = {}
        for b in BANDS:
            months = pd.period_range(t + 3 * b - 2, t + 3 * b, freq='M'); through = pd.period_range(t + 1, t + 3 * b, freq='M')
            truth = core.reindex(months); published = dates.reindex(through)
            complete = truth.notna().all() and truth.gt(-100).all() and published.notna().all() and core.reindex(through).notna().all()
            base = np.array([state['forecasts_log']['fast'][str(h)] for h in range(3 * b - 2, 3 * b + 1)])
            row[b] = float((100 * np.log1p(truth.to_numpy() / 100) - base).mean()) if complete else np.nan
            when[b] = published.max() if complete else pd.NaT
            audit.append(dict(origin=origin, band=b, last_target=str(t + 3 * b), available_from=str(when[b]), complete=bool(complete)))
        values[t] = row; releases[t] = when
    return pd.DataFrame.from_dict(values, orient='index'), pd.DataFrame.from_dict(releases, orient='index'), pd.DataFrame(audit)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); ap.add_argument('--limit', type=int)
    args = ap.parse_args(); out = args.output; out.mkdir(parents=True, exist_ok=False); start = time.perf_counter()
    core, dates, raw, fx, hashes = load_inputs(); hashes.update(c.preserved_hashes())
    for path in ['models/cost_pressure_r23b.py', 'models/cost_gaps_r23.py', 'tools/research_r23b/run.py', SPEC, NATIVE]:
        hashes[path] = c.sha(ROOT / path)
    states = json.loads((ROOT / 'output/research_r15/states.json').read_text())
    native = c.read(NATIVE); native = native[native.model.isin(CONTROLS)].copy()
    outer = native[native.model.eq('STATE_FAST_R15') & native.h.eq(0)].set_index('origin').as_of_utc.to_dict()
    features = {}; provenance = []; clocks = {}
    for origin, state in states.items():
        t = pd.Period(origin, 'M'); clock = outer.get(origin, state['as_of'])
        if local(state['as_of']) > local(clock) or local(state['last_release']) > local(clock):
            raise ValueError('Saved core state postdates decision')
        row, info = features_at(core, dates, raw, fx, t, clock, state['seasonal']); features[t] = row; clocks[t] = local(clock)
        provenance.extend(dict(origin=origin, as_of=str(local(clock)), **r) for r in info)
    x = pd.DataFrame.from_dict(features, orient='index')[COLUMNS]; clock_series = pd.Series(clocks)
    if not x.index.is_monotonic_increasing:
        raise ValueError('Origins must be chronological')
    y, a, target_audit = targets(core, dates, states)
    x.to_csv(out / 'features.csv', index_label='origin'); y.to_csv(out / 'band_targets.csv', index_label='origin')
    a.to_csv(out / 'target_available.csv', index_label='origin'); clock_series.to_csv(out / 'feature_clocks.csv', index_label='origin')
    pd.DataFrame(provenance).to_csv(out / 'feature_provenance.csv', index=False); target_audit.to_csv(out / 'target_audit.csv', index=False)
    c.dump(out / 'sources.json', [dict(variable=name, a6_number=n, source=raw[n].source, kind=raw[n].kind, frequency=raw[n].values.index.freqstr,
                                       first=str(raw[n].values.index.min()), last=str(raw[n].values.index.max()))
                                  for name, n in [('unemployment', 11), ('ulc', 17), ('imports', 26), ('ppi', 47)]])
    origins = sorted(outer); origins = origins[:args.limit] if args.limit else origins; native = native[native.origin.isin(origins)]
    results = [native]; statuses = []; validation = []; contributions = []; training = []
    print(f'R23B inputs frozen: {len(x)} snapshots, {int(x.notna().all(axis=1).sum())} complete; fitting {len(origins)} origins.', flush=True)
    with (out / 'fits.jsonl').open('w', encoding='utf-8') as log:
        for i, origin in enumerate(origins):
            t = pd.Period(origin, 'M'); base = native[native.model.eq('STATE_FAST_R15') & native.origin.eq(origin)].sort_values('h')
            if len(base) != 13 or base.h.duplicated().any():
                raise ValueError('Invalid baseline support')
            baseline = np.array([states[origin]['forecasts_log']['fast'][str(h)] for h in range(1, 13)])
            np.testing.assert_allclose(100 * np.log1p(base[base.h.gt(0)].value_core.to_numpy() / 100), baseline, atol=1e-10, rtol=0)
            result = run_origin(x, y, a, clock_series, t, outer[origin]); estimated = result['status'] == 'estimated'
            log.write(json.dumps(dict(origin=origin, as_of=outer[origin], **result), allow_nan=False) + '\n')
            for model in MODELS:
                if estimated:
                    rates = 100 * np.expm1((baseline + np.array(result['paths'][model])) / 100)
                    if not np.isfinite(rates).all():
                        raise ArithmeticError('Nonfinite monthly core forecast')
                    frame = c.replace_block(base, 'core', dict(zip(range(1, 13), rates)))
                else:
                    frame = base.copy()
                frame['model'] = model; frame['core_model_status'] = result['status']; frame['core_fallback_used'] = not estimated
                results.append(frame)
                pick = result['selection'].get(model, {})
                statuses.append(dict(origin=origin, model=model, status=result['status'],
                                     **{f'n_train_{b}': result['n_train'][str(b)] for b in BANDS},
                                     **{f'band{b}_status': pick.get(str(b), {}).get('status') for b in BANDS},
                                     **{f'band{b}_alpha': pick.get(str(b), {}).get('alpha') for b in BANDS}))
            if estimated:
                for b in BANDS:
                    for key in result['train_dates'][str(b)]:
                        k = pd.Period(key, 'M')
                        training.append(dict(origin=origin, band=b, training_origin=key, last_target=str(k + 3 * b),
                                             target_available=str(a.loc[k, b]), as_of=str(local(outer[origin]))))
                for model, per_band in result['fits'].items():
                    for b, fit in per_band.items():
                        for j, column in enumerate(fit['columns']):
                            contributions.append(dict(origin=origin, model=model, band=int(b), feature=column, coefficient=fit['coefficients'][j],
                                                      band_log_core_correction=fit['contributions'][j], applied=fit['applied'], alpha=fit['alpha'], kind=fit['kind']))
                        setting = result['selection'][model][b]
                        validation.extend(dict(origin=origin, model=model, chosen_alpha=setting['alpha'], **r) for r in setting['validation'])
            if i % 5 == 0 or i == len(origins) - 1:
                print(f'R23B {i + 1}/{len(origins)} {origin}: {result["status"]} n={result["n_train"]}, {time.perf_counter() - start:.1f}s', flush=True)
    combined = pd.concat(results, ignore_index=True); combined.to_csv(out / 'native_forecasts.csv', index=False)
    c.compound(combined).to_csv(out / 'forecasts.csv', index=False)
    for name, rows in [('status', statuses), ('inner_validation', validation), ('coefficient_contributions', contributions), ('training', training)]:
        pd.DataFrame(rows).to_csv(out / (name + '.csv'), index=False)
    c.finish(out, hashes, controls=CONTROLS, models=MODELS, origin_count=len(origins),
             notes='Six frozen R23B cost-pressure candidates for h1-6; no intercept; do-no-harm validation; shared FAST seasonality, independent h0 and noncore unchanged.')
    m = json.loads((out / 'manifest.json').read_text()); m['outputs']['fits.jsonl'] = c.sha(out / 'fits.jsonl'); c.dump(out / 'manifest.json', m)
    print('Completed R23B', out, flush=True)


if __name__ == '__main__':
    main()
