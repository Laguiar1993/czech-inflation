"""CNB Rounds Replayed, third edition: the current path roster against every CNB report since 2022.

    python -m tools.cnb_rounds_v3.build --output output/cnb_rounds_v3

Reads the frozen research runs and their evaluations (nothing is refitted), the archived CNB report tables and the
realised component targets, and writes one self-contained page plus its data and a hash manifest.

Roster shown (20 September 2026): the R27 research path (FAST core, R24 food drift, R27 producer-price gap
correction), its R24 predecessor, the FAST reference, the current-core path with the R27 food block swapped in
(a presentation frame built here by the arithmetic of tools.current_path_r24.extend, not a candidate), and the
R29B core phase rule, which failed the promotion rule and is shown as research only.

Every number on the page is recomputed from the exported files and checked against the evaluations where the two
overlap: annual rates, per-round misses, primary-support RMSE and the block attribution of gaps.
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
from models.path_inputs import compound_path
from tools.cnb_tracker.component_gaps import BLOCK_MAP, WEIGHT, annual_rates, cnb_long_value, cnb_weight, model_block_rates

RUNS = {'r24': 'output/research_r24/final', 'r27': 'output/research_r27/final', 'r29b': 'output/research_r29b/final'}
RUN_FILES = ['forecasts.csv', 'native_forecasts.csv', 'evaluation/cnb_clocks.csv', 'evaluation/cnb_pairs.csv', 'evaluation/primary_scoreboard.csv', 'evaluation/block_error_table.csv']
INPUTS = [f'{run}/{name}' for run in RUNS.values() for name in RUN_FILES] + [
    'output/research_r17/attribution/primary_support.csv', 'output/research_r14b/attribution/actual_component_targets.csv', 'output/independent_path_frozen_inputs.csv',
    'data/cnb_mpr_cpi_quarterly.csv', 'data/cnb_mpr_tables_20260917/cnb_mpr_indicators_long.csv',
    'output/cnb_tracker_20260917/component_gaps/component_gaps.csv', 'CZK_CPI_FORECASTING_LATEST_MODELS_2026-09-14.md']
FOOD = 'FOOD_ECM_R27'         # the roster's food block; FAST with this block swapped in must equal the R27 export exactly
ROSTER_ID = 'ROSTER_R27'
# id, run, source model, swap the roster food block in, label, colour token, dash, default on
ROSTER = [(ROSTER_ID, 'r27', FOOD, False, 'R27 research path · FAST core, food drift and producer-price gap', '--s-roster', None, True),
          ('R24_PATH', 'r27', 'FOOD_NORM_SHIFT_R24', False, 'R24 path · FAST core, food drift (predecessor)', '--s-roster', '2 4', False),
          ('FAST', 'r27', 'STATE_FAST_R15', False, 'FAST · reference', '--s-fast', '7 4', True),
          ('LOCAL_R27FOOD', 'r24', 'STABLE_LOCAL_CORE_R14B', True, 'Current core + R27 food block · presentation frame', '--s-local', None, False),
          ('CORE_PHASE_R29B', 'r29b', 'CORE_LEVELPHASE_FIXED080_R29B', False, 'R27 + core phase rule (1.0 / 0.8) · research, not promoted', '--s-phase', '9 3 2 3', False)]
TAG = {ROSTER_ID: 'R27', 'R24_PATH': 'R24', 'FAST': 'FAST', 'LOCAL_R27FOOD': 'Current core', 'CORE_PHASE_R29B': 'R27 + phase'}
BLOCK_LABEL = {v: k for k, _, v, *_ in ROSTER}
BLOCKS = [('core', 'Core'), ('food_alc_tobacco', 'Food, alcohol & tobacco'), ('fuel', 'Fuel'), ('administered', 'Administered prices')]
SEASON_CS = {'Winter': 'Zima', 'Spring': 'Jaro', 'Summer': 'Léto', 'Autumn': 'Podzim'}
NOWCAST = dict(source='CZK_CPI_FORECASTING_LATEST_MODELS_2026-09-14.md, section 4 (90 first releases, February 2019 to July 2026)',
               columns=['RMSE, all 90', 'RMSE, origins 2024+ (31)', 'RMSE, flash era (19)', 'Large surprises: material wins / losses (23)'],
               rows=[dict(name='Release consensus', values=[.3815, .2410, .1947], wins='—', role='benchmark'),
                     dict(name='BASE · independent, uncorrected', values=[.4180, .2190, .1730], wins='—', role='operating'),
                     dict(name='HALF · half of the learned core-error correction', values=[.4137, .2196, .1656], wins='7 / 1', role='challenger'),
                     dict(name='FULL · full correction', values=[.4139, .2253, .1638], wins='9 / 2', role='monitor for large surprises'),
                     dict(name='Category Raw · category-level core', values=[.4089, .1978, .1610], wins='8 / 2', role='accuracy challenger')])


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(name, **kw):
    return pd.read_csv(ROOT / name, float_precision='round_trip', low_memory=False, **kw)


def monthly(name):
    frame = read(name).set_index(read(name).columns[0]); frame.index = pd.PeriodIndex(frame.index, freq='M')
    if not frame.index.is_unique:
        raise ValueError('Duplicate month in ' + name)
    return frame


def combine(frames, keys, value_columns):
    """Concatenate per-run tables; rows repeated across runs (controls) must agree exactly, and one copy is kept."""
    table = pd.concat(frames, ignore_index=True)
    duplicated = table[table.duplicated(keys, keep=False)]
    if not duplicated.empty:
        spread = duplicated.groupby(keys)[value_columns].agg(lambda s: float(np.nanmax(s.to_numpy(float)) - np.nanmin(s.to_numpy(float))) if s.notna().any() else 0.)
        if (spread.to_numpy() > 1e-9).any():
            raise ValueError('The same model differs between runs: ' + str(spread[(spread > 1e-9).any(axis=1)].head()))
    return table.drop_duplicates(keys, keep='first').reset_index(drop=True)


def quarter_months(quarter):
    q = pd.Period(quarter, 'Q'); return pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M')


def quarter_mean(quarter, origin, path, actual):
    """Mean of three annual rates: known history before the origin, the model path from the origin."""
    values = np.array([actual.get(t, np.nan) if t < origin else path.get(t, np.nan) for t in quarter_months(quarter)], dtype=float)
    return float(values.mean()) if np.isfinite(values).all() else np.nan


def quarter_actual(quarter, actual):
    values = actual.reindex(quarter_months(quarter)).to_numpy(float)
    return float(values.mean()) if np.isfinite(values).all() else np.nan


def swap_food(rows, food, origin, history):
    """FAST-style native rows (h0..h12) with the roster food block for h1-12 swapped in and the annual rates recompounded."""
    g = rows.sort_values('h').reset_index(drop=True); t = pd.Period(origin, 'M'); new = g.copy()
    if list(g.h) != list(range(13)):
        raise ValueError(f'{origin}: h0..h12 required')
    for h in range(1, 13):
        value = food.get((origin, h), np.nan)
        new.loc[h, 'mm_forecast'] += new.loc[h, 'weight_food'] * (value - new.loc[h, 'value_food'])
        new.loc[h, 'value_food'] = value; new.loc[h, 'contribution_food'] = new.loc[h, 'weight_food'] * value
    h0 = float(new.mm_forecast.iloc[0]); forecast = dict(zip(new.h, new.mm_forecast))
    new['yy_exante'] = [compound_path(history[history.index < t], forecast, t, h, h0) for h in range(13)]
    return new


def build_frames(native, frame, headline):
    """One native table per roster series (h0..h12 per origin) with recomputed annual rates, checked against the runs."""
    history = headline.loc[:, 'headline_mm']; stored = frame.set_index(['model', 'origin', 'h']).yy_exante
    outcomes = frame.set_index(['model', 'origin', 'h']).yy_actual; food = native[native.model.eq(FOOD)].set_index(['origin', 'h']).value_food
    frames = {}; checks = {}
    for sid, _, source, swap, *_ in ROSTER:
        rows = []
        for origin, g in native[native.model.eq(source)].groupby('origin'):
            if swap:
                new = swap_food(g, food, origin, history)
            else:
                new = g.sort_values('h').reset_index(drop=True).copy(); t = pd.Period(origin, 'M')
                if list(new.h) != list(range(13)):
                    raise ValueError(f'{source} {origin}: h0..h12 required')
                h0 = float(new.mm_forecast.iloc[0]); forecast = dict(zip(new.h, new.mm_forecast))
                new['yy_exante'] = [compound_path(history[history.index < t], forecast, t, h, h0) for h in range(13)]
            new['yy_actual'] = [outcomes.get((source, origin, h), np.nan) for h in range(13)]
            rows.append(new)
        table = pd.concat(rows, ignore_index=True); table['series'] = sid; frames[sid] = table
        # Same arithmetic as the runs: the recomputed annual rates must reproduce the exported ones for every unswapped series.
        if not swap:
            expected = table.apply(lambda r: stored.get((source, r.origin, r.h), np.nan), axis=1).to_numpy(float)
            mine = table.yy_exante.to_numpy(float); both = np.isfinite(expected) & np.isfinite(mine)
            if (np.isfinite(expected) != np.isfinite(mine)).any():
                raise ValueError(sid + ': annual-rate support differs from the run')
            checks[sid + '_max_abs_gap_vs_run'] = float(np.abs(expected[both] - mine[both]).max())
    # The swap applied to FAST must reproduce the roster's export exactly (the roster differs from FAST in the food block only).
    swapped = pd.concat([swap_food(g, food, o, history) for o, g in native[native.model.eq('STATE_FAST_R15')].groupby('origin')], ignore_index=True)
    gap = np.abs(swapped.yy_exante.to_numpy(float) - frames[ROSTER_ID].yy_exante.to_numpy(float))
    checks['swap_arithmetic_reproduces_roster_export_max_abs_gap'] = float(np.nanmax(gap))
    if max(checks.values()) > 1e-9:
        raise ValueError('Reconstruction differs from the runs: ' + json.dumps(checks))
    return frames, checks


def realised_block_rates(actual, weights, months):
    """Realised monthly rates of CNB's blocks, parts combined with the origin's basket weights, then annual rates."""
    out = {}
    for block, parts in BLOCK_MAP.items():
        total = sum(weights[p] for p in parts); series = pd.Series(0., index=months)
        for p in parts:
            series = series + weights[p] / total * actual[p].reindex(months)
        out[block] = series
    return annual_rates(pd.DataFrame(out))


def report_payload(clock, date, cutoff, origin, as_of, cnb_rows, frames, actual, components, cnb_long, pairs):
    o = pd.Period(origin, 'M'); q = pd.Period(date, 'Q'); season = str(cnb_rows.season.iloc[0]).capitalize()
    start = (q - 2).asfreq('M', 'start'); end = pd.Period(cnb_rows.quarter.iloc[-1], 'Q').asfreq('M', 'end')
    window = pd.period_range(start, end, freq='M'); paths = {}; points = {}; block_paths = {b: {} for b, _ in BLOCKS}; gaps = {}; mae = {}
    included = pairs[pairs.clock.eq(clock) & pairs.report_date.eq(date)]; quarters = sorted(included.quarter.unique())
    cnb_cpi = {r.quarter: float(r.value) for r in cnb_rows.itertuples()}
    if quarters:
        mae['cnb'] = float(np.mean([abs(cnb_cpi[k] - quarter_actual(k, actual)) for k in quarters]))
    block_cnb = {}; block_realised = {}
    quarterly = cnb_long[cnb_long.report_date.eq(date) & cnb_long.frequency.eq('Q') & cnb_long.indicator.isin(BLOCK_MAP)]
    forecast_q = quarterly[quarterly.is_forecast.astype(str).str.lower().eq('true')]
    cnb_w = {r.indicator: cnb_weight(r.row_label) for r in quarterly.drop_duplicates('indicator').itertuples()}
    for block, _ in BLOCKS:
        g = forecast_q[forecast_q.indicator.eq(block)].sort_values('period')
        block_cnb[block] = [dict(quarter=r.period, value=float(r.value)) for r in g.itertuples() if np.isfinite(r.value)]
    for sid, *_ in ROSTER:
        rows = frames[sid][frames[sid].origin.eq(origin)].sort_values('h')
        if rows.empty:
            continue
        path = {o + int(h): float(v) for h, v in zip(rows.h, rows.yy_exante) if np.isfinite(v)}
        anchor = actual.get(o - 1, np.nan)
        pathpoints = [[str(o - 1), float(anchor)]] if np.isfinite(anchor) else []
        for h in range(13):
            if o + h not in path:
                break
            pathpoints.append([str(o + h), path[o + h]])
        paths[sid] = pathpoints
        qvals = {k: quarter_mean(k, o, path, actual) for k in cnb_rows.quarter}
        points[sid] = [[k, v] for k, v in qvals.items() if np.isfinite(v)]
        errors = [abs(qvals[k] - quarter_actual(k, actual)) for k in quarters]
        if quarters and np.isfinite(errors).all():
            mae[sid] = float(np.mean(errors))
        monthly_blocks, weights = model_block_rates(rows, components, origin); yearly = annual_rates(monthly_blocks)
        for block, _ in BLOCKS:
            s = yearly[block].reindex(window)
            block_paths[block][sid] = [[str(m), float(v)] for m, v in s.items() if np.isfinite(v) and m >= o - 1]
        if sid == ROSTER_ID:
            part_weights = {p: float(rows[rows.h.gt(0)][w].mean()) for p, w in WEIGHT.items()}
            realised_yearly = realised_block_rates(components, part_weights, pd.period_range(start - 12, end, freq='M'))
            for block, _ in BLOCKS:
                s = realised_yearly[block].reindex(window)
                block_realised[block] = [[str(m), float(v)] for m, v in s.items() if np.isfinite(v)]
        gap_rows = []
        for k in cnb_rows.quarter:
            if not np.isfinite(qvals[k]) or k not in cnb_cpi:
                continue
            span = quarter_months(k); parts = {}; explained = 0.
            for block, _ in BLOCKS:
                ours = yearly[block].reindex(span)
                ours = float(ours.mean()) if ours.notna().all() else np.nan
                theirs = cnb_long_value(cnb_long, date, block, k); w_cnb = cnb_w.get(block, np.nan)
                parts[block] = weights[block] * ours - w_cnb * theirs if np.isfinite([ours, theirs, w_cnb]).all() else np.nan
                if np.isfinite(parts[block]):
                    explained += parts[block]
            headline = qvals[k] - cnb_cpi[k]
            complete = all(np.isfinite(v) for v in parts.values())
            parts['unexplained'] = headline - explained if complete else np.nan
            realised = quarter_actual(k, actual)
            gap_rows.append(dict(quarter=k, quarters_ahead=pd.Period(k, 'Q').ordinal - q.ordinal + 1, model=qvals[k], cnb=cnb_cpi[k], gap=headline,
                                 realised=realised if np.isfinite(realised) else None, parts=parts, complete=complete))
        gaps[sid] = gap_rows
    return dict(id=f'{date}-{clock}', clock=clock, report_date=date, cutoff_date=cutoff, origin=origin,
                origin_clock=pd.Timestamp(as_of).tz_convert('Europe/Prague').strftime('%Y-%m-%d %H:%M'), season=season, season_cs=SEASON_CS.get(season, ''),
                year=int(date[:4]), window=dict(start=str(start), end=str(end)), cnb=[dict(quarter=r.quarter, value=float(r.value)) for r in cnb_rows.itertuples()],
                realised_quarters=[dict(quarter=k, value=v) for k in cnb_rows.quarter if np.isfinite(v := quarter_actual(k, actual))],
                paths=paths, quarter_points=points, score=dict(n=len(quarters), quarters=quarters, mae=mae),
                blocks={b: dict(cnb=block_cnb[b], realised=block_realised.get(b, []), paths=block_paths[b], cnb_weight=cnb_w.get(b)) for b, _ in BLOCKS}, gaps=gaps)


def check_rounds(reports, pairs, tracker_gaps):
    """Per-round misses and gap parts must equal the R24 evaluation and the tracker where the roster overlaps."""
    worst = dict(mae=0., gap=0., n_mae=0, n_gap=0)
    source_of = {sid: src for sid, _, src, swap, *_ in ROSTER if not swap}; source_of['cnb'] = 'cnb'
    for rep in reports:
        own = pairs[pairs.clock.eq(rep['clock']) & pairs.report_date.eq(rep['report_date'])]
        for sid, src in source_of.items():
            if sid in rep['score']['mae']:
                expected = float(own[own.model.eq(src)].error.abs().mean())
                worst['mae'] = max(worst['mae'], abs(expected - rep['score']['mae'][sid])); worst['n_mae'] += 1
            for row in rep['gaps'].get(sid, []):
                hit = tracker_gaps[tracker_gaps.model.eq(src) & tracker_gaps.clock.eq(rep['clock']) & tracker_gaps.report_date.eq(rep['report_date']) & tracker_gaps.quarter.eq(row['quarter'])]
                if hit.empty:
                    continue
                parts = hit.set_index('block').contribution_gap
                for block, value in row['parts'].items():
                    if np.isfinite(value) and np.isfinite(parts.get(block, np.nan)):
                        worst['gap'] = max(worst['gap'], abs(value - float(parts[block]))); worst['n_gap'] += 1
                worst['gap'] = max(worst['gap'], abs(float(hit.headline_gap.iloc[0]) - row['gap']))
    if worst['mae'] > 1e-9 or worst['gap'] > 1e-9:
        raise ValueError('Round arithmetic differs from the evaluation: ' + json.dumps(worst))
    return worst


def board_path(frames, support, pairs, scoreboard, actual):
    """Headline annual-rate RMSE on the 969-key primary support and against CNB on the matched pairs from 2024."""
    rows = []; recent = pairs[pairs.clock.eq('report') & pairs.report_date.ge('2024-01-01')]
    cnb_recent = recent[recent.model.eq('cnb')]; cnb_4q = cnb_recent[cnb_recent.quarters_ahead.eq(4)]
    checks = {}
    for sid, _, src, swap, label, *_ in ROSTER:
        f = frames[sid].merge(support, on=['origin', 'h'], validate='many_to_one'); e = f.yy_exante - f.yy_actual
        cells = {}
        for name, mask in [('full', pd.Series(True, index=f.index)), ('recent', f.origin.ge('2024-01'))]:
            for h in (3, 6, 12):
                m = mask & f.h.eq(h) & np.isfinite(e); cells[f'{name}_h{h}'] = float(np.sqrt((e[m] ** 2).mean())); cells[f'{name}_n{h}'] = int(m.sum())
        if not swap:
            for name, sample in [('full', 'full'), ('recent', 'origins_2024plus')]:
                for h in (3, 6, 12):
                    ref = scoreboard[scoreboard.model.eq(src) & scoreboard.metric.eq('headline_yy') & scoreboard.h.eq(h) & scoreboard['sample'].eq(sample)].rmse
                    checks[f'{sid}_{name}_h{h}'] = abs(float(ref.iloc[0]) - cells[f'{name}_h{h}'])
        # Against CNB: recompute the quarter means from this frame on the evaluation's own matched support.
        q_err = []; q4 = []
        for r in recent[recent.model.eq('cnb')].itertuples():
            own = frames[sid][frames[sid].origin.eq(r.origin)]
            path = {pd.Period(r.origin, 'M') + int(h): float(v) for h, v in zip(own.h, own.yy_exante) if np.isfinite(v)}
            v = quarter_mean(r.quarter, pd.Period(r.origin, 'M'), path, actual)
            q_err.append(v - r.realised)
            if r.quarters_ahead == 4:
                q4.append(v - r.realised)
        cells['cnb_pairs'] = len(q_err); cells['vs_cnb_rmse'] = float(np.sqrt(np.mean(np.square(q_err)))); cells['vs_cnb_rmse_4q'] = float(np.sqrt(np.mean(np.square(q4)))); cells['cnb_pairs_4q'] = len(q4)
        if not swap:
            mine = recent[recent.model.eq(src)]
            checks[f'{sid}_vs_cnb'] = abs(float(np.sqrt((mine.error ** 2).mean())) - cells['vs_cnb_rmse'])
        rows.append(dict(id=sid, label=label, promoted=sid == ROSTER_ID, **cells))
    if max(checks.values()) > 1e-9:
        raise ValueError('Board differs from the evaluation: ' + json.dumps(checks))
    cnb = dict(rmse=float(np.sqrt((cnb_recent.error ** 2).mean())), rmse_4q=float(np.sqrt((cnb_4q.error ** 2).mean())), n=len(cnb_recent), n_4q=len(cnb_4q))
    return dict(rows=rows, cnb=cnb, support=len(support)), checks


def board_blocks(block_table):
    """Block attribution from the evaluations: RMS of the cumulative weighted block error, h1-12, pp of headline."""
    shown = ['STATE_FAST_R15', 'FOOD_NORM_SHIFT_R24', FOOD, 'CORE_LEVELPHASE_FIXED080_R29B']
    keep = block_table[block_table.H.eq(12) & block_table['sample'].isin(['full', 'origins_2024plus']) & block_table.model.isin(shown)]
    rows = []
    for sample in ('full', 'origins_2024plus'):
        for model in shown:
            g = keep[keep.model.eq(model) & keep['sample'].eq(sample)]
            rows.append(dict(id=BLOCK_LABEL[model], sample='recent' if sample == 'origins_2024plus' else 'full', n=int(g.n.max()),
                             **{f'{r.block}_rms': float(r.rms) for r in g.itertuples()}, **{f'{r.block}_bias': float(r.bias) for r in g.itertuples()}))
    return rows


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (pd.Period, pd.Timestamp, Path)):
        return str(value)
    return value


METHOD = [
    'Historical research replay of the roster of 20 September 2026 on the frozen R24, R27 and R29B runs (90 monthly origins, February 2019 to July 2026). Current-vintage inputs and reconstructed availability; no untouched holdout, no live forecast, no prospective record yet.',
    'Each panel freezes one CNB Monetary Policy Report. The replay origin is the last simulated snapshot strictly before report-day midnight in Prague (the report clock) or through the CNB cut-off day (the cut-off clock). Neither clock is chosen by accuracy. CNB has one more CPI print than our snapshot in every round.',
    'Every monthly path keeps the independent HARD_BASE h0. Annual inflation compounds one origin\u2019s own monthly rates; a model quarter is the mean of three annual rates, with known history before the origin. No later forecast is borrowed.',
    'The R27 research path is FAST\u2019s core, fuel, administered and alcohol-and-tobacco blocks with the food block replaced by the R24 long-history drift and a fixed correction that closes about 0.6 of the retail-to-producer food price gap over h1\u20136 (R27; promoted under the R26 rule after an independent review, as a fixed rule, not an estimator). The R24 path is its predecessor. The current-core path with the R27 food block is a presentation frame built here by replacing only the food block; it was never a candidate. The R29B line applies a core persistence of 1.0 while producer-price momentum runs above 2% a year and pulls core toward 2% at 0.8 otherwise; it failed two conditions of the rule (the era-mean phase reading and one assembled cell by 0.05%) and is shown as research only.',
    'Block panels: our monthly annual rate of each CNB block (core; food with alcohol and tobacco; fuel; administered prices), compounded from realised monthly rates before the origin, the realised h0 month and the model\u2019s block forecasts from h1. CNB\u2019s quarterly block forecasts come from the report\u2019s own table (bold rows), with the weights printed there. Realised block rates use the origin\u2019s basket weights to combine food with alcohol and tobacco.',
    'Where the gap sits: for each CNB forecast quarter, model minus CNB on the headline, split as basket weight \u00d7 our block rate minus CNB weight \u00d7 CNB block rate. What the four blocks do not explain (the reconciliation wedge, weight and aggregation differences, CNB\u2019s indirect-tax treatment) is reported as unexplained, never forced into a block. This is an accounting of an ex-ante gap; CNB forecasts never enter any model.',
    'Per-round misses use the evaluations\u2019 matched support (every quarter where all run models, CNB and the outcome are complete), regardless of which series are switched on. Repeated quarters across reports are dependent. The roster board uses the fixed 969-key primary support for annual-rate RMSE and the 34 matched report-clock pairs from 2024 against CNB.',
    'Nowcast figures are copied from the 14 September 2026 model document and are not recomputed here. A material win or loss is an absolute error at least 0.15 pp below or above the benchmark. Every path gain shown is historical evidence on a studied sample, not established superiority over CNB.',
    'Defaults show the R27 research path and FAST for readability, not promotion beyond what the results documents state. No survey, inflation-expectations or CNB forecast enters any independent path.']


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); args = ap.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    hashes = {name: sha(ROOT / name) for name in INPUTS}
    template = Path(__file__).with_name('template.html'); hashes['tools/cnb_rounds_v3/template.html'] = sha(template); hashes['tools/cnb_rounds_v3/build.py'] = sha(__file__)
    keys = ['model', 'origin', 'h']
    frame = combine([read(f'{run}/forecasts.csv') for run in RUNS.values()], keys, ['mm_forecast', 'yy_exante', 'yy_actual'])
    native = combine([read(f'{run}/native_forecasts.csv') for run in RUNS.values()], keys, ['mm_forecast', 'value_food', 'value_core', 'value_administered', 'value_fuel'])
    clocks = read(f'{RUNS["r27"]}/evaluation/cnb_clocks.csv')
    pairs = combine([read(f'{run}/evaluation/cnb_pairs.csv') for run in RUNS.values()], ['clock', 'report_date', 'quarter', 'model'], ['forecast', 'realised', 'error'])
    scoreboard = combine([read(f'{run}/evaluation/primary_scoreboard.csv') for run in RUNS.values()], ['model', 'h', 'metric', 'sample'], ['rmse', 'mae', 'bias'])
    block_table = combine([read(f'{run}/evaluation/block_error_table.csv') for run in RUNS.values()], ['model', 'H', 'sample', 'block'], ['rms', 'bias'])
    support = read('output/research_r17/attribution/primary_support.csv'); components = monthly('output/research_r14b/attribution/actual_component_targets.csv')
    headline = monthly('output/independent_path_frozen_inputs.csv'); cnb = read('data/cnb_mpr_cpi_quarterly.csv'); cnb_long = read('data/cnb_mpr_tables_20260917/cnb_mpr_indicators_long.csv')
    tracker_gaps = read('output/cnb_tracker_20260917/component_gaps/component_gaps.csv')
    actual = 100 * np.expm1(np.log1p(headline.headline_mm / 100).rolling(12).sum())
    frames, checks = build_frames(native, frame, headline)
    selected = cnb[cnb.is_forecast.astype(str).str.lower().eq('true') & cnb.report_date.ge('2022-01-01')]
    reports = {'report': [], 'cutoff': []}
    for clock in clocks.to_dict('records'):
        if not isinstance(clock['origin'], str):
            continue
        g = selected[selected.report_date.eq(clock['report_date'])].sort_values('quarter')
        if g.empty:
            continue
        reports[clock['clock']].append(report_payload(clock['clock'], clock['report_date'], clock['cutoff_date'], clock['origin'], clock['as_of_utc'], g, frames, actual, components, cnb_long, pairs))
    checks['rounds'] = check_rounds([*reports['report'], *reports['cutoff']], pairs, tracker_gaps)
    path_board, board_checks = board_path(frames, support, pairs, scoreboard, actual); checks['board_max_abs_gap_vs_evaluation'] = max(board_checks.values())
    series = [dict(id='realised', label='Realised · current vintage', short='Realised', kind='realised', color='--realised', width=2.4, default=True),
              dict(id='cnb', label='CNB published forecast', short='CNB', kind='cnb', color='--cnb', width=2., default=True)]
    for sid, run, src, swap, label, color, dash, default in ROSTER:
        series.append(dict(id=sid, source=src, run=RUNS[run], label=label, short=label.split(' · ')[0], tag=TAG[sid], kind='model', color=color, width=2.2, dash=dash, default=default,
                           note='presentation frame: source path with the R27 food block swapped in' if swap else f'exactly the frozen export of {RUNS[run]}'))
    payload = dict(title='CNB Rounds Replayed', roster_date='20 September 2026', built=datetime.now(timezone.utc).strftime('%Y-%m-%d'), runs=RUNS, roster_id=ROSTER_ID,
                   series=series, blocks=[dict(id=b, label=l) for b, l in BLOCKS], board=dict(nowcast=NOWCAST, path=path_board, blocks=board_blocks(block_table)),
                   reportsByClock=reports, realised={str(k): float(v) for k, v in actual.dropna().items()}, method=METHOD)
    (out / 'replay_data.json').write_text(json.dumps(json_safe(payload), indent=1, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    html = template.read_text(encoding='utf-8')
    if html.count('/*__DATA__*/null') != 1:
        raise ValueError('Template must carry exactly one data slot')
    html = html.replace('/*__DATA__*/null', json.dumps(json_safe(payload), ensure_ascii=False, allow_nan=False).replace('</', '<\\/'))
    (out / 'cnb_rounds_v3.html').write_text(html, encoding='utf-8')
    for sid, table in frames.items():
        table.to_csv(out / f'frame_{sid}.csv', index=False)
    (out / 'checks.json').write_text(json.dumps(json_safe(checks), indent=1), encoding='utf-8')
    for name, digest in hashes.items():
        if sha(ROOT / name) != digest:
            raise ValueError('Input changed during the build: ' + name)
    (out / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs=hashes,
        outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    print(json.dumps(json_safe(dict(reports={k: len(v) for k, v in reports.items()}, checks=checks, board=path_board)), indent=1))


if __name__ == '__main__':
    main()
