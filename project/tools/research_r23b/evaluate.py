"""R23B scoring: the fixed R23 evaluation stack plus the diagnostics the R23 review asked for.

    python -m tools.research_r23b.evaluate --root output/research_r23b/final
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from tools.review import evaluate_r17 as previous
from tools.research_r23.lead import lead_pairs, first_episodes, summaries
from tools.path_diagnostics import gates, bootstrap, attribution, benchmarks, lead_baselines

LABELS = {'PRESS_ULC_R23B': 'Labour cost pressure', 'PRESS_DOMESTIC_R23B': 'Domestic pressure', 'PRESS_MOMENTUM_R23B': 'Imported momentum',
          'PRESS_JOINT_R23B': 'Joint pressure - free', 'PRESS_SIGNED_R23B': 'Joint pressure - signed', 'PRESS_LEVELS_R23B': 'R23 level gaps, repaired',
          'CORE_FEEDBACK_R21': 'Core error feedback - R21'}
COMPONENTS = 'output/research_r14b/attribution/actual_component_targets.csv'
DIAGNOSTIC_CODE = ['gates.py', 'bootstrap.py', 'attribution.py', 'benchmarks.py', 'lead_baselines.py']


def period_of_year(reference):
    text = str(reference)
    return float(text[-1]) if 'Q' in text else float(text[-2:]) if len(text) == 7 else np.nan


def feature_gates(root):
    x = pd.read_csv(root / 'features.csv', index_col=0); p = pd.read_csv(root / 'feature_provenance.csv'); rows = []
    for feature in x.columns:
        own = p[p.feature.eq(feature)].set_index('origin'); label = own.reference.map(period_of_year).reindex(x.index)
        quarter_end = pd.PeriodIndex(x.index, freq='M').month % 3 == 0
        for scope, mask in [('all_origins', np.ones(len(x), bool)), ('quarter_end_origins', quarter_end)]:
            rows.append(dict(feature=feature, scope=scope, n=int(x[feature][mask].notna().sum()), reference_frequency='Q' if own.reference.astype(str).str.contains('Q').any() else 'M',
                             seasonal_variance_share=gates.seasonal_share(x[feature][mask], label[mask])))
    return pd.DataFrame(rows)


def coefficient_gates(root):
    k = pd.read_csv(root / 'coefficient_contributions.csv'); rows = []
    for (model, band), g in k.groupby(['model', 'band']):
        signed = g.kind.iloc[0] == 'positive'
        share = gates.binding_share(g) if signed else gates.wrong_sign_share(g)
        for feature, value in share.items():
            rows.append(dict(model=model, band=band, feature=feature, test='on_zero_bound' if signed else 'negative_unrestricted', share=float(value),
                             n=int(g.feature.eq(feature).sum()), applied_share=float(g[g.feature.eq(feature)].applied.mean())))
    return pd.DataFrame(rows)


def needed_applied(frame, roster):
    rows = []; fast = frame[frame.model.eq(c.FAST)].set_index(['origin', 'h'])
    for h in (3, 6, 12):
        base = fast.xs(h, level='h'); needed = (base.core_cumulative_log_actual - base.core_cumulative_log_forecast).dropna()
        for model in roster:
            own = frame[frame.model.eq(model) & frame.h.eq(h)].set_index('origin')
            applied = (own.core_cumulative_log_forecast - base.core_cumulative_log_forecast).reindex(needed.index)
            for sample, keep in [('full', needed.index), ('origins_2024plus', needed.index[needed.index >= '2024-01'])]:
                rows.append(dict(model=model, h=h, sample=sample, **gates.needed_vs_applied(needed.loc[keep], applied.loc[keep])))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--root', type=Path, required=True); args = ap.parse_args(); root = args.root
    # Gates first: they describe the inputs and the fits, and do not read a score.
    gate_features = feature_gates(root); gate_coefficients = coefficient_gates(root)
    previous.evaluate(root); out = root / 'evaluation'
    gate_features.to_csv(out / 'gate_feature_seasonality.csv', index=False); gate_coefficients.to_csv(out / 'gate_coefficient_signs.csv', index=False)
    manifest = json.loads((root / 'manifest.json').read_text()); models = manifest['models']; roster = [*manifest['controls'], *models]

    frame = pd.read_csv(out / 'forecast_core_outcomes.csv', low_memory=False)
    needed_applied(frame, models + ['CORE_FEEDBACK_R21']).to_csv(out / 'needed_vs_applied.csv', index=False)

    rows = pd.read_csv(out / 'primary_rows.csv'); boot = []; omissions = []; same = []
    metrics = {'headline_yy': ('yy_exante', 'yy_actual'), 'core_cumulative_log': ('core_cumulative_log_forecast', 'core_cumulative_log_actual')}
    for h, g in rows.groupby('h'):
        for metric, (prediction, truth) in metrics.items():
            error = g.pivot(index='origin', columns='model', values=prediction).sub(g.drop_duplicates('origin').set_index('origin')[truth], axis=0)
            for sample, mask in [('full', np.ones(len(error), bool)), ('origins_2024plus', error.index >= '2024-01')]:
                z = error.loc[mask]
                for model in roster:
                    e = z[model].dropna()
                    same.append(dict(metric=metric, h=h, sample=sample, model=model, n=len(e), rmse=float(np.sqrt((e ** 2).mean())) if len(e) else np.nan,
                                     mae=float(e.abs().mean()) if len(e) else np.nan, bias=float(e.mean()) if len(e) else np.nan))
                    if model == c.FAST:
                        continue
                    pair = z[[model, c.FAST]].dropna()
                    boot.append(dict(metric=metric, model=model, h=h, sample=sample,
                                     **bootstrap.circular_block_bootstrap(pair[model].to_numpy() ** 2 - pair[c.FAST].to_numpy() ** 2, origins=pair.index)))
            if metric == 'headline_yy':
                for model in models:
                    for year in sorted(set(error.index.str[:4])):
                        z = error[~error.index.str.startswith(year)]
                        omissions.append(dict(model=model, h=h, omitted_year=year, n=len(z), rmse_delta=np.sqrt((z[model] ** 2).mean()) - np.sqrt((z[c.FAST] ** 2).mean()),
                                              mae_delta=z[model].abs().mean() - z[c.FAST].abs().mean()))
    pd.DataFrame(same).to_csv(out / 'same_support_scoreboard.csv', index=False)
    pd.DataFrame(boot).to_csv(out / 'primary_support_circular_bootstrap.csv', index=False)
    pd.DataFrame(omissions).to_csv(out / 'leave_one_origin_year_out.csv', index=False)

    # Block accounting and block benchmarks.
    native = pd.read_csv(root / 'native_forecasts.csv', low_memory=False); actual = c.monthly(COMPONENTS)
    monthly = attribution.monthly_block_errors(native, actual)
    attribution.block_error_table(monthly, horizons=(3, 6, 12)).to_csv(out / 'block_error_table.csv', index=False)
    benchmarks.block_benchmark_scores(native, actual, c.publication_dates(actual.index)).to_csv(out / 'block_benchmarks.csv', index=False)

    # CNB lead test with base rates, report clustering and a block label on every call.
    projections = pd.read_csv(out / 'cnb_quarter_projections.csv'); projections = projections[projections.model.ne('cnb')]
    cnb = pd.read_csv(ROOT / 'data/cnb_mpr_cpi_quarterly.csv'); clocks = pd.read_csv(out / 'cnb_clocks.csv')
    headline = c.monthly('output/independent_path_frozen_inputs.csv', 'headline_mm')
    actual_yy = 100 * np.expm1(np.log1p(headline / 100).rolling(12).sum())
    base = lead_baselines.baseline_projections(cnb[cnb.report_date.ge('2022-01-01')], clocks, actual_yy)
    columns = ['model', 'clock', 'report_date', 'quarter', 'forecast', 'realised']
    every = pd.concat([projections[columns], base[columns]], ignore_index=True)
    lead = pd.concat([first_episodes(lead_pairs(every, cnb, t), cnb) for t in (.3, .5)], ignore_index=True)
    lead['is_baseline'] = lead.model.isin(lead_baselines.MODELS)
    lead.to_csv(out / 'cnb_lead_pairs.csv', index=False); summaries(lead).to_csv(out / 'cnb_lead_summary.csv', index=False)
    lead[lead.episode_start].to_csv(out / 'cnb_first_call_episodes.csv', index=False)
    flags = ['forecast_available', 'next_report_available', 'next_forecast_available', 'target_still_future', 'revision_eligible']
    lead.groupby(['model', 'clock', 'threshold'] + flags, dropna=False).agg(rows=('quarter', 'size'), calls=('call', 'sum')).reset_index().to_csv(out / 'cnb_lead_coverage.csv', index=False)
    scored = lead[lead.episode_start & lead.call & lead.revision_eligible & lead.realised.notna()]
    pd.concat([lead_baselines.report_clusters(g).assign(clock=k[0], threshold=k[1]) for k, g in scored.groupby(['clock', 'threshold'])]).to_csv(out / 'cnb_lead_report_clusters.csv', index=False)
    calls = scored[~scored.is_baseline]
    attributed = attribution.call_attribution(calls, clocks, monthly)
    attributed.insert(3, 'threshold', calls.threshold.to_numpy()); attributed['outcome'] = np.where(calls.material_gain.to_numpy(), 'gain', np.where(calls.material_loss.to_numpy(), 'loss', 'immaterial'))
    attributed.to_csv(out / 'cnb_call_attribution.csv', index=False)

    payload = json.loads((out / 'replay_data.json').read_text()); payload['title'] = 'CNB Rounds Replayed | R23B | historical research'
    payload['method'] = [
        'R23B: six declared cost-pressure candidates around the saved FAST core path, original 90 origins and 969 primary keys; h0 and noncore unchanged. Historical research, not a live or untouched holdout record.',
        'Repairs of R23: a same-quarter unit-labour-cost gap that carries no seasonal; six-month momentum differentials in place of late-cycle level gaps; no intercept and no centering, so zero pressure gives zero correction.',
        'Only h1-6 receive a learned correction, from two separate band equations with their own label maturity. h7-12 corrections are zero on average by construction.',
        'A correction is applied only when nested chronological validation beats applying none. One training origin per calendar quarter; quarterly labour data are never interpolated.',
        'No survey, CNB forecast or future realised driver enters the independent predictions. Current-vintage histories, assumed publication rules, repeated research on one inflation cycle and a transformation chosen after in-sample inspection remain limitations.',
        'Lead tables flag abs(model-CNB)>=0.30pp (0.50 sensitivity) and compare the immediately next CNB report for the same still-future quarter. Base-rate rows (constant 2%, random-walk annual rate, previous CNB, CNB momentum) pass through the same rules.',
        'Defaults show FAST with the joint free and signed candidates; no promotion is implied. Every control and candidate remains selectable.']
    for s in payload['series']:
        if s['kind'] == 'model':
            s['default'] = s['id'] in ['STATE_FAST_R15', 'PRESS_JOINT_R23B', 'PRESS_SIGNED_R23B']
            if s['id'] in LABELS:
                s['label'] = s['short'] = LABELS[s['id']]
    c.dump(out / 'replay_data.json', payload)
    old = out / 'cnb_rounds_replayed_r17.html'; previous.write_replay(old, payload)
    html = old.read_text(encoding='utf-8').replace('Czech CPI · R17 ·', 'Czech CPI · R23B ·').replace('CNB Rounds Replayed · R17 · historical', 'CNB Rounds Replayed · R23B · historical').replace('cnb-rounds-r17-visible-v1', 'cnb-rounds-r23b-visible-v1')
    (out / 'cnb_rounds_replayed_r23b.html').write_text(html, encoding='utf-8'); old.unlink()
    d = json.loads((out / 'definitions.json').read_text()); d['limitations'] = payload['method']
    d['bootstrap'] = 'Circular blocks on consecutive monthly origins: 12 months from 48 observations, 6 from 24, no interval below 24; 2000 draws, seed 1509.'
    d['cnb_lead'] = '.30 and .50 ex-ante deviation thresholds; immediate next report, same target beyond next report quarter; .15pp closer CNB revision and separate eventual .15pp absolute-error improvement; first calls deduplicated by model/clock/target/direction streak; base-rate rows flagged is_baseline.'
    c.dump(out / 'definitions.json', d)
    m = json.loads((out / 'input_manifest.json').read_text())
    for file in [Path(__file__), ROOT / 'tools/research_r23/lead.py', *[ROOT / 'tools/path_diagnostics' / f for f in DIAGNOSTIC_CODE]]:
        m['inputs'][str(file.resolve())] = c.sha(file)
    m['outputs'] = {p.name: c.sha(p) for p in out.iterdir() if p.is_file() and p.name != 'input_manifest.json'}; c.dump(out / 'input_manifest.json', m)
    print('Completed R23B evaluation', out, flush=True)


if __name__ == '__main__':
    main()
