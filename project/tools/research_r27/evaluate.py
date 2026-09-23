"""R27 scoring: gates first, then the food block against the R24 baseline and the R26 benchmark family, then the six conditions.

    python -m tools.research_r27.evaluate --root output/research_r27/final
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from models.benchmarks_r26 import MEMBERS, family_paths, to_log
from models.food_ecm_r27 import MODELS, FIXED_ALPHAS
from tools.path_diagnostics import bootstrap, gates, standard

BASELINE = 'FOOD_NORM_SHIFT_R24'; FAST = 'STATE_FAST_R15'
VARIANTS = {f'FOOD_ECM_A{abs(a):.2f}_R27'.replace('.', ''): a for a in FIXED_ALPHAS}
LABELS = {'FOOD_ECM_R27': 'Food: error correction, producer and farm prices', 'FOOD_ECM_PPI_R27': 'Food: error correction, producer prices only',
          **{k: f'Food: error correction, fixed speed {v:.2f}' for k, v in VARIANTS.items()}}
METHOD = [
    'R27: error-correction candidates for the food block on the frozen R24 research path (FAST core with the long-history food drift), original 90 origins and 969 primary keys. Only the food block of h1-6 changes; h0, h7-12, every other block, the wedge and the weights are untouched. Historical research, not a live record.',
    'The gap is the residual of retail food’s log level on a trend and the producer (and farm) price levels over the food system’s window (at most 96 months), centred by calendar month; the speed is the least-squares response of the centred food rate to the previous month’s gap, clipped to [-0.25, 0]. The correction decays from the last month at which all three levels are published. Four fixed speeds are run for the specificity condition of the R26 rule.',
    'Every parameter uses observations published by the origin’s clock; no forecast error or outcome after the origin enters. Judged by the R26 promotion rule against the R24 path as baseline, block first.',
    'Lead tables flag abs(model-CNB)>=0.30pp (0.50 sensitivity) against the immediately next CNB report for the same still-future quarter, with base-rate rows passed through the same rules.',
    'Defaults show the R24 path with the producer-and-farm candidate; no promotion is implied by the display.']
SCORE_H = (3, 6, 12)


def rmse(e):
    e = np.asarray(e, float); return float(np.sqrt((e ** 2).mean())) if len(e) else np.nan


def era_mask(origins):
    o = np.asarray(origins).astype(str); return {name: rule(o) for name, rule in standard.ERAS.items()}


def cumulative(values):
    logs = to_log(values); return {H: float(logs[:H].sum()) if np.isfinite(logs[:H]).all() else np.nan for H in SCORE_H}


def food_table(native, actual, family, support, names):
    keys = set(zip(support.origin, support.h)); rows = []
    for origin, g in native[native.model.eq(BASELINE)].groupby('origin'):
        t = pd.Period(origin, 'M'); months = pd.period_range(t + 1, t + 12, freq='M')
        truth = cumulative(actual.food.reindex(months).to_numpy(float)); values = {}
        for name in names:
            own = native[native.model.eq(name) & native.origin.eq(origin)].set_index('h').reindex(range(1, 13))
            values[name] = cumulative(own.value_food.to_numpy(float))
        for member in MEMBERS:
            values[member] = cumulative([family[origin][0][member]['food'][h] for h in range(1, 13)])
        for H in SCORE_H:
            if (origin, H) in keys:
                rows.append(dict(origin=origin, H=H, actual=truth[H], **{k: v[H] for k, v in values.items()}))
    return pd.DataFrame(rows)


def scores(table, names):
    rows = []
    for H, g in table.groupby('H'):
        z = g[np.isfinite(g[[*names, *MEMBERS, 'actual']]).all(axis=1)]
        for sample, mask in era_mask(z.origin).items():
            s = z[mask]
            for name in [*names, *MEMBERS]:
                e = s[name] - s.actual
                rows.append(dict(H=H, sample=sample, name=name, n=len(s), rmse=rmse(e), bias=float(e.mean()) if len(s) else np.nan))
    frame = pd.DataFrame(rows); ref = frame[frame.name.eq(BASELINE)].set_index(['H', 'sample']).rmse
    frame['ratio_to_baseline'] = [r.rmse / ref.get((r.H, r.sample), np.nan) for r in frame.itertuples()]
    return frame


def phase_gate(table, candidate):
    out = {}
    for H in (3, 6):
        for sample in ('full', 'origins_2024plus'):
            w = table[table.H.eq(H)]; w = w[era_mask(w.origin)[sample]].dropna(subset=[candidate, BASELINE, 'actual'])
            g = gates.needed_vs_applied(w.actual - w[BASELINE], w[candidate] - w[BASELINE])
            out[f'{sample}_h{H}'] = dict(correlation=g['correlation'], sign_agreement=g['sign_agreement'], n=g['n'], n_active=g['n_active'])
    return out


def interval(table, candidate, reference, H):
    w = table[table.H.eq(H)].dropna(subset=[candidate, reference, 'actual']).sort_values('origin')
    return bootstrap.circular_block_bootstrap((w[candidate] - w.actual) ** 2 - (w[reference] - w.actual) ** 2, origins=w.origin)


def assembled_condition(forecasts, support, pairs, candidate):
    merged = forecasts[forecasts.model.isin([BASELINE, candidate])].merge(support, on=['origin', 'h'], validate='many_to_one'); cells = {}
    for h in (6, 12):
        g = merged[merged.h.eq(h)].pivot(index='origin', columns='model', values='yy_exante'); truth = merged[merged.h.eq(h)].drop_duplicates('origin').set_index('origin').yy_actual
        for sample, mask in era_mask(g.index).items():
            z = g[mask].dropna(); t = truth.reindex(z.index); cells[f'{sample}_h{h}'] = dict(candidate=rmse(z[candidate] - t), baseline=rmse(z[BASELINE] - t))
    recent = pairs[pairs.clock.eq('report') & pairs.report_date.ge('2024-01-01')]
    cells['cnb_pairs_2024plus'] = dict(candidate=rmse(recent[recent.model.eq(candidate)].error), baseline=rmse(recent[recent.model.eq(BASELINE)].error))
    return dict(cells=cells, holds=bool(all(v['candidate'] <= v['baseline'] + 1e-12 for v in cells.values())))


def verdict(table, score, forecasts, support, pairs, candidate):
    pivot = score.set_index(['name', 'H', 'sample']).rmse; feasible = score[score.name.isin(MEMBERS)].groupby(['H', 'sample']).rmse.min()
    cells = [(H, s) for H in SCORE_H for s in standard.ERAS]
    c1 = all(pivot.get((candidate, H, s), np.nan) <= pivot.get((BASELINE, H, s), np.nan) + 1e-12 for H, s in cells)
    c2 = all(pivot.get((candidate, H, s), np.nan) <= feasible.get((H, s), np.nan) + 1e-12 for H in (6, 12) for s in ('full', 'origins_2024plus'))
    spec = None
    if candidate == 'FOOD_ECM_R27':
        grid = {name: pivot.get((name, 6, 'full'), np.nan) for name in VARIANTS}; best = min(grid, key=grid.get)
        boot = interval(table, candidate, best, 6)
        passing = [name for name in VARIANTS if all(pivot.get((name, H, s), np.nan) <= pivot.get((BASELINE, H, s), np.nan) + 1e-12 for H, s in cells)]
        balanced = {name: float(np.mean([pivot.get((name, H, s), np.nan) / pivot.get((BASELINE, H, s), np.nan) for H, s in cells])) for name in VARIANTS}
        spec = dict(grid_rmse_h6_full=grid, best_fixed=best, best_fixed_alpha=VARIANTS[best], bootstrap_vs_best_fixed_h6=boot,
                    estimator_distinguishable=bool(boot['status'] == 'ok' and boot['ci_high'] < 0), fixed_passing_condition_1=passing,
                    era_balanced_score={k: v for k, v in balanced.items()}, candidate_era_balanced_score=float(np.mean([pivot.get((candidate, H, s), np.nan) / pivot.get((BASELINE, H, s), np.nan) for H, s in cells])),
                    simplest_equivalent=min(passing, key=balanced.get) if passing else None)
    phase = phase_gate(table, candidate)
    c4 = all(np.isfinite(v['correlation']) and v['correlation'] >= 0 and np.isfinite(v['sign_agreement']) and v['sign_agreement'] >= .5 for v in phase.values())
    b6 = interval(table, candidate, BASELINE, 6); b12 = interval(table, candidate, BASELINE, 12)
    c5 = all(b['status'] == 'ok' and b['ci_high'] < 0 for b in (b6, b12))
    c6 = assembled_condition(forecasts, support, pairs, candidate)
    c3 = spec['estimator_distinguishable'] if spec else None
    failed = [n for n, ok in [('1', c1), ('2', c2), ('3', c3), ('4', c4), ('5', c5), ('6', c6['holds'])] if ok is False]
    return dict(candidate=candidate, c1_baseline_every_era=c1, c2_feasible_benchmarks=c2, c3_specificity=c3, c4_in_phase=c4, c5_interval=c5, c6_assembled=c6['holds'],
                failed=failed, promotable=not failed, phase=phase, interval_h6=b6, interval_h12=b12, assembled=c6, specificity=spec)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--root', type=Path, required=True); args = ap.parse_args()
    root = args.root if args.root.is_absolute() else ROOT / args.root
    out, _ = standard.standard_evaluation(root, 'R27', LABELS, METHOD, defaults={BASELINE, 'FOOD_ECM_R27'})
    manifest = json.loads((root / 'manifest.json').read_text()); names = [*manifest['controls'], *manifest['models']]
    native = pd.read_csv(root / 'native_forecasts.csv', low_memory=False); forecasts = pd.read_csv(root / 'forecasts.csv')
    actual = c.monthly(standard.COMPONENTS); published = c.publication_dates(actual.index)
    support = c.read('output/research_r17/attribution/primary_support.csv'); pairs = pd.read_csv(out / 'cnb_pairs.csv')
    clocks = native[native.h.eq(0) & native.model.eq(BASELINE)].drop_duplicates('origin').set_index('origin').as_of_utc
    family = {o: family_paths(actual, published, o, clocks[o], blocks=('food',)) for o in clocks.index}
    audit = pd.read_csv(root / 'ecm_audit.csv'); gate_rows = []
    for model, g in audit.groupby('model'):
        gate_rows.append(dict(model=model, n=len(g), wrong_sign_share=float(g.speed_wrong_sign.mean()), alpha_median=float(g.alpha.median()), alpha_min=float(g.alpha.min()),
                              alpha_max=float(g.alpha.max()), alpha_raw_median=float(g.speed_alpha_raw.median()), gap_seasonal_share_raw_median=float(g.gap_seasonal_share_raw.median()),
                              gap_seasonal_share_centred_median=float(g.gap_seasonal_share_centred.median()), gap_sd_median=float(g.gap_sd.median()),
                              gap_last_median_abs=float(g.gap_last.abs().median()), cumulative_correction_h6_median_abs=float(g.cumulative_correction_h6.abs().median()),
                              trend_per_month_median=float(g.trend_per_month.median()), r2_median=float(g.r2.median())))
    pd.DataFrame(gate_rows).to_csv(out / 'gates.csv', index=False)
    table = food_table(native, actual, family, support, names); table.to_csv(out / 'food_cumulative_table.csv', index=False)
    score = scores(table, names); score.to_csv(out / 'food_family_scores.csv', index=False)
    verdicts = {m: verdict(table, score, forecasts, support, pairs, m) for m in MODELS}
    c.dump(out / 'rule_verdicts.json', verdicts)
    standard.close_manifest(out, extra_code=[Path(__file__), ROOT / 'models/benchmarks_r26.py', ROOT / 'models/food_ecm_r27.py'])
    print(json.dumps({m: dict(failed=v['failed'], promotable=v['promotable']) for m, v in verdicts.items()}, indent=1))
    print('Completed R27 evaluation', out, flush=True)


if __name__ == '__main__':
    main()
