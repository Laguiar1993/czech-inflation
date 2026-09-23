import numpy as np
import pandas as pd
import pytest

from tools.path_diagnostics.gates import seasonal_share, binding_share, wrong_sign_share, needed_vs_applied
from tools.path_diagnostics.bootstrap import block_length, circular_block_bootstrap
from tools.path_diagnostics.attribution import monthly_block_errors, block_error_table, quarter_attribution, call_attribution
from tools.path_diagnostics.benchmarks import seasonal_naive_path, block_benchmark_scores
from tools.path_diagnostics.lead_baselines import baseline_projections, report_clusters


def test_seasonal_share_separates_a_pure_seasonal_from_noise():
    quarter = pd.Series(np.tile([1, 2, 3, 4], 30))
    seasonal = quarter.map({1: 4., 2: 0., 3: -3., 4: 2.})
    assert seasonal_share(seasonal, quarter) == pytest.approx(1.)
    noise = pd.Series(np.random.default_rng(1).normal(size=120))
    assert seasonal_share(noise, quarter) < .08
    mixed = seasonal + 3 * noise
    assert .3 < seasonal_share(mixed, quarter) < .7
    assert np.isnan(seasonal_share(noise.iloc[:5], quarter.iloc[:5]))
    assert np.isnan(seasonal_share(pd.Series(np.ones(40)), quarter.iloc[:40]))   # constant feature: undefined, not zero


def test_binding_and_wrong_sign_shares_ignore_the_intercept():
    rows = pd.DataFrame({'feature': ['a'] * 4 + ['b'] * 4 + ['intercept'] * 4,
                         'coefficient': [0., 0., 0., .2, -.1, .3, -.2, -.4, 0., 0., 0., 0.]})
    assert binding_share(rows).to_dict() == {'a': .75, 'b': 0.}
    assert wrong_sign_share(rows).to_dict() == {'a': 0., 'b': .75}


def test_needed_vs_applied_reports_an_anti_phase_correction():
    t = np.arange(40)
    needed = pd.Series(np.sin(t / 4), index=pd.period_range('2015-01', periods=40, freq='M').astype(str))
    applied = -0.1 * needed
    out = needed_vs_applied(needed, applied)
    assert out['n'] == 40 and out['correlation'] == pytest.approx(-1.)
    assert out['sign_agreement'] < .1
    assert np.isnan(needed_vs_applied(needed, applied * 0)['correlation'])      # nothing applied: undefined, not zero


def test_block_length_rule_and_no_interval_for_short_panels():
    assert block_length(75) == 12 and block_length(30) == 6 and block_length(19) is None
    short = circular_block_bootstrap(np.arange(19.), origins=pd.period_range('2024-01', periods=19, freq='M').astype(str))
    assert short['status'] == 'too_few_observations_for_an_interval'
    assert np.isnan(short['ci_low']) and short['mean_loss_difference'] == pytest.approx(9.)


def test_circular_bootstrap_weights_every_origin_equally_and_contains_its_mean():
    # A late-sample spike is exactly what the truncated moving-block scheme under-weighted.
    values = np.r_[np.zeros(60), np.full(12, 5.)]
    origins = pd.period_range('2019-05', periods=72, freq='M').astype(str)
    out = circular_block_bootstrap(values, origins=origins, draws=4000, seed=7)
    assert out['status'] == 'ok' and out['block'] == 12
    assert out['ci_low'] <= out['mean_loss_difference'] <= out['ci_high']
    assert out['bootstrap_mean'] == pytest.approx(values.mean(), abs=.05)
    gap = circular_block_bootstrap(values, origins=np.r_[origins[:30], origins[31:], ['2030-01']])
    assert gap['status'] == 'noncontiguous_origins'


def native_fixture():
    rows = []
    weights = dict(weight_core=.5, weight_food=.2, weight_fuel=.05, weight_administered=.15, weight_alc=.1)
    for origin in ['2020-01', '2020-02']:
        for h in range(13):
            target = str(pd.Period(origin, 'M') + h)
            values = dict(value_core=.2, value_food=.3, value_fuel=0., value_administered=.1, value_alcohol_tobacco=.2)
            blocks = sum(weights[w] * values[v] for w, v in [('weight_core', 'value_core'), ('weight_food', 'value_food'), ('weight_fuel', 'value_fuel'),
                                                           ('weight_administered', 'value_administered'), ('weight_alc', 'value_alcohol_tobacco')])
            rows.append(dict(origin=origin, model='M', h=h, target=target, mm_forecast=blocks + .01, mm_actual=.25, as_of_utc='2020-02-10T22:59:00+00:00',
                             **weights, **values))
    return pd.DataFrame(rows)


def actual_fixture():
    ix = pd.period_range('2015-01', '2021-06', freq='M')
    return pd.DataFrame(dict(core=.15, food=.5, fuel=1., administered=.1, alcohol_tobacco=.2), index=ix)


def test_block_errors_reconcile_exactly_and_h0_is_its_own_bucket():
    monthly = monthly_block_errors(native_fixture(), actual_fixture())
    parts = ['e_h0', 'e_core', 'e_food', 'e_fuel', 'e_administered', 'e_alcohol_tobacco', 'e_wedge']
    np.testing.assert_allclose(monthly[parts].sum(axis=1), monthly.e_total, atol=1e-14)
    first = monthly[monthly.h.eq(0)]
    assert (first[['e_core', 'e_food', 'e_wedge']] == 0).all().all() and np.allclose(first.e_h0, first.e_total)
    row = monthly[(monthly.origin == '2020-01') & (monthly.h == 3)].iloc[0]
    assert row.e_food == pytest.approx(.2 * (.3 - .5)) and row.c_food == pytest.approx(3 * .2 * (.3 - .5))
    table = block_error_table(monthly, horizons=(6,))
    food = table[(table.block == 'food') & (table['sample'] == 'full')].iloc[0]
    assert food.n == 2 and food.rms == pytest.approx(6 * .04) and food.bias == pytest.approx(-6 * .04)


def test_quarter_attribution_needs_the_whole_quarter_inside_the_path():
    monthly = monthly_block_errors(native_fixture(), actual_fixture())
    inside = quarter_attribution(monthly, 'M', '2020-01', '2020Q3')
    assert inside['c_food'] == pytest.approx(np.mean([6, 7, 8]) * .2 * (.3 - .5))
    assert quarter_attribution(monthly, 'M', '2020-01', '2021Q1') is None        # March 2021 is beyond h12
    calls = pd.DataFrame(dict(model=['M'], clock=['report'], report_date=['2020-02-13'], quarter=['2020Q3'], forecast=[3.], realised=[2.], deviation=[.5]))
    clocks = pd.DataFrame(dict(clock=['report'], report_date=['2020-02-13'], origin=['2020-01']))
    out = call_attribution(calls, clocks, monthly)
    assert out.iloc[0].dominant_block in {'h0', 'core', 'food', 'fuel', 'administered', 'alcohol_tobacco', 'wedge'}
    assert out.iloc[0].model_error == pytest.approx(1.)


def test_seasonal_naive_uses_only_published_years_and_three_of_them():
    ix = pd.period_range('2010-01', '2020-12', freq='M')
    rates = pd.Series([float(p.year - 2000) if p.month == 3 else 0. for p in ix], index=ix)
    published = pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=9), index=ix)
    path = seasonal_naive_path(rates, published, pd.Period('2020-02', 'M'), pd.Timestamp('2020-03-09'))
    assert path[1] == pytest.approx(np.mean([17., 18., 19.]))                    # March: 2017-2019; March 2020 is unpublished
    assert path[2] == 0. and set(path) == set(range(1, 13))
    rates.loc['2020-03'] = 1e9                                                   # future value cannot leak
    assert seasonal_naive_path(rates, published, pd.Period('2020-02', 'M'), pd.Timestamp('2020-03-09'))[1] == path[1]
    assert np.isnan(seasonal_naive_path(rates.loc['2019-06':], published, pd.Period('2020-02', 'M'), pd.Timestamp('2020-03-09'))[1])


def test_block_benchmarks_score_model_zero_and_seasonal_on_identical_origins():
    native = native_fixture(); actual = actual_fixture()
    published = pd.Series((actual.index + 1).to_timestamp() + pd.Timedelta(days=9), index=actual.index)
    scores = block_benchmark_scores(native, actual, published, horizons=(3,))
    food = scores[(scores.block == 'food') & (scores['sample'] == 'full') & (scores.model == 'M')].iloc[0]
    assert food.n == 2
    assert food.model_rmse == pytest.approx(abs(3 * 100 * (np.log1p(.003) - np.log1p(.005))))
    assert food.zero_rmse == pytest.approx(3 * 100 * np.log1p(.005))
    assert food.seasonal_rmse == pytest.approx(0., abs=1e-12)                    # a constant block is forecast exactly by its own history


def test_lead_baselines_use_known_history_only_and_previous_reports():
    cnb = pd.DataFrame({'report_date': ['2022-02-10'] * 2 + ['2022-05-12'] * 2, 'quarter': ['2022Q3', '2022Q4'] * 2,
                        'value': [3., 2.5, 5., 4.], 'is_forecast': [True] * 4})
    clocks = pd.DataFrame({'clock': ['report', 'report'], 'report_date': ['2022-02-10', '2022-05-12'], 'origin': ['2021-12', '2022-04']})
    ix = pd.period_range('2021-01', '2022-12', freq='M')
    actual = pd.Series(np.linspace(1., 12.5, len(ix)), index=ix)
    out = baseline_projections(cnb, clocks, actual)
    assert set(out.model) == {'CONST_2', 'RW_YY', 'PREV_CNB', 'CNB_MOMENTUM'}
    get = lambda m, d, q: out[(out.model == m) & (out.report_date == d) & (out.quarter == q)].forecast.iloc[0]
    assert get('CONST_2', '2022-02-10', '2022Q3') == 2.
    assert get('RW_YY', '2022-02-10', '2022Q3') == pytest.approx(actual.loc['2021-11'])       # latest known annual rate at origin 2021-12
    assert np.isnan(get('PREV_CNB', '2022-02-10', '2022Q3'))                                   # no earlier report
    assert get('PREV_CNB', '2022-05-12', '2022Q3') == 3. and get('CNB_MOMENTUM', '2022-05-12', '2022Q3') == 7.
    assert out[(out.model == 'RW_YY') & (out.quarter == '2022Q3')].realised.iloc[0] == pytest.approx(actual.loc['2022-07':'2022-09'].mean())
    rows = pd.DataFrame(dict(model=['A'] * 4, report_date=['r1', 'r1', 'r2', 'r3'], material_gain=[True, True, False, False],
                             material_loss=[False, False, True, True], joint_success=[True, False, False, False]))
    assert report_clusters(rows).iloc[0].to_dict() == dict(model='A', episodes=4, reports=3, gain_reports=1, loss_reports=2, success_reports=1)
