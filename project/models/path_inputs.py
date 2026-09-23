"""Origin-frozen hard-data inputs and calendar-exact path accounting."""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.vintages import DEFAULT_UNEMPLOYMENT_PATH, released_unemployment
from models.trend_gap import require_monthly_contiguous


def prepare_origin(headline, fx_levels, origin, as_of,
                   vintage_path=DEFAULT_UNEMPLOYMENT_PATH, horizon=12):
    """Freeze released CPI, unemployment vintages and completed-month FX.

    The caller supplies CPI already screened by its publication calendar. The
    additional origin cutoff always excludes y[origin] and every later value.
    Source row s enters the corrected state transition to s+1: U.diff()[s]
    and FX12[s-2], i.e. destination lags one and three, respectively.

    FX after the last completed observed month stays at that observed level.
    Unpublished U changes equal zero. Missing initial FX history also has a
    neutral zero driver and is counted in metadata, rather than backfilled.
    """
    origin = pd.Period(origin, "M")
    clock = pd.Timestamp(as_of)
    if pd.isna(clock) or clock.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    clock = clock.tz_convert("UTC")
    history = headline.loc[headline.index < origin].copy()
    history = history.loc[history.first_valid_index():]
    require_monthly_contiguous(history, "headline history")
    if history.empty or history.index[-1] != origin - 1:
        raise ValueError("Released headline must end exactly at origin minus one month")
    if not np.isfinite(history.to_numpy(dtype=float)).all():
        raise ValueError("Released headline has missing or nonfinite interior observations")
    require_monthly_contiguous(fx_levels, "FX levels")
    local = clock.tz_convert("Europe/Prague").tz_localize(None)
    last_completed = local.to_period("M") - 1
    fx_known = fx_levels.loc[fx_levels.index <= last_completed].dropna()
    if fx_known.empty or not np.isfinite(fx_known.to_numpy(dtype=float)).all() or (fx_known <= 0).any():
        raise ValueError("FX requires positive finite completed-month observations")
    require_monthly_contiguous(fx_known, "observed FX levels")
    months = pd.period_range(history.index[0], origin + horizon, freq="M")
    fx_index = pd.period_range(min(months[0] - 14, fx_known.index[0]), months[-1], freq="M")
    fx_scenario = fx_known.reindex(fx_index).ffill()
    fx12 = 100 * (fx_scenario / fx_scenario.shift(12) - 1)
    fx_driver = fx12.shift(2).reindex(months)
    u = released_unemployment(clock, vintage_path, adjustment="published_adjusted")
    u_change = u.diff().reindex(months)
    drivers = pd.DataFrame({"un_d": u_change.fillna(0.), "fx12_l3": fx_driver.fillna(0.)}, index=months)
    return {"headline": history, "drivers": drivers, "unemployment": u,
        "metadata": {"origin": str(origin), "as_of_utc": clock.isoformat(),
            "headline_end": str(history.index[-1]), "headline_n": len(history),
            "unemployment_end": str(u.index[-1]) if len(u) else None,
            "unemployment_adjustments": u.attrs.get("adjustments", []),
            "unemployment_vintage_mode": "historical_release" if len(u) else "unavailable",
            "fx_end": str(fx_known.index[-1]), "fx_availability": "completed_month_assumption",
            "unemployment_unknown_driver_rows": int(u_change.isna().sum()),
            "fx_initial_missing_driver_rows": int(fx_driver.isna().sum()),
            "future_scenario": "FX last observed level held; unpublished U changes zero",
            "destination_lags": {"unemployment_change": 1, "fx_twelve_month_pct": 3}}}


def direct_training_data(headline, source_drivers, origin, h):
    """Direct y[origin+h] training with outcome labels no later than y's edge.

    Feature row r contains headline[r-1/r-2/r-3/r-12], its trailing twelve-month
    inflation/state, destination-month seasonal dummies, and source drivers[r-1].
    At forecast origin t, h=3 is therefore four months beyond y's last month.
    """
    if not isinstance(h, int) or h < 0:
        raise ValueError("h must be a nonnegative path horizon")
    require_monthly_contiguous(headline, "direct headline history")
    origin = pd.Period(origin, "M")
    if headline.index[-1] != origin - 1:
        raise ValueError("Direct history must end at origin minus one")
    index = pd.period_range(headline.index[0], origin, freq="M")
    y = headline.reindex(index)
    x = pd.DataFrame({f"headline_l{lag}": y.shift(lag) for lag in (1, 2, 3, 12)})
    x["trailing_yoy"] = 100 * ((1 + y / 100).rolling(12).apply(np.prod, raw=True).shift(1) - 1)
    x["state"] = (x["trailing_yoy"] >= 4.).astype(float)
    destination_drivers = source_drivers.shift(1).reindex(index)
    for name in destination_drivers:
        x[name] = destination_drivers[name]
    for month in range(1, 13):
        x[f"target_month_{month}"] = ((index + h).month == month).astype(float)
    target = pd.Series(headline.reindex(index + h).to_numpy(), index=index, name="target")
    eligible = (index + h <= headline.index[-1]) & target.notna() & x.notna().all(axis=1)
    now = x.loc[origin]
    if not np.isfinite(now.to_numpy(dtype=float)).all():
        raise ValueError("Direct forecast row contains missing predictors")
    return x.loc[eligible], target.loc[eligible], now


def compound_path(history, forecast, origin, h, h0):
    """Exact twelve-month YoY; missing intermediate forecasts remain missing.

    h0 substitution only changes path accounting. It never refits the models
    using an outcome that was not available at the forecast's decision time.
    """
    origin = pd.Period(origin, "M")
    window = pd.period_range(origin + h - 11, origin + h, freq="M")
    values = []
    for month in window:
        if month < origin:
            value = history.get(month, np.nan)
        elif month == origin:
            value = h0
        else:
            value = forecast.get(month.ordinal - origin.ordinal, np.nan)
        values.append(value)
    values = np.asarray(values, dtype=float)
    if len(values) != 12 or not np.isfinite(values).all() or (values <= -100).any():
        return np.nan
    return float(100 * np.expm1(np.log1p(values / 100).sum()))
