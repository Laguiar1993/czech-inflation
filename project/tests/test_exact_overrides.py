"""Helpers that turn ARAD and CZSO downloads into exact Table A6 override rows."""
import numpy as np
import pandas as pd
import pytest

from tools.paper_replication import build_exact_overrides as ov


def test_chain_prefers_the_later_base_year():
    old = pd.Series([101.0, 102.0, 103.0], index=pd.period_range("2017-11", periods=3, freq="M"))
    new = pd.Series([99.0, 98.0], index=pd.period_range("2018-01", periods=2, freq="M"))
    out = ov.chain_previous_month([old, new])
    assert out.index.astype(str).tolist() == ["2017-11", "2017-12", "2018-01", "2018-02"]
    assert out["2018-01"] == 99.0 and out["2017-12"] == 102.0


def test_backcast_rebuilds_known_monthly_changes():
    rng = np.random.default_rng(7)
    index = pd.period_range("2000-01", "2016-12", freq="M")
    level = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.02, len(index)))), index=index)
    mm = (level / level.shift(1) * 100.0).dropna()
    yoy = ((level / level.shift(12) - 1) * 100.0).dropna()
    rebuilt = ov.backcast_previous_month(mm.loc["2010-01":], yoy, pd.Period("2002-05", freq="M"))
    assert rebuilt.index.min() == pd.Period("2002-05", freq="M")
    np.testing.assert_allclose(rebuilt.loc["2002-05":"2009-12"].to_numpy(), mm.loc["2002-05":"2009-12"].to_numpy(), rtol=1e-9)
    check = ov.backcast_check(mm.loc["2010-01":], yoy)
    assert check["mae_pp"] < 1e-6 and check["corr"] == pytest.approx(1.0)


def test_contiguous_tail_drops_history_before_an_internal_gap():
    series = pd.Series([1.0, 2.0, 3.0, 4.0], index=pd.PeriodIndex(["2000Q3", "2000Q4", "2002Q1", "2002Q2"], freq="Q"))
    tail, gaps = ov.contiguous_tail(series)
    assert tail.index.astype(str).tolist() == ["2002Q1", "2002Q2"]
    assert gaps == ["2001Q1", "2001Q2", "2001Q3", "2001Q4"]
    unbroken, none = ov.contiguous_tail(tail)
    assert none == [] and len(unbroken) == 2


def test_rows_frame_dates_follow_the_lag_rule():
    monthly = ov.rows_frame(25, pd.Series([1.0], index=pd.PeriodIndex(["2002-05"], freq="M")), "arad:SVEVZM4", "level", "M", 40, "x")
    quarterly = ov.rows_frame(17, pd.Series([2.0], index=pd.PeriodIndex(["2002Q2"], freq="Q")), "arad:NULC", "level", "Q", 75, "x", "SA; do not re-adjust")
    assert monthly.available_from_assumed.iloc[0] == "2002-07-10"
    assert quarterly.period.iloc[0] == "2002Q2" and quarterly.available_from_assumed.iloc[0] == "2002-09-13"
    assert quarterly.seasonal_adjustment.iloc[0] == "SA; do not re-adjust"
