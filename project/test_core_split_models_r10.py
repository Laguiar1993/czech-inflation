"""Economic identities and information-set invariance for the R10 experiment."""
import importlib

import numpy as np
import pandas as pd
import pytest


def module():
    return importlib.import_module('models.core_split')


def synthetic():
    ix = pd.period_range('2007-01', periods=180, freq='M')
    rng = np.random.default_rng(82)
    core = pd.Series(.2 + rng.normal(0, .2, len(ix)), index=ix)
    cats = pd.DataFrame(rng.normal(.2, .4, (len(ix), 5)), index=ix,
                        columns=['actual_rent', 'imputed_rent', 'catering', 'accommodation', 'package_holidays'])
    broad = pd.DataFrame({'goods': 2 + np.cumsum(rng.normal(0, .12, len(ix))),
                          'services': 3 + np.cumsum(rng.normal(0, .1, len(ix)))}, index=ix)
    x = pd.DataFrame({'eurczk_mm': rng.normal(size=len(ix)), 'import_l2': rng.normal(size=len(ix)),
                      'state': (np.arange(len(ix)) % 2).astype(float), 'services_l1': rng.normal(size=len(ix)),
                      'exp12': rng.normal(size=len(ix)), 'esi': rng.normal(size=len(ix))}, index=ix)
    x['core_l1'] = core.shift(1)
    food = pd.DataFrame({'food_l1': rng.normal(size=len(ix)), 'food_ppi_l1': rng.normal(size=len(ix))}, index=ix)
    available = pd.Series([(p+1).to_timestamp() + pd.Timedelta(days=10, hours=9) for p in ix], index=ix)
    origin = ix[-6]
    clock = (origin+1).to_timestamp() + pd.Timedelta(days=3)
    weights = pd.Series([.035, .11, .06, .008, .02], index=cats.columns)
    return core, cats, broad, x, food, available, origin, clock, weights


def test_log_annual_change_restores_monthly_rate_exactly():
    m = module()
    core, *_ = synthetic()
    annual = 100 * (np.expm1(np.log1p(core / 100).rolling(12).sum()))
    delta = m.annual_log_change(annual)
    recovered = m.monthly_from_annual_change(delta, core.shift(12))
    np.testing.assert_allclose(recovered.dropna(), core.reindex(recovered.dropna().index), atol=2e-13)
    with pytest.raises(ValueError):
        m.annual_log_change(pd.Series([-100., 0.]))


def test_projection_is_past_only_constrained_and_preserves_residual():
    m = module()
    core, cats, broad, x, food, dates, t, clock, w = synthetic()
    dy = 100 * np.log1p(core / 100).diff(12)
    bd = broad.apply(m.annual_log_change)
    coefficient, residual, info = m.past_projection(dy, bd, t, clock, dates)
    assert 0 <= coefficient <= 1
    assert info['projection_n'] == 60
    assert info['projection_end'] < t
    check = coefficient * bd.goods + (1-coefficient) * bd.services + residual
    np.testing.assert_allclose(check.dropna(), dy.reindex(check.dropna().index), atol=1e-12)
    poisoned = bd.copy()
    poisoned.loc[t:] = 1e8
    c2, _, _ = m.past_projection(dy, poisoned, t, clock, dates)
    assert coefficient == c2


def test_identical_design_split_commutes_with_aggregate_ridge():
    m = module()
    args = synthetic()
    result = m.forecast_origin(*args, core_weight=.55)
    assert result['predictions']['TARGET_SHARED'] == pytest.approx(result['predictions']['AGG_COMMON'], abs=2e-12)
    assert result['checks']['max_target_reconciliation_error'] < 1e-12
    for variant in ('TARGET_OWN', 'TARGET_CHANNEL'):
        rows = [r for r in result['contributions'] if r['model'] == variant]
        assert len(rows) == 6
        assert sum(r['contribution'] for r in rows) == pytest.approx(.55 * result['predictions'][variant], abs=1e-12)


def test_broad_split_and_aggregate_control_share_training_label_calendar():
    result = module().forecast_origin(*synthetic(), core_weight=.55)
    fits = [r for r in result['fits'] if r['model'] in ('BROAD_SPLIT', 'BROAD_AGG_CONTROL')]
    assert len(fits) == 4
    assert len({(r['n_train'], r['train_start'], r['train_end']) for r in fits}) == 1


def test_future_outcomes_and_expectations_cannot_change_predictions():
    m = module()
    args = list(synthetic())
    expected = m.forecast_origin(*args, core_weight=.55)['predictions']
    t = args[6]
    for i in (0, 1, 2):
        args[i] = args[i].copy()
        args[i].loc[t:] = 999.
    args[3] = args[3].copy()
    args[3].loc[:, ['exp12', 'esi']] = 1e15
    actual = m.forecast_origin(*args, core_weight=.55)['predictions']
    assert expected.keys() == actual.keys()
    np.testing.assert_allclose(list(expected.values()), list(actual.values()), atol=1e-12)


def test_unpublished_previous_category_observation_fails_closed():
    m = module()
    args = list(synthetic())
    args[5] = args[5].copy()
    args[5].loc[args[6]-1] = args[7] + pd.Timedelta(days=10)
    result = m.forecast_origin(*args, core_weight=.55)
    assert np.isnan(result['predictions']['TARGET_OWN'])
    assert 'previous_target_unavailable' in {r['fit_status'] for r in result['fits']}


def test_easter_exposure_is_known_and_conserves_nine_days():
    m = module()
    ix = pd.period_range('2000-01', '2035-12', freq='M')
    e = m.easter_exposure(ix)
    np.testing.assert_allclose(e.groupby(e.index.year).sum(), 1.)
    assert e.loc['2024-03'] == pytest.approx(8/9)
    assert e.loc['2024-04'] == pytest.approx(1/9)
