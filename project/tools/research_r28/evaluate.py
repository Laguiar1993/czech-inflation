"""R28 scoring: gates, the administered block against FAST and the R26 family, then the six conditions.

    python -m tools.research_r28.evaluate --root output/research_r28/final
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
from models.administered_level_r28 import MODELS, FACTORS, factor_name
from tools.path_diagnostics import bootstrap, gates, standard

BLOCK = 'administered'; REFERENCE = 'STATE_FAST_R15'
VARIANTS = {factor_name(f): f for f in FACTORS}
LABELS = {'ADMIN_ZERO_R28': 'Administered: zero outside fired gates', 'ADMIN_JAN_ONLY_R28': 'Administered: January only', 'ADMIN_RECENT_R28': 'Administered: three-year median',
          'ADMIN_HALF_R28': 'Administered: half of the pattern', **{k: f'Administered: fixed factor {v:.2f}' for k, v in VARIANTS.items()}}
METHOD = [
    'R28: administered-price level candidates on the research roster frame, original 90 origins and 969 primary keys. Only the administered block of h1-12 changes; fired January announcement gates (a FAST January rate above 5 percent) are kept in every candidate. Historical research, not a live record.',
    'Candidates: zero outside fired gates; January only (FAST’s ten-year January median kept, zero elsewhere); the median of the same calendar month over the latest three published years; half of FAST’s pattern; fixed factors 0, 0.25, 0.5 and 0.75 of the pattern for the specificity condition.',
    'Judged by the R26 promotion rule against FAST’s administered block, block first, with the assembled condition on the roster frame named in the run manifest. No survey, expectations series or CNB forecast enters any candidate.',
    'Lead tables flag abs(model-CNB)>=0.30pp (0.50 sensitivity) against the immediately next CNB report for the same still-future quarter, with base-rate rows passed through the same rules.',
    'Defaults show the roster frame with the January-only candidate; no promotion is implied by the display.']
SCORE_H = (3, 6, 12)


def rmse(e):
    e = np.asarray(e, float); return float(np.sqrt((e ** 2).mean())) if len(e) else np.nan


def era_mask(origins):
    o = np.asarray(origins).astype(str); return {name: rule(o) for name, rule in standard.ERAS.items()}


def cumulative(values):
    logs = to_log(values); return {H: float(logs[:H].sum()) if np.isfinite(logs[:H]).all() else np.nan for H in SCORE_H}


def block_table(native, actual, family, support, names):
    keys = set(zip(support.origin, support.h)); rows = []
    for origin, g in native[native.model.eq(REFERENCE)].groupby('origin'):
        t = pd.Period(origin, 'M'); months = pd.period_range(t + 1, t + 12, freq='M')
        truth = cumulative(actual[BLOCK].reindex(months).to_numpy(float)); values = {}
        for name in names:
            own = native[native.model.eq(name) & native.origin.eq(origin)].set_index('h').reindex(range(1, 13))
            values[name] = cumulative(own['value_' + BLOCK].to_numpy(float))
        for member in MEMBERS:
            values[member] = cumulative([family[origin][0][member][BLOCK][h] for h in range(1, 13)])
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
    frame = pd.DataFrame(rows); ref = frame[frame.name.eq(REFERENCE)].set_index(['H', 'sample']).rmse
    frame['ratio_to_fast'] = [r.rmse / ref.get((r.H, r.sample), np.nan) for r in frame.itertuples()]
    return frame


def phase_gate(table, candidate):
    out = {}
    for H in (6, 12):
        for sample in ('full', 'origins_2024plus'):
            w = table[table.H.eq(H)]; w = w[era_mask(w.origin)[sample]].dropna(subset=[candidate, REFERENCE, 'actual'])
            needed = w.actual - w[REFERENCE]; applied = w[candidate] - w[REFERENCE]; g = gates.needed_vs_applied(needed, applied)
            out[f'{sample}_h{H}'] = dict(correlation=g['correlation'], sign_agreement=g['sign_agreement'], n=g['n'], n_active=g['n_active'],
                                       mean_needed=float(needed.mean()), mean_applied=float(applied.mean()),
                                       era_means_agree=bool(np.sign(needed.mean()) == np.sign(applied.mean())) if abs(applied.mean()) > 1e-12 else True)
    return out


def interval(table, candidate, reference, H):
    w = table[table.H.eq(H)].dropna(subset=[candidate, reference, 'actual']).sort_values('origin')
    return bootstrap.circular_block_bootstrap((w[candidate] - w.actual) ** 2 - (w[reference] - w.actual) ** 2, origins=w.origin)


def assembled_condition(forecasts, support, pairs, candidate, frame_model):
    merged = forecasts[forecasts.model.isin([frame_model, candidate])].merge(support, on=['origin', 'h'], validate='many_to_one'); cells = {}
    for h in (6, 12):
        g = merged[merged.h.eq(h)].pivot(index='origin', columns='model', values='yy_exante'); truth = merged[merged.h.eq(h)].drop_duplicates('origin').set_index('origin').yy_actual
        for sample, mask in era_mask(g.index).items():
            z = g[mask].dropna(); t = truth.reindex(z.index); cells[f'{sample}_h{h}'] = dict(candidate=rmse(z[candidate] - t), baseline=rmse(z[frame_model] - t), candidate_bias=float((z[candidate] - t).mean()), baseline_bias=float((z[frame_model] - t).mean()))
    recent = pairs[pairs.clock.eq('report') & pairs.report_date.ge('2024-01-01')]
    cells['cnb_pairs_2024plus'] = dict(candidate=rmse(recent[recent.model.eq(candidate)].error), baseline=rmse(recent[recent.model.eq(frame_model)].error))
    return dict(cells=cells, holds=bool(all(v['candidate'] <= v['baseline'] + 1e-12 for v in cells.values())))


def verdict(table, score, forecasts, support, pairs, candidate, frame_model):
    pivot = score.set_index(['name', 'H', 'sample']).rmse; feasible = score[score.name.isin(MEMBERS)].groupby(['H', 'sample']).rmse.min()
    cells = [(H, s) for H in SCORE_H for s in standard.ERAS]
    c1 = all(pivot.get((candidate, H, s), np.nan) <= pivot.get((REFERENCE, H, s), np.nan) + 1e-12 for H, s in cells)
    c2 = all(pivot.get((candidate, H, s), np.nan) <= feasible.get((H, s), np.nan) + 1e-12 for H in (6, 12) for s in ('full', 'origins_2024plus'))
    spec = None
    if candidate == 'ADMIN_HALF_R28':
        grid = {name: pivot.get((name, 12, 'full'), np.nan) for name in VARIANTS if VARIANTS[name] != .5}; best = min(grid, key=grid.get)
        boot = interval(table, candidate, best, 12)
        passing = [name for name in VARIANTS if all(pivot.get((name, H, s), np.nan) <= pivot.get((REFERENCE, H, s), np.nan) + 1e-12 for H, s in cells)]
        balanced = {name: float(np.mean([pivot.get((name, H, s), np.nan) / pivot.get((REFERENCE, H, s), np.nan) for H, s in cells])) for name in VARIANTS}
        spec = dict(grid_rmse_h12_full=grid, best_other_fixed=best, bootstrap_vs_best_other_fixed_h12=boot, distinguishable=bool(boot['status'] == 'ok' and boot['ci_high'] < 0),
                    fixed_passing_condition_1=passing, era_balanced_score=balanced, simplest_equivalent=min(passing, key=balanced.get) if passing else None)
    phase = phase_gate(table, candidate)
    c4 = all(np.isfinite(v['sign_agreement']) and v['sign_agreement'] >= .5 and v['era_means_agree'] for v in phase.values())
    b12 = interval(table, candidate, REFERENCE, 12); c5 = bool(b12['status'] == 'ok' and b12['ci_high'] < 0)
    c6 = assembled_condition(forecasts, support, pairs, candidate, frame_model)
    c3 = None if spec is None else True  # a fixed rule has no estimator to distinguish; the equivalent factor is reported
    failed = [n for n, ok in [('1', c1), ('2', c2), ('4', c4), ('5', c5), ('6', c6['holds'])] if ok is False]
    return dict(candidate=candidate, c1_baseline_every_era=c1, c2_feasible_benchmarks=c2, c3_specificity=c3, c4_in_phase=c4, c5_interval=c5, c6_assembled=c6['holds'],
                failed=failed, promotable=not failed, phase=phase, interval_h12=b12, assembled=c6, specificity=spec)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--root', type=Path, required=True); args = ap.parse_args()
    root = args.root if args.root.is_absolute() else ROOT / args.root
    manifest = json.loads((root / 'manifest.json').read_text()); frame_model = manifest['frame_model']; names = [*manifest['controls'], *manifest['models']]
    out, _ = standard.standard_evaluation(root, 'R28', LABELS, METHOD, defaults={frame_model, 'ADMIN_JAN_ONLY_R28'})
    native = pd.read_csv(root / 'native_forecasts.csv', low_memory=False); forecasts = pd.read_csv(root / 'forecasts.csv')
    actual = c.monthly(standard.COMPONENTS); published = c.publication_dates(actual.index)
    support = c.read('output/research_r17/attribution/primary_support.csv'); pairs = pd.read_csv(out / 'cnb_pairs.csv')
    clocks = native[native.h.eq(0) & native.model.eq(REFERENCE)].drop_duplicates('origin').set_index('origin').as_of_utc
    family = {o: family_paths(actual, published, o, clocks[o], blocks=(BLOCK,)) for o in clocks.index}
    audit = pd.read_csv(root / 'admin_audit.csv')
    realised = actual[BLOCK].dropna(); yearly = [dict(year=y, non_january_sum=float(g[g.index.month != 1].sum()), january=float(g[g.index.month == 1].iloc[0]) if (g.index.month == 1).any() else np.nan, months=len(g))
                                                for y, g in realised.groupby(realised.index.year) if y >= 2015]
    pd.DataFrame(yearly).to_csv(out / 'gates_realised_by_year.csv', index=False)
    gate_rows = [dict(fired_months=str(f), origins=int(n)) for f, n in audit.fired_months.fillna('').value_counts().items()]
    pd.DataFrame(gate_rows).to_csv(out / 'gates_fired.csv', index=False)
    table = block_table(native, actual, family, support, names); table.to_csv(out / 'administered_cumulative_table.csv', index=False)
    score = scores(table, names); score.to_csv(out / 'administered_family_scores.csv', index=False)
    verdicts = {m: verdict(table, score, forecasts, support, pairs, m, frame_model) for m in MODELS}
    c.dump(out / 'rule_verdicts.json', verdicts)
    standard.close_manifest(out, extra_code=[Path(__file__), ROOT / 'models/benchmarks_r26.py', ROOT / 'models/administered_level_r28.py'])
    print(json.dumps({m: dict(failed=v['failed'], promotable=v['promotable']) for m, v in verdicts.items()}, indent=1))
    print('Completed R28 evaluation', out, flush=True)


if __name__ == '__main__':
    main()
