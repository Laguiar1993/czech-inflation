"""R27: food error-correction candidates on the R24 research path, h1-6 only.

Run from the repository root into a directory that does not exist yet:
    python -m tools.research_r27.run --output output/research_r27/final
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
from models.food_path_r14 import load_inputs
from models.food_ecm_r27 import MODELS, FIXED_ALPHAS, candidates_at

CONTROLS = ['STATE_FAST_R15', 'FOOD_NORM_SHIFT_R24']
BASELINE = 'FOOD_NORM_SHIFT_R24'
NATIVE = 'output/research_r24/final/native_forecasts.csv'
SPEC = 'docs/implementation/R27_FOOD_ERROR_CORRECTION_SPEC_2026-09-18.md'
CODE = ['models/food_ecm_r27.py', 'models/food_stable_r14b.py', 'models/food_path_r14.py', 'r17_common.py', 'tools/research_r27/run.py']
VARIANTS = [f'FOOD_ECM_A{abs(a):.2f}_R27'.replace('.', '') for a in FIXED_ALPHAS]


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); ap.add_argument('--limit', type=int)
    args = ap.parse_args(); out = args.output; out.mkdir(parents=True, exist_ok=False); start = time.perf_counter()
    levels, available, _ = load_inputs()
    hashes = {name: c.sha(ROOT / name) for name in [*CODE, SPEC, NATIVE, 'output/research_r24/final/manifest.json', 'data/research_r14/food/input_manifest.json',
                                                   'data/research_r14/food/pipeline_log_levels.csv', 'data/research_r14/food/pipeline_available_from.csv']}
    native = c.read(NATIVE); native = native[native.model.isin(CONTROLS)].copy()
    clocks = native[native.model.eq(BASELINE) & native.h.eq(0)].set_index('origin').as_of_utc.to_dict()
    origins = sorted(clocks); origins = origins[:args.limit] if args.limit else origins; native = native[native.origin.isin(origins)]
    results = [native]; audits = []; rates = []; statuses = []; all_models = [*MODELS, *VARIANTS]
    print(f'R27: {len(origins)} origins on the R24 path.', flush=True)
    with (out / 'fits.jsonl').open('w', encoding='utf-8') as log:
        for i, origin in enumerate(origins):
            base = native[native.model.eq(BASELINE) & native.origin.eq(origin)].sort_values('h')
            if len(base) != 13 or base.h.duplicated().any():
                raise ValueError('Invalid baseline support')
            baseline_log = 100 * np.log1p(base[base.h.gt(0)].value_food.to_numpy(float) / 100)
            result = candidates_at(levels, available, origin, pd.Timestamp(clocks[origin]), baseline_log)
            estimated = result['status'] == 'estimated'
            log.write(json.dumps(dict(origin=origin, as_of=clocks[origin], status=result['status'], last_common_month=result['last_common_month'],
                                      audits=result['audits'], corrections=result['corrections'], log_rates=result['log_rates']), allow_nan=False, default=str) + '\n')
            for model, audit in result['audits'].items():
                audits.append(dict(origin=origin, as_of=clocks[origin], model=model, last_common_month=result['last_common_month'], **audit))
            for name, path in result['log_rates'].items():
                rates.extend(dict(origin=origin, model=name, h=h, log_rate=v, correction=result['corrections'][name][h]) for h, v in enumerate(path, 1))
            for model in all_models:
                available_path = estimated and model in result['paths']
                frame = c.replace_block(base, 'food', result['paths'][model]) if available_path else base.copy()
                frame['model'] = model; frame['food_model_status'] = result['status'] if available_path else 'fallback_' + result['status']
                frame['food_fallback_used'] = not available_path
                results.append(frame); statuses.append(dict(origin=origin, model=model, status=result['status'], fallback=not available_path))
            if i % 10 == 0 or i == len(origins) - 1:
                print(f'R27 {i + 1}/{len(origins)} {origin}: {result["status"]}, {time.perf_counter() - start:.1f}s', flush=True)
    combined = pd.concat(results, ignore_index=True); combined.to_csv(out / 'native_forecasts.csv', index=False)
    c.compound(combined).to_csv(out / 'forecasts.csv', index=False)
    pd.DataFrame(audits).to_csv(out / 'ecm_audit.csv', index=False); pd.DataFrame(rates).to_csv(out / 'food_log_rates.csv', index=False)
    pd.DataFrame(statuses).to_csv(out / 'status.csv', index=False)
    c.finish(out, hashes, controls=CONTROLS, models=all_models, origin_count=len(origins),
             notes='R27 food error-correction candidates (two estimated speeds, four fixed speeds) on the R24 research path; only the food block of h1-6 changes.')
    m = json.loads((out / 'manifest.json').read_text()); m['outputs']['fits.jsonl'] = c.sha(out / 'fits.jsonl'); c.dump(out / 'manifest.json', m)
    print('Completed R27', out, flush=True)


if __name__ == '__main__':
    main()
