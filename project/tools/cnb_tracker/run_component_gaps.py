"""Block attribution of every model-minus-CNB gap in an evaluated run.

    python -m tools.cnb_tracker.run_component_gaps --root output/research_r24/final --tables data/cnb_mpr_tables_20260917 --output output/cnb_tracker_20260917/component_gaps
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from tools.cnb_tracker.component_gaps import component_gaps, dominant_block

COMPONENTS = 'output/research_r14b/attribution/actual_component_targets.csv'


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--root', type=Path, required=True); ap.add_argument('--tables', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True); ap.add_argument('--models', nargs='*'); args = ap.parse_args()
    out = args.output; out.mkdir(parents=True, exist_ok=False); ev = args.root / 'evaluation'
    native = pd.read_csv(args.root / 'native_forecasts.csv', low_memory=False); actual = c.monthly(COMPONENTS)
    cnb_long = pd.read_csv(args.tables / 'cnb_mpr_indicators_long.csv'); clocks = pd.read_csv(ev / 'cnb_clocks.csv')
    projections = pd.read_csv(ev / 'cnb_quarter_projections.csv'); projections = projections[projections.model.ne('cnb')]
    models = args.models or sorted(projections.model.unique())
    gaps = component_gaps(native, actual, cnb_long, projections, clocks, models); gaps.to_csv(out / 'component_gaps.csv', index=False)
    top = dominant_block(gaps); top.to_csv(out / 'dominant_blocks.csv', index=False)
    lead = pd.read_csv(ev / 'cnb_lead_pairs.csv'); keys = ['model', 'clock', 'report_date', 'quarter']
    calls = lead[lead.episode_start & lead.call & lead.revision_eligible & lead.threshold.eq(.3)].merge(top, on=keys, how='left')
    calls['outcome'] = np.where(calls.realised.isna(), 'unmatured', np.where(calls.material_gain, 'gain', np.where(calls.material_loss, 'loss', 'immaterial')))
    calls.to_csv(out / 'first_calls_with_driver.csv', index=False)
    quality = gaps[gaps.block.eq('unexplained')].groupby('model').contribution_gap.agg(n='count', mean='mean', rms=lambda s: float(np.sqrt((s ** 2).mean())), max_abs=lambda s: float(s.abs().max()))
    quality.to_csv(out / 'unexplained_summary.csv')
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.suffix == '.csv'}
    (out / 'manifest.json').write_text(json.dumps(dict(root=str(args.root.as_posix()), tables=str(args.tables.as_posix()), models=models, outputs=files,
        inputs={k: c.sha(ROOT / k) for k in [COMPONENTS, 'tools/cnb_tracker/component_gaps.py', 'tools/cnb_tracker/run_component_gaps.py']},
        note='Accounting of ex-ante gaps against CNB blocks. The h0 month uses realised block rates; see component_gaps.py. CNB forecasts never enter a model.'), indent=2), encoding='utf-8')
    print(quality.round(3).to_string()); print('Completed component gaps', out, flush=True)


if __name__ == '__main__':
    main()
