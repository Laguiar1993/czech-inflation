"""R26 evaluation: the benchmark family against the roster, the assembled sell-side path, and the promotion rule
applied to the one promoted object so far (the R24 food block).

    python -m tools.research_r26.evaluate --output output/research_r26/final

Reads the frozen R24 run and its evaluation; fits nothing on outcomes. Every benchmark is rebuilt at each of the
90 origins from block rates published by that origin's clock.
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
import r17_common as c
from models.path_inputs import compound_path
from models.benchmarks_r26 import BLOCKS, HORIZONS, MEMBERS, constant_oracle, family_paths, replace_blocks, to_log
from tools.path_diagnostics import bootstrap, gates
from tools.path_diagnostics.standard import ERAS

RUN = 'output/research_r24/final'
INPUTS = [f'{RUN}/manifest.json', f'{RUN}/native_forecasts.csv', f'{RUN}/forecasts.csv', f'{RUN}/drift_audit.csv', f'{RUN}/evaluation/cnb_pairs.csv',
          'output/research_r17/attribution/primary_support.csv', 'output/research_r14b/attribution/actual_component_targets.csv',
          'output/independent_path_frozen_inputs.csv', 'data/release_calendar_cz_cpi.csv']
CODE = ['models/benchmarks_r26.py', 'tools/research_r26/evaluate.py', 'tools/path_diagnostics/benchmarks.py', 'tools/path_diagnostics/bootstrap.py',
        'tools/path_diagnostics/gates.py', 'tools/path_diagnostics/standard.py', 'models/path_inputs.py', 'r17_common.py']
ROSTER = {'STATE_FAST_R15': 'FAST', 'STABLE_LOCAL_CORE_R14B': 'CURRENT_CORE', 'DAMPED_P95_Q001_R16': 'GENTLE_SLOPE', 'FOOD_NORM_SHIFT_R24': 'FAST_FOODNORM_R24'}
FAST = 'STATE_FAST_R15'; FOOD = 'FOOD_NORM_SHIFT_R24'
SCORE_H = (3, 6, 12)
GRID_ANNUAL_PCT = [1.75 + .25 * k for k in range(13)]
ASSEMBLED = {'SELL_SIDE_PATH': 'SA_AR', 'SELL_SIDE_TARGET_PATH': 'SA_AR_TARGET'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(name):
    return pd.read_csv(ROOT / name, float_precision='round_trip', low_memory=False)


def era_mask(origins):
    o = np.asarray(origins).astype(str)
    return {name: rule(o) for name, rule in ERAS.items()}


def rmse(e):
    e = np.asarray(e, float); return float(np.sqrt((e ** 2).mean())) if len(e) else np.nan


def cumulative(values):
    """Cumulative log change over h1..H of a 12-vector of monthly percent rates, for each H in SCORE_H."""
    logs = to_log(values); return {H: float(logs[:H].sum()) if np.isfinite(logs[:H]).all() else np.nan for H in SCORE_H}


def block_table(native, actual, family, support):
    """One row per (block, origin, H) with every roster model's and member's cumulative log change and the truth."""
    keys = set(zip(support.origin, support.h)); rows = []
    for block in BLOCKS:
        for origin, g in native[native.model.eq(FAST)].groupby('origin'):
            t = pd.Period(origin, 'M'); months = pd.period_range(t + 1, t + 12, freq='M')
            truth = cumulative(actual[block].reindex(months).to_numpy(float))
            values = {}
            for model, label in ROSTER.items():
                own = native[native.model.eq(model) & native.origin.eq(origin)].set_index('h').reindex(range(1, 13))
                values[label] = cumulative(own['value_' + block].to_numpy(float))
            for member in MEMBERS:
                values[member] = cumulative([family[origin][0][member][block][h] for h in HORIZONS])
            for H in SCORE_H:
                if (origin, H) not in keys:
                    continue
                rows.append(dict(block=block, origin=origin, H=H, actual=truth[H], **{k: v[H] for k, v in values.items()}))
    return pd.DataFrame(rows)


def score_blocks(table):
    names = [*ROSTER.values(), *MEMBERS]; rows = []; oracles = {}
    for (block, H), g in table.groupby(['block', 'H']):
        z = g[np.isfinite(g[[*names, 'actual']]).all(axis=1)].sort_values('origin')
        oracle = constant_oracle(z[z.H.eq(12)].actual if H == 12 else np.nan, 12) if H == 12 else np.nan
        if H == 12:
            oracles[block] = oracle
        for sample, mask in era_mask(z.origin).items():
            s = z[mask]
            for name in names:
                e = s[name] - s.actual
                rows.append(dict(block=block, H=H, sample=sample, name=name, kind='model' if name in ROSTER.values() else 'benchmark', n=len(s),
                                 rmse=rmse(e), bias=float(e.mean()) if len(s) else np.nan))
            if H == 12 and np.isfinite(oracle):
                e = 12 * oracle - s.actual
                rows.append(dict(block=block, H=H, sample=sample, name='CONSTANT_ORACLE', kind='ceiling', n=len(s), rmse=rmse(e), bias=float(e.mean()),
                                 constant_log_per_month=oracle, constant_annual_pct=100 * np.expm1(12 * oracle / 100)))
    scores = pd.DataFrame(rows)
    ref = scores[scores.name.eq('FAST')].set_index(['block', 'H', 'sample']).rmse
    scores['ratio_to_fast'] = [r.rmse / ref.get((r.block, r.H, r.sample), np.nan) for r in scores.itertuples()]
    return scores, oracles


def verdicts(table, scores):
    """Conditions 1, 2, 4 and 5 of the rule for every roster model and block against FAST."""
    feasible = list(MEMBERS); rows = []
    best_feasible = scores[scores.name.isin(feasible)].groupby(['block', 'H', 'sample']).rmse.min()
    pivot = scores.set_index(['name', 'block', 'H', 'sample']).rmse
    for label in [v for v in ROSTER.values() if v != 'FAST']:
        for block in BLOCKS:
            g = table[table.block.eq(block)]
            z = g[np.isfinite(g[[label, 'FAST', 'actual']]).all(axis=1)]
            differs = bool((z[label] - z['FAST']).abs().gt(1e-9).any())
            cells = [(H, s) for H in SCORE_H for s in ERAS]
            c1 = all(pivot.get((label, block, H, s), np.nan) <= pivot.get(('FAST', block, H, s), np.nan) + 1e-12 for H, s in cells)
            c2_cells = [(H, s) for H in (6, 12) for s in ('full', 'origins_2024plus')]
            c2 = all(pivot.get((label, block, H, s), np.nan) <= best_feasible.get((block, H, s), np.nan) + 1e-12 for H, s in c2_cells)
            phase = {}
            for H, s in c2_cells:
                w = z[z.H.eq(H)]; w = w[era_mask(w.origin)[s]]
                phase[f'{s}_h{H}'] = gates.needed_vs_applied(w.actual - w['FAST'], w[label] - w['FAST'])['correlation']
            c4 = all(np.isfinite(v) and v >= 0 for v in phase.values()) if differs else True
            w = z[z.H.eq(12)].sort_values('origin')
            boot = bootstrap.circular_block_bootstrap((w[label] - w.actual) ** 2 - (w['FAST'] - w.actual) ** 2, origins=w.origin)
            c5 = bool(boot['status'] == 'ok' and boot['ci_high'] < 0)
            rows.append(dict(model=label, block=block, differs_from_fast=differs, c1_baseline_every_era=c1, c2_feasible_benchmarks=c2,
                             c4_in_phase=c4, c5_interval=c5, **{'phase_' + k: v for k, v in phase.items()},
                             boot_n=boot['n'], boot_status=boot['status'], boot_ci_low=boot['ci_low'], boot_ci_high=boot['ci_high'],
                             failed=','.join(n for n, ok in [('1', c1), ('2', c2), ('4', c4), ('5', c5)] if not ok) if differs else 'not_a_candidate_for_this_block'))
    return pd.DataFrame(rows)


def specificity(native, drift, actual, support):
    """Condition 3 for the R24 food block: the estimator against the grid of fixed annual drifts, at h12 on the full support."""
    keys = set(zip(support.origin, support.h)); rows = []; parity = 0.
    mu = drift.set_index('origin')
    for origin, g in native[native.model.eq(FAST)].groupby('origin'):
        if not any((origin, H) in keys for H in SCORE_H):
            continue
        t = pd.Period(origin, 'M'); months = pd.period_range(t + 1, t + 12, freq='M')
        base = to_log(g.sort_values('h').set_index('h').reindex(range(1, 13)).value_food.to_numpy(float))
        cand = native[native.model.eq(FOOD) & native.origin.eq(origin)].sort_values('h').set_index('h').reindex(range(1, 13)).value_food.to_numpy(float)
        mu_window, mu_long = float(mu.loc[origin, 'mu_window']), float(mu.loc[origin, 'mu_long'])
        parity = max(parity, float(np.nanmax(np.abs(100 * np.expm1((base - mu_window + mu_long) / 100) - cand))))
        truth_log = to_log(actual.food.reindex(months).to_numpy(float))
        for H in SCORE_H:
            if (origin, H) not in keys:
                continue
            row = dict(origin=origin, H=H, actual=float(truth_log[:H].sum()), candidate=float((base - mu_window + mu_long)[:H].sum()), baseline=float(base[:H].sum()))
            for pct in GRID_ANNUAL_PCT:
                row[f'const_{pct:.2f}'] = float((base - mu_window + pct / 12)[:H].sum())
            rows.append(row)
    frame = pd.DataFrame(rows).sort_values(['H', 'origin']); frame = frame[np.isfinite(frame.drop(columns='origin')).all(axis=1)]
    full12 = frame[frame.H.eq(12)]
    grid = {pct: rmse(full12[f'const_{pct:.2f}'] - full12.actual) for pct in GRID_ANNUAL_PCT}
    best = min(grid, key=grid.get)
    boot = bootstrap.circular_block_bootstrap((full12.candidate - full12.actual) ** 2 - (full12[f'const_{best:.2f}'] - full12.actual) ** 2, origins=full12.origin)
    # Condition 1 for every grid constant: at or below the baseline in all twelve era-by-horizon cells.
    cells = []
    for H, g in frame.groupby('H'):
        for sample, mask in era_mask(g.origin).items():
            z = g[mask]; base_rmse = rmse(z.baseline - z.actual)
            cells.append(dict(H=H, sample=sample, n=len(z), baseline=base_rmse, candidate=rmse(z.candidate - z.actual),
                              **{f'const_{pct:.2f}': rmse(z[f'const_{pct:.2f}'] - z.actual) for pct in GRID_ANNUAL_PCT}))
    cells = pd.DataFrame(cells)
    equivalent = [pct for pct in GRID_ANNUAL_PCT if (cells[f'const_{pct:.2f}'] <= cells.baseline + 1e-12).all()]
    candidate_every_era = bool((cells.candidate <= cells.baseline + 1e-12).all())
    # Era-balanced score: mean over the twelve cells of RMSE relative to the baseline, so no single era dominates the choice.
    balanced = {pct: float((cells[f'const_{pct:.2f}'] / cells.baseline).mean()) for pct in GRID_ANNUAL_PCT}
    balanced_candidate = float((cells.candidate / cells.baseline).mean())
    chosen = min(equivalent, key=balanced.get) if equivalent else None
    chosen_full_sample = min(equivalent, key=grid.get) if equivalent else None
    result = dict(candidate_rmse=rmse(full12.candidate - full12.actual), baseline_rmse=rmse(full12.baseline - full12.actual), grid_rmse=grid,
                  best_constant_annual_pct=best, best_constant_rmse=grid[best], n=len(full12), bootstrap_vs_best_constant=boot,
                  estimator_distinguishable=bool(boot['status'] == 'ok' and boot['ci_high'] < 0), reconstruction_max_abs_gap=parity,
                  constants_below_baseline_full_h12=[pct for pct, v in grid.items() if v <= rmse(full12.baseline - full12.actual)],
                  constants_passing_condition_1_every_cell=equivalent, candidate_passes_condition_1=candidate_every_era,
                  era_balanced_score={pct: balanced[pct] for pct in GRID_ANNUAL_PCT}, era_balanced_score_candidate=balanced_candidate,
                  simplest_equivalent_annual_pct=chosen, lowest_full_sample_rmse_in_passing_set_annual_pct=chosen_full_sample, era_cells=cells.to_dict('records'))
    return result, frame


def assembled(native, forecasts, family, headline, support, pairs, actual_yy):
    """Headline RMSE of the sell-side paths and the roster on the primary support and on the matched CNB pairs from 2024."""
    history = headline.headline_mm; rows = []; parity = 0.; paths = {}
    for origin, g in native[native.model.eq(FAST)].groupby('origin'):
        t = pd.Period(origin, 'M'); own = g.sort_values('h').reset_index(drop=True)
        h0 = float(own.mm_forecast.iloc[0]); stored = forecasts[forecasts.model.eq(FAST) & forecasts.origin.eq(origin)].set_index('h').yy_exante
        same = replace_blocks(own, {b: {h: float(own.loc[h, 'value_' + b]) for h in HORIZONS} for b in BLOCKS})
        check = [compound_path(history[history.index < t], dict(zip(same.h, same.mm_forecast)), t, h, h0) for h in range(13)]
        both = np.isfinite(check) & np.isfinite(stored.reindex(range(13)).to_numpy(float))
        parity = max(parity, float(np.abs(np.asarray(check)[both] - stored.reindex(range(13)).to_numpy(float)[both]).max()) if both.any() else 0.)
        singles = {f'FAST_{b.upper()}_SA_AR': {b: family[origin][0]['SA_AR'][b]} for b in BLOCKS}
        for name, member in [*ASSEMBLED.items(), *singles.items()]:
            new = replace_blocks(own, {b: family[origin][0][member][b] for b in BLOCKS} if isinstance(member, str) else member)
            yy = [compound_path(history[history.index < t], dict(zip(new.h, new.mm_forecast)), t, h, h0) for h in range(13)]
            paths[(name, origin)] = dict(zip(range(13), yy))
            for h in range(13):
                rows.append(dict(model=name, origin=origin, h=h, target=str(t + h), yy_exante=yy[h], yy_actual=float(stored.index.size and forecasts[forecasts.model.eq(FAST) & forecasts.origin.eq(origin) & forecasts.h.eq(h)].yy_actual.iloc[0])))
    frame = pd.concat([pd.DataFrame(rows), forecasts[forecasts.model.isin(ROSTER)].assign(model=lambda d: d.model.map(ROSTER))[['model', 'origin', 'h', 'target', 'yy_exante', 'yy_actual']]], ignore_index=True)
    merged = frame.merge(support, on=['origin', 'h'], validate='many_to_one'); scores = []
    for (model, h), g in merged.groupby(['model', 'h']):
        if h not in SCORE_H:
            continue
        e = (g.yy_exante - g.yy_actual)
        for sample, mask in era_mask(g.origin).items():
            z = e[mask].dropna(); scores.append(dict(scope='primary_support', model=model, h=h, sample=sample, n=len(z), rmse=rmse(z), bias=float(z.mean()) if len(z) else np.nan))
    recent = pairs[pairs.clock.eq('report') & pairs.report_date.ge('2024-01-01')]
    for name in [*ASSEMBLED, *[f'FAST_{b.upper()}_SA_AR' for b in BLOCKS]]:
        errors = []; q4 = []
        for r in recent[recent.model.eq('cnb')].itertuples():
            o = pd.Period(r.origin, 'M'); path = {o + h: v for h, v in paths[(name, r.origin)].items() if np.isfinite(v)}
            q = pd.Period(r.quarter, 'Q'); months = pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M')
            values = np.array([actual_yy.get(m, np.nan) if m < o else path.get(m, np.nan) for m in months], float)
            v = float(values.mean()) if np.isfinite(values).all() else np.nan
            errors.append(v - r.realised)
            if r.quarters_ahead == 4:
                q4.append(v - r.realised)
        scores.append(dict(scope='cnb_pairs_2024plus_report_clock', model=name, h='all', sample='reports_2024plus', n=len(errors), rmse=rmse(errors), bias=float(np.mean(errors))))
        scores.append(dict(scope='cnb_pairs_2024plus_report_clock', model=name, h='4Q', sample='reports_2024plus', n=len(q4), rmse=rmse(q4), bias=float(np.mean(q4))))
    for model, label in [*ROSTER.items(), ('cnb', 'CNB')]:
        z = recent[recent.model.eq(model)]
        scores.append(dict(scope='cnb_pairs_2024plus_report_clock', model=label, h='all', sample='reports_2024plus', n=len(z), rmse=rmse(z.error), bias=float(z.error.mean())))
        z4 = z[z.quarters_ahead.eq(4)]
        scores.append(dict(scope='cnb_pairs_2024plus_report_clock', model=label, h='4Q', sample='reports_2024plus', n=len(z4), rmse=rmse(z4.error), bias=float(z4.error.mean())))
    return pd.DataFrame(scores), frame, parity


def condition6(forecasts, support, pairs):
    """Assembled-path condition for the R24 path against FAST: primary-support headline cells at h6/h12 and the CNB pairs from 2024."""
    merged = forecasts[forecasts.model.isin([FAST, FOOD])].merge(support, on=['origin', 'h'], validate='many_to_one'); cells = {}
    for h in (6, 12):
        g = merged[merged.h.eq(h)].pivot(index='origin', columns='model', values='yy_exante')
        truth = merged[merged.h.eq(h)].drop_duplicates('origin').set_index('origin').yy_actual
        for sample, mask in era_mask(g.index).items():
            z = g[mask].dropna(); t = truth.reindex(z.index)
            cells[f'{sample}_h{h}'] = dict(candidate=rmse(z[FOOD] - t), baseline=rmse(z[FAST] - t))
    recent = pairs[pairs.clock.eq('report') & pairs.report_date.ge('2024-01-01')]
    cells['cnb_pairs_2024plus'] = dict(candidate=rmse(recent[recent.model.eq(FOOD)].error), baseline=rmse(recent[recent.model.eq(FAST)].error))
    return dict(cells=cells, holds=bool(all(v['candidate'] <= v['baseline'] + 1e-12 for v in cells.values())))


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); args = ap.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    hashes = {name: sha(ROOT / name) for name in [*INPUTS, *CODE]}
    native = read(f'{RUN}/native_forecasts.csv'); forecasts = read(f'{RUN}/forecasts.csv'); drift = read(f'{RUN}/drift_audit.csv')
    pairs = read(f'{RUN}/evaluation/cnb_pairs.csv'); support = read('output/research_r17/attribution/primary_support.csv')
    actual = c.monthly('output/research_r14b/attribution/actual_component_targets.csv'); published = c.publication_dates(actual.index)
    headline = c.monthly('output/independent_path_frozen_inputs.csv'); actual_yy = 100 * np.expm1(np.log1p(headline.headline_mm / 100).rolling(12).sum())
    clocks = native[native.h.eq(0) & native.model.eq(FAST)].drop_duplicates('origin').set_index('origin').as_of_utc
    if len(clocks) != 90:
        raise ValueError('Original 90 origins required')
    family = {o: family_paths(actual, published, o, clocks[o]) for o in clocks.index}
    path_rows = []; diag_rows = []
    for o, (members, diagnostics) in family.items():
        for member in MEMBERS:
            for block in BLOCKS:
                for h in HORIZONS:
                    path_rows.append(dict(member=member, origin=o, block=block, h=h, value=members[member][block][h]))
        for block, d in diagnostics.items():
            diag_rows.append(dict(origin=o, block=block, **d))
    pd.DataFrame(path_rows).to_csv(out / 'benchmark_paths.csv', index=False); pd.DataFrame(diag_rows).to_csv(out / 'sa_ar_diagnostics.csv', index=False)
    table = block_table(native, actual, family, support); table.to_csv(out / 'block_cumulative_table.csv', index=False)
    scores, oracles = score_blocks(table); scores.to_csv(out / 'block_family_scores.csv', index=False)
    verdict = verdicts(table, scores); verdict.to_csv(out / 'block_verdicts.csv', index=False)
    spec3, grid_frame = specificity(native, drift, actual, support); grid_frame.to_csv(out / 'food_constant_grid.csv', index=False)
    assembled_scores, assembled_frame, parity = assembled(native, forecasts, family, headline, support, pairs, actual_yy)
    assembled_scores.to_csv(out / 'assembled_scores.csv', index=False); assembled_frame[~assembled_frame.model.isin(ROSTER.values())].to_csv(out / 'sell_side_paths.csv', index=False)
    cond6 = condition6(forecasts, support, pairs)
    checks = dict(origins=int(len(clocks)), sa_ar_estimated=int(sum(d['status'] == 'estimated' for _, dg in family.values() for d in dg.values())),
                  fast_reassembly_max_abs_gap=parity, r24_food_reconstruction_max_abs_gap=spec3['reconstruction_max_abs_gap'], constant_oracles_log_per_month=oracles)
    if max(parity, spec3['reconstruction_max_abs_gap']) > 1e-9:
        raise ValueError('Reconstruction differs from the run: ' + json.dumps(checks))
    for name, digest in hashes.items():
        if sha(ROOT / name) != digest:
            raise ValueError('Input changed during evaluation: ' + name)
    c.dump(out / 'checks.json', checks)
    c.dump(out / 'rule_r24_food.json', dict(condition_3_specificity=spec3, condition_6_assembled=cond6))
    c.dump(out / 'manifest.json', dict(created_at_utc=datetime.now(timezone.utc).isoformat(), run=RUN, inputs=hashes,
                                       outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}))
    print(json.dumps(dict(checks=checks, specificity={k: v for k, v in spec3.items() if k not in ('grid_rmse', 'era_cells', 'era_balanced_score')}, condition6=cond6), indent=1, default=str))


if __name__ == '__main__':
    main()
