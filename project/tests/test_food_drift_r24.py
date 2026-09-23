import numpy as np
import pandas as pd
import pytest

import r17_common as c
from models.food_stable_r14b import forecast_origin, MODELS as BASELINE_MODELS
from models.food_path_r14 import load_inputs
from models.food_drift_r24 import (MODELS, median_annual_drift, decompose, long_food_rates, refit_forecast, candidates_at, LONG_HISTORY)


def synthetic_history():
    ix = pd.period_range('1996-01', '2024-12', freq='M')
    rates = pd.Series(.2, index=ix); rates.loc['2022-01':'2022-12'] = 2.
    published = pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=9, hours=9), index=ix).dt.tz_localize('Europe/Prague')
    return rates, published


def test_median_drift_ignores_one_extreme_year_and_every_unpublished_month():
    rates, published = synthetic_history(); clock = pd.Timestamp('2024-07-09 23:59', tz='Europe/Prague')
    assert median_annual_drift(rates, published, clock) == pytest.approx(.2)
    assert rates.loc[:'2024-05'].mean() > .25                                     # the window mean is what the surge contaminates
    poisoned = rates.copy(); poisoned.loc[published > clock] = 1e9
    assert median_annual_drift(poisoned, published, clock) == median_annual_drift(rates, published, clock)
    recent = pd.period_range('2019-01', '2024-05', freq='M')                      # a window where the surge is a fifth of the months
    assert median_annual_drift(rates, published, clock, allowed=recent) == pytest.approx(.2)
    assert np.isnan(median_annual_drift(rates, published, clock, allowed=recent[:13]))   # too few complete years to call a median
    holed = rates.copy(); holed.loc['2010-06'] = np.nan
    assert median_annual_drift(holed, published, clock) == pytest.approx(.2)     # windows across a hole are dropped, not bridged


def test_centre_decomposition_is_exact_and_the_shape_sums_to_zero():
    means = np.array([.9, .1, -.2, .3, .4, .0, -.5, .2, .1, .6, -.1, .2])
    mu, shape = decompose(means)
    assert mu == pytest.approx(means.mean()) and shape.sum() == pytest.approx(0., abs=1e-14)
    np.testing.assert_allclose(mu + shape, means, atol=1e-15)


@pytest.fixture(scope='module')
def real():
    levels, available, _ = load_inputs()
    rates, published = long_food_rates(levels, available, c.ROOT / LONG_HISTORY)
    return levels, available, rates, published


def test_long_history_splices_exactly_onto_the_model_series(real):
    levels, available, rates, published = real
    assert rates.index.min() == pd.Period('1995-02', 'M') and rates.index.is_monotonic_increasing and rates.index.is_unique
    own = levels.food.diff().dropna()
    np.testing.assert_allclose(rates.reindex(own.index), own, atol=0, rtol=0)     # from 2015-02 it IS the model's series
    assert rates.loc['2005-01':'2014-12'].notna().all() and published.notna().all()
    assert (published.loc[own.index] == pd.to_datetime(available.food.reindex(own.index), utc=True)).all()


@pytest.mark.parametrize('origin,clock', [('2019-02', '2019-03-10T23:59:00+01:00'), ('2024-06', '2024-07-09T23:59:00+02:00')])
def test_refit_routine_reproduces_the_frozen_baseline_under_its_own_centre(real, origin, clock):
    levels, available, _, _ = real
    frozen = forecast_origin(levels, available, origin, pd.Timestamp(clock))
    again = refit_forecast(levels, available, origin, pd.Timestamp(clock), shift=0.)
    np.testing.assert_allclose(again['log_rates'], frozen['forecast_food_rates'][BASELINE_MODELS[0]], atol=1e-12, rtol=0)
    moved = refit_forecast(levels, available, origin, pd.Timestamp(clock), shift=-.2)
    assert not np.allclose(moved['log_rates'], again['log_rates'])


def test_shift_candidates_differ_from_the_baseline_by_exactly_their_constant(real):
    levels, available, rates, published = real; clock = pd.Timestamp('2024-07-09T23:59:00+02:00')
    out = candidates_at(levels, available, rates, published, '2024-06', clock)
    assert out['status'] == 'estimated' and set(out['log_rates']) == set(MODELS)
    base = np.array(out['baseline_log_rates']); d = out['drifts']
    assert d['mu_window'] > d['mu_long'] > 0 and d['mu_window'] > d['mu_robust']          # the 2016-2024 window mean carries the 2022 surge
    for name, constant in [('FOOD_ZERO_DRIFT_R24', -d['mu_window']), ('FOOD_ROBUST_WINDOW_R24', d['mu_robust'] - d['mu_window']),
                           ('FOOD_NORM_SHIFT_R24', d['mu_long'] - d['mu_window'])]:
        np.testing.assert_allclose(np.array(out['log_rates'][name]) - base, constant, atol=1e-12)
        np.testing.assert_allclose([out['paths'][name][h] for h in range(1, 13)], 100 * np.expm1(np.array(out['log_rates'][name]) / 100), atol=1e-12)
    assert len(out['log_rates']['FOOD_NORM_REFIT_R24']) == 12 and np.isfinite(out['log_rates']['FOOD_NORM_REFIT_R24']).all()
    later = candidates_at(levels, available, rates.where(published <= clock), published, '2024-06', clock)
    assert later['drifts'] == out['drifts']                                                 # nothing unpublished entered a drift


def test_food_replacement_leaves_h0_other_blocks_and_weights_untouched():
    native = c.read('output/research_r21/path_anchor/native_forecasts.csv')
    base = native[native.model.eq('STATE_FAST_R15') & native.origin.eq('2024-06')].sort_values('h')
    changed = c.replace_block(base, 'food', {h: 1.5 for h in range(1, 13)})
    fixed = [col for col in base if col.startswith('weight_') or (col.startswith(('value_', 'contribution_')) and not col.endswith('_food'))]
    pd.testing.assert_frame_equal(changed[fixed], base[fixed], check_exact=True)
    assert changed.loc[changed.h.eq(0), 'mm_forecast'].iloc[0] == base.loc[base.h.eq(0), 'mm_forecast'].iloc[0]
    future = changed.h.gt(0)
    np.testing.assert_allclose(changed.loc[future, 'mm_forecast'] - base.loc[future, 'mm_forecast'],
                               base.loc[future, 'weight_food'] * (1.5 - base.loc[future, 'value_food']), atol=1e-14)


# --- Added after the independent R24 review: five mutants survived the first seven tests. Each test below kills one. ---

def test_log_rate_slices_are_aligned_with_horizons_one_to_twelve(real):
    levels, available, rates, published = real; clock = pd.Timestamp('2024-07-09T23:59:00+02:00')
    out = candidates_at(levels, available, rates, published, '2024-06', clock)
    frozen = forecast_origin(levels, available, '2024-06', clock)
    assert len(out['baseline_log_rates']) == 12
    np.testing.assert_allclose(100 * np.expm1(np.array(out['baseline_log_rates']) / 100), [frozen['paths'][BASELINE_MODELS[0]][h] for h in range(1, 13)], atol=1e-12)
    np.testing.assert_allclose(out['baseline_log_rates'], frozen['forecast_food_rates'][BASELINE_MODELS[0]][1:13], atol=0, rtol=0)   # index 0 is the origin month
    refit = refit_forecast(levels, available, '2024-06', clock, shift=out['drifts']['mu_long'] - out['drifts']['mu_window'])
    np.testing.assert_allclose(out['log_rates']['FOOD_NORM_REFIT_R24'], refit['log_rates'][1:13], atol=0, rtol=0)


def test_robust_window_drift_is_confined_to_the_training_window(real):
    levels, available, rates, published = real; clock = pd.Timestamp('2024-07-09T23:59:00+02:00')
    out = candidates_at(levels, available, rates, published, '2024-06', clock)
    window = forecast_origin(levels, available, '2024-06', clock)['fits'][0]['training_dates']
    assert out['drifts']['mu_robust'] == median_annual_drift(rates, published, clock, allowed=window)
    assert out['drifts']['mu_robust'] != out['drifts']['mu_long']
    inside = rates.loc[window[0]:window[-1]].rolling(12).sum().dropna()
    assert out['drifts']['mu_robust'] == pytest.approx(float(inside.median() / 12))


def test_a_lower_food_centre_lowers_the_long_horizon_forecast_by_about_the_shift(real):
    levels, available, _, _ = real; clock = pd.Timestamp('2024-07-09T23:59:00+02:00')
    base = np.array(refit_forecast(levels, available, '2024-06', clock, shift=0.)['log_rates'])
    lower = np.array(refit_forecast(levels, available, '2024-06', clock, shift=-.2)['log_rates'])
    assert (lower[7:] < base[7:]).all() and -.3 < (lower[12] - base[12]) < -.1


def test_long_history_starts_in_1996_and_the_first_origin_value_is_pinned(real):
    from models.food_drift_r24 import LONG_START
    levels, available, rates, published = real; clock = pd.Timestamp('2019-03-10T23:59:00+01:00')
    assert LONG_START == pd.Period('1996-01', 'M')
    own = rates.loc['1996-01':'2019-01'].rolling(12).sum().dropna()              # food for January 2019 is the last month published by this clock
    assert median_annual_drift(rates, published, clock) == pytest.approx(float(own.median() / 12))
    assert 12 * median_annual_drift(rates, published, clock) == pytest.approx(2.5587407, abs=1e-6)
    assert abs(12 * median_annual_drift(rates, published, clock, start=pd.Period('2005-01', 'M')) - 2.5587407) > .05


def test_window_drift_is_the_food_centre_only(real):
    levels, available, rates, published = real; clock = pd.Timestamp('2024-07-09T23:59:00+02:00')
    fit = forecast_origin(levels, available, '2024-06', clock)['fits'][0]; means = np.asarray(fit['seasonal_means'])
    out = candidates_at(levels, available, rates, published, '2024-06', clock)
    assert out['drifts']['mu_window'] == pytest.approx(means[:, fit['columns'].index('food')].mean())
    assert abs(out['drifts']['mu_window'] - means.mean()) > 1e-3
