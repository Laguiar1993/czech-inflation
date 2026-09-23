"""PATH_SPEC_v4 unit checks: robust seasonal, driver availability lags."""
import numpy as np
import pandas as pd

from models.trend_gap import seasonal_means, fit_forecast


def _series(n=240, shock_jan=None):
    idx = pd.period_range("2000-01", periods=n, freq="M")
    rng = np.random.default_rng(0)
    y = pd.Series(0.2 + 0.3 * np.sin(2 * np.pi * (idx.month - 1) / 12) + 0.05 * rng.standard_normal(n), index=idx)
    if shock_jan:
        y.loc[pd.Period(shock_jan, "M")] += 6.0
    return y


def test_robust_seasonal_ignores_a_shock_january():
    y0, y1 = _series(), _series(shock_jan="2015-01")
    mean_move = seasonal_means(y1)[1] - seasonal_means(y0)[1]
    robust_move = seasonal_means(y1, robust=True)[1] - seasonal_means(y0, robust=True)[1]
    assert mean_move > 0.2                  # one shock January lifts the mean factor by ~6/20
    assert abs(robust_move) < 0.05          # the median factor barely moves


def test_seasonal_means_default_unchanged():
    y = _series()
    assert seasonal_means(y) == seasonal_means(y, robust=False)


def test_fit_forecast_robust_option_runs_and_differs_after_shock():
    y = _series(shock_jan="2015-01")
    a = fit_forecast(y, range(1, 14), anchored=True)
    b = fit_forecast(y, range(1, 14), anchored=True, robust_seasonal=True)
    assert np.isfinite(a["mm"][1]) and np.isfinite(b["mm"][1])
    jan_h = next(h for h in range(1, 14) if (y.index[-1] + h).month == 1)
    assert a["mm"][jan_h] - b["mm"][jan_h] > 0.15       # robust January forecast sits below the mean-seasonal one


def test_lci_monthly_carry_uses_quarter_end_plus_three():
    from path_step4_backtest import load_lci
    s = load_lci()
    assert len(s) > 250 and s.index.min() >= pd.Period("2001-06", "M")
    # a quarter's value first appears three months after the quarter end (Q1 -> June, Q2 -> September ...)
    changes = s[s.diff().fillna(1.0) != 0.0].index
    assert all(p.month in (3, 6, 9, 12) for p in changes)
