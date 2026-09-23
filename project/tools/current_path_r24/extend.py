"""Add the R24 long-history food drift to a recorded current-path run, without touching it.

The R20 runner and its recorded bundles are sealed. This tool reads a recorded run's own saved
inputs, recomputes the frozen food path to prove it is looking at the same information, and
writes the three paths again with the R24 food drift into a new directory beside nothing else.

    python -m tools.current_path_r24.extend --run output/current_runs/<run> --output <new directory>
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from models.food_drift_r24 import LONG_HISTORY, long_food_rates, candidates_at
from models.path_inputs import compound_path

FOOD = 'FOOD_NORM_SHIFT_R24'
SUFFIX = '+' + FOOD
BLOCKS = ('core', 'food', 'administered', 'alcohol_tobacco', 'fuel', 'wedge')
CODE = ['models/food_drift_r24.py', 'models/food_stable_r14b.py', 'models/food_path_r14.py', 'models/path_inputs.py', 'tools/current_path_r24/extend.py']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def monthly(path):
    frame = pd.read_csv(path, index_col=0, float_precision='round_trip'); frame.index = pd.PeriodIndex(frame.index, freq='M')
    return frame


def extend(path, levels, available, headline, origin, as_of, long_csv=ROOT / LONG_HISTORY):
    """Return (extended path table, drift record). `path` is a recorded three-model h0..h12 table."""
    t = pd.Period(origin, 'M'); clock = pd.Timestamp(as_of)
    rates, published = long_food_rates(levels, available, long_csv)
    food = candidates_at(levels, available, rates, published, t, clock)
    if food['status'] != 'estimated':
        raise ValueError('Food drift unavailable: ' + food['status'])
    history = headline.iloc[:, 0].loc[headline.index < t]; out = []
    for model, g in path.groupby('model', sort=False):
        g = g.sort_values('h').reset_index(drop=True)
        if list(g.h) != list(range(13)):
            raise ValueError('Recorded path must hold h0..h12 for ' + model)
        h0 = float(g.mm_forecast.iloc[0]); stored = dict(zip(g.h, g.mm_forecast))
        # Same information, same arithmetic: the frozen food path and the stored annual rates must be reproduced first.
        np.testing.assert_allclose([food['baseline_path'][h] for h in range(1, 13)], g.value_food.iloc[1:].to_numpy(), atol=1e-10, rtol=0)
        np.testing.assert_allclose([compound_path(history, stored, t, h, h0) for h in range(13)], g.yy_exante.to_numpy(), atol=1e-10, rtol=0)
        new = g.copy(); new['model'] = model + SUFFIX
        for h in range(1, 13):
            new.loc[h, 'value_food'] = food['paths'][FOOD][h]; new.loc[h, 'contribution_food'] = new.loc[h, 'weight_food'] * food['paths'][FOOD][h]
            new.loc[h, 'mm_forecast'] = float(new.loc[h, ['contribution_' + b for b in BLOCKS]].sum())
        changed = dict(zip(new.h, new.mm_forecast)); new['yy_exante'] = [compound_path(history, changed, t, h, h0) for h in range(13)]
        if not np.isfinite(new[['mm_forecast', 'yy_exante']]).all().all():
            raise ArithmeticError('Nonfinite extended path')
        out.extend([g, new])
    return pd.concat(out, ignore_index=True), dict(drifts=food['drifts'], annual_pct={k: 12 * v for k, v in food['drifts'].items()}, refit=food['refit'])


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--run', type=Path, required=True); ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(); run = args.run; out = args.output; out.mkdir(parents=True, exist_ok=False)
    snapshot = json.loads((run / 'snapshot.json').read_text(encoding='utf-8')); receipt = json.loads((run / 'receipt.json').read_text(encoding='utf-8'))
    used = ['path.csv', 'path_food_levels.csv', 'path_food_available.csv', 'headline.csv']
    expected = {**snapshot.get('hashes', {}), **receipt}
    for name in used:
        if name in expected and sha(run / name) != expected[name]:
            raise ValueError('Recorded run file changed: ' + name)
    table, drift = extend(pd.read_csv(run / 'path.csv', float_precision='round_trip'), monthly(run / 'path_food_levels.csv'),
                          monthly(run / 'path_food_available.csv'), monthly(run / 'headline.csv'), snapshot['target'], snapshot['as_of'])
    table.to_csv(out / 'path_r24.csv', index=False)
    (out / 'manifest.json').write_text(json.dumps(dict(
        created_at_utc=datetime.now(timezone.utc).isoformat(), source_run=run.as_posix(), capture_kind=snapshot.get('capture_kind'),
        target=snapshot['target'], as_of=snapshot['as_of'], food_model=FOOD, **drift,
        inputs={**{'run/' + name: sha(run / name) for name in used}, LONG_HISTORY: sha(ROOT / LONG_HISTORY), **{name: sha(ROOT / name) for name in CODE}},
        outputs={'path_r24.csv': sha(out / 'path_r24.csv')},
        note='Base rows are copied unchanged from the recorded run; rows with the suffix carry the R24 long-history food drift. Research status: historical evidence only.'), indent=2), encoding='utf-8')
    show = table[table.h.isin([3, 6, 12])].pivot(index='model', columns='h', values='yy_exante').round(3)
    print(show.to_string()); print('Extended', run, '->', out, flush=True)


if __name__ == '__main__':
    main()
