"""R28: administered-price level candidates on the research roster frame, h1-12.

Run from the repository root into a directory that does not exist yet:
    python -m tools.research_r28.run --output output/research_r28/final [--frame-run output/research_r27/final --frame-model FOOD_ECM_R27]

The block is FAST's administered path; the frame (whose food block the roster carries) only matters for the
assembled headline path. The frame model's rows are copied and their administered block replaced.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from models.administered_level_r28 import MODELS, FACTORS, candidate_paths, factor_name

SPEC = 'docs/implementation/R28_ADMINISTERED_LEVEL_SPEC_2026-09-18.md'
CODE = ['models/administered_level_r28.py', 'models/benchmarks_r26.py', 'r17_common.py', 'tools/research_r28/run.py']
COMPONENTS = 'output/research_r14b/attribution/actual_component_targets.csv'
VARIANTS = [factor_name(f) for f in FACTORS]


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--frame-run', default='output/research_r27/final'); ap.add_argument('--frame-model', default='FOOD_ECM_R27'); ap.add_argument('--limit', type=int)
    args = ap.parse_args(); out = args.output; out.mkdir(parents=True, exist_ok=False); start = time.perf_counter()
    native_path = f'{args.frame_run}/native_forecasts.csv'
    hashes = {name: c.sha(ROOT / name) for name in [*CODE, SPEC, native_path, f'{args.frame_run}/manifest.json', COMPONENTS, 'data/release_calendar_cz_cpi.csv']}
    native = c.read(native_path); controls = ['STATE_FAST_R15', args.frame_model] if args.frame_model != 'STATE_FAST_R15' else ['STATE_FAST_R15']
    native = native[native.model.isin(controls)].copy()
    actual = c.monthly(COMPONENTS); published = c.publication_dates(actual.index)
    clocks = native[native.model.eq(args.frame_model) & native.h.eq(0)].set_index('origin').as_of_utc.to_dict()
    origins = sorted(clocks); origins = origins[:args.limit] if args.limit else origins; native = native[native.origin.isin(origins)]
    results = [native]; audits = []; all_models = [*MODELS, *VARIANTS]
    print(f'R28: {len(origins)} origins on frame {args.frame_model} from {args.frame_run}.', flush=True)
    with (out / 'fits.jsonl').open('w', encoding='utf-8') as log:
        for i, origin in enumerate(origins):
            frame = native[native.model.eq(args.frame_model) & native.origin.eq(origin)].sort_values('h')
            fast = native[native.model.eq('STATE_FAST_R15') & native.origin.eq(origin)].sort_values('h')
            if len(frame) != 13 or len(fast) != 13 or frame.h.duplicated().any():
                raise ValueError('Invalid frame support at ' + origin)
            fast_path = dict(zip(fast.h, fast.value_administered)); fast_path = {h: float(fast_path[h]) for h in range(1, 13)}
            if any(abs(float(frame[frame.h.eq(h)].value_administered.iloc[0]) - fast_path[h]) > 1e-9 for h in range(1, 13)):
                raise ValueError('Frame administered block differs from FAST at ' + origin)
            paths, audit = candidate_paths(fast_path, origin, actual.administered, published, pd.Timestamp(clocks[origin]))
            log.write(json.dumps(dict(origin=origin, as_of=clocks[origin], audit=audit, paths=paths), allow_nan=True, default=str) + '\n')
            audits.append(dict(origin=origin, as_of=clocks[origin], fired_months='|'.join(audit['fired_months']), january_horizons='|'.join(map(str, audit['january_horizons'])),
                               fast_january='|'.join(f'{v:.3f}' for v in audit['fast_january']), fast_non_january_sum=audit['fast_non_january_sum'],
                               recent_available=all(pd.notna(v) for v in paths['ADMIN_RECENT_R28'].values())))
            for model in all_models:
                path = paths[model]; usable = all(pd.notna(v) for v in path.values())
                rows = c.replace_block(frame, 'administered', path) if usable else frame.copy()
                rows['model'] = model; rows['admin_fallback_used'] = not usable; results.append(rows)
            if i % 10 == 0 or i == len(origins) - 1:
                print(f'R28 {i + 1}/{len(origins)} {origin}: fired {audit["fired_months"]}, {time.perf_counter() - start:.1f}s', flush=True)
    combined = pd.concat(results, ignore_index=True); combined.to_csv(out / 'native_forecasts.csv', index=False)
    c.compound(combined).to_csv(out / 'forecasts.csv', index=False); pd.DataFrame(audits).to_csv(out / 'admin_audit.csv', index=False)
    c.finish(out, hashes, controls=controls, models=all_models, origin_count=len(origins), frame_run=args.frame_run, frame_model=args.frame_model,
             notes='R28 administered-level candidates on the research roster frame; only the administered block of h1-12 changes; fired January gates kept.')
    m = json.loads((out / 'manifest.json').read_text()); m['outputs']['fits.jsonl'] = c.sha(out / 'fits.jsonl'); c.dump(out / 'manifest.json', m)
    print('Completed R28', out, flush=True)


if __name__ == '__main__':
    main()
