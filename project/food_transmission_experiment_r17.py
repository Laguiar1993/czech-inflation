"""Offline R17 food experiment. Refuses existing destinations; declares before fitting."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from models.food_transmission_r17 import (MODELS, LAMBDAS, FEATURE_NAMES, MIN_TRAIN, WINDOW,
    MIN_VALIDATION, VALIDATION_WINDOW, snapshot, forecast_origin, load_inputs, replace_food, to_monthly_percent, _aware)
from models.path_inputs import compound_path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/research_r17_food'
SPEC = 'docs/implementation/R17_FOOD_SPEC_2026-09-14.md'
CONTROL = 'STATE_FAST_R15'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def dump(path, value):
    Path(path).write_text(json.dumps(_clean(value), indent=2, allow_nan=False)+'\n', encoding='utf-8')


def verify_manifest(root, manifest_path):
    """Verify BOTH source and output hashes in a preserved earlier manifest."""
    root = Path(root); manifest_path = Path(manifest_path)
    declaration = json.loads(manifest_path.read_text(encoding='utf-8'))
    hashes = {manifest_path.relative_to(root).as_posix(): sha(manifest_path)}
    for category in ('inputs', 'outputs'):
        base = root if category == 'inputs' else manifest_path.parent
        for name, expected in declaration[category].items():
            path = base / name
            if sha(path) != expected:
                raise ValueError(f'Preserved {category} hash changed: {path}')
            hashes[path.relative_to(root).as_posix()] = expected
    return hashes


def dependency_hashes():
    result = {}
    for manifest in ('output/research_r15/manifest.json', 'output/research_r16/manifest.json', 'data/research_r14/food/input_manifest.json'):
        verified = verify_manifest(ROOT, ROOT / manifest)
        for name, digest in verified.items():
            if name in result and result[name] != digest:
                raise ValueError(f'Conflicting preserved hash: {name}')
            result[name] = digest
    names = ['models/food_transmission_r17.py', 'food_transmission_experiment_r17.py', 'tests/test_food_transmission_r17.py', SPEC,
             'models/food_path_r14.py', 'models/food_stable_r14b.py', 'models/path_inputs.py',
             'docs/implementation/R14B_FOOD_DESIGN.md', 'output/research_r14b/food/food_outcomes.csv']
    result.update({name: sha(ROOT/name) for name in names})
    return dict(sorted(result.items()))


def integrate_food(base, predictions, headline):
    """Keep original h0/nonfood, replace future food, rebuild all annual accounting."""
    rows = []
    invariant = [c for c in base if c.startswith('weight_') or (c.startswith('value_') and c != 'value_food') or
                 (c.startswith('contribution_') and c != 'contribution_food')]
    for (origin, name), selected in predictions.groupby(['origin', 'model'], sort=False):
        source = base.loc[base.origin.eq(origin)].copy().sort_values('h')
        if source.empty:
            continue
        if list(source.h) != list(range(13)):
            raise ValueError('Exactly h0..12 required from original FAST')
        path = selected.set_index('h').mm_forecast.to_dict()
        if set(path) != set(range(1, 13)):
            raise ValueError('Exactly future h1..12 required from food model')
        changed = replace_food(source, path); changed['model'] = name
        pd.testing.assert_frame_equal(source[invariant], changed[invariant], check_exact=True)
        if source.mm_forecast.iloc[0] != changed.mm_forecast.iloc[0]:
            raise AssertionError('HARD_BASE h0 changed')
        changed['food_model_status'] = changed.h.map(selected.set_index('h').status).fillna('preserved_h0')
        changed['food_fallback_reason'] = changed.h.map(selected.set_index('h').reason).fillna('')
        changed['food_fallback_used'] = changed.food_model_status.str.startswith('fallback')
        future = changed.h.gt(0)
        changed.loc[future, 'status'] = np.where(np.isfinite(changed.loc[future, 'mm_forecast']), 'research_estimated', 'unavailable')
        changed.loc[future, 'converged'] = np.isfinite(changed.loc[future, 'mm_forecast'])
        changed.loc[future, 'fallback_used'] = changed.loc[future, 'fallback_used'].astype(bool) | changed.loc[future, 'food_fallback_used']
        allpath = changed.set_index('h').mm_forecast.to_dict(); t = pd.Period(origin, 'M')
        for index, row in changed.iterrows():
            h = int(row.h)
            changed.loc[index, 'yy_exante'] = compound_path(headline.loc[headline.index < t], allpath, t, h, allpath[0])
            changed.loc[index, 'yy_conditional'] = compound_path(headline.loc[headline.index < t], allpath, t, h, headline.get(t, np.nan))
            values = np.asarray([allpath[j] for j in range(1, h+1)], dtype=float)
            changed.loc[index, 'cumulative_log_forecast'] = float(100*np.log1p(values/100).sum()) if np.isfinite(values).all() and (values > -100).all() else np.nan
        rows.extend(changed.to_dict('records'))
    return pd.DataFrame(rows)


def component_outcomes(predictions, control, levels):
    actual_log = levels.food.diff(); frames = [predictions.copy()]
    c = control.loc[control.h.between(1, 12), ['origin', 'target', 'model', 'h', 'value_food']].copy()
    c = c.rename(columns={'value_food': 'mm_forecast'}); c['log_rate_forecast'] = 100*np.log1p(c.mm_forecast/100)
    c['status'] = 'preserved_control'; c['reason'] = ''; frames.append(c)
    records = []
    for (origin, name), group in pd.concat(frames, ignore_index=True).groupby(['origin', 'model'], sort=False):
        t = pd.Period(origin, 'M'); group = group.set_index('h')
        for h in range(1, 13):
            row = group.loc[h].to_dict(); row.update(origin=origin, model=name, h=h, target=str(t+h))
            target_rate = actual_log.get(t+h, np.nan); row['mm_actual'] = float(100*np.expm1(target_rate/100))
            for suffix, values in [('forecast', group.reindex(range(1, h+1)).log_rate_forecast.to_numpy()),
                                   ('actual', actual_log.reindex(pd.period_range(t+1, t+h, freq='M')).to_numpy())]:
                total = float(np.sum(values)) if np.isfinite(values).all() else np.nan
                row['cumulative_log_'+suffix] = total; row['cumulative_pct_'+suffix] = float(100*np.expm1(total/100))
            records.append(row)
    return pd.DataFrame(records)


def component_scores(outcomes):
    rows = []; names = sorted(outcomes.model.unique()); keys = ['origin', 'h']
    for sample in ('full', 'recent_origins', 'recent_targets'):
        data = outcomes if sample == 'full' else outcomes.loc[outcomes.origin.ge('2024-01') if sample == 'recent_origins' else outcomes.target.ge('2024-01')]
        for h in range(13):
            subset = data if h == 0 else data.loc[data.h.eq(h)]
            if subset.empty:
                continue
            for metric in ('mm', 'cumulative_log', 'cumulative_pct'):
                value, truth = f'{metric}_forecast', f'{metric}_actual'
                wide = subset.pivot(index=keys, columns='model', values=value).reindex(columns=names)
                actual = subset.drop_duplicates(keys).set_index(keys)[truth].reindex(wide.index)
                base_mask = np.isfinite(actual) & np.isfinite(wide[CONTROL])
                common = base_mask & np.isfinite(wide).all(axis=1)
                for scope, mask in [('primary_control_calendar', base_mask), ('common', common)]:
                    calendar = wide.index[mask]
                    for name in names:
                        own = subset.loc[subset.model.eq(name)].set_index(keys).reindex(calendar)
                        error = own[value] - own[truth]; finite = np.isfinite(error); scored = error.loc[finite]
                        fallback = own.status.fillna('').str.startswith('fallback')
                        rows.append(dict(scope=scope, sample=sample, h=h, horizon_label='pooled_h1_12' if h == 0 else f'h{h}',
                                         metric=metric, model=name, n_intended=len(calendar), n_scored=int(finite.sum()),
                                         n_missing_forecast=int((~np.isfinite(own[value])).sum()), n_fallback=int(fallback.sum()),
                                         rmse=float(np.sqrt(np.mean(scored**2))) if len(scored) else np.nan,
                                         mae=float(scored.abs().mean()) if len(scored) else np.nan,
                                         bias=float(scored.mean()) if len(scored) else np.nan))
    return pd.DataFrame(rows)


def run(destination=OUT, end='2026-07'):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite experiment destination: {destination}')
    end = str(pd.Period(end, 'M'))
    if not '2019-02' <= end <= '2026-07':
        raise ValueError('Run end must be an original outer origin')
    hashes = dependency_hashes(); levels, available, source_meta = load_inputs()
    states = json.loads((ROOT/'output/research_r15/states.json').read_text(encoding='utf-8'))
    baseline = pd.read_csv(ROOT/'output/research_r15/native_forecasts.csv', float_precision='round_trip')
    baseline = baseline.loc[baseline.model.eq(CONTROL) & baseline.origin.le(end)].copy()
    control_forecasts = pd.read_csv(ROOT/'output/research_r16/forecasts.csv', float_precision='round_trip')
    control_forecasts = control_forecasts.loc[control_forecasts.model.eq(CONTROL) & control_forecasts.origin.le(end)].copy()
    expected_outer = list(map(str, pd.period_range('2019-02', end, freq='M')))
    if sorted(baseline.origin.unique()) != expected_outer:
        raise ValueError('Original complete outer calendar missing')
    checks = baseline.merge(control_forecasts, on=['origin', 'h'], suffixes=('_native', '_control'))
    if len(checks) != len(baseline) or not np.array_equal(checks.mm_forecast_native, checks.mm_forecast_control, equal_nan=True):
        raise AssertionError('R15 FAST monthly path differs from R16 preserved control')
    for origin in expected_outer:
        clock = baseline.loc[baseline.origin.eq(origin), 'as_of_utc'].iloc[0]
        if _aware(states[origin]['as_of']) != _aware(clock):
            raise AssertionError('R15 snapshot clock differs from original FAST clock')
    destination.mkdir(parents=True)
    declaration = dict(declared_at=datetime.now(timezone.utc).isoformat(), inputs=hashes, specification=SPEC, models=MODELS,
                       penalties=LAMBDAS, own_penalty=.1, min_train=MIN_TRAIN, training_window=WINDOW,
                       validation_window=VALIDATION_WINDOW, min_validation=MIN_VALIDATION,
                       first_snapshot='2016-02', last_snapshot=end, outer_origins=expected_outer,
                       no_future_upstream_forecasts=True, source=source_meta, parameters_frozen_before_fit=True)
    dump(destination/'declaration.json', declaration)
    print(f'Preserved {len(hashes)} hashes verified; declaration saved before fitting.', flush=True)
    snapshots = {str(t): snapshot(levels, available, t, states[str(t)]['as_of']) for t in pd.period_range('2016-02', end, freq='M')}
    dump(destination/'snapshots.json', snapshots)
    feature_rows = [dict(origin=s, as_of=v['as_of'], **dict(zip(FEATURE_NAMES, v['features']))) for s, v in snapshots.items()]
    pd.DataFrame(feature_rows).to_csv(destination/'features_by_origin.csv', index=False)
    history, fits, calendars, selections, records, candidates = [], [], {}, [], [], []
    for i, (origin, state) in enumerate(snapshots.items()):
        result = forecast_origin(snapshots, levels, available, origin, state['as_of'], history)
        for fit in result['fits']:
            calendar = fit.pop('training'); key = f"{origin}|{fit['h']}"
            if key in calendars and calendars[key] != calendar:
                raise AssertionError('Own/cost or lambda training calendars differ')
            calendars[key] = calendar; fit['training_calendar_id'] = key; fits.append(fit)
        selections.extend(dict(origin=origin, as_of=state['as_of'], **r) for r in result['selections'])
        for row in result['candidates']:
            for h, value in enumerate(row['log_rates'], 1):
                candidates.append(dict(origin=origin, as_of=state['as_of'], h=h, target=str(pd.Period(origin, 'M')+h),
                                       family=row['family'], penalty=row['penalty'], log_rate_forecast=value,
                                       mm_forecast=float(to_monthly_percent(value)), status=row['statuses'][h-1],
                                       reason=row['reasons'][h-1], all_path_estimated=row['all_estimated']))
        history.extend(result['candidates'])
        for name, path in result['paths'].items():
            for h, value in enumerate(path, 1):
                records.append(dict(origin=origin, as_of_utc=_aware(state['as_of']).tz_convert('UTC').isoformat(),
                                    target=str(pd.Period(origin, 'M')+h), h=h, model=name, log_rate_forecast=float(value),
                                    mm_forecast=float(to_monthly_percent(value)), status=result['statuses'][name][h-1],
                                    reason=result['reasons'][name][h-1], outer_origin=origin in expected_outer))
        if i % 12 == 0 or i == len(snapshots)-1:
            print(f'Food own-origin paths {i+1}/{len(snapshots)}: {origin}', flush=True)
    predictions = pd.DataFrame(records); predictions.to_csv(destination/'food_predictions.csv', index=False)
    pd.DataFrame(candidates).to_csv(destination/'fixed_candidates.csv', index=False)
    dump(destination/'fits.json', fits); dump(destination/'training_calendars.json', calendars); dump(destination/'selections.json', selections)
    outer = predictions.loc[predictions.outer_origin].copy()
    headline = pd.read_csv(ROOT/'output/independent_path_frozen_inputs.csv', index_col=0, float_precision='round_trip').headline_mm
    headline.index = pd.PeriodIndex(headline.index, freq='M')
    native = integrate_food(baseline, outer, headline); native.to_csv(destination/'native_forecasts.csv', index=False)
    columns = ['origin','h','target','as_of_utc','model','mm_forecast','mm_actual','yy_actual','yy_exante','cumulative_log_forecast','cumulative_log_actual']
    pd.concat([native[columns], control_forecasts[columns]], ignore_index=True).to_csv(destination/'forecasts.csv', index=False)
    outcomes = component_outcomes(outer, baseline, levels)
    # Check targets against the previously preserved food experiment, independently of our conversion.
    old = pd.read_csv(ROOT/'output/research_r14b/food/food_outcomes.csv', float_precision='round_trip').drop_duplicates(['origin','h'])
    agreement = outcomes.loc[outcomes.model.eq(CONTROL)].merge(old[['origin','h','mm_actual']], on=['origin','h'], suffixes=('_new','_old'))
    difference = float((agreement.mm_actual_new-agreement.mm_actual_old).abs().max())
    if difference > 1e-10:
        raise AssertionError('Food targets differ from the original component experiment')
    outcomes.to_csv(destination/'food_outcomes.csv', index=False)
    summary = component_scores(outcomes); summary.to_csv(destination/'food_summary.csv', index=False)
    coverage = outer.groupby(['model', 'status', 'reason'], dropna=False).size().rename('rows').reset_index()
    coverage.to_csv(destination/'coverage.csv', index=False)
    validation = dict(status='passed', all_original_origins_retained=len(expected_outer), snapshot_count=len(snapshots),
                      standalone_prediction_rows=len(predictions), original_nonfood_h0_weights_exact=True,
                      r15_fast_equals_r16_control=True, original_clocks_exact=True, shared_training_calendars=True,
                      food_target_reconstruction_max_abs=difference, future_upstream_forecast_used=False,
                      finite_outer_food_rows=int(np.isfinite(outer.mm_forecast).sum()), expected_outer_food_rows=len(outer),
                      full_run=end == '2026-07')
    if dependency_hashes() != hashes:
        raise AssertionError('Input or code changed during the declared experiment')
    dump(destination/'validation.json', validation)
    outputs = {p.name: sha(p) for p in sorted(destination.iterdir()) if p.is_file() and p.name != 'manifest.json'}
    manifest = dict(completed_at=datetime.now(timezone.utc).isoformat(), inputs=hashes, outputs=outputs,
                    origin_count=len(expected_outer), snapshot_count=len(snapshots), models=MODELS, control=CONTROL,
                    specification_sha256=hashes[SPEC], declaration_sha256=outputs['declaration.json'],
                    parameters_frozen_before_fit=True, packages={p: importlib.metadata.version(p) for p in ('numpy', 'pandas')},
                    interpretation='Direct released cost-lag forecasting association; current stored histories with reconstructed availability; no fresh holdout or structural claim.')
    dump(destination/'manifest.json', manifest)
    print(summary.loc[summary.scope.eq('primary_control_calendar') & summary['sample'].eq('full') & summary.h.isin([0, 12]) & summary.metric.eq('mm'),
                      ['horizon_label','model','n_intended','n_scored','n_fallback','rmse','bias']].to_string(index=False), flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--end', default='2026-07')
    args = parser.parse_args(); run(args.output, args.end)
