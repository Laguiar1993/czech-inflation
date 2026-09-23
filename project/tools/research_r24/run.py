"""R24: four frozen food-drift candidates on the saved FAST path.

Run from the repository root into a directory that does not exist yet:
    python -m tools.research_r24.run --output output/research_r24/final
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
from models.food_drift_r24 import MODELS, LONG_HISTORY, long_food_rates, candidates_at

CONTROLS = ['STATE_FAST_R15', 'STABLE_LOCAL_CORE_R14B', 'DAMPED_P95_Q001_R16']
NATIVE = 'output/research_r21/path_anchor/native_forecasts.csv'
SPEC = 'docs/implementation/R24_FOOD_DRIFT_SPEC_2026-09-17.md'
CODE = ['models/food_drift_r24.py', 'models/food_stable_r14b.py', 'models/food_path_r14.py', 'r17_common.py', 'tools/research_r24/run.py']


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); ap.add_argument('--limit', type=int)
    args = ap.parse_args(); out = args.output; out.mkdir(parents=True, exist_ok=False); start = time.perf_counter()
    levels, available, food_manifest = load_inputs()
    hashes = {name: c.sha(ROOT / name) for name in [*CODE, SPEC, NATIVE, LONG_HISTORY, 'data/research_r14/food/input_manifest.json',
                                                   'data/research_r14/food/pipeline_log_levels.csv', 'data/research_r14/food/pipeline_available_from.csv']}
    hashes.update(c.preserved_hashes())
    long_rates, long_published = long_food_rates(levels, available, ROOT / LONG_HISTORY)
    native = c.read(NATIVE); native = native[native.model.isin(CONTROLS)].copy()
    clocks = native[native.model.eq(c.FAST) & native.h.eq(0)].set_index('origin').as_of_utc.to_dict()
    origins = sorted(clocks); origins = origins[:args.limit] if args.limit else origins; native = native[native.origin.isin(origins)]
    results = [native]; drifts = []; rates = []; statuses = []
    print(f'R24 inputs frozen: food history {long_rates.index.min()}..{long_rates.index.max()}; fitting {len(origins)} origins.', flush=True)
    with (out / 'fits.jsonl').open('w', encoding='utf-8') as log:
        for i, origin in enumerate(origins):
            base = native[native.model.eq(c.FAST) & native.origin.eq(origin)].sort_values('h')
            if len(base) != 13 or base.h.duplicated().any():
                raise ValueError('Invalid baseline support')
            result = candidates_at(levels, available, long_rates, long_published, origin, pd.Timestamp(clocks[origin]))
            estimated = result['status'] == 'estimated'
            if estimated:       # the frozen food path must be reproduced exactly before anything is substituted
                np.testing.assert_allclose([result['baseline_path'][h] for h in range(1, 13)], base[base.h.gt(0)].value_food.to_numpy(), atol=1e-9, rtol=0)
                drifts.append(dict(origin=origin, as_of=clocks[origin], **result['drifts'], **{k + '_annual_pct': 12 * v for k, v in result['drifts'].items()}, **result['refit']))
                rates.extend(dict(origin=origin, model=name, h=h, log_rate=v) for name, path in
                             {'FOOD_STABLE_PIPELINE_R14B': result['baseline_log_rates'], **result['log_rates']}.items() for h, v in enumerate(path, 1))
            log.write(json.dumps(dict(origin=origin, as_of=clocks[origin], status=result['status'], drifts=result['drifts'], refit=result['refit'],
                                      log_rates=result['log_rates'], baseline_log_rates=result['baseline_log_rates']), allow_nan=False) + '\n')
            for model in MODELS:
                frame = c.replace_block(base, 'food', result['paths'][model]) if estimated else base.copy()
                frame['model'] = model; frame['food_model_status'] = result['status']; frame['food_fallback_used'] = not estimated
                results.append(frame); statuses.append(dict(origin=origin, model=model, status=result['status']))
            if i % 10 == 0 or i == len(origins) - 1:
                print(f'R24 {i + 1}/{len(origins)} {origin}: {result["status"]}, {time.perf_counter() - start:.1f}s', flush=True)
    combined = pd.concat(results, ignore_index=True); combined.to_csv(out / 'native_forecasts.csv', index=False)
    c.compound(combined).to_csv(out / 'forecasts.csv', index=False)
    pd.DataFrame(drifts).to_csv(out / 'drift_audit.csv', index=False); pd.DataFrame(rates).to_csv(out / 'food_log_rates.csv', index=False)
    pd.DataFrame(statuses).to_csv(out / 'status.csv', index=False)
    c.finish(out, hashes, controls=CONTROLS, models=list(MODELS), origin_count=len(origins),
             notes='Four frozen R24 food-drift candidates on the saved FAST path; only the food block of h1-12 changes.')
    m = json.loads((out / 'manifest.json').read_text()); m['outputs']['fits.jsonl'] = c.sha(out / 'fits.jsonl'); c.dump(out / 'manifest.json', m)
    print('Completed R24', out, flush=True)


if __name__ == '__main__':
    main()
