"""R17 food contracts: information time, generated features and path arithmetic."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MODULE = Path(__file__).resolve().parents[1] / 'models/food_transmission_r17.py'


def implementation():
    assert MODULE.exists(), 'R17 food implementation has not been written'
    from models import food_transmission_r17
    return food_transmission_r17


def panel():
    index = pd.period_range('2015-01', '2024-12', freq='M')
    k = np.arange(len(index), dtype=float)
    rates = np.column_stack([np.sin(k) + .1, np.cos(k) * .5, .2 + .4 * np.sin(2*np.pi*k/12) + .1*np.cos(k)])
    levels = pd.DataFrame(rates.cumsum(axis=0), index=index, columns=['agri4', 'food_ppi', 'food'])
    availability = pd.DataFrame({c: [(m+1).start_time.tz_localize('Europe/Prague').isoformat() for m in index] for c in levels})
    availability.index = index
    return levels, availability


def snapshots(end='2021-12'):
    model = implementation(); levels, availability = panel()
    saved = {str(t): model.snapshot(levels, availability, t, (t+1).start_time.tz_localize('Europe/Prague'))
             for t in pd.period_range('2016-02', end, freq='M')}
    return levels, availability, saved


def test_signed_window_decomposition_is_before_averaging():
    model = implementation()
    result = model.lag_summary(np.array([3., -2., 1., -4., 2., -1.]))
    assert result['symmetric'] == pytest.approx([2/3, -1.])
    assert result['positive'] == pytest.approx([4/3, 2/3])
    assert result['negative'] == pytest.approx([-2/3, -5/3])
    assert np.array(result['positive']) + result['negative'] == pytest.approx(result['symmetric'])


def test_endpoint_release_gate_masks_difference_even_when_newer_endpoint_released():
    model = implementation(); levels, availability = panel()
    availability.loc[pd.Period('2018-11'), 'agri4'] = '2030-01-01T00:00:00+01:00'
    rates = model.released_rates(levels, availability, '2019-01', '2019-02-01T00:00:00+01:00')
    assert np.isnan(rates.loc['2018-12', 'agri4'])
    assert np.isnan(rates.loc['2018-11', 'agri4'])
    assert rates.index.max() == pd.Period('2018-12')
    assert rates.iloc[0].isna().all()


def test_snapshot_is_invariant_to_future_and_unreleased_values():
    model = implementation(); levels, availability = panel()
    availability.loc[pd.Period('2018-11'), 'agri4'] = '2030-01-01T00:00:00+01:00'
    a = model.snapshot(levels, availability, '2019-01', '2019-02-01T00:00:00+01:00')
    changed = levels.copy(); changed.loc[changed.index >= pd.Period('2019-01')] += 1e8
    changed.loc[pd.Period('2018-11'), 'agri4'] = -1e12
    b = model.snapshot(changed, availability, '2019-01', '2019-02-01T00:00:00+01:00')
    assert a['seasonal'] == b['seasonal']
    np.testing.assert_allclose(a['features'], b['features'], equal_nan=True)
    assert a['seasonal_dates'] == b['seasonal_dates']


def test_missing_contiguous_lag_is_not_collapsed_or_filled():
    model = implementation(); levels, availability = panel()
    with pytest.raises(ValueError, match='Contiguous'):
        model.snapshot(levels.drop(pd.Period('2018-11')), availability, '2019-01', '2019-02-01T00:00:00+01:00')
    availability.loc[pd.Period('2018-11'), 'food_ppi'] = None
    result = model.snapshot(levels, availability, '2019-01', '2019-02-01T00:00:00+01:00')
    assert np.isnan(result['features'][4])
    assert result['lag_audit']['food_ppi'][1]['status'] == 'unavailable'


def test_seasonal_and_persistence_use_only_own_origin_history():
    model = implementation(); levels, availability = panel()
    result = model.snapshot(levels, availability, '2019-01', '2019-02-01T00:00:00+01:00')
    rates = levels.loc[:'2018-12', 'food'].diff()
    means = rates.groupby(rates.index.month).mean()
    assert result['seasonal'] == pytest.approx(means.to_list())
    own3 = np.mean([rates.loc[m] - means.loc[m.month] for m in pd.period_range('2018-10', '2018-12', freq='M')])
    assert result['features'][1] == pytest.approx(own3)
    assert model.control_paths(result)['FOOD_PERSISTENCE_R17'][0] == pytest.approx(means.loc[2] + own3)


def test_training_labels_require_reference_and_endpoint_publication_maturity():
    model = implementation(); levels, availability, saved = snapshots()
    availability.loc[pd.Period('2021-10'), 'food'] = '2030-01-01T00:00:00+01:00'
    x, y, audit = model.training_data(saved, levels, availability, '2022-01', '2022-02-01T00:00:00+01:00', 12, 'own')
    assert len(x) == len(y) == len(audit)
    assert all(pd.Period(row['target']) < pd.Period('2022-01') for row in audit)
    assert not {'2021-10', '2021-11'} & {r['target'] for r in audit}
    first = audit[0]; source = saved[first['origin']]
    target = pd.Period(first['target'])
    assert y[0] == pytest.approx(levels.food.diff().loc[target] - source['seasonal'][target.month-1])
    np.testing.assert_array_equal(x[0], source['features'][:2])


def test_ridge_scaling_is_training_only_and_future_feature_cannot_affect_fit():
    model = implementation(); x = np.array([[1., 2.], [3., 4.], [5., 6.]])
    y = np.array([1., 0., 2.])
    result = model.ridge_fit(x, y, np.array([.1, .1]))
    assert result['scale'] == pytest.approx(np.sqrt(np.mean(x*x, axis=0)))
    z = x / result['scale']; beta = np.linalg.solve(z.T@z/3 + np.eye(2)*.1, z.T@y/3)
    assert result['coefficients'] == pytest.approx(beta)


def test_early_fit_has_visible_persistence_fallback_and_no_origin_loss():
    model = implementation(); levels, availability, saved = snapshots('2016-02')
    result = model.forecast_origin(saved, levels, availability, '2016-02', '2016-03-01T00:00:00+01:00', [])
    assert set(result['paths']) == set(model.MODELS)
    assert all(len(path) == 12 for path in result['paths'].values())
    np.testing.assert_array_equal(result['paths']['FOOD_ASYMMETRIC_R17'], result['paths']['FOOD_PERSISTENCE_R17'])
    assert all(r['status'] == 'fallback_persistence' for r in result['fits'])
    assert all(r['reason'] == 'insufficient_training_rows' for r in result['fits'])


def test_forecast_and_coefficients_are_invariant_to_unmatured_outcomes():
    model = implementation(); levels, availability, saved = snapshots('2021-01')
    a = model.forecast_origin(saved, levels, availability, '2021-01', '2021-02-01T00:00:00+01:00', [])
    poison = levels.copy(); poison.loc[poison.index >= pd.Period('2021-01')] = 9e9
    b = model.forecast_origin(saved, poison, availability, '2021-01', '2021-02-01T00:00:00+01:00', [])
    for name in model.MODELS:
        np.testing.assert_array_equal(a['paths'][name], b['paths'][name])
    assert a['fits'] == b['fits']


def test_lambda_selector_never_uses_incomplete_path_or_future_labels():
    model = implementation(); levels, availability = panel(); history = []
    truth = levels.food.diff()
    for origin in pd.period_range('2018-01', '2021-12', freq='M'):
        for penalty in model.LAMBDAS:
            values = [float(truth.loc[origin+h]) + (0 if penalty == 10 else 1) for h in range(1, 13)]
            history.append(dict(origin=str(origin), family='asymmetric', penalty=penalty, log_rates=values, all_estimated=True))
    result = model.select_penalty(history, levels, availability, '2021-01', '2021-02-01T00:00:00+01:00', 'asymmetric')
    assert result['penalty'] == 10
    assert all(pd.Period(s)+12 < pd.Period('2021-01') for s in result['validation_origins'])
    mutated = levels.copy(); mutated.loc[mutated.index >= pd.Period('2021-01')] = 1e6
    assert result == model.select_penalty(history, mutated, availability, '2021-01', '2021-02-01T00:00:00+01:00', 'asymmetric')


def test_half_correction_and_percent_compounding_are_exact():
    model = implementation(); levels, availability, saved = snapshots('2021-01')
    result = model.forecast_origin(saved, levels, availability, '2021-01', '2021-02-01T00:00:00+01:00', [])
    half = result['paths']['FOOD_HALF_CORRECTION_R17']; asymmetric = result['paths']['FOOD_ASYMMETRIC_R17']; persistence = result['paths']['FOOD_PERSISTENCE_R17']
    np.testing.assert_allclose(half, (asymmetric+persistence)/2, rtol=0, atol=1e-15)
    mm = model.to_monthly_percent(half)
    assert 100*(np.prod(1+mm/100)-1) == pytest.approx(100*np.expm1(half.sum()/100), abs=1e-12)


def test_native_replacement_keeps_h0_nonfood_and_complete_sum():
    model = implementation()
    frame = pd.DataFrame({'h': [0, 1, 2], 'mm_forecast': [.2, .3, .4], 'value_food': [np.nan, 1., 2.], 'weight_food': [.2]*3,
                          'contribution_food': [np.nan, .2, .4]})
    for name in ['core', 'administered', 'alcohol_tobacco', 'fuel', 'wedge']:
        frame['contribution_'+name] = [np.nan, .01, .02]
    before = frame.copy(); result = model.replace_food(frame, {1: 2., 2: 3.})
    assert result.mm_forecast.iloc[0] == before.mm_forecast.iloc[0]
    assert result.mm_forecast.iloc[1] == pytest.approx(.45)
    pd.testing.assert_frame_equal(result[[c for c in frame if c not in ['value_food','contribution_food','mm_forecast']]], before[[c for c in frame if c not in ['value_food','contribution_food','mm_forecast']]], check_exact=True)
    frame.loc[1, 'contribution_core'] = np.nan
    assert np.isnan(model.replace_food(frame, {1: 2.}).mm_forecast.iloc[1])


def runner():
    path = MODULE.parents[1] / 'food_transmission_experiment_r17.py'
    assert path.exists(), 'R17 food runner has not been written'
    import food_transmission_experiment_r17
    return food_transmission_experiment_r17


def test_runner_annual_window_retains_h0_and_h12_excludes_it():
    module = runner()
    history = pd.Series(.1, index=pd.period_range('2019-01', '2019-12', freq='M'))
    path = {h: .2 for h in range(13)}; path[0] = 4.
    assert module.compound_path(history, path, '2020-01', 1, path[0]) == pytest.approx(100*((1.001**10)*1.04*1.002-1))
    assert module.compound_path(history, path, '2020-01', 12, path[0]) == pytest.approx(100*(1.002**12-1))
    path[3] = np.nan
    assert np.isnan(module.compound_path(history, path, '2020-01', 12, path[0]))


def test_runner_rejects_existing_destination_and_changed_manifest(tmp_path):
    module = runner()
    with pytest.raises(FileExistsError):
        module.run(tmp_path)
    source = tmp_path / 'source.csv'; source.write_text('hello')
    manifest = tmp_path / 'manifest.json'; manifest.write_text('{"inputs":{"source.csv":"wrong"},"outputs":{}}')
    with pytest.raises(ValueError, match='hash changed'):
        module.verify_manifest(tmp_path, manifest)


def test_own_and_cost_training_use_identical_upstream_complete_calendar():
    model = implementation(); levels, availability, saved = snapshots()
    saved['2018-03']['features'][6] = np.nan
    audits = [model.training_data(saved, levels, availability, '2022-01', '2022-02-01T00:00:00+01:00', 3, family)[2] for family in model.FEATURE_COLUMNS]
    assert audits[0] == audits[1] == audits[2]
    assert '2018-03' not in [r['origin'] for r in audits[0]]


def test_runner_component_scores_never_hide_missing_candidate_months():
    module = runner()
    rows = []
    for name, forecast in [('STATE_FAST_R15', [1., 1.]), ('FOOD_OWN_R17', [1., np.nan])]:
        for h, value in enumerate(forecast, 1):
            rows.append(dict(origin='2020-01', target=f'2020-0{h+1}', model=name, h=h,
                             mm_forecast=value, mm_actual=.2, cumulative_log_forecast=value,
                             cumulative_log_actual=.2, cumulative_pct_forecast=value,
                             cumulative_pct_actual=.2, status='estimated'))
    scores = module.component_scores(pd.DataFrame(rows))
    primary = scores[(scores.scope == 'primary_control_calendar') & (scores.model == 'FOOD_OWN_R17') & (scores.h == 2) & (scores['sample'] == 'full') & (scores.metric == 'mm')].iloc[0]
    assert primary.n_intended == 1 and primary.n_missing_forecast == 1 and primary.n_scored == 0


def test_missing_any_calendar_season_disables_the_entire_declared_path():
    model = implementation(); levels, availability = panel()
    state = model.snapshot(levels, availability, '2015-08', '2015-09-01T00:00:00+02:00')
    assert state['status'] == 'unavailable_seasonality'
    for values in model.control_paths(state).values():
        assert np.isnan(values).all()
