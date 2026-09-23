"""Chronological calibration of saved forecast distributions."""
import numpy as np
import pandas as pd
import pytest
from models import paper_tvwqrf as engine


def saved(h=6, n=50):
    edges = pd.period_range('2010-01', periods=n, freq='M')
    q = pd.DataFrame([dict(edge=str(e), horizon=h, quantile=p,
                           value=float(i / 100 + p))
                      for i, e in enumerate(edges) for p in engine.ALL_QUANTILES])
    y = pd.Series(.8, index=pd.period_range(edges[0], edges[-1] + h, freq='M'))
    return q, y, edges


def calibrate(q, y):
    assert hasattr(engine, 'recalibrate_saved'), 'Saved-origin causal calibration must replace the internal holdout'
    return engine.recalibrate_saved(q, y)


def test_causal_weights_use_only_matured_origins_and_keep_the_boundary():
    q, y, edges = saved(h=13)
    result = calibrate(q, y)
    row = result['diagnostics'].set_index('edge').loc[str(edges[35])]
    assert row.validation_n == 12 and row.calibration_status == 'past_origin_forecasts'
    assert row.validation_last_origin == str(edges[35] - 13)
    assert row.validation_first_origin == str(edges[35] - 24)
    assert row.validation_last_target == str(edges[35])


def test_future_quantiles_and_outcomes_cannot_change_an_earlier_calibration():
    q, y, edges = saved()
    edge = edges[30]
    expected = calibrate(q, y)
    changed = q.copy()
    changed.loc[pd.PeriodIndex(changed.edge, freq='M') > edge, 'value'] += 99
    y2 = y.copy(); y2.loc[y2.index > edge] += 100
    actual = calibrate(changed, y2)
    for key in ('points', 'weights', 'diagnostics'):
        a = expected[key]; b = actual[key]
        pd.testing.assert_frame_equal(a[a.edge <= str(edge)].reset_index(drop=True),
                                      b[b.edge <= str(edge)].reset_index(drop=True))


def test_missing_validation_month_uses_an_explicit_fixed_combination():
    q, y, edges = saved()
    edge = edges[30]
    q = q[q.edge != str(edge - 7)]
    result = calibrate(q, y)
    row = result['diagnostics'].set_index('edge').loc[str(edge)]
    assert row.validation_n == 11 and row.calibration_status == 'fixed_insufficient_history'
    w = result['weights']
    w = w[(w.edge == str(edge)) & (w.scheme == 'TVW3')].weight.to_numpy()
    _, lo, hi = engine.SCHEMES['TVW3']
    np.testing.assert_allclose(w, engine._feasible_start(np.array(lo), np.array(hi)))


def test_duplicate_saved_quantiles_fail_closed():
    q, y, _ = saved()
    with pytest.raises(ValueError, match='[Dd]uplicate'):
        calibrate(pd.concat([q, q.iloc[:1]], ignore_index=True), y)


def test_forest_without_calibration_has_no_claimed_validation_history():
    rng = np.random.default_rng(76)
    X = rng.normal(size=(70, 3)); y = X[:, 0] + rng.normal(size=70)
    out = engine.fit_forecast(X, y, X[-1], forest={'n_estimators': 30})
    assert out.get('calibration_status') == 'fixed_insufficient_history'
    assert out.get('validation_n') == 0


def test_single_fit_preserves_mean_and_quantiles():
    from quantile_forest import RandomForestQuantileRegressor
    rng = np.random.default_rng(41)
    X = rng.normal(size=(65, 4)); y = rng.normal(size=65)
    opts = {**engine.FOREST_DEFAULTS, 'n_estimators': 30}
    out = engine.fit_forecast(X, y, X[-1], forest=opts)
    ref = RandomForestQuantileRegressor(**opts).fit(X, y)
    np.testing.assert_array_equal(list(out['quantiles'].values()),
                                  ref.predict(X[-1:], quantiles=list(engine.ALL_QUANTILES))[0])
    assert out['points']['QRF_MEAN'] == float(ref.predict(X[-1:], quantiles='mean')[0])


def test_runner_generates_twelve_mature_warmup_forecasts_for_each_horizon():
    import paper_tvwqrf_experiment as runner
    assert hasattr(runner, 'forecast_tasks'), 'Runner must explicitly schedule causal warmup origins'
    edge = pd.Period('2020-01', freq='M')
    tasks = runner.forecast_tasks([edge], [1, 13], edge+13, edge)
    for h in (1, 13):
        origins = {pd.Period(e, freq='M') for e, k in tasks if k == h}
        assert edge in origins
        assert set(pd.period_range(edge-h-11, edge-h, freq='M')) <= origins
        assert max(origins) == edge


def test_runner_rejects_duplicate_horizons_before_scheduling():
    import paper_tvwqrf_experiment as runner
    edge = pd.Period('2020-01', freq='M')
    with pytest.raises(ValueError, match='[Dd]uplicate'):
        runner.forecast_tasks([edge], [1, 1], edge+1, edge)


def test_runner_benchmarks_only_requested_forest_keys(monkeypatch):
    import paper_tvwqrf_experiment as runner
    edge = pd.Period('2020-01', freq='M')
    seen = []
    def fake(target, edges, horizons, tmh=False):
        seen.extend((str(e), h) for e in edges for h in horizons)
        return [dict(edge=str(e), horizon=h, model='RW', forecast=1.)
                for e in edges for h in horizons]
    monkeypatch.setattr(runner, 'benchmark_rows', fake)
    tasks = [('2019-12', 1), ('2020-01', 1), ('2020-01', 13)]
    assert hasattr(runner, 'benchmarks_for_tasks')
    result = runner.benchmarks_for_tasks(pd.Series(dtype=float), tasks, edge)
    assert seen == [('2020-01', 1), ('2020-01', 13)]
    assert {(r['edge'], r['horizon']) for r in result} == set(seen)


def test_short_warmup_is_recorded_without_failing_valid_requested_origin():
    import paper_tvwqrf_experiment as runner
    months = pd.period_range('2005-05', '2009-12', freq='M')
    panel = pd.DataFrame({'a6_01':np.arange(len(months), dtype=float)}, index=months)
    target = pd.Series(np.sin(np.arange(len(months))), index=months)
    out = runner.forecast_task('2007-12', 13, panel, target, 'realtime',
                               {'n_estimators':3}, False, warmup=True)
    assert out['points'] == [] and out['quantiles'] == []
    assert out['diagnostics']['status'] == 'skipped_short_warmup'
    valid = runner.forecast_task('2009-12', 13, panel, target, 'realtime',
                                 {'n_estimators':3}, False)
    assert valid['points'] and valid['quantiles']
