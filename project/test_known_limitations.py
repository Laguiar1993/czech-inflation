"""Former next-batch requirements (Codex cleanup, 7 Sep 2026), now REQUIRED
to pass under v2.5-timing (TIMING_SPEC_v25.md T1-T3). They were strict
expected failures under v2.4; keeping them green is part of the live-
readiness contract in docs/LIVE_READINESS.md.
"""
from types import SimpleNamespace
import numpy as np
import pandas as pd
import cz_struct as S


def test_january_2026_detail_is_unavailable_on_february_11():
    # https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-january-2026
    # Publication Date: 13. 02. 2026 -- the old day-11 rule admitted it two days early
    assert not S._cpi_family_released_by(pd.Period('2026-01'), pd.Timestamp('2026-02-11 12:00'))
    assert not S._cpi_family_released_by(pd.Period('2026-01'), pd.Timestamp('2026-02-13 08:59'))
    assert S._cpi_family_released_by(pd.Period('2026-01'), pd.Timestamp('2026-02-13 09:00'))


def _food_fixture():
    idx = pd.period_range('2015-01', '2026-07', freq='M')
    food = pd.Series(np.sin(np.arange(len(idx))), index=idx)
    frame = pd.DataFrame({'x': np.arange(len(idx), dtype=float)}, index=idx)
    return food, frame


def test_food_seasonal_adjustment_filters_history_before_fitting(monkeypatch):
    import statsmodels.tsa.x13 as x13
    calls = []

    def record(series, **kwargs):
        calls.append(series.index.max().to_period('M'))
        return SimpleNamespace(seasadj=series.copy())
    monkeypatch.setattr(x13, 'x13_arima_analysis', record)
    food, frame = _food_fixture()
    S._X13_CACHE.clear()
    try:
        # June-2026 detail release is 2026-07-10: on 1 July only May is public
        S.food_forecast(food, frame, pd.Period('2026-07'), as_of=pd.Timestamp('2026-07-01'))
        assert calls[-1] <= pd.Period('2026-05')
        S.food_forecast(food, frame, pd.Period('2026-07'), as_of=pd.Timestamp('2026-07-31'))
        assert calls[-1] == pd.Period('2026-06')
    finally:
        S._X13_CACHE.clear()


def test_food_cache_refits_when_input_vintage_changes(monkeypatch):
    import statsmodels.tsa.x13 as x13
    calls = []

    def record(series, **kwargs):
        calls.append(series.copy())
        return SimpleNamespace(seasadj=series.copy())
    monkeypatch.setattr(x13, 'x13_arima_analysis', record)
    food, frame = _food_fixture()
    S._X13_CACHE.clear()
    try:
        S.food_forecast(food, frame, pd.Period('2026-07'), as_of=pd.Timestamp('2026-07-31'))
        revised = food.copy()
        revised.loc[pd.Period('2026-06')] += 1
        S.food_forecast(revised, frame, pd.Period('2026-07'), as_of=pd.Timestamp('2026-07-31'))
        assert len(calls) == 2, "a changed input vintage must refit X-13"
        S.food_forecast(revised, frame, pd.Period('2026-07'), as_of=pd.Timestamp('2026-07-31'))
        assert len(calls) == 2, "an identical vintage must hit the cache"
    finally:
        S._X13_CACHE.clear()
