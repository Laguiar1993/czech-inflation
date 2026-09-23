"""Frozen R10 services experiment. Run, or --verify for an offline exact replay.

Only core changes; every headline prediction retains R9's non-core contribution.
The benchmark survey is loaded AFTER predictions, solely for evaluation.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from data.core_split import load_frozen, monthly_rates, weights_at
from models.core_split import forecast_origin
from models.core_tuning import hard_features, ridge_prediction

ROOT = Path(__file__).resolve().parent
FIX = ROOT / 'tests/fixtures/cleanup'
OUTPUT = ROOT / 'output'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_frame(path):
    frame = pd.read_csv(path, index_col=0, float_precision='round_trip')
    frame.index = pd.PeriodIndex(frame.index, freq='M')
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError(f'invalid monthly index: {path}')
    return frame


def publication_dates(index):
    import cz_struct as s
    earliest = s._release_calendar().index.min()
    dates = {}
    for month in index:
        date = s._detail_release_dt(month)
        if pd.isna(date) and month < earliest:
            date = (month+1).to_timestamp() + pd.Timedelta(days=19, hours=9)
        dates[month] = date
    return pd.Series(dates, dtype='datetime64[ns]')


def input_hashes():
    files = [ROOT / name for name in (
        'core_split_experiment.py', 'models/core_split.py', 'data/core_split.py',
        'evaluation/core_split.py', 'models/core_tuning.py', 'cz_struct.py',
        'data/release_calendar_cz_cpi.csv', 'data/czcpmom_survey_history_extended.csv',
        'output/independent_nowcast_forecasts.csv', 'output/independent_nowcast_diagnostics.json',
        'docs/implementation/CORE_SPLIT_PLAN_2026-09-09.md')]
    files += [FIX / name for name in ('MANIFEST.json', 'core_features.csv', 'cnb_core_mm.csv', 'food_block_features.csv')]
    files += [p for p in (ROOT/'data/core_split').rglob('*') if p.is_file()]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}


def component_evidence(reference_core, candidate_core, actual_core, weight, fixed_noncore, headline_actual):
    """Exact error decomposition; non-core term includes first/detail reconciliation."""
    base_error = weight * (reference_core-actual_core)
    candidate_error = weight * (candidate_core-actual_core)
    other_error = fixed_noncore + weight*actual_core - headline_actual
    return dict(weighted_core_error=candidate_error, noncore_reconciliation_error=other_error,
        weighted_core_squared_gain=base_error**2-candidate_error**2,
        cross_term_gain=2*other_error*(base_error-candidate_error),
        headline_squared_gain=(base_error+other_error)**2-(candidate_error+other_error)**2)


def diagnostic_tables(auxiliary, previous_diag, survey, contribution_rows):
    """Post-scoring attribution; never chooses or changes a forecasting formula."""
    auxiliary = pd.DataFrame(auxiliary)
    attribution, scores, influence = [], [], []
    for name, group in auxiliary.groupby('model', sort=False):
        periods = pd.PeriodIndex(group.period, freq='M')
        reference_core = previous_diag.core_forecast.reindex(group.period).to_numpy()
        candidate = group.core_forecast.to_numpy()
        actual = group.core_actual.to_numpy()
        first_actual = survey.actual.reindex(periods).to_numpy()
        ev = component_evidence(reference_core, candidate, actual, group.core_weight.to_numpy(),
                                group.fixed_noncore.to_numpy(), first_actual)
        proof = ev['headline_squared_gain'] - ev['weighted_core_squared_gain'] - ev['cross_term_gain']
        if np.nanmax(np.abs(proof)) > 1e-10:
            raise AssertionError('core/non-core error attribution identity failed')
        attribution.append(pd.DataFrame(dict(period=group.period.to_numpy(), model=name, **ev)))
        base_headline_error = group.fixed_noncore.to_numpy() + group.core_weight.to_numpy()*reference_core-first_actual
        candidate_headline_error = group.fixed_noncore.to_numpy() + group.core_weight.to_numpy()*candidate-first_actual
        for frame, mask in [('all', np.ones(len(group), bool)), ('2024+', periods >= pd.Period('2024-01')),
                            ('ex_jan', periods.month != 1), ('big', np.abs(first_actual-survey.survey_median.reindex(periods).to_numpy()) >= .4-1e-9)]:
            e, base_e = (candidate-actual)[mask], (reference_core-actual)[mask]
            finite = np.isfinite(e) & np.isfinite(base_e)
            e, base_e = e[finite], base_e[finite]
            scores.append(dict(model=name, frame=frame, n=len(e), core_rmse=np.sqrt(np.mean(e**2)),
                core_mae=np.mean(np.abs(e)), reference_core_rmse=np.sqrt(np.mean(base_e**2)),
                reference_core_mae=np.mean(np.abs(base_e))))
        # Every omitted origin is reported, rather than selecting one favourable deletion.
        for omitted in periods:
            mask = (periods != omitted) & np.isfinite(base_headline_error) & np.isfinite(candidate_headline_error)
            br = np.sqrt(np.mean(base_headline_error[mask]**2))
            cr = np.sqrt(np.mean(candidate_headline_error[mask]**2))
            influence.append(dict(model=name, omitted_period=str(omitted), n=int(mask.sum()),
                                  reference_rmse=br, candidate_rmse=cr, relative_rmse_gain=1-cr/br))
    category_scores = []
    contributions = pd.DataFrame(contribution_rows)
    for (model, block), group in contributions[contributions.category_actual_mm.notna()].groupby(['model', 'block']):
        for frame, mask in [('all', np.ones(len(group), bool)), ('2024+', group.period >= '2024-01')]:
            g = group.loc[mask].dropna(subset=['prediction','category_actual_mm','seasonal_norm'])
            e = g.prediction-g.category_actual_mm
            naive = g.seasonal_norm-g.category_actual_mm
            category_scores.append(dict(model=model, category=block, frame=frame, n=len(g),
                rmse=np.sqrt(np.mean(e**2)), mae=e.abs().mean(),
                seasonal_rmse=np.sqrt(np.mean(naive**2)), seasonal_mae=naive.abs().mean()))
    return {'component_error_attribution': pd.concat(attribution, ignore_index=True),
            'core_scores': pd.DataFrame(scores), 'leave_one_out': pd.DataFrame(influence),
            'category_scores': pd.DataFrame(category_scores)}


def run(destination=OUTPUT):
    import cz_struct as s
    from evaluation.core_split import evaluate
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    frozen_hashes = json.loads((FIX/'MANIFEST.json').read_text(encoding='utf-8'))
    for name, expected in frozen_hashes.items():
        if digest(FIX/name) != expected:
            raise ValueError(f'R9 frozen fixture changed: {name}')
    sources = load_frozen()
    categories = monthly_rates(sources['levels'])
    core = read_frame(FIX/'cnb_core_mm.csv').iloc[:, 0]
    features = read_frame(FIX/'core_features.csv')
    food = read_frame(FIX/'food_block_features.csv')
    reference = read_frame(OUTPUT/'independent_nowcast_forecasts.csv')
    if len(reference) != 90 or not reference.index.equals(pd.period_range('2019-02', '2026-07', freq='M')):
        raise ValueError('the fixed experiment requires the declared 90 release origins')
    previous_diag = pd.DataFrame(json.loads((OUTPUT/'independent_nowcast_diagnostics.json').read_text()))
    previous_diag = previous_diag[previous_diag.policy == 'hard'].set_index('period')
    available = publication_dates(core.index)
    observation_calendar = []
    for source_name, source_index in [('CNB_core', core.index), ('CZSO_five_categories', categories.index),
                                      ('ARAD_tradables_nontradables', sources['broad_yoy'].index)]:
        for period, date in publication_dates(source_index).items():
            observation_calendar.append(dict(source=source_name, target_month=str(period),
                assumed_available_from=date, timezone='Europe/Prague',
                status='publication rule, not recorded source vintage'))
    pd.DataFrame(observation_calendar).to_csv(destination/'core_split_observation_calendar.csv', index=False)
    predictions, fits, contributions, origin_checks, auxiliary, weight_rows = [], [], [], [], [], []
    max_baseline_difference = 0.
    for i, (t, ref) in enumerate(reference.iterrows()):
        clock = pd.Timestamp(ref.as_of_eve)
        if clock >= s._first_release_dt(t):
            raise ValueError(f'forecast does not precede first release: {t}')
        if not clock < available.loc[t]:
            raise ValueError(f'core target already known: {t}')
        x = s._mask_row_by_availability(hard_features(features), t, clock)
        f = s._mask_row_by_availability(food, t, clock)
        base_fit = ridge_prediction(x, core, t, clock, available)
        base = base_fit['prediction']
        difference = abs(base-previous_diag.loc[str(t), 'core_forecast'])
        max_baseline_difference = max(max_baseline_difference, difference)
        if difference > 1e-10:
            raise ValueError(f'R9 core baseline replay failed: {t} {difference}')
        weights = weights_at(sources['weights'], t, clock)
        fit = forecast_origin(core, categories, sources['broad_yoy'], x, f, available,
                              t, clock, weights, core_weight=ref.coreweight)
        fixed_noncore = ref.HARD_BASE - ref.coreweight * base
        row = dict(period=str(t), R9_BASE=ref.HARD_BASE, R9_HALF=ref.HARD_HALF, R9_FULL=ref.HARD_FULL)
        for name, cp in fit['predictions'].items():
            row[name] = fixed_noncore + ref.coreweight * cp
            auxiliary.append(dict(period=str(t), model=name, core_forecast=cp, core_actual=core.loc[t],
                                  core_weight=ref.coreweight, fixed_noncore=fixed_noncore))
            if name not in ('TARGET_SHARED', 'AGG_COMMON', 'BROAD_AGG_CONTROL'):
                row[name+'_HALF'] = .5*ref.HARD_BASE + .5*row[name]
        predictions.append(row)
        for entry in fit['fits']:
            fits.append(dict(period=str(t), as_of=clock, **entry))
        for entry in fit['contributions']:
            block = entry['block']
            actual = categories.loc[t, block] if block in categories else np.nan
            contributions.append(dict(period=str(t), as_of=clock, **entry, category_actual_mm=actual))
        origin_checks.append(dict(period=str(t), as_of=clock, baseline_difference=difference, **fit['checks']))
        for block, value in weights.items():
            weight_rows.append(dict(period=str(t), category=block, base_basket_fraction=value,
                                   effective_year=weights.attrs.get('effective_year'),
                                   assumed_available_from=weights.attrs.get('availability_assumption_date')))
        if i % 15 == 0:
            print(f'Completed {i+1}/{len(reference)} origins: {t}', flush=True)
    pred = pd.DataFrame(predictions).set_index('period')
    pred.index = pd.PeriodIndex(pred.index, freq='M')
    check = pd.DataFrame(origin_checks)
    if (check.shared_design_commutation_error > 1e-10).any() or (check.max_target_reconciliation_error > 1e-10).any():
        raise AssertionError('category accounting / identical-design linear control failed')
    fit_table = pd.DataFrame(fits)
    estimated = fit_table[fit_table.fit_status == 'estimated']
    if (pd.PeriodIndex(estimated.train_end, freq='M') >= pd.PeriodIndex(estimated.period, freq='M')).any():
        raise AssertionError('future training label')
    if (pd.to_datetime(estimated.training_last_release) > pd.to_datetime(estimated.as_of)).any():
        raise AssertionError('unpublished training label')
    # Forecasts are complete before this file is opened. No survey enters estimation.
    survey = pd.read_csv(ROOT/'data/czcpmom_survey_history_extended.csv')
    survey = survey[survey.era != 'flash_survey_suspect'].copy()
    survey.index = pd.PeriodIndex(survey.target_month, freq='M')
    if not survey.index.is_unique:
        raise ValueError('duplicate first-release survey labels')
    assessment = evaluate(pred, survey.reindex(pred.index))
    for name, table in diagnostic_tables(auxiliary, previous_diag, survey, contributions).items():
        table.to_csv(destination/f'core_split_{name}.csv', index=False)
    pred.to_csv(destination/'core_split_forecasts.csv', index_label='period')
    fit_table.to_csv(destination/'core_split_fit_audit.csv', index=False)
    pd.DataFrame(contributions).to_csv(destination/'core_split_contributions.csv', index=False)
    pd.DataFrame(auxiliary).to_csv(destination/'core_split_core_predictions.csv', index=False)
    pd.DataFrame(weight_rows).to_csv(destination/'core_split_weights.csv', index=False)
    check.to_csv(destination/'core_split_origin_checks.csv', index=False)
    for key, filename in [('scores', 'scores'), ('release_rows', 'releases'), ('bootstrap', 'bootstrap')]:
        assessment[key].to_csv(destination/f'core_split_{filename}.csv', index=(key == 'release_rows'), index_label='period')
    (destination/'core_split_gates.json').write_text(json.dumps(assessment['gates'], indent=2, default=str), encoding='utf-8')
    # Observed category monitor. This is a latest-vintage diagnostic, NOT a new live forecast.
    latest = categories.dropna().index.max()
    levels = sources['levels']
    w_latest = weights_at(sources['weights'], latest, pd.Timestamp('2026-09-09 23:59'))
    monitor = []
    for name in categories:
        history = categories.loc[categories.index < latest, name].dropna()
        seasonal = history[history.index.month == latest.month].iloc[-5:].mean()
        mm = categories.loc[latest, name]
        monitor.append(dict(period=str(latest), category=name, mom=mm,
            yoy=100*(levels.loc[latest,name]/levels.loc[latest-12,name]-1),
            same_month_prior_five_mean=seasonal, excess_over_seasonal=mm-seasonal,
            base_basket_fraction=w_latest[name], approximate_headline_contribution=w_latest[name]*mm,
            approximate_excess_contribution=w_latest[name]*(mm-seasonal)))
    pd.DataFrame(monitor).to_csv(destination/'core_split_latest_categories.csv', index=False)
    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs=input_hashes(),
        evaluation='90 fixed first-release origins; release-eve information; survey is scoring-only',
        vintage_status='latest-vintage histories plus documented publication rules; exploratory pseudo-OOS',
        weight_status='base-basket service weights and fitted core coefficient; approximate projection, not official contributions',
        baseline_max_absolute_difference=max_baseline_difference,
        outputs={p.name: digest(p) for p in sorted(destination.glob('core_split_*.csv'))},
        gates_sha256=digest(destination/'core_split_gates.json'))
    (destination/'core_split_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(assessment['scores'].query("coverage == 'common' and frame == 'all'")[['model', 'n', 'rmse', 'mae']].to_string(index=False))
    return manifest


def verify():
    """Regenerate every result with all database/network access forbidden."""
    manifest = json.loads((OUTPUT/'core_split_manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['inputs'].items():
        if digest(ROOT/name) != expected:
            raise ValueError(f'experiment input/code changed since freeze: {name}')
    saved = {**manifest['outputs'], 'core_split_gates.json': manifest['gates_sha256']}
    for name, expected in saved.items():
        if not (OUTPUT/name).is_file() or digest(OUTPUT/name) != expected:
            raise ValueError(f'saved output changed since freeze: {name}')
    def forbidden(*args, **kwargs):
        raise AssertionError('offline replay attempted network/database access')
    with tempfile.TemporaryDirectory(prefix='cz_core_split_') as temporary, ExitStack() as stack:
        for target in ('socket.socket', 'socket.create_connection', 'requests.sessions.Session.request', 'duckdb.connect'):
            stack.enter_context(patch(target, side_effect=forbidden))
        actual = run(Path(temporary))
        if actual['outputs'] != manifest['outputs'] or actual['gates_sha256'] != manifest['gates_sha256']:
            raise AssertionError('frozen output replay mismatch')
    print(f"Offline replay: all {len(manifest['outputs'])} CSVs and gates are byte-identical.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    verify() if args.verify else run()
