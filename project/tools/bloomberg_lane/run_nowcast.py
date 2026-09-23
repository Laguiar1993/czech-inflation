"""R31 nowcast lane: BASE, HALF and FULL at the 90 recorded release-eve clocks on the Bloomberg input bundle.

    python -m tools.bloomberg_lane.run_nowcast --bundle data/bloomberg_inputs_20260922 --output output/bloomberg_lane_20260922/nowcast

Variant A reads the bundle's CZSO pump survey; variant B the EC bulletin from Bloomberg. Both go through
forecast_independent.calculate, the recorded code path, and are scored against the 14 September scoreboard's
actuals and consensus. The recorded forecasts are the comparison.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import types

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
for name in ('duckdb', 'requests'):      # module-level imports of the live loaders; none is called on the bundle
    if name not in sys.modules:
        stub = types.ModuleType(name); stub.__getattr__ = lambda attr, _n=name: (_ for _ in ()).throw(RuntimeError(f'{_n} stub')); stub.DuckDBPyConnection = object; sys.modules[name] = stub
import forecast_independent as fi

FORECASTS = 'output/independent_nowcast_forecasts.csv'
EVIDENCE = 'work/model_briefing_20260914/nowcast_release_evidence.csv'
MODELS = ['HARD_BASE', 'HARD_HALF', 'HARD_FULL']
NAMES = {'headline': 'target_headline_cpi_mm.csv', 'components': 'component_food_fuel_mm.csv', 'core': 'cnb_core_mm.csv', 'regulated': 'cnb_regulated_mm.csv',
         'alcohol': 'alcohol_tobacco.csv', 'features': 'core_features.csv', 'food_features': 'food_block_features.csv'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rmse(e):
    e = np.asarray(e, float); e = e[np.isfinite(e)]; return float(np.sqrt((e ** 2).mean())) if len(e) else np.nan


def bundle_frames(bundle, variant):
    manifest = json.loads((bundle / 'MANIFEST.json').read_text(encoding='utf-8'))
    for rel, digest in manifest['files'].items():
        if sha(bundle / rel) != digest:
            raise ValueError('Bundle file changed: ' + rel)
    frames = {}
    for key, name in NAMES.items():
        d = pd.read_csv(bundle / 'nowcast' / name, index_col=0, float_precision='round_trip'); d.index = pd.PeriodIndex(d.index, freq='M'); frames[key] = d
    weekly = pd.read_csv(bundle / 'nowcast' / ('fuel_weekly.csv' if variant == 'A' else 'fuel_weekly_variant_b.csv'), index_col=0, float_precision='round_trip'); weekly.index = pd.to_datetime(weekly.index)
    frames['weekly_fuel'] = weekly
    return frames


def run(frames, targets, clocks, label):
    rows = []; started = time.perf_counter()
    for i, target in enumerate(targets):
        r = fi.calculate(frames, pd.Period(target, 'M'), clocks[target])
        rows.append(dict(period=target, **{m: r['points_mm_pct'][m] for m in MODELS}, **{'contrib_' + k: v for k, v in r['main_contributions_pp'].items()}, ready=r['ready_for_first_release']))
        if i % 15 == 0 or i == len(targets) - 1:
            print(f'{label} {i + 1}/{len(targets)} {target}: BASE {r["points_mm_pct"]["HARD_BASE"]:.4f}, {time.perf_counter() - started:.0f}s', flush=True)
    return pd.DataFrame(rows).set_index('period')


def score(table, models, sources, samples):
    rows = []
    for m in models:
        for sample, mask in samples.items():
            z = table[mask]; big = (z.actual - z.consensus).abs() >= .4 - 1e-12
            for source in sources:
                col = f'{m}_{source}'; e = z[col] - z.actual; gain = (z.consensus - z.actual).abs() - e.abs(); dev = z[col] - z.consensus; alert = dev.abs() >= .2 - 1e-12
                rows.append(dict(model=m, source=source, sample=sample, n=int(mask.sum()), rmse=rmse(e), mae=float(e.abs().mean()), bias=float(e.mean()), consensus_rmse=rmse(z.consensus - z.actual),
                                 closer_than_consensus=int((gain > 0).sum()), material_wins_big=int(((gain >= .15 - 1e-12) & big).sum()), material_losses_big=int(((gain <= -.15 + 1e-12) & big).sum()),
                                 alerts=int(alert.sum()), alerts_direction_right=int((alert & (np.sign(dev) == np.sign(z.actual - z.consensus))).sum()),
                                 alert_material_wins=int((alert & (gain >= .15 - 1e-12)).sum()), alert_material_losses=int((alert & (gain <= -.15 + 1e-12)).sum()), alert_net_pp=float(gain[alert].sum())))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--bundle', type=Path, required=True); ap.add_argument('--output', type=Path, required=True); ap.add_argument('--limit', type=int); args = ap.parse_args()
    bundle = args.bundle if args.bundle.is_absolute() else ROOT / args.bundle; out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    recorded = pd.read_csv(ROOT / FORECASTS, index_col='period'); ev = pd.read_csv(ROOT / EVIDENCE); base_ev = ev[ev.model.eq('HARD_BASE')].set_index('period')
    targets = [p for p in recorded.index if p >= '2019-02']; targets = targets[:args.limit] if args.limit else targets
    clocks = {p: pd.Timestamp(recorded.loc[p, 'as_of_eve']).tz_localize('Europe/Prague') for p in targets}
    runs = {v: run(bundle_frames(bundle, v), targets, clocks, 'variant ' + v) for v in ('A', 'B')}
    for v, frame in runs.items():
        frame.to_csv(out / f'run_variant_{v}.csv')
    table = pd.DataFrame(index=targets); table['actual'] = base_ev.actual.reindex(targets); table['consensus'] = base_ev.consensus.reindex(targets)
    for m in MODELS:
        table[f'{m}_recorded'] = recorded[m].reindex(targets)
        for v in ('A', 'B'):
            table[f'{m}_{v}'] = runs[v][m].reindex(targets)
    table.to_csv(out / 'comparison.csv', index_label='period')
    samples = {'all': table.index >= '2000', 'prints_2024plus': table.index >= '2024-01', 'flash_era_2025plus': table.index >= '2025-01'}
    scores = score(table, MODELS, ['recorded', 'A', 'B'], samples); scores.to_csv(out / 'scores.csv', index=False)
    summary = {}
    for m in MODELS:
        summary[m] = {}
        for v in ('A', 'B'):
            d = (table[f'{m}_{v}'] - table[f'{m}_recorded']).abs()
            summary[m][v] = dict(max_abs_change=float(d.max()), mean_abs_change=float(d.mean()), months_over_0p05=int((d > .05).sum()), months_over_0p10=int((d > .10).sum()), largest=d.sort_values(ascending=False).head(3).round(4).to_dict(),
                                 rmse={s: dict(recorded=float(scores[(scores.model == m) & (scores.source == 'recorded') & (scores['sample'] == s)].rmse.iloc[0]), lane=float(scores[(scores.model == m) & (scores.source == v) & (scores['sample'] == s)].rmse.iloc[0])) for s in samples})
    blocks = {}
    for k in [c for c in runs['A'].columns if c.startswith('contrib_')]:
        blocks[k] = {v: dict(max_abs_change_pp=float((runs[v][k] - runs['A'][k]).abs().max()) if v == 'B' else None) for v in ('B',)}
    summary['fuel_block_variant_B_minus_A_max_pp'] = float((runs['B'].contrib_fuel - runs['A'].contrib_fuel).abs().max())
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), bundle=str(bundle.relative_to(ROOT)) if bundle.is_relative_to(ROOT) else str(bundle), bundle_manifest=sha(bundle / 'MANIFEST.json'),
                                                       inputs={'forecasts': sha(ROOT / FORECASTS), 'evidence': sha(ROOT / EVIDENCE)}, runtime=fi.runtime_identity(), code=sha(__file__),
                                                       outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
