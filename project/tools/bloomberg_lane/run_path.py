"""R31 path lane: the R27 research path re-run at the 90 origins on the Bloomberg input bundle.

    python -m tools.bloomberg_lane.run_path --bundle data/bloomberg_inputs_20260922 --nowcast output/bloomberg_lane_20260922/nowcast --output output/bloomberg_lane_20260922/path

Blocks: core and administered reused from the recorded FAST rows (their inputs are identical on Bloomberg, register
tests T1 and T2); fuel and alcohol re-run on the bundle; food re-run through the R14B system, the R24 long-history
drift and the R27 gap correction on the bundle's food level; h0 from the lane's nowcast BASE (variant A); annual rates
compounded on the bundle's headline history. Scored on the 969-key primary support against the previous truth (the
unrounded CZSO compounded annual rate, comparable with R27) and against the Bloomberg-compounded rate, and on the
matched CNB pairs from 2024.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from models.path_inputs import compound_path
from models.food_drift_r24 import LONG_HISTORY, long_food_rates, candidates_at as r24_candidates
from models.food_ecm_r27 import candidates_at as r27_candidates
from tools.model_register_20260921.build import constant_pump_rates, expanding_same_month_mean, regime_share, rmse
from tools.cnb_rounds_v3.build import quarter_mean

R27 = 'output/research_r27/final'; FAST = 'STATE_FAST_R15'; ROSTER = 'FOOD_ECM_R27'
SUPPORT = 'output/research_r17/attribution/primary_support.csv'; CALENDAR = 'data/release_calendar_cz_cpi.csv'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--bundle', type=Path, required=True); ap.add_argument('--nowcast', type=Path, required=True); ap.add_argument('--output', type=Path, required=True); ap.add_argument('--limit', type=int); args = ap.parse_args()
    bundle = args.bundle if args.bundle.is_absolute() else ROOT / args.bundle; nowcast = args.nowcast if args.nowcast.is_absolute() else ROOT / args.nowcast
    out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((bundle / 'MANIFEST.json').read_text(encoding='utf-8'))
    for rel, digest in manifest['files'].items():
        if sha(bundle / rel) != digest:
            raise ValueError('Bundle file changed: ' + rel)
    headline = pd.read_csv(bundle / 'path/headline_history.csv', index_col=0, float_precision='round_trip'); headline.index = pd.PeriodIndex(headline.index, freq='M'); history = headline.headline_mm
    previous = c.monthly('output/independent_path_frozen_inputs.csv', 'headline_mm')
    levels = pd.read_csv(bundle / 'path/food_log_levels.csv', index_col=0, float_precision='round_trip'); levels.index = pd.PeriodIndex(levels.index, freq='M')
    available = pd.read_csv(bundle / 'path/food_available_from.csv', index_col=0); available.index = pd.PeriodIndex(available.index, freq='M')
    alc = pd.read_csv(bundle / 'path/alcohol_tobacco_mm.csv', index_col=0, float_precision='round_trip'); alc.index = pd.PeriodIndex(alc.index, freq='M'); alc = alc.alcohol_tobacco
    pump = pd.read_csv(bundle / 'path/pump_weekly.csv', index_col=0, parse_dates=True, float_precision='round_trip'); calendar = c.read(CALENDAR)
    long_rates, long_published = long_food_rates(levels, available, ROOT / LONG_HISTORY)
    native = c.read(f'{R27}/native_forecasts.csv'); fast = native[native.model.eq(FAST)]; recorded = native[native.model.eq(ROSTER)]
    forecasts = c.read(f'{R27}/forecasts.csv'); rec_yy = forecasts[forecasts.model.eq(ROSTER)].set_index(['origin', 'h']).yy_exante; rec_actual = forecasts[forecasts.model.eq(ROSTER)].set_index(['origin', 'h']).yy_actual
    lane_base = pd.read_csv(nowcast / 'run_variant_A.csv', index_col='period').HARD_BASE
    clocks = fast[fast.h.eq(0)].set_index('origin').as_of_utc; origins = sorted(clocks.index); origins = origins[:args.limit] if args.limit else origins
    support = c.read(SUPPORT); keys = set(zip(support.origin, support.h))
    actual_prev = 100 * np.expm1(np.log1p(previous / 100).rolling(12).sum()); actual_bbg = 100 * np.expm1(np.log1p(history / 100).rolling(12).sum())
    rows = []; audits = []; started = time.perf_counter()
    for i, origin in enumerate(origins):
        t = pd.Period(origin, 'M'); clock = pd.Timestamp(clocks[origin]); base = fast[fast.origin.eq(origin)].sort_values('h').reset_index(drop=True)
        if list(base.h) != list(range(13)):
            raise ValueError('h0..h12 required at ' + origin)
        # food: R14B system -> R24 long-history drift -> R27 gap correction, all on the bundle's food level
        r24 = r24_candidates(levels, available, long_rates, long_published, origin, clock)
        if r24['status'] != 'estimated':
            raise ValueError(f'{origin}: food drift {r24["status"]}')
        r27 = r27_candidates(levels, available, origin, clock, np.asarray(r24['log_rates']['FOOD_NORM_SHIFT_R24']), fixed_alphas=())
        if r27['status'] != 'estimated':
            raise ValueError(f'{origin}: food gap {r27["status"]}')
        food_path = r27['paths'][ROSTER]
        # alcohol: expanding same-month mean with month t-1 released; fuel: constant pump prices with the release-eve share
        alc_path = {h: expanding_same_month_mean(alc, t + h, t - 1) for h in range(1, 13)}
        share, _ = regime_share(origin, clock.tz_convert('Europe/Prague').tz_localize(None), calendar); fuel_path = dict(zip(range(1, 13), map(float, constant_pump_rates(pump, origin, clock.tz_convert('Europe/Prague').tz_localize(None), share))))
        new = c.replace_block(base, 'food', food_path); new = c.replace_block(new, 'alcohol_tobacco', alc_path); new = c.replace_block(new, 'fuel', fuel_path)
        h0 = float(lane_base.loc[origin]); new.loc[new.h.eq(0), 'mm_forecast'] = h0
        forecast = {int(h): float(v) for h, v in zip(new.h, new.mm_forecast) if h > 0}
        yy_prev_hist = [compound_path(previous[previous.index < t], forecast, t, h, h0) for h in range(13)]        # same forecast, previous history (isolates the history's effect)
        yy_bbg = [compound_path(history[history.index < t], forecast, t, h, h0) for h in range(13)]
        rec = recorded[recorded.origin.eq(origin)].sort_values('h').reset_index(drop=True)
        for h in range(13):
            rows.append(dict(origin=origin, h=h, target=str(t + h), scored=(origin, h) in keys, mm_recorded=float(rec.mm_forecast.iloc[h]), mm_lane=float(new.mm_forecast.iloc[h]),
                             food_recorded=float(rec.value_food.iloc[h]) if h else np.nan, food_lane=float(new.value_food.iloc[h]) if h else np.nan,
                             alc_recorded=float(rec.value_alcohol_tobacco.iloc[h]) if h else np.nan, alc_lane=float(new.value_alcohol_tobacco.iloc[h]) if h else np.nan,
                             fuel_recorded=float(rec.value_fuel.iloc[h]) if h else np.nan, fuel_lane=float(new.value_fuel.iloc[h]) if h else np.nan,
                             yy_recorded=float(rec_yy.get((origin, h), np.nan)), yy_lane_previous_history=yy_prev_hist[h], yy_lane=yy_bbg[h],
                             actual_previous=float(rec_actual.get((origin, h), np.nan)), actual_bbg=float(actual_bbg.get(t + h, np.nan))))
        audits.append(dict(origin=origin, h0_recorded=float(rec.mm_forecast.iloc[0]), h0_lane=h0, mu_long_lane=r24['drifts']['mu_long'], mu_window_lane=r24['drifts']['mu_window'],
                           alpha_lane=r27['audits'][ROSTER]['alpha'], gap_last_lane=r27['audits'][ROSTER]['gap_last'], petrol_share=share))
        if i % 15 == 0 or i == len(origins) - 1:
            print(f'{i + 1}/{len(origins)} {origin}: h0 {h0:.3f} (recorded {rec.mm_forecast.iloc[0]:.3f}), food h6 {food_path[6]:.3f} (recorded {rec.value_food.iloc[6]:.3f}), {time.perf_counter() - started:.0f}s', flush=True)
    frame = pd.DataFrame(rows); frame.to_csv(out / 'path_rows.csv', index=False); pd.DataFrame(audits).to_csv(out / 'audit.csv', index=False)
    z = frame[frame.scored & frame.h.isin([3, 6, 12])].copy(); z['recent'] = z.origin.ge('2024-01'); scores = []
    for h in (3, 6, 12):
        for sample, mask in [('full', z.h.eq(h)), ('origins_2024plus', z.h.eq(h) & z.recent)]:
            w = z[mask]
            scores.append(dict(h=h, sample=sample, n=int(len(w)), rmse_recorded=rmse(w.yy_recorded - w.actual_previous), rmse_lane_forecast_previous_history=rmse(w.yy_lane_previous_history - w.actual_previous),
                               rmse_lane_vs_previous_truth=rmse(w.yy_lane - w.actual_previous), rmse_lane_vs_bbg_truth=rmse(w.yy_lane - w.actual_bbg), rmse_recorded_vs_bbg_truth=rmse(w.yy_recorded - w.actual_bbg),
                               max_abs_forecast_change=float((w.yy_lane - w.yy_recorded).abs().max()), mean_abs_forecast_change=float((w.yy_lane - w.yy_recorded).abs().mean())))
    scores = pd.DataFrame(scores); scores.to_csv(out / 'scores.csv', index=False)
    blocks = {}
    for b in ('food', 'alc', 'fuel'):
        d = (frame[f'{b}_lane'] - frame[f'{b}_recorded']).abs(); blocks[b] = dict(max_abs_change_pp=float(d.max()), mean_abs_change_pp=float(d.mean()))
    d0 = (frame[frame.h.eq(0)].mm_lane - frame[frame.h.eq(0)].mm_recorded).abs(); blocks['h0'] = dict(max_abs_change_pp=float(d0.max()), mean_abs_change_pp=float(d0.mean()))
    # CNB pairs from 2024, report clock: the same matched quarters as R27's evaluation
    pairs = c.read(f'{R27}/evaluation/cnb_pairs.csv'); recent = pairs[pairs.clock.eq('report') & pairs.report_date.ge('2024-01-01')]; cnb = recent[recent.model.eq('cnb')]
    lane_paths = {o: {pd.Period(o, 'M') + int(h): v for h, v in zip(g.h, g.yy_lane) if np.isfinite(v)} for o, g in frame.groupby('origin')}
    errs = []; errs4 = []
    cnb = cnb[cnb.origin.isin(lane_paths)]; rec_pairs_mask = recent.origin.isin(lane_paths)
    for r in cnb.itertuples():
        v = quarter_mean(r.quarter, pd.Period(r.origin, 'M'), lane_paths[r.origin], actual_prev); errs.append(v - r.realised)
        if r.quarters_ahead == 4:
            errs4.append(v - r.realised)
    rec_pairs = recent[recent.model.eq(ROSTER) & rec_pairs_mask]
    cnb_scores = dict(pairs=len(errs), rmse_lane=rmse(errs), rmse_recorded=rmse(rec_pairs.error), rmse_cnb=rmse(cnb.error), rmse_lane_4q=rmse(errs4), rmse_recorded_4q=rmse(rec_pairs[rec_pairs.quarters_ahead.eq(4)].error), rmse_cnb_4q=rmse(cnb[cnb.quarters_ahead.eq(4)].error))
    summary = dict(blocks=blocks, cnb_pairs_2024plus=cnb_scores, scores=scores.to_dict('records'))
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), bundle=str(bundle.relative_to(ROOT)) if bundle.is_relative_to(ROOT) else str(bundle), bundle_manifest=sha(bundle / 'MANIFEST.json'), nowcast_run=sha(nowcast / 'run_variant_A.csv'),
                                                       inputs={k: sha(ROOT / p) for k, p in dict(native=f'{R27}/native_forecasts.csv', forecasts=f'{R27}/forecasts.csv', pairs=f'{R27}/evaluation/cnb_pairs.csv', support=SUPPORT, previous_headline='output/independent_path_frozen_inputs.csv', long_history=LONG_HISTORY, calendar=CALENDAR).items()},
                                                       code=sha(__file__), outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    pd.set_option('display.width', 250); print(scores.round(4).to_string(index=False)); print(json.dumps(dict(blocks=blocks, cnb=cnb_scores), indent=1))


if __name__ == '__main__':
    main()
