"""Pure, offline panels from an archived Bloomberg daily snapshot.

Nothing here changes model inputs or claims a documented historical vintage.
Quotes remain on their observation dates, including year-ahead contracts.
Availability is an explicit assumption: next calendar day in Europe/Prague for
daily observations, next month for completed calendar-month aggregates.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import csv
from datetime import timedelta
import json
from numbers import Integral
from pathlib import Path
import re

import numpy as np
import pandas as pd


TICKERS = {
    "brent_front_usd": "CO1 Comdty",
    "brent_y1_usd": "FSBTY1 Index",
    "gas_y1_eur": "TTFGCY1 Index",
    "usdczk": "USDCZK Curncy",
    "eurczk": "EURCZK Curncy",
}
AVAILABILITY_BASIS = "assumed_not_documented_vintage"
AVAILABILITY_TIMEZONE = "Europe/Prague"


def _date_only(value: str, name: str) -> pd.Timestamp:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{name} must be date-only ISO YYYY-MM-DD")
    try:
        return pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid {name}: {value!r}") from exc


def _daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a date-indexed numerical panel without filling any cells."""
    if not frame.columns.is_unique:
        raise ValueError("duplicate series columns")
    dates = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="raise"))
    if dates.hasnans or dates.tz is not None or not dates.equals(dates.normalize()):
        raise ValueError("observation_date must contain valid naive date-only values")
    if not dates.is_unique:
        raise ValueError("duplicate observation_date")
    result = frame.copy()
    result.index = dates.rename("observation_date")
    result = result.sort_index().apply(pd.to_numeric, errors="raise")
    # Negative rates are valid; infinity is not a valid quote or missing marker.
    if np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("infinite quote value")
    return result


def prepare_snapshot(folder: str | Path) -> dict[str, Path]:
    """Write derived_daily.csv and monthly panels beside untouched raw inputs.

    Inputs are daily.csv (observation_date and exact Bloomberg ticker columns)
    and request.json (end_date YYYY-MM-DD and an explicit UTC retrieved_at).
    All raw series, including extra commodity/rates tickers, enter monthly.csv.
    The five named source series and same-date CZK products enter derived_daily.

    Monthly ``mean`` and ``last`` use nonmissing observations within that month;
    ``last`` means last quoted value, not necessarily a quote on month-end.
    Every month from the first raw observation through end_date is represented,
    including entirely missing months. ``calendar_month_complete`` says only
    that end_date reaches calendar month-end, never that exchange-day coverage
    is complete. Counts and quote bounds expose actual available observations.

    MTD rows are separately labelled and have no full-month availability date.
    No forward/backward fill, cross-month fill, or delivery-date shift is used.
    Return output paths; neither daily.csv nor request.json is rewritten.
    """
    folder = Path(folder)
    request = json.loads((folder / "request.json").read_text(encoding="utf-8-sig"))
    end_date = _date_only(request["end_date"], "end_date")
    try:
        retrieved_at = pd.Timestamp(request["retrieved_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("retrieved_at must be an explicit UTC ISO timestamp") from exc
    if pd.isna(retrieved_at) or retrieved_at.tz is None or retrieved_at.utcoffset() != timedelta(0):
        raise ValueError("retrieved_at must be an explicit UTC ISO timestamp")

    # read_csv otherwise silently changes duplicate names to ticker.1, etc.
    with (folder / "daily.csv").open(encoding="utf-8-sig", newline="") as source:
        headers = next(csv.reader(source), [])
    if len(headers) != len(set(headers)):
        raise ValueError("duplicate series columns in daily.csv")
    raw = pd.read_csv(folder / "daily.csv", index_col="observation_date")
    if raw.empty:
        raise ValueError("daily.csv contains no observations")
    for value in raw.index:
        _date_only(value, "observation_date")
    raw = _daily_frame(raw)
    if (raw.index > end_date).any():
        raise ValueError("daily.csv contains observations after request end_date")
    missing = set(TICKERS.values()) - set(raw.columns)
    if missing:
        raise ValueError(f"daily.csv is missing required tickers: {sorted(missing)}")

    derived = pd.DataFrame({name: raw[ticker] for name, ticker in TICKERS.items()})
    derived["brent_y1_czk"] = derived["brent_y1_usd"] * derived["usdczk"]
    derived["gas_y1_czk"] = derived["gas_y1_eur"] * derived["eurczk"]
    derived = _daily_frame(derived)
    if set(raw.columns) & set(derived.columns):
        raise ValueError("raw Bloomberg ticker names collide with derived series names")
    all_series = pd.concat([raw, derived], axis=1)
    observation_months = all_series.index.to_period("M")
    months = pd.period_range(raw.index.min().to_period("M"), end_date.to_period("M"), freq="M")
    rows = []
    for month in months:
        complete = month.end_time.normalize() <= end_date
        block = all_series.loc[observation_months == month]
        for series in all_series.columns:
            observed = block[series].dropna()
            rows.append({
                "month": str(month),
                "series": series,
                "mean": observed.mean() if len(observed) else np.nan,
                "last": observed.iloc[-1] if len(observed) else np.nan,
                "nobs": len(observed),
                "first_quote_date": observed.index[0] if len(observed) else pd.NaT,
                "last_quote_date": observed.index[-1] if len(observed) else pd.NaT,
                "calendar_month_complete": bool(complete),
                "period_status": "calendar_month" if complete else "month_to_date",
                "available_from_assumed": (month + 1).start_time if complete else pd.NaT,
                "availability_basis": AVAILABILITY_BASIS,
                "availability_timezone": AVAILABILITY_TIMEZONE,
                "snapshot_end_date": end_date,
                "retrieved_at": retrieved_at.isoformat(),
            })
    monthly = pd.DataFrame(rows)
    paths = {name: folder / f"{name}.csv" for name in (
        "derived_daily", "monthly", "monthly_complete", "monthly_mtd",
    )}
    derived.to_csv(paths["derived_daily"], date_format="%Y-%m-%d")
    monthly.to_csv(paths["monthly"], index=False, date_format="%Y-%m-%d")
    monthly.loc[monthly["calendar_month_complete"]].to_csv(
        paths["monthly_complete"], index=False, date_format="%Y-%m-%d")
    monthly.loc[~monthly["calendar_month_complete"]].to_csv(
        paths["monthly_mtd"], index=False, date_format="%Y-%m-%d")
    return paths


def select_asof(
    daily: pd.DataFrame,
    asof: str | pd.Timestamp,
    max_age_days: int | Mapping[str, int] | None = 7,
) -> pd.DataFrame:
    """Select each series' last eligible quote, suppressing stale values.

    This is a selection view, not a filled daily/monthly history. Input index is
    date-only observation_date. Quote day is excluded: availability is assumed
    at next calendar-day midnight in Europe/Prague. An aware asof timestamp is
    converted to that local date; a naive date/time is interpreted as Prague.

    Age is calendar days from each series' own observation_date; values exactly
    at the maximum age remain eligible. Default 7 days is an explicit utility
    policy, not an exchange calendar. A per-series mapping must name every input
    series. None explicitly disables the cutoff. Missing/stale values return
    NaN, with observation/availability dates and status retained for auditing.
    Historical availability is assumed, not a documented Bloomberg vintage.
    """
    daily = _daily_frame(daily)
    asof_date = pd.Timestamp(asof)
    if pd.isna(asof_date):
        raise ValueError("asof must be a valid date or timestamp")
    if asof_date.tz is not None:
        asof_date = asof_date.tz_convert(AVAILABILITY_TIMEZONE).tz_localize(None)
    asof_date = asof_date.normalize()
    eligible = daily.loc[daily.index < asof_date]
    rows = []
    for series in daily.columns:
        if isinstance(max_age_days, Mapping):
            if series not in max_age_days:
                raise ValueError(f"max_age_days lacks series {series!r}")
            limit = max_age_days[series]
        else:
            limit = max_age_days
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, Integral) or limit < 0):
            raise ValueError("max_age_days must be a nonnegative integer or None")
        observed = eligible[series].dropna()
        quote_date = observed.index[-1] if len(observed) else pd.NaT
        age_days = (asof_date - quote_date).days if len(observed) else np.nan
        stale = bool(len(observed) and limit is not None and age_days > limit)
        rows.append({
            "series": series,
            "value": observed.iloc[-1] if len(observed) and not stale else np.nan,
            "observation_date": quote_date,
            "available_from_assumed": quote_date + pd.Timedelta(days=1),
            "asof_date": asof_date,
            "age_days": age_days,
            "max_age_days": limit,
            "is_stale": stale,
            "availability_status": "missing" if not len(observed) else ("stale" if stale else "available"),
            "availability_basis": AVAILABILITY_BASIS,
            "availability_timezone": AVAILABILITY_TIMEZONE,
        })
    return pd.DataFrame(rows).set_index("series")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder containing daily.csv and request.json")
    args = parser.parse_args()
    for name, path in prepare_snapshot(args.folder).items():
        print(f"{name}: {path}")
