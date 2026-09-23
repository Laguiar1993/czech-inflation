"""R31B: the path's food-products PPI level from cumulated CZPPA10M, as a variant of the R31 bundle.

    python -m tools.bloomberg_lane.food_ppi_variant build --bundle data/bloomberg_inputs_20260922 --output data/bloomberg_inputs_20260922_foodppi
    python -m tools.bloomberg_lane.run_path --bundle data/bloomberg_inputs_20260922_foodppi --nowcast output/bloomberg_lane_20260922/nowcast --output output/bloomberg_lane_20260922_foodppi/path
    python -m tools.bloomberg_lane.food_ppi_variant compare --lane output/bloomberg_lane_20260922/path --variant output/bloomberg_lane_20260922_foodppi/path --output output/bloomberg_lane_20260922_foodppi/comparison

`build` copies the R31 bundle and replaces the food_ppi column of path/food_log_levels.csv with the cumulated
published m/m (100*ln(1 + CZPPA10M/100), summed, re-based to 2015-01); provenance and manifest are rewritten.
`compare` sets the variant's path rows against the R31 lane's and the recorded R27.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.model_register_20260921.build import load_snapshots, monthly

TICKER = 'CZPPA10M Index'; COLUMN = 'path/food_levels.food_ppi'; BASE = pd.Period('2015-01', 'M')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cumulated_level(mm, base=BASE):
    """100*ln(level / level at `base`) from published percentage m/m: the sum of 100*ln(1 + mm/100), re-based.

    Only the contiguous run of months around `base` is used (the snapshot has a hole at 2002-08, far before the frame).
    """
    if base not in mm.index or not mm.index.is_monotonic_increasing or mm.index.has_duplicates:
        raise ValueError('published m/m must cover the base month and be sorted')
    missing = pd.period_range(mm.index.min(), mm.index.max(), freq='M').difference(mm.index)
    start = max([m for m in missing if m < base], default=mm.index.min() - 1) + 1; stop = min([m for m in missing if m > base], default=mm.index.max() + 1) - 1
    run = mm.loc[start:stop]
    level = (100 * np.log1p(run / 100)).cumsum(); return level - level.loc[base]


def resolve(p):
    p = Path(p); return p if p.is_absolute() else ROOT / p


def build(args):
    bundle = resolve(args.bundle); out = resolve(args.output)
    if out.exists():
        raise FileExistsError(out)
    manifest = json.loads((bundle / 'MANIFEST.json').read_text(encoding='utf-8'))
    for rel, digest in manifest['files'].items():
        if sha(bundle / rel) != digest:
            raise ValueError('Bundle file changed: ' + rel)
    shutil.copytree(bundle, out, ignore=shutil.ignore_patterns('.gitattributes'))
    bbg = load_snapshots(); mm = monthly(bbg[TICKER]); level = cumulated_level(mm)
    levels = pd.read_csv(out / 'path/food_log_levels.csv', index_col=0, float_precision='round_trip'); levels.index = pd.PeriodIndex(levels.index, freq='M')
    previous = levels.food_ppi.copy(); common = previous.dropna().index.intersection(level.index)
    if len(common) != int(previous.notna().sum()):
        raise ValueError('cumulated CZPPA10M does not cover every month of the frame')
    gap = (level.loc[common] - previous.loc[common]).abs(); levels.loc[common, 'food_ppi'] = level.loc[common]
    levels.to_csv(out / 'path/food_log_levels.csv', index_label='period')
    prov = json.loads((out / 'provenance.json').read_text(encoding='utf-8'))
    prov['columns'][COLUMN] = dict(ticker=TICKER, transform='cumulated published m/m: sum of 100*ln(1 + m/m/100), re-based to 2015-01', months_from_bloomberg=int(len(common)), first=str(common.min()), last=str(common.max()),
                                   months_kept_from_previous_source=0, kept_span=None, exact_share=float((gap <= 1e-9).mean()), max_abs_gap=float(gap.max()), mean_abs_gap=float(gap.mean()), gap_at_last=float((level.loc[common] - previous.loc[common]).iloc[-1]))
    prov['variant'] = dict(of=str(bundle.relative_to(ROOT)) if bundle.is_relative_to(ROOT) else str(bundle), built_at_utc=datetime.now(timezone.utc).isoformat(), changed=[COLUMN])
    (out / 'provenance.json').write_text(json.dumps(prov, indent=1), encoding='utf-8')
    files = {str(p.relative_to(out)).replace('\\', '/'): sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('MANIFEST.json', '.gitattributes')}
    (out / 'MANIFEST.json').write_text(json.dumps(dict(variant_of=sha(bundle / 'MANIFEST.json'), snapshots=manifest.get('snapshots'), previous_sources=manifest.get('previous_sources'), code=sha(__file__), files=files), indent=1), encoding='utf-8')
    print(json.dumps(prov['columns'][COLUMN], indent=1))


def compare(args):
    lane = resolve(args.lane); variant = resolve(args.variant); out = resolve(args.output); out.mkdir(parents=True, exist_ok=False)
    a = pd.read_csv(lane / 'path_rows.csv'); b = pd.read_csv(variant / 'path_rows.csv')
    if not (a.origin.equals(b.origin) and a.h.equals(b.h)):
        raise ValueError('lane and variant rows differ in origins or horizons')
    rows = pd.DataFrame(dict(origin=a.origin, h=a.h, target=a.target, scored=a.scored, food_recorded=a.food_recorded, food_lane=a.food_lane, food_variant=b.food_lane,
                             mm_lane=a.mm_lane, mm_variant=b.mm_lane, yy_recorded=a.yy_recorded, yy_lane=a.yy_lane, yy_variant=b.yy_lane, actual_previous=a.actual_previous))
    rows['food_variant_minus_lane'] = rows.food_variant - rows.food_lane; rows['yy_variant_minus_lane'] = rows.yy_variant - rows.yy_lane
    rows.to_csv(out / 'rows.csv', index=False)
    by_h = rows.groupby('h').agg(food_max=('food_variant_minus_lane', lambda s: float(s.abs().max())), food_mean=('food_variant_minus_lane', lambda s: float(s.abs().mean())),
                                 yy_max=('yy_variant_minus_lane', lambda s: float(s.abs().max())), yy_mean=('yy_variant_minus_lane', lambda s: float(s.abs().mean()))).reset_index()
    by_h.to_csv(out / 'by_horizon.csv', index=False)
    sa = pd.read_csv(lane / 'scores.csv'); sb = pd.read_csv(variant / 'scores.csv')
    scores = sa[['h', 'sample', 'n', 'rmse_recorded', 'rmse_lane_vs_previous_truth', 'rmse_lane_vs_bbg_truth']].rename(columns={'rmse_lane_vs_previous_truth': 'rmse_lane', 'rmse_lane_vs_bbg_truth': 'rmse_lane_bbg_truth'})
    scores['rmse_variant'] = sb.rmse_lane_vs_previous_truth.to_numpy(); scores['rmse_variant_bbg_truth'] = sb.rmse_lane_vs_bbg_truth.to_numpy(); scores['max_abs_change_vs_recorded_variant'] = sb.max_abs_forecast_change.to_numpy()
    z = rows[rows.scored & rows.h.isin([3, 6, 12])]
    scores['max_abs_change_vs_lane'] = [float((z[z.h.eq(h) & (z.origin.ge('2024-01') if s == 'origins_2024plus' else True)].yy_variant_minus_lane).abs().max()) for h, s in zip(scores.h, scores['sample'])]
    scores.to_csv(out / 'scores.csv', index=False)
    aa = pd.read_csv(lane / 'audit.csv'); ab = pd.read_csv(variant / 'audit.csv')
    audit = pd.DataFrame(dict(origin=aa.origin, alpha_lane=aa.alpha_lane, alpha_variant=ab.alpha_lane, gap_last_lane=aa.gap_last_lane, gap_last_variant=ab.gap_last_lane, mu_long_lane=aa.mu_long_lane, mu_long_variant=ab.mu_long_lane))
    audit.to_csv(out / 'audit.csv', index=False)
    ca = json.loads((lane / 'summary.json').read_text(encoding='utf-8'))['cnb_pairs_2024plus']; cb = json.loads((variant / 'summary.json').read_text(encoding='utf-8'))['cnb_pairs_2024plus']
    summary = dict(food_block=dict(max_abs_change_pp=float(rows.food_variant_minus_lane.abs().max()), mean_abs_change_pp=float(rows.food_variant_minus_lane.abs().mean()),
                                   months_over_0p05=int((rows.food_variant_minus_lane.abs() > .05).sum()), months_over_0p10=int((rows.food_variant_minus_lane.abs() > .10).sum()),
                                   largest=rows.assign(d=rows.food_variant_minus_lane.abs()).sort_values('d', ascending=False).head(5)[['origin', 'h', 'd']].round(4).to_dict('records')),
                   annual_rate=dict(max_abs_change_pp=float(rows.yy_variant_minus_lane.abs().max()), by_h=by_h.round(5).to_dict('records')),
                   alpha=dict(lane_unique=sorted(set(audit.alpha_lane.round(6))), variant_unique=sorted(set(audit.alpha_variant.round(6))), gap_last_max_abs_change=float((audit.gap_last_variant - audit.gap_last_lane).abs().max()), mu_long_max_abs_change=float((audit.mu_long_variant - audit.mu_long_lane).abs().max())),
                   cnb_pairs_2024plus=dict(pairs=ca['pairs'], rmse_recorded=ca['rmse_recorded'], rmse_lane=ca['rmse_lane'], rmse_variant=cb['rmse_lane'], rmse_cnb=ca['rmse_cnb'], rmse_lane_4q=ca['rmse_lane_4q'], rmse_variant_4q=cb['rmse_lane_4q'], rmse_cnb_4q=ca['rmse_cnb_4q']),
                   scores=scores.to_dict('records'))
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), lane_manifest=sha(lane / 'manifest.json'), variant_manifest=sha(variant / 'manifest.json'), code=sha(__file__),
                                                       outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    pd.set_option('display.width', 250); print(scores.round(4).to_string(index=False)); print(json.dumps({k: v for k, v in summary.items() if k != 'scores'}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__); sub = ap.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('--bundle', required=True); b.add_argument('--output', required=True); b.set_defaults(func=build)
    c = sub.add_parser('compare'); c.add_argument('--lane', required=True); c.add_argument('--variant', required=True); c.add_argument('--output', required=True); c.set_defaults(func=compare)
    args = ap.parse_args(); args.func(args)


if __name__ == '__main__':
    main()
