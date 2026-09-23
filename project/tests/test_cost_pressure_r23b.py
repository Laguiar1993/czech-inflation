from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from data.cost_gaps_r23 import features_at as r23_features_at
from data.cost_pressure_r23b import features_at, COLUMNS
from models.cost_gaps_r23 import monthly_correction
from models.cost_pressure_r23b import fit, eligible, choose, run_origin, FAMILIES, GRID


def input_fixture(seasonal_ulc=True):
    ix = pd.period_range('2000-01', periods=180, freq='M')
    core = pd.Series(.2, index=ix); pub = pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=10), index=ix)
    q = pd.period_range('2000Q1', periods=60, freq='Q')
    qa = pd.Series(q.to_timestamp(how='end').normalize() + pd.Timedelta(days=75), index=q)
    pattern = np.array([.05, .0, -.04, .03])[np.arange(60) % 4] if seasonal_ulc else np.zeros(60)
    ulc = pd.Series(100 * np.exp(.012 * np.arange(60) + pattern), index=q)
    raw = {11: SimpleNamespace(values=pd.Series(5., index=ix), available=pub.copy()),
           17: SimpleNamespace(values=ulc, available=qa.copy()),
           26: SimpleNamespace(values=pd.Series(.5, index=ix), available=pub.copy()),
           47: SimpleNamespace(values=pd.Series(np.exp(np.arange(180) * .004) * 100, index=ix), available=pub.copy())}
    return core, pub, raw, pd.Series(25., index=ix)


SEASON = {i: 0. for i in range(1, 13)}


def at(origin, fixture):
    core, pub, raw, fx = fixture; t = pd.Period(origin, 'M')
    return features_at(core, pub, raw, fx, t, (t + 1).to_timestamp() + pd.Timedelta(days=9), SEASON)


def test_same_quarter_gap_is_seasonally_neutral_where_the_r23_gap_is_not():
    fixture = input_fixture(); core, pub, raw, fx = fixture
    new, old = [], []
    for origin in pd.period_range('2010-03', '2013-12', freq='Q').asfreq('M', 'end'):
        values, _ = at(origin, fixture); new.append(values.ulc_sameq)
        legacy, _ = r23_features_at(core, pub, raw, fx, origin, (origin + 1).to_timestamp() + pd.Timedelta(days=9), SEASON)
        old.append(legacy.ulc_gap)
    assert np.isfinite(new).all() and np.ptp(new) < 1e-9          # pure trend plus stable seasonal: one constant reading
    assert np.ptp(old) > 5                                         # the level-against-median gap swings with the quarter
    # 8 quarters (the median lookback) of ULC growth less core growth: 100*(8*.012) - 100*log1p(.002)*24
    assert new[0] == pytest.approx(100 * 8 * .012 - 24 * 100 * np.log1p(.002), abs=1e-9)


def test_new_features_ignore_unpublished_and_future_values():
    core, pub, raw, fx = input_fixture(); t = pd.Period('2010-01', 'M'); clock = pd.Timestamp('2010-02-05'); season = SEASON
    a, audit = features_at(core, pub, raw, fx, t, clock, season)
    assert list(a.index) == COLUMNS and np.isfinite(a).all()
    assert {r['feature'] for r in audit} == set(COLUMNS)
    reference = {r['feature']: r['reference'] for r in audit}
    assert reference['ulc_sameq'] == '2009Q3' and reference['import_mom'] == '2009-12' and reference['ppi_mom'] == '2009-12'
    for r in raw.values(): r.values.loc[r.available.gt(clock)] = 1e12
    core.loc[pub.gt(clock)] = 1e12; fx.loc[fx.index > t] = 1e12
    b, _ = features_at(core, pub, raw, fx, t, clock, season)
    np.testing.assert_allclose(a, b, atol=0, rtol=0)


def test_momentum_needs_exactly_its_six_published_changes():
    fixture = input_fixture(); core, pub, raw, fx = fixture; t = pd.Period('2010-01', 'M'); clock = pd.Timestamp('2010-02-05')
    base, _ = features_at(core, pub, raw, fx, t, clock, SEASON)
    assert base.import_mom == pytest.approx(6 * 100 * (np.log1p(.005) - np.log1p(.002)))
    assert base.ppi_mom == pytest.approx(6 * .4 - 6 * 100 * np.log1p(.002))
    raw[26].available.loc['2003-03'] = pd.NaT                      # an old hole breaks R23's chained level gap, not the momentum
    old_hole, _ = features_at(core, pub, raw, fx, t, clock, SEASON)
    assert np.isnan(old_hole.import_gap) and old_hole.import_mom == base.import_mom
    raw[26].available.loc['2009-08'] = pd.NaT                      # a hole inside the six-month window fails closed
    inside, audit = features_at(core, pub, raw, fx, t, clock, SEASON)
    assert np.isnan(inside.import_mom)
    assert next(r for r in audit if r['feature'] == 'import_mom')['status'] == 'missing_required_history'


def label_fixture(signal=1.):
    ix = pd.period_range('2000Q1', periods=80, freq='Q').asfreq('M', 'end')
    x = pd.DataFrame({c: np.sin(np.arange(80) / 5 + i) for i, c in enumerate(COLUMNS)}, index=ix)
    y = pd.DataFrame({1: signal * x[COLUMNS[0]] / 10, 2: signal * x[COLUMNS[0]] / 20})
    available = pd.DataFrame({b: (ix + 3 * b + 1).to_timestamp() + pd.Timedelta(days=12) for b in (1, 2)}, index=ix)
    clocks = pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=5), index=ix)
    return x, y, available, clocks


def test_band_specific_maturity_for_outer_rows_and_inner_folds():
    x, y, a, clocks = label_fixture(); t = pd.Period('2016-01', 'M'); clock = pd.Timestamp('2016-02-05')
    near = eligible(x, y, a, t, clock, 1, 24); far = eligible(x, y, a, t, clock, 2, 24)
    assert ((near + 3) < t).all() and ((far + 6) < t).all() and (a.loc[near, 1] <= clock).all() and (a.loc[far, 2] <= clock).all()
    assert near[-1] == pd.Period('2015-09', 'M') and far[-1] == pd.Period('2015-06', 'M')     # the near band learns a quarter sooner
    assert len(near) == 40 and all(near.month % 3 == 0)
    result = choose(x, y, a, clocks, t, clock, 1, [COLUMNS[0]], 'ridge')
    assert len(result['validation']) == 8 * len(GRID)
    for row in result['validation']:
        assert pd.Period(row['last_training_target'], 'M') < pd.Period(row['validation_origin'], 'M')
        assert pd.Timestamp(row['max_training_release']) <= pd.Timestamp(row['validation_clock'])
    poisoned = y.copy(); poisoned.loc[a[1] > clock, 1] = 1e8
    again = choose(x, poisoned, a, clocks, t, clock, 1, [COLUMNS[0]], 'ridge')
    assert again['alpha'] == result['alpha'] and again['scores'] == result['scores']


def test_zero_pressure_gives_zero_correction_and_there_is_no_intercept():
    x, y, _, _ = label_fixture()
    result = fit(x[COLUMNS[:2]], y[1].to_numpy() + 5., pd.Series({c: 0. for c in COLUMNS[:2]}), 1., 'ridge')
    assert result['prediction'] == 0. and len(result['coefficients']) == 2        # a level shift in the target cannot leak through
    scaled = fit(x[COLUMNS[:1]] * 1000, y[1].to_numpy(), pd.Series({COLUMNS[0]: 1000.}), 1., 'ridge')
    plain = fit(x[COLUMNS[:1]], y[1].to_numpy(), pd.Series({COLUMNS[0]: 1.}), 1., 'ridge')
    assert scaled['prediction'] == pytest.approx(plain['prediction'])              # RMS scaling, not centering
    assert sum(result['contributions']) == pytest.approx(result['prediction'])


def test_signed_fit_does_not_flip_and_free_fit_does():
    x = pd.DataFrame({'a': np.linspace(-2, 2, 40)}); y = -x.a.to_numpy()
    assert fit(x, y, pd.Series({'a': 1.}), 1., 'positive')['coefficients'][0] >= -1e-12
    assert fit(x, y, pd.Series({'a': 1.}), 1., 'ridge')['coefficients'][0] < 0


def test_do_no_harm_rule_applies_a_correction_only_when_validation_beats_none():
    x, y, a, clocks = label_fixture(signal=1.); t = pd.Period('2016-01', 'M'); clock = pd.Timestamp('2016-02-05')
    useful = choose(x, y, a, clocks, t, clock, 1, [COLUMNS[0]], 'ridge')
    assert useful['status'] == 'nested_selected' and useful['alpha'] == min(GRID)
    assert useful['scores'][str(useful['alpha'])] < useful['zero_loss']
    nothing = choose(x, y * 0, a, clocks, t, clock, 1, [COLUMNS[0]], 'ridge')     # every fit predicts zero: a tie goes to no correction
    assert nothing['alpha'] is None and nothing['status'] == 'no_correction_validated'
    rng = np.random.default_rng(3); noise = pd.DataFrame({1: rng.normal(size=80), 2: rng.normal(size=80)}, index=x.index)
    unrelated = choose(x, noise, a, clocks, t, clock, 1, COLUMNS[:5], 'ridge')
    assert unrelated['alpha'] is None or unrelated['scores'][str(unrelated['alpha'])] < unrelated['zero_loss']
    early = choose(x, y, a, clocks, pd.Period('2006-01', 'M'), pd.Timestamp('2006-02-05'), 1, [COLUMNS[0]], 'ridge')
    assert early['alpha'] is None and early['status'] == 'no_correction_insufficient_validation'


def test_far_bands_receive_no_correction_on_average():
    monthly = monthly_correction([.2, -.1, 0., 0.])
    np.testing.assert_allclose(monthly.reshape(4, 3).mean(axis=1), [.2, -.1, 0., 0.], atol=1e-14)


def test_targets_are_band_means_of_log_errors_and_mature_with_their_own_last_release():
    from tools.research_r23b.run import targets
    ix = pd.period_range('2019-01', '2020-12', freq='M')
    core = pd.Series(np.linspace(.1, .5, len(ix)), index=ix); dates = pd.Series((ix + 1).to_timestamp() + pd.Timedelta(days=9), index=ix)
    fast = {str(h): .05 * h for h in range(1, 13)}
    states = {'2020-03': dict(forecasts_log=dict(fast=fast)), '2020-09': dict(forecasts_log=dict(fast=fast))}
    y, available, audit = targets(core, dates, states)
    o = pd.Period('2020-03', 'M'); logs = 100 * np.log1p(core / 100)
    assert y.loc[o, 1] == pytest.approx((logs.loc['2020-04':'2020-06'].to_numpy() - np.array([.05, .10, .15])).mean())
    assert y.loc[o, 2] == pytest.approx((logs.loc['2020-07':'2020-09'].to_numpy() - np.array([.20, .25, .30])).mean())
    assert available.loc[o, 1] == dates.loc['2020-06'] and available.loc[o, 2] == dates.loc['2020-09']
    late = pd.Period('2020-09', 'M')                               # h4-6 would need January-March 2021, which do not exist yet
    assert np.isfinite(y.loc[late, 1]) and np.isnan(y.loc[late, 2]) and pd.isna(available.loc[late, 2])
    damaged = dates.copy(); damaged.loc['2020-05'] = pd.NaT
    again, when, _ = targets(core, damaged, states)
    assert np.isnan(again.loc[o, 1]) and np.isnan(again.loc[o, 2]) and pd.isna(when.loc[o, 1])


def test_run_origin_reports_fallbacks_and_builds_every_candidate():
    x, y, a, clocks = label_fixture(); t = pd.Period('2016-03', 'M'); clock = pd.Timestamp('2016-04-05')
    done = run_origin(x, y, a, clocks, t, clock)
    assert done['status'] == 'estimated' and set(done['paths']) == set(FAMILIES)
    for name, path in done['paths'].items():
        assert len(path) == 12 and np.isfinite(path).all()
        bands = [done['fits'][name][str(b)]['prediction'] if done['selection'][name][str(b)]['alpha'] is not None else 0. for b in (1, 2)]
        np.testing.assert_allclose(np.reshape(path, (4, 3)).mean(axis=1), [*bands, 0., 0.], atol=1e-12)
    holed = x.copy(); holed.loc[t, COLUMNS[2]] = np.nan
    missing = run_origin(holed, y, a, clocks, t, clock)
    assert missing['status'] == 'missing_current_features' and missing['paths'] == {}
    assert run_origin(x, y, a, clocks, pd.Period('2004-03', 'M'), pd.Timestamp('2004-04-05'))['status'] == 'insufficient_common_history'
