"""Tests added after the independent R23B review: 19 behaviour-changing mutants survived the first suite.

Each test below pins one declared behaviour of R23B or of tools/path_diagnostics with an expectation computed by
hand, not by the rule under test. The modules themselves are unchanged (their hashes are inputs of sealed runs).
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import r17_common as c
import models.cost_pressure_r23b as m
from data.cost_pressure_r23b import features_at, COLUMNS
from models.cost_pressure_r23b import fit, eligible, choose, run_origin, GRID
from tools.path_diagnostics.gates import needed_vs_applied
from tools.path_diagnostics.attribution import monthly_block_errors, quarter_attribution, call_attribution
from tools.path_diagnostics.benchmarks import seasonal_naive_path
from tools.path_diagnostics.lead_baselines import baseline_projections

SEASON = {i: 0. for i in range(1, 13)}


def inputs(ulc):
    ix = pd.period_range('2000-01', periods=180, freq='M'); q = pd.period_range('2000Q1', periods=60, freq='Q')
    pub = pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=10), index=ix)
    qa = pd.Series(q.to_timestamp(how='end').normalize() + pd.Timedelta(days=75), index=q)
    raw = {11: SimpleNamespace(values=pd.Series(5., index=ix), available=pub.copy()), 17: SimpleNamespace(values=pd.Series(ulc, index=q), available=qa.copy()),
           26: SimpleNamespace(values=pd.Series(.5, index=ix), available=pub.copy()),
           47: SimpleNamespace(values=pd.Series(np.exp(np.arange(180) * .004) * 100, index=ix), available=pub.copy())}
    return pd.Series(.2, index=ix), pub, raw, pd.Series(25., index=ix)


def test_ulc_gap_uses_the_median_of_the_three_earlier_same_quarters():
    ulc = 100 * np.exp(.012 * np.arange(60)); ulc[27] *= np.exp(.30)                 # 2006Q4, twelve quarters before the reference, is an outlier
    core, pub, raw, fx = inputs(ulc)
    values, audit = features_at(core, pub, raw, fx, pd.Period('2010-03', 'M'), pd.Timestamp('2010-04-10'), SEASON)
    assert next(r for r in audit if r['feature'] == 'ulc_sameq')['reference'] == '2009Q4'
    step = 100 * 4 * .012 - 12 * 100 * np.log1p(.002)                              # real ULC growth over four quarters
    # Earlier same quarters sit 1, 2 and 3 steps below the reference, the last one lifted by 30: sorted, the middle one is 1 step below.
    assert values.ulc_sameq == pytest.approx(step) and abs(values.ulc_sameq - (2 * step - 10)) > 5      # a mean would give 2 steps - 10


def test_ulc_reference_is_never_the_unfinished_quarter_even_if_it_is_published():
    core, pub, raw, fx = inputs(100 * np.exp(.012 * np.arange(60)))
    raw[17].available.loc['2010Q1'] = pd.Timestamp('2010-01-02')                   # a leak: the running quarter stamped as public
    _, audit = features_at(core, pub, raw, fx, pd.Period('2010-02', 'M'), pd.Timestamp('2010-03-10'), SEASON)
    assert next(r for r in audit if r['feature'] == 'ulc_sameq')['reference'] == '2009Q3'   # 2009Q4 is published on 16 March, after this clock


def labels(late=()):
    ix = pd.period_range('2000Q1', periods=80, freq='Q').asfreq('M', 'end')
    x = pd.DataFrame({k: np.sin(np.arange(80) / 5 + i) for i, k in enumerate(COLUMNS)}, index=ix)
    y = pd.DataFrame({1: x[COLUMNS[0]] / 10, 2: x[COLUMNS[0]] / 20})
    a = pd.DataFrame({b: (ix + 3 * b + 1).to_timestamp() + pd.Timedelta(days=12) for b in (1, 2)}, index=ix)
    for key, stamp in late:
        a.loc[key, 1] = pd.Timestamp(stamp)
    return x, y, a, pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=5), index=ix)


def test_a_label_ending_in_the_origin_month_is_not_mature_whatever_the_clock_says():
    x, y, a, _ = labels(); t = pd.Period('2015-12', 'M')
    keys = eligible(x, y, a, t, pd.Timestamp('2016-06-01'), 1, 24)                 # a generous clock: only the month rule can exclude 2015-09
    assert keys[-1] == pd.Period('2015-06', 'M') and pd.Period('2015-09', 'M') not in keys


def test_a_label_released_after_the_clock_is_not_used_even_if_its_months_have_passed():
    x, y, a, _ = labels(late=[('2015-09', '2016-03-01')]); t = pd.Period('2016-01', 'M')
    keys = eligible(x, y, a, t, pd.Timestamp('2016-02-05'), 1, 24)
    assert pd.Period('2015-09', 'M') not in keys and keys[-1] == pd.Period('2015-06', 'M')


def test_validation_uses_the_latest_eight_folds_each_with_sixteen_matured_rows_at_its_own_clock():
    x, y, a, clocks = labels(late=[('2012-03', '2015-08-20')]); t = pd.Period('2016-01', 'M'); clock = pd.Timestamp('2016-02-05')
    out = choose(x, y, a, clocks, t, clock, 1, [COLUMNS[0]], 'ridge'); audit = pd.DataFrame(out['validation'])
    outer = eligible(x, y, a, t, clock, 1, 24)
    assert sorted(audit.validation_origin.unique()) == [str(k) for k in outer[-8:]]                # the latest eight, not the earliest
    assert (audit.n_train >= 16).all()
    # 2012-03's label was released on 20 August 2015: folds whose own clock is earlier must not have trained on it
    for v, g in audit.groupby('validation_origin'):
        inner = eligible(x, y, a, pd.Period(v, 'M'), clocks.loc[pd.Period(v, 'M')], 1, 16)
        assert (pd.Period('2012-03', 'M') in inner) == (clocks.loc[pd.Period(v, 'M')] >= pd.Timestamp('2015-08-20'))
        assert g.n_train.iloc[0] == len(inner)


def test_fewer_than_four_folds_means_no_correction():
    x, y, a, clocks = labels(); a.loc[a.index <= pd.Period('2014-12', 'M'), 1] = pd.Timestamp('2015-12-20')   # a mass late release
    t = pd.Period('2016-04', 'M'); clock = pd.Timestamp('2016-05-05')
    assert len(eligible(x, y, a, t, clock, 1, 24)) >= 24
    capable = [v for v in eligible(x, y, a, t, clock, 1, 24) if len(eligible(x, y, a, v, clocks.loc[v], 1, 16))]
    assert 0 < len(capable) < 4
    out = choose(x, y, a, clocks, t, clock, 1, [COLUMNS[0]], 'ridge')
    assert out['alpha'] is None and out['status'] == 'no_correction_insufficient_validation'


def test_ties_between_penalties_go_to_the_stronger_one(monkeypatch):
    x, y, a, clocks = labels(); y = y * 0 + .1
    monkeypatch.setattr(m, 'fit', lambda *args, **kwargs: dict(prediction=.05))    # every penalty predicts the same, and better than none
    out = choose(x, y, a, clocks, pd.Period('2016-01', 'M'), pd.Timestamp('2016-02-05'), 1, [COLUMNS[0]], 'ridge')
    assert len(set(out['scores'].values())) == 1 and out['scores'][str(GRID[0])] < out['zero_loss'] and out['alpha'] == max(GRID)


def test_an_unvalidated_band_adds_nothing_to_the_path_although_its_diagnostic_fit_is_kept(monkeypatch):
    x, y, a, clocks = labels()
    monkeypatch.setattr(m, 'choose', lambda *args, **kwargs: dict(alpha=None, status='no_correction_validated', scores={}, zero_loss=0., validation=[]))
    out = run_origin(x, y, a, clocks, pd.Period('2016-03', 'M'), pd.Timestamp('2016-04-05'))
    for name, path in out['paths'].items():
        np.testing.assert_allclose(path, 0., atol=1e-15)
        assert abs(out['fits'][name]['1']['prediction']) > 1e-6 and out['fits'][name]['1']['applied'] is False


def test_estimator_is_mean_squared_error_ridge_on_root_mean_square_scaled_predictors():
    rng = np.random.default_rng(11); x = pd.DataFrame({'a': 3 + rng.normal(size=30), 'b': rng.normal(size=30)}); y = rng.normal(size=30)
    now = pd.Series({'a': 2., 'b': -1.}); alpha = 3.; out = fit(x, y, now, alpha, 'ridge')
    rms = np.sqrt((x ** 2).mean()); z = (x / rms).to_numpy(); n = len(y)
    beta = np.linalg.solve(z.T @ z / n + alpha * np.eye(2), z.T @ y / n)           # the declared objective, written out
    np.testing.assert_allclose(out['coefficients'], beta, atol=1e-12); assert out['scale'] == pytest.approx(rms.to_dict())
    assert out['prediction'] == pytest.approx(float((now / rms).to_numpy() @ beta))
    assert abs(rms['a'] - x.a.std(ddof=0)) > 1 and not np.allclose(beta, np.linalg.solve(z.T @ z + alpha * np.eye(2), z.T @ y))


def block_native():
    weights = dict(weight_core=.5, weight_food=.2, weight_fuel=.05, weight_administered=.15, weight_alc=.1); rows = []
    for origin in ['2020-02', '2020-03']:
        for h in range(13):
            values = dict(value_core=.2, value_food=.3, value_fuel=0., value_administered=.1, value_alcohol_tobacco=.2)
            rows.append(dict(origin=origin, model='M', h=h, target=str(pd.Period(origin, 'M') + h), mm_forecast=.9 if h == 0 else .2, mm_actual=.25,
                             as_of_utc='2020-03-09T22:59:00+00:00', **weights, **values))
    ix = pd.period_range('2015-01', '2021-12', freq='M')
    return pd.DataFrame(rows), pd.DataFrame(dict(core=.15, food=.5, fuel=1., administered=.1, alcohol_tobacco=.2), index=ix)


def test_quarter_attribution_counts_known_months_as_zero_and_drops_h0_at_h12():
    native, actual = block_native(); monthly = monthly_block_errors(native, actual); h0 = .9 - .25; food = .2 * (.3 - .5)
    early = quarter_attribution(monthly, 'M', '2020-02', '2020Q1')                 # January is history, February is h0, March is h1
    assert early['c_food'] == pytest.approx((0 + 0 + food) / 3) and early['c_h0'] == pytest.approx((0 + h0 + h0) / 3)
    late = quarter_attribution(monthly, 'M', '2020-03', '2021Q1')                  # January h10, February h11, March h12
    assert late['c_h0'] == pytest.approx((h0 + h0 + 0) / 3)                        # at h12 the nowcast month has left the twelve-month window
    assert late['c_food'] == pytest.approx(food * (10 + 11 + 12) / 3)


def test_dominant_block_is_the_largest_push_in_the_direction_of_the_error():
    months = pd.DataFrame(dict(origin='2020-01', model='M', h=range(13), target=[str(pd.Period('2020-01', 'M') + h) for h in range(13)],
                               c_h0=0., c_core=-.5, c_food=.3, c_fuel=.1, c_administered=0., c_alcohol_tobacco=0., c_wedge=0.))
    calls = pd.DataFrame(dict(model=['M'], clock=['report'], report_date=['d'], quarter=['2020Q3'], forecast=[3.], realised=[2.5], deviation=[.4]))
    clocks = pd.DataFrame(dict(clock=['report'], report_date=['d'], origin=['2020-01']))
    assert call_attribution(calls, clocks, months).dominant_block.iloc[0] == 'food'      # the forecast was too high; core pushed the other way
    calls['realised'] = 3.5
    assert call_attribution(calls, clocks, months).dominant_block.iloc[0] == 'core'      # too low: now core is the culprit


def test_seasonal_naive_never_uses_the_origin_month_or_an_unpublished_month():
    ix = pd.period_range('2010-01', '2020-12', freq='M'); rates = pd.Series(1., index=ix)
    published = pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=9), index=ix); origin = pd.Period('2020-02', 'M')
    leaked = rates.copy(); leaked.loc['2020-02'] = 1e9; stamped = published.copy(); stamped.loc['2020-02'] = pd.Timestamp('2020-01-01')
    assert seasonal_naive_path(leaked, stamped, origin, pd.Timestamp('2020-03-09'))[12] == 1.    # February 2021 must not see February 2020
    hidden = rates.copy(); hidden.loc['2020-01'] = 1e9                                            # January 2020 is released on 10 February
    assert seasonal_naive_path(hidden, published, origin, pd.Timestamp('2020-02-05'))[11] == 1.  # ... so a 5 February clock cannot use it
    assert seasonal_naive_path(hidden, published, origin, pd.Timestamp('2020-02-11'))[11] > 1e8


def test_base_rates_treat_the_origin_month_as_unknown():
    cnb = pd.DataFrame({'report_date': ['2022-05-12'], 'quarter': ['2022Q2'], 'value': [10.], 'is_forecast': [True]})
    clocks = pd.DataFrame({'clock': ['report'], 'report_date': ['2022-05-12'], 'origin': ['2022-04']})
    ix = pd.period_range('2021-01', '2022-12', freq='M'); actual = pd.Series(8., index=ix); actual.loc['2022-04'] = 99.
    out = baseline_projections(cnb, clocks, actual).set_index('model').forecast
    assert out['CONST_2'] == 2. and out['RW_YY'] == 8.                                           # April 2022 is the month being nowcast: never 99


def test_needed_against_applied_is_measured_over_every_origin_not_only_active_ones():
    needed = pd.Series([1., -1., 2., -2., 1.5, -1.5]); applied = pd.Series([.5, 0., .5, 0., .5, 0.])
    out = needed_vs_applied(needed, applied)
    assert out['n'] == 6 and out['n_active'] == 3 and out['correlation'] == pytest.approx(float(needed.corr(applied)))
    assert out['sign_agreement'] == 1. and abs(out['correlation']) < .99                          # active rows alone would give a different number


def test_delivered_r23b_paths_leave_h0_other_blocks_and_weights_untouched():
    native = pd.read_csv(c.ROOT / 'output/research_r23b/final/native_forecasts.csv', low_memory=False)
    base = native[native.model.eq('STATE_FAST_R15')].set_index(['origin', 'h']).sort_index()
    fixed = [col for col in native if col.startswith('weight_') or (col.startswith(('value_', 'contribution_')) and not col.endswith('_core'))]
    for model in [name for name in native.model.unique() if name.endswith('_R23B')]:
        own = native[native.model.eq(model)].set_index(['origin', 'h']).sort_index()
        np.testing.assert_allclose(own[fixed].to_numpy(float), base[fixed].to_numpy(float), rtol=0, atol=0)
        assert (own.xs(0, level='h').mm_forecast == base.xs(0, level='h').mm_forecast).all()
        future = own.index.get_level_values('h') > 0
        np.testing.assert_allclose((own.mm_forecast - base.mm_forecast)[future], (own.weight_core * (own.value_core - base.value_core))[future], atol=1e-12)


def test_a_fold_needs_sixteen_matured_training_rows_of_its_own():
    x, y, a, clocks = labels(); t = pd.Period('2006-04', 'M'); clock = pd.Timestamp('2006-05-05')
    outer = eligible(x, y, a, t, clock, 1, 24)
    assert len(outer) == 24                                                        # exactly the minimum: the ninth-latest key has 15 inner rows
    sizes = {str(v): len(eligible(x, y, a, v, clocks.loc[v], 1, 1)) for v in outer[-8:]}
    assert min(sizes.values()) == 15 and sorted(sizes.values())[1] == 16
    audit = pd.DataFrame(choose(x, y, a, clocks, t, clock, 1, [COLUMNS[0]], 'ridge')['validation'])
    assert audit.validation_origin.nunique() == 7 and str(outer[-8]) not in set(audit.validation_origin) and audit.n_train.min() == 16
