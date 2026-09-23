"""The standard path evaluation for rounds from R24: the fixed R17 stack plus the review's diagnostics.

`standard_evaluation(root, ...)` expects a run directory with `manifest.json` (controls, models),
`native_forecasts.csv` and `forecasts.csv` on the original 90 origins, and writes
`root/evaluation`. It never fits or selects anything.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
import r17_common as c
from tools.review import evaluate_r17 as previous
from tools.research_r23.lead import lead_pairs, first_episodes, summaries
from tools.path_diagnostics import bootstrap, attribution, benchmarks, lead_baselines

COMPONENTS = 'output/research_r14b/attribution/actual_component_targets.csv'
CODE = ['standard.py', 'gates.py', 'bootstrap.py', 'attribution.py', 'benchmarks.py', 'lead_baselines.py']
METRICS = {'headline_yy': ('yy_exante', 'yy_actual'), 'core_cumulative_log': ('core_cumulative_log_forecast', 'core_cumulative_log_actual')}
ERAS = {'full': lambda o: np.ones(len(o), bool), 'origins_2019_2021': lambda o: o <= '2021-12',
        'origins_2022_2023': lambda o: (o >= '2022-01') & (o <= '2023-12'), 'origins_2024plus': lambda o: o >= '2024-01'}


def era_samples(frame):
    return {name: pd.Series(rule(frame.origin.to_numpy().astype(str)), index=frame.index) for name, rule in ERAS.items()}


def standard_evaluation(root, tag, labels, method, defaults, reference=c.FAST, extra_code=()):
    root = Path(root); previous.evaluate(root); out = root / 'evaluation'
    manifest = json.loads((root / 'manifest.json').read_text()); models = manifest['models']; roster = [*manifest['controls'], *models]

    rows = pd.read_csv(out / 'primary_rows.csv'); boot = []; omissions = []; same = []
    for h, g in rows.groupby('h'):
        for metric, (prediction, truth) in METRICS.items():
            error = g.pivot(index='origin', columns='model', values=prediction).sub(g.drop_duplicates('origin').set_index('origin')[truth], axis=0)
            for sample, rule in ERAS.items():
                z = error.loc[rule(error.index.to_numpy().astype(str))]
                for model in roster:
                    e = z[model].dropna()
                    same.append(dict(metric=metric, h=h, sample=sample, model=model, n=len(e), rmse=float(np.sqrt((e ** 2).mean())) if len(e) else np.nan,
                                     mae=float(e.abs().mean()) if len(e) else np.nan, bias=float(e.mean()) if len(e) else np.nan))
                    if model == reference or sample not in ('full', 'origins_2024plus'):
                        continue
                    pair = z[[model, reference]].dropna()
                    boot.append(dict(metric=metric, model=model, reference=reference, h=h, sample=sample,
                                     **bootstrap.circular_block_bootstrap(pair[model].to_numpy() ** 2 - pair[reference].to_numpy() ** 2, origins=pair.index)))
            if metric == 'headline_yy':
                for model in models:
                    for year in sorted(set(error.index.str[:4])):
                        z = error[~error.index.str.startswith(year)]
                        omissions.append(dict(model=model, h=h, omitted_year=year, n=len(z), rmse_delta=np.sqrt((z[model] ** 2).mean()) - np.sqrt((z[reference] ** 2).mean()),
                                              mae_delta=z[model].abs().mean() - z[reference].abs().mean()))
    pd.DataFrame(same).to_csv(out / 'same_support_scoreboard.csv', index=False)
    pd.DataFrame(boot).to_csv(out / 'primary_support_circular_bootstrap.csv', index=False)
    pd.DataFrame(omissions).to_csv(out / 'leave_one_origin_year_out.csv', index=False)

    native = pd.read_csv(root / 'native_forecasts.csv', low_memory=False); actual = c.monthly(COMPONENTS)
    monthly = attribution.monthly_block_errors(native, actual)
    attribution.block_error_table(monthly, horizons=(3, 6, 12), samples=era_samples).to_csv(out / 'block_error_table.csv', index=False)
    benchmarks.block_benchmark_scores(native, actual, c.publication_dates(actual.index), samples=era_samples).to_csv(out / 'block_benchmarks.csv', index=False)

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
    attributed.insert(3, 'threshold', calls.threshold.to_numpy())
    attributed['outcome'] = np.where(calls.material_gain.to_numpy(), 'gain', np.where(calls.material_loss.to_numpy(), 'loss', 'immaterial'))
    attributed.to_csv(out / 'cnb_call_attribution.csv', index=False)

    payload = json.loads((out / 'replay_data.json').read_text()); payload['title'] = f'CNB Rounds Replayed | {tag} | historical research'; payload['method'] = list(method)
    for s in payload['series']:
        if s['kind'] == 'model':
            s['default'] = s['id'] in defaults
            if s['id'] in labels:
                s['label'] = s['short'] = labels[s['id']]
    c.dump(out / 'replay_data.json', payload)
    old = out / 'cnb_rounds_replayed_r17.html'; previous.write_replay(old, payload)
    html = old.read_text(encoding='utf-8').replace('Czech CPI · R17 ·', f'Czech CPI · {tag} ·').replace('CNB Rounds Replayed · R17 · historical', f'CNB Rounds Replayed · {tag} · historical').replace('cnb-rounds-r17-visible-v1', f'cnb-rounds-{tag.lower()}-visible-v1')
    (out / f'cnb_rounds_replayed_{tag.lower()}.html').write_text(html, encoding='utf-8'); old.unlink()
    d = json.loads((out / 'definitions.json').read_text()); d['limitations'] = payload['method']
    d['bootstrap'] = 'Circular blocks on consecutive monthly origins: 12 months from 48 observations, 6 from 24, no interval below 24; 2000 draws, seed 1509.'
    d['cnb_lead'] = '.30 and .50 ex-ante deviation thresholds; immediate next report, same target beyond next report quarter; .15pp closer CNB revision and separate eventual .15pp absolute-error improvement; first calls deduplicated by model/clock/target/direction streak; base-rate rows flagged is_baseline.'
    d['samples'] = 'full; origins 2019-2021; origins 2022-2023; origins from 2024.'
    c.dump(out / 'definitions.json', d)
    return out, monthly


def close_manifest(out, extra_code=()):
    m = json.loads((out / 'input_manifest.json').read_text())
    for file in [ROOT / 'tools/research_r23/lead.py', *[ROOT / 'tools/path_diagnostics' / f for f in CODE], *map(Path, extra_code)]:
        m['inputs'][str(Path(file).resolve())] = c.sha(file)
    m['outputs'] = {p.name: c.sha(p) for p in out.iterdir() if p.is_file() and p.name != 'input_manifest.json'}
    c.dump(out / 'input_manifest.json', m)
