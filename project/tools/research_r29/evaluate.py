"""R29 scoring: the panel gate first, then the core block against FAST and the R26 family, then the six conditions.

    python -m tools.research_r29.evaluate --root output/research_r29/final
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
from models.core_phase_r29 import MODELS, FIXED_FADING, fixed_name
from tools.path_diagnostics import bootstrap, gates, standard

BLOCK = 'core'; REFERENCE = 'STATE_FAST_R15'
FIXED = {fixed_name(f): f for f in FIXED_FADING}
LABELS = {'CORE_PHASE_TARGET_R29': 'Core: phase-conditioned persistence, 2% norm', 'CORE_PHASE_OWN_R29': 'Core: phase-conditioned persistence, own norm',
          'CORE_SINGLE_TARGET_R29': 'Core: single panel weight, 2% norm (control)', **{k: f'Core: fixed weights 1.0 / {v:.1f}, 2% norm' for k, v in FIXED.items()}}
METHOD = [
    'R29: core persistence conditioned on the phase of upstream producer-price momentum, on the research roster frame, original 90 origins and 969 primary keys. Only the core block of h1-12 changes. Historical research, not a live record.',
    'The phase at an origin is read from the last published producer-price month: six-month momentum above its value six months earlier is building, otherwise fading. Persistence weights per band and phase are pooled slopes on the frozen R25 EU-panel rows (26 member states, no Czechia) whose labels are published by the origin; only these weights come from the panel.',
    'The Czech core path becomes norm + weight x (FAST - norm) band by band, with a fixed 2%-a-year norm or the own-history norm, converted back with the origin’s own seasonal pattern as in R25. Fixed weight pairs (1.0 building; 0.4, 0.6, 0.8 fading) are run for the specificity condition.',
    'Judged by the R26 promotion rule against FAST’s core block, block first. No survey, expectations series or CNB forecast enters any candidate.',
    'Lead tables flag abs(model-CNB)>=0.30pp (0.50 sensitivity) against the immediately next CNB report for the same still-future quarter, with base-rate rows passed through the same rules.',
    'Defaults show the roster frame with the phase-conditioned 2%-norm candidate; no promotion is implied by the display.']
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
            out[f'{sample}_h{H}'] = dict(correlation=g['correlation'], sign_agreement=g['sign_agreement'], n=g['n'], n_active=g['n_active'], mean_needed=float(needed.mean()),
                                       mean_applied=float(applied.mean()), era_means_agree=bool(np.sign(needed.mean()) == np.sign(applied.mean())) if abs(applied.mean()) > 1e-12 else True)
    return out


def interval(table, candidate, reference, H):
    w = table[table.H.eq(H)].dropna(subset=[candidate, reference, 'actual']).sort_values('origin')
    return bootstrap.circular_block_bootstrap((w[candidate] - w.actual) ** 2 - (w[reference] - w.actual) ** 2, origins=w.origin)


def assembled_condition(forecasts, support, pairs, candidate, frame_model):
    merged = forecasts[forecasts.model.isin([frame_model, candidate])].merge(support, on=['origin', 'h'], validate='many_to_one'); cells = {}
    for h in (6, 12):
        g = merged[merged.h.eq(h)].pivot(index='origin', columns='model', values='yy_exante'); truth = merged[merged.h.eq(h)].drop_duplicates('origin').set_index('origin').yy_actual
        for sample, mask in era_mask(g.index).items():
            z = g[mask].dropna(); t = truth.reindex(z.index)
            cells[f'{sample}_h{h}'] = dict(candidate=rmse(z[candidate] - t), baseline=rmse(z[frame_model] - t), candidate_bias=float((z[candidate] - t).mean()), baseline_bias=float((z[frame_model] - t).mean()))
    recent = pairs[pairs.clock.eq('report') & pairs.report_date.ge('2024-01-01')]
    cells['cnb_pairs_2024plus'] = dict(candidate=rmse(recent[recent.model.eq(candidate)].error), baseline=rmse(recent[recent.model.eq(frame_model)].error))
    return dict(cells=cells, holds=bool(all(v['candidate'] <= v['baseline'] + 1e-12 for v in cells.values())))


def verdict(table, score, forecasts, support, pairs, candidate, frame_model):
    pivot = score.set_index(['name', 'H', 'sample']).rmse; feasible = score[score.name.isin(MEMBERS)].groupby(['H', 'sample']).rmse.min()
    cells = [(H, s) for H in SCORE_H for s in standard.ERAS]
    c1 = all(pivot.get((candidate, H, s), np.nan) <= pivot.get((REFERENCE, H, s), np.nan) + 1e-12 for H, s in cells)
    c2 = all(pivot.get((candidate, H, s), np.nan) <= feasible.get((H, s), np.nan) + 1e-12 for H in (6, 12) for s in ('full', 'origins_2024plus'))
    spec = None
    if candidate == 'CORE_PHASE_TARGET_R29':
        grid = {name: pivot.get((name, 12, 'full'), np.nan) for name in FIXED}; best = min(grid, key=grid.get); boot = interval(table, candidate, best, 12)
        passing = [name for name in FIXED if all(pivot.get((name, H, s), np.nan) <= pivot.get((REFERENCE, H, s), np.nan) + 1e-12 for H, s in cells)]
        balanced = {name: float(np.mean([pivot.get((name, H, s), np.nan) / pivot.get((REFERENCE, H, s), np.nan) for H, s in cells])) for name in FIXED}
        spec = dict(grid_rmse_h12_full=grid, best_fixed=best, best_fixed_fading=FIXED[best], bootstrap_vs_best_fixed_h12=boot, estimator_distinguishable=bool(boot['status'] == 'ok' and boot['ci_high'] < 0),
                    fixed_passing_condition_1=passing, era_balanced_score=balanced,
                    candidate_era_balanced_score=float(np.mean([pivot.get((candidate, H, s), np.nan) / pivot.get((REFERENCE, H, s), np.nan) for H, s in cells])),
                    simplest_equivalent=min(passing, key=balanced.get) if passing else None)
    phase = phase_gate(table, candidate)
    c4 = all(np.isfinite(v['sign_agreement']) and v['sign_agreement'] >= .5 and v['era_means_agree'] for v in phase.values())
    b6 = interval(table, candidate, REFERENCE, 6); b12 = interval(table, candidate, REFERENCE, 12)
    c5 = all(b['status'] == 'ok' and b['ci_high'] < 0 for b in (b6, b12))
    c6 = assembled_condition(forecasts, support, pairs, candidate, frame_model)
    c3 = spec['estimator_distinguishable'] if spec else None
    failed = [n for n, ok in [('1', c1), ('2', c2), ('3', c3), ('4', c4), ('5', c5), ('6', c6['holds'])] if ok is False]
    return dict(candidate=candidate, c1_baseline_every_era=c1, c2_feasible_benchmarks=c2, c3_specificity=c3, c4_in_phase=c4, c5_interval=c5, c6_assembled=c6['holds'],
                failed=failed, promotable=not failed, phase=phase, interval_h6=b6, interval_h12=b12, assembled=c6, specificity=spec)


def panel_gate(lambda_audit):
    """The declared gate: lambda(building) above lambda(fading) in every band at the six named origins."""
    named = ['2019-02', '2021-02', '2022-02', '2023-02', '2024-02', '2026-02']; rows = lambda_audit[lambda_audit.origin.isin(named)].copy()
    rows['separation'] = rows.lambda_building - rows.lambda_fading
    return dict(table=rows[['origin', 'band', 'lambda_building', 'n_building', 'lambda_fading', 'n_fading', 'lambda_single', 'separation']].to_dict('records'),
                passes=bool((rows.separation > 0).all()), min_separation=float(rows.separation.min()), mean_separation_h1_6=float(rows[rows.band.le(2)].separation.mean()))


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--root', type=Path, required=True); args = ap.parse_args()
    root = args.root if args.root.is_absolute() else ROOT / args.root
    manifest = json.loads((root / 'manifest.json').read_text()); frame_model = manifest['frame_model']; names = [*manifest['controls'], *manifest['models']]
    out, _ = standard.standard_evaluation(root, 'R29', LABELS, METHOD, defaults={frame_model, 'CORE_PHASE_TARGET_R29'})
    native = pd.read_csv(root / 'native_forecasts.csv', low_memory=False); forecasts = pd.read_csv(root / 'forecasts.csv')
    actual = c.monthly(standard.COMPONENTS); published = c.publication_dates(actual.index)
    support = c.read('output/research_r17/attribution/primary_support.csv'); pairs = pd.read_csv(out / 'cnb_pairs.csv')
    clocks = native[native.h.eq(0) & native.model.eq(REFERENCE)].drop_duplicates('origin').set_index('origin').as_of_utc
    family = {o: family_paths(actual, published, o, clocks[o], blocks=(BLOCK,)) for o in clocks.index}
    lam = pd.read_csv(root / 'lambda_audit.csv'); gate = panel_gate(lam); c.dump(out / 'panel_gate.json', gate)
    phase_audit = pd.read_csv(root / 'phase_audit.csv')
    phase_audit.assign(era=[standard.ERAS['origins_2019_2021'](np.array([o]))[0] and '2019_2021' or (standard.ERAS['origins_2022_2023'](np.array([o]))[0] and '2022_2023' or '2024plus') for o in phase_audit.origin.astype(str)]) \
        .groupby(['era', 'czech_phase'], dropna=False).size().rename('origins').reset_index().to_csv(out / 'czech_phase_by_era.csv', index=False)
    table = block_table(native, actual, family, support, names); table.to_csv(out / 'core_cumulative_table.csv', index=False)
    score = scores(table, names); score.to_csv(out / 'core_family_scores.csv', index=False)
    verdicts = {m: verdict(table, score, forecasts, support, pairs, m, frame_model) for m in MODELS}
    if not gate['passes']:
        for v in verdicts.values():
            v['promotable'] = False; v['failed'] = ['panel_gate', *v['failed']]
    c.dump(out / 'rule_verdicts.json', verdicts)
    standard.close_manifest(out, extra_code=[Path(__file__), ROOT / 'models/benchmarks_r26.py', ROOT / 'models/core_phase_r29.py'])
    print(json.dumps(dict(panel_gate=dict(passes=gate['passes'], min_separation=gate['min_separation'], mean_separation_h1_6=gate['mean_separation_h1_6']),
                          verdicts={m: dict(failed=v['failed'], promotable=v['promotable']) for m, v in verdicts.items()}), indent=1))
    print('Completed R29 evaluation', out, flush=True)


if __name__ == '__main__':
    main()
