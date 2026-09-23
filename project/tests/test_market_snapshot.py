"""Economic and information-timing checks for offline Bloomberg snapshots."""

import importlib
import json

import numpy as np
import pandas as pd
import pytest


TICKERS = {
    "brent_front_usd": "CO1 Comdty",
    "brent_y1_usd": "FSBTY1 Index",
    "gas_y1_eur": "TTFGCY1 Index",
    "usdczk": "USDCZK Curncy",
    "eurczk": "EURCZK Curncy",
}


def module():
    return importlib.import_module("tools.market_data.prepare")


def snapshot(tmp_path, dates, data=None, end_date="2026-09-09"):
    if data is None:
        data = {ticker: [float(i + 1)] * len(dates)
                for i, ticker in enumerate(TICKERS.values())}
    daily = pd.DataFrame(data, index=pd.Index(dates, name="observation_date"))
    daily.to_csv(tmp_path / "daily.csv")
    (tmp_path / "request.json").write_text(json.dumps({
        "end_date": end_date, "retrieved_at": "2026-09-09T15:20:00+00:00",
    }), encoding="utf-8")
    return daily


def read_monthly(tmp_path, name="monthly.csv"):
    return pd.read_csv(tmp_path / name, dtype={"month": str})


def test_prepare_does_not_require_a_bloomberg_connection():
    # Import inside each test keeps a missing implementation a focused failure.
    assert callable(module().prepare_snapshot)


def test_same_observation_date_fx_products_preserve_missing_fx(tmp_path):
    snapshot(tmp_path, ["2026-08-31", "2026-09-01", "2026-09-02"], {
        TICKERS["brent_front_usd"]: [70., 71., 72.],
        TICKERS["brent_y1_usd"]: [80., 90., 100.],
        TICKERS["gas_y1_eur"]: [30., 40., 50.],
        TICKERS["usdczk"]: [20., np.nan, 22.],
        TICKERS["eurczk"]: [25., 26., np.nan],
    })
    original = (tmp_path / "daily.csv").read_bytes()
    module().prepare_snapshot(tmp_path)
    daily = pd.read_csv(tmp_path / "derived_daily.csv", index_col="observation_date")
    assert daily.loc["2026-08-31", "brent_y1_czk"] == 1600.
    assert pd.isna(daily.loc["2026-09-01", "brent_y1_czk"])
    assert daily.loc["2026-09-02", "brent_y1_czk"] == 2200.
    assert daily.loc["2026-09-01", "gas_y1_czk"] == 1040.
    assert pd.isna(daily.loc["2026-09-02", "gas_y1_czk"])
    assert (tmp_path / "daily.csv").read_bytes() == original
    # Year-ahead prices remain attached to their observed date, not delivery date.
    assert list(daily.index) == ["2026-08-31", "2026-09-01", "2026-09-02"]


def test_monthly_czk_mean_uses_daily_products_not_product_of_means(tmp_path):
    snapshot(tmp_path, ["2026-08-28", "2026-08-31"], {
        TICKERS["brent_y1_usd"]: [10., 30.],
        TICKERS["usdczk"]: [2., 4.],
        TICKERS["gas_y1_eur"]: [10., 20.],
        TICKERS["eurczk"]: [3., 5.],
        TICKERS["brent_front_usd"]: [5., 6.],
    }, end_date="2026-08-31")
    module().prepare_snapshot(tmp_path)
    rows = read_monthly(tmp_path).set_index(["month", "series"])
    row = rows.loc[("2026-08", "brent_y1_czk")]
    assert row["mean"] == 70.  # (10*2 + 30*4)/2; 20*3 would be wrong.
    assert row["last"] == 120.
    assert row["nobs"] == 2
    assert row["first_quote_date"] == "2026-08-28"
    assert row["last_quote_date"] == "2026-08-31"
    assert set(TICKERS.values()) <= set(rows.index.get_level_values("series"))


def test_monthly_availability_does_not_leak_at_month_end(tmp_path):
    snapshot(tmp_path, ["2026-08-28", "2026-08-31", "2026-09-01"])
    module().prepare_snapshot(tmp_path)
    rows = read_monthly(tmp_path)
    august = rows[rows["month"] == "2026-08"]
    assert august["calendar_month_complete"].all()
    assert set(august["available_from_assumed"]) == {"2026-09-01"}
    assert rows.loc[rows["available_from_assumed"] <= "2026-08-31"].empty


def test_september_mtd_is_labelled_separately_and_not_a_full_month(tmp_path):
    snapshot(tmp_path, ["2026-08-31", "2026-09-08"])
    module().prepare_snapshot(tmp_path)
    complete = read_monthly(tmp_path, "monthly_complete.csv")
    mtd = read_monthly(tmp_path, "monthly_mtd.csv")
    assert set(complete["month"]) == {"2026-08"}
    assert set(mtd["month"]) == {"2026-09"}
    assert not mtd["calendar_month_complete"].any()
    assert set(mtd["period_status"]) == {"month_to_date"}
    assert mtd["available_from_assumed"].isna().all()


def test_completeness_uses_request_end_not_final_traded_date(tmp_path):
    snapshot(tmp_path, ["2026-05-29"], end_date="2026-05-31")
    module().prepare_snapshot(tmp_path)
    monthly = read_monthly(tmp_path)
    assert monthly["calendar_month_complete"].all()
    assert set(monthly["last_quote_date"]) == {"2026-05-29"}
    assert set(monthly["available_from_assumed"]) == {"2026-06-01"}


def test_missing_month_and_missing_series_are_not_filled(tmp_path):
    daily = snapshot(tmp_path, ["2026-07-31", "2026-09-08"])
    daily[TICKERS["gas_y1_eur"]] = np.nan
    daily.to_csv(tmp_path / "daily.csv")
    module().prepare_snapshot(tmp_path)
    rows = read_monthly(tmp_path)
    august = rows[rows["month"] == "2026-08"]
    assert len(august) > 0
    assert (august["nobs"] == 0).all()
    assert august[["mean", "last", "first_quote_date", "last_quote_date"]].isna().all().all()
    gas = rows[rows["series"] == "gas_y1_czk"]
    assert (gas["nobs"] == 0).all()
    assert gas["mean"].isna().all()


def test_asof_excludes_quote_day_but_allows_next_prague_calendar_day():
    daily = pd.DataFrame({"a": [10., 99.]},
                         index=pd.to_datetime(["2026-08-31", "2026-09-01"]))
    module_ = module()
    assert pd.isna(module_.select_asof(daily, "2026-08-31").loc["a", "value"])
    chosen = module_.select_asof(daily, "2026-09-01")
    assert chosen.loc["a", "value"] == 10.
    assert chosen.loc["a", "observation_date"] == pd.Timestamp("2026-08-31")
    assert chosen.loc["a", "available_from_assumed"] == pd.Timestamp("2026-09-01")
    # 22:30 UTC is the next local date in Prague during summer.
    assert module_.select_asof(daily, "2026-08-31T22:30:00Z").loc["a", "value"] == 10.


def test_staleness_is_checked_per_series_against_its_own_observation():
    daily = pd.DataFrame({"liquid": [1., 2., 3.], "stale": [99., np.nan, np.nan]},
                         index=pd.to_datetime(["2026-08-28", "2026-09-04", "2026-09-08"]))
    before = daily.copy(deep=True)
    chosen = module().select_asof(daily, "2026-09-09", max_age_days={"liquid": 1, "stale": 7})
    assert chosen.loc["liquid", "value"] == 3.
    assert chosen.loc["liquid", "age_days"] == 1
    assert not chosen.loc["liquid", "is_stale"]
    assert pd.isna(chosen.loc["stale", "value"])
    assert chosen.loc["stale", "age_days"] == 12
    assert chosen.loc["stale", "is_stale"]
    pd.testing.assert_frame_equal(before, daily)


def test_asof_ignores_future_observations_even_if_last_valid_value_is_missing():
    daily = pd.DataFrame({"a": [np.nan, 100.]},
                         index=pd.to_datetime(["2026-09-08", "2026-09-09"]))
    chosen = module().select_asof(daily, "2026-09-09")
    assert pd.isna(chosen.loc["a", "value"])
    assert pd.isna(chosen.loc["a", "observation_date"])


@pytest.mark.parametrize("dates, message", [
    (["2026-09-08", "2026-09-08"], "duplicate"),
    (["2026-09-10"], "end_date"),
    (["2026-09-08T12:00:00"], "date-only"),
])
def test_invalid_observation_dates_are_rejected(tmp_path, dates, message):
    snapshot(tmp_path, dates)
    with pytest.raises(ValueError, match=message):
        module().prepare_snapshot(tmp_path)


def test_snapshot_retrieval_time_must_be_explicit_utc(tmp_path):
    snapshot(tmp_path, ["2026-09-08"])
    (tmp_path / "request.json").write_text(json.dumps({
        "end_date": "2026-09-09", "retrieved_at": "2026-09-09T15:20:00",
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="UTC"):
        module().prepare_snapshot(tmp_path)


def test_all_extra_raw_tickers_and_negative_rate_quotes_are_retained(tmp_path):
    daily = snapshot(tmp_path, ["2026-08-28", "2026-08-31"], end_date="2026-08-31")
    daily["CO13 Comdty"] = [77., 79.]
    daily["CZSW2 Curncy"] = [-.5, -.1]
    daily.to_csv(tmp_path / "daily.csv")
    module().prepare_snapshot(tmp_path)
    monthly = read_monthly(tmp_path).set_index("series")
    assert monthly.loc["CO13 Comdty", "mean"] == 78.
    assert monthly.loc["CZSW2 Curncy", "mean"] == pytest.approx(-.3)
    assert monthly.loc["CZSW2 Curncy", "last"] == -.1
    assert monthly.loc["CZSW2 Curncy", "nobs"] == 2


def test_assumed_availability_and_actual_retrieval_are_explicit(tmp_path):
    snapshot(tmp_path, ["2026-08-31"])
    module().prepare_snapshot(tmp_path)
    monthly = read_monthly(tmp_path)
    assert set(monthly["availability_basis"]) == {"assumed_not_documented_vintage"}
    assert set(monthly["availability_timezone"]) == {"Europe/Prague"}
    assert set(monthly["retrieved_at"]) == {"2026-09-09T15:20:00+00:00"}
    assert set(monthly["snapshot_end_date"]) == {"2026-09-09"}


def test_duplicate_csv_headers_fail_instead_of_creating_a_fake_ticker(tmp_path):
    snapshot(tmp_path, ["2026-09-08"])
    path = tmp_path / "daily.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] += ",USDCZK Curncy"
    lines[1] += ",999"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        module().prepare_snapshot(tmp_path)
