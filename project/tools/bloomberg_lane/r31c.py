"""R31C: the nowcast without its last three non-Bloomberg live inputs, one at a time and together.

    python -m tools.bloomberg_lane.r31c --bundle data/bloomberg_inputs_20260922_foodppi --output output/bloomberg_lane_20260922_r31c

C1: services_l1 removed from the core feature frame. C2: the fuel item m/m from CP7FCZ (HICP fuels, two-decimal
index). C3: the EC bulletin pump prices (R31 variant B, read from the lane run, not re-run). C123: all three.
C0 is the R31 lane's variant A. BASE, HALF and FULL go through forecast_independent.calculate at the 90 recorded
release-eve clocks (run_nowcast's own functions). The path effect is h0 only: the R31B path rows are recompounded
with each variant's BASE as h0 and scored as R31 (h3/h6/h12 against the previous truth; CNB pairs from 2024).
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.bloomberg_lane.run_nowcast import bundle_frames, run, score, sha, MODELS, FORECASTS, EVIDENCE   # imports forecast_independent with the loader stubs
from tools.model_register_20260921.build import load_snapshots, monthly, rmse
from tools.cnb_rounds_v3.build import quarter_mean
from models.path_inputs import compound_path
import r17_common as c

LANE = 'output/bloomberg_lane_20260922/nowcast'; PATH_B = 'output/bloomberg_lane_20260922_foodppi/path'
R27 = 'output/research_r27/final'; SUPPORT = 'output/research_r17/attribution/primary_support.csv'; PREVIOUS = 'output/independent_path_frozen_inputs.csv'
FUEL_TICKER = 'CP7FCZ Index'; SERVICES = 'services_l1'
VARIANTS = {'C1': dict(drop_services=True, hicp_fuel=False, weekly='A'), 'C2': dict(drop_services=False, hicp_fuel=True, weekly='A'), 'C123': dict(drop_services=True, hicp_fuel=True, weekly='B')}
SAMPLES = {'all': '2000', 'prints_2024plus': '2024-01', 'flash_era_2025plus': '2025-01'}


def hicp_fuel_mm(bbg):
    s = monthly(bbg[FUEL_TICKER]); return (100 * (s / s.shift(1) - 1)).dropna()


def variant_frames(bundle, spec, bbg, provenance):
    frames = bundle_frames(bundle, spec['weekly'])
    if spec['drop_services']:
        if SERVICES not in frames['features'].columns or any(col.startswith(SERVICES + '_x') for col in frames['features'].columns):
            raise ValueError('services_l1 expected as a plain column')
        frames['features'] = frames['features'].drop(columns=[SERVICES])
    if spec['hicp_fuel']:
        comp = frames['components'].copy(); source = hicp_fuel_mm(bbg); previous = comp.fuel.dropna(); common = previous.index.intersection(source.index)
        if len(common) != len(previous):
            raise ValueError('CP7FCZ does not cover every month of the fuel column')
        gap = (source.loc[common] - previous.loc[common]).abs()
        provenance['nowcast/components.fuel'] = dict(ticker=FUEL_TICKER, transform='100*(I_t/I_{t-1} - 1) of the HICP 07.2.2 fuels index', months_from_bloomberg=int(len(common)), first=str(common.min()), last=str(common.max()),
                                                     months_kept_from_previous_source=0, exact_share=float((gap <= 1e-9).mean()), share_within_0p1=float((gap <= .1 + 1e-9).mean()), max_abs_gap=float(gap.max()), mean_abs_gap=float(gap.mean()))
        comp.loc[common, 'fuel'] = source.loc[common]; frames['components'] = comp
    return frames


def path_effect(bundle, variants_base, targets, out):
    """Recompound the R31B path rows with each variant's BASE as h0; reproduce R31B first. `targets` restricts the origins (--limit)."""
    rows = c.read(f'{PATH_B}/path_rows.csv'); rows = rows[rows.origin.isin(targets)]
    headline = pd.read_csv(bundle / 'path/headline_history.csv', index_col=0, float_precision='round_trip'); headline.index = pd.PeriodIndex(headline.index, freq='M'); history = headline.headline_mm
    previous = c.monthly(PREVIOUS, 'headline_mm'); actual_prev = 100 * np.expm1(np.log1p(previous / 100).rolling(12).sum())
    support = c.read(SUPPORT); keys = set(zip(support.origin, support.h))
    pairs = c.read(f'{R27}/evaluation/cnb_pairs.csv'); recent = pairs[pairs.clock.eq('report') & pairs.report_date.ge('2024-01-01')]; cnb = recent[recent.model.eq('cnb') & recent.origin.isin(rows.origin.unique())]
    out_rows = []; scores = []; cnb_scores = {}
    for name, base in [('C0', None)] + list(variants_base.items()):
        paths = {}
        for origin, g in rows.groupby('origin'):
            t = pd.Period(origin, 'M'); g = g.sort_values('h'); forecast = {int(h): float(v) for h, v in zip(g.h, g.mm_lane) if h > 0}
            h0 = float(g[g.h.eq(0)].mm_lane.iloc[0]) if base is None else float(base.loc[origin])
            yy = [compound_path(history[history.index < t], forecast, t, h, h0) for h in range(13)]
            if base is None and not np.allclose(yy, g.yy_lane.to_numpy(), atol=1e-9, equal_nan=True):
                raise ValueError('recompounding does not reproduce R31B at ' + origin)
            paths[origin] = {t + h: v for h, v in enumerate(yy) if np.isfinite(v)}
            for h, v in enumerate(yy):
                out_rows.append(dict(variant=name, origin=origin, h=h, yy=v, actual_previous=float(g.actual_previous.iloc[h]), scored=(origin, h) in keys))
        z = pd.DataFrame([r for r in out_rows if r['variant'] == name]); z = z[z.scored & z.h.isin([3, 6, 12])]
        for h in (3, 6, 12):
            for sample, mask in [('full', z.h.eq(h)), ('origins_2024plus', z.h.eq(h) & z.origin.ge('2024-01'))]:
                w = z[mask]; scores.append(dict(variant=name, h=h, sample=sample, n=int(len(w)), rmse=rmse(w.yy - w.actual_previous)))
        errs = []; errs4 = []
        for r in cnb.itertuples():
            v = quarter_mean(r.quarter, pd.Period(r.origin, 'M'), paths[r.origin], actual_prev); errs.append(v - r.realised)
            if r.quarters_ahead == 4:
                errs4.append(v - r.realised)
        cnb_scores[name] = dict(pairs=len(errs), rmse=rmse(errs), rmse_4q=rmse(errs4))
    cnb_scores['cnb'] = dict(pairs=int(len(cnb)), rmse=rmse(cnb.error), rmse_4q=rmse(cnb[cnb.quarters_ahead.eq(4)].error))
    pd.DataFrame(out_rows).to_csv(out / 'path_rows.csv', index=False)
    scores = pd.DataFrame(scores).pivot(index=['h', 'sample', 'n'], columns='variant', values='rmse').reset_index(); scores.to_csv(out / 'path_scores.csv', index=False)
    return scores, cnb_scores


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--bundle', type=Path, required=True); ap.add_argument('--output', type=Path, required=True); ap.add_argument('--limit', type=int); args = ap.parse_args()
    bundle = args.bundle if args.bundle.is_absolute() else ROOT / args.bundle; out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    recorded = pd.read_csv(ROOT / FORECASTS, index_col='period'); ev = pd.read_csv(ROOT / EVIDENCE); base_ev = ev[ev.model.eq('HARD_BASE')].set_index('period')
    targets = [p for p in recorded.index if p >= '2019-02']; targets = targets[:args.limit] if args.limit else targets
    clocks = {p: pd.Timestamp(recorded.loc[p, 'as_of_eve']).tz_localize('Europe/Prague') for p in targets}
    lane = {v: pd.read_csv(ROOT / LANE / f'run_variant_{v}.csv', index_col='period') for v in ('A', 'B')}
    bbg = load_snapshots(); provenance = {}; runs = {'C0': lane['A'], 'C3': lane['B']}
    for name, spec in VARIANTS.items():
        runs[name] = run(variant_frames(bundle, spec, bbg, provenance), targets, clocks, name); runs[name].to_csv(out / f'run_{name}.csv')
    order = ['C0', 'C1', 'C2', 'C3', 'C123']
    table = pd.DataFrame(index=targets); table['actual'] = base_ev.actual.reindex(targets); table['consensus'] = base_ev.consensus.reindex(targets)
    for m in MODELS:
        table[f'{m}_recorded'] = recorded[m].reindex(targets)
        for v in order:
            table[f'{m}_{v}'] = runs[v][m].reindex(targets)
    table.to_csv(out / 'comparison.csv', index_label='period')
    samples = {k: table.index >= v for k, v in SAMPLES.items()}
    scores = score(table, MODELS, ['recorded'] + order, samples); scores.to_csv(out / 'scores.csv', index=False)
    path_scores, cnb_scores = path_effect(bundle, {v: runs[v].HARD_BASE for v in order if v != 'C0'}, targets, out)
    summary = dict(provenance=provenance, changes={}, rmse={}, tallies={}, decision={}, path=dict(scores=path_scores.to_dict('records'), cnb_pairs_2024plus=cnb_scores))
    for m in MODELS:
        summary['changes'][m] = {}; summary['rmse'][m] = {}; summary['tallies'][m] = {}
        for v in order:
            d = (table[f'{m}_{v}'] - table[f'{m}_C0']).abs()
            summary['changes'][m][v] = dict(max_abs_change=float(d.max()), mean_abs_change=float(d.mean()), months_over_0p05=int((d > .05).sum()), months_over_0p10=int((d > .10).sum()), largest=d.sort_values(ascending=False).head(3).round(4).to_dict())
            summary['rmse'][m][v] = {s: float(scores[(scores.model == m) & (scores.source == v) & (scores['sample'] == s)].rmse.iloc[0]) for s in SAMPLES}
            row = scores[(scores.model == m) & (scores.source == v) & (scores['sample'] == 'all')].iloc[0]
            summary['tallies'][m][v] = dict(closer_than_consensus=int(row.closer_than_consensus), material_wins_big=int(row.material_wins_big), material_losses_big=int(row.material_losses_big), alerts=int(row.alerts), alerts_direction_right=int(row.alerts_direction_right),
                                            alert_material_wins=int(row.alert_material_wins), alert_material_losses=int(row.alert_material_losses), alert_net_pp=float(row.alert_net_pp))
    base = summary['rmse']['HARD_BASE']; wins = {v: summary['tallies']['HARD_BASE'][v]['material_wins_big'] for v in order}
    for v in ('C1', 'C2', 'C123'):
        summary['decision'][v] = dict(rmse_all_within_0p005=abs(base[v]['all'] - base['C0']['all']) <= .005, rmse_2024_within_0p005=abs(base[v]['prints_2024plus'] - base['C0']['prints_2024plus']) <= .005, wins_not_down_more_than_one=wins[v] >= wins['C0'] - 1)
        summary['decision'][v]['passes'] = all(summary['decision'][v].values())
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), bundle=str(bundle.relative_to(ROOT)) if bundle.is_relative_to(ROOT) else str(bundle), bundle_manifest=sha(bundle / 'MANIFEST.json'),
                                                       inputs={k: sha(ROOT / p) for k, p in dict(lane_A=f'{LANE}/run_variant_A.csv', lane_B=f'{LANE}/run_variant_B.csv', path_b_rows=f'{PATH_B}/path_rows.csv', forecasts=FORECASTS, evidence=EVIDENCE, previous_headline=PREVIOUS, pairs=f'{R27}/evaluation/cnb_pairs.csv', support=SUPPORT).items()},
                                                       snapshots={p.parent.name: sha(p) for p in sorted((ROOT / 'data/market_snapshots').glob('*/history_long.csv'))}, code=sha(__file__),
                                                       outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    pd.set_option('display.width', 250); print(json.dumps({k: summary[k] for k in ('changes', 'rmse', 'tallies', 'decision', 'path')}, indent=1))


if __name__ == '__main__':
    main()
