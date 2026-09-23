"""Fixed Table A6 transformations must not depend on future observations."""
import numpy as np
import pandas as pd
import pytest

from tools.paper_replication import build_paper_panel as bp


@pytest.fixture
def calendar(tmp_path):
    path = tmp_path / "calendar.csv"
    pd.DataFrame(columns=["target_month", "first_release_dt"]).to_csv(path, index=False)
    return path


def raw_series(number, values, frequency="M"):
    index = pd.period_range("2002-01", periods=len(values), freq=frequency)
    levels = pd.Series(values, index=index, dtype=float)
    available = pd.Series(index.to_timestamp(how="end").normalize() + pd.Timedelta(days=35), index=index)
    return bp.Raw(number, "synthetic", levels, available, "quarterly" if frequency == "Q" else "level")


@pytest.mark.parametrize("future_value", [0.0, -1.0])
def test_appending_nonpositive_level_cannot_change_earlier_log_differences(future_value):
    levels = pd.Series([100.0, 102.0, 101.0])
    before, _ = bp.transform(levels, 2)
    after, _ = bp.transform(pd.concat([levels, pd.Series([future_value], index=[3])]), 2)
    pd.testing.assert_series_equal(after.loc[levels.index], before)


def test_nonpositive_levels_only_remove_their_adjacent_log_differences():
    levels = pd.Series([100.0, 101.0, 0.0, 102.0, 104.0, -2.0, 106.0, 108.0])
    actual, note = bp.transform(levels, 2)
    expected = pd.Series([np.nan, np.log(101.0) - np.log(100.0), np.nan, np.nan,
                          np.log(104.0) - np.log(102.0), np.nan, np.nan,
                          np.log(108.0) - np.log(106.0)])
    pd.testing.assert_series_equal(actual, expected)
    assert "4 invalid adjacent pairs" in note
    assert "non-positive" in note and "missing" in note


@pytest.mark.parametrize("frequency", ["M", "Q"])
@pytest.mark.parametrize("future_change", ["append", "mutate"])
def test_future_nonpositive_input_cannot_change_earlier_realtime_rows(calendar, frequency, future_change):
    original = raw_series(61, np.arange(100.0, 112.0), frequency)
    earlier_end = original.values.index[-2].asfreq("M", "end")
    before, _ = bp.realtime_panel({61: original}, calendar, end=earlier_end)
    later_values = np.arange(100.0, 113.0) if future_change == "append" else original.values.to_numpy().copy()
    later_values[-1] = -1.0
    changed = raw_series(61, later_values, frequency)
    after, _ = bp.realtime_panel({61: changed}, calendar, end=earlier_end)
    assert before.notna().any().any()
    pd.testing.assert_frame_equal(after, before)


@pytest.mark.parametrize("number", [22, 25, 64])
@pytest.mark.parametrize("frequency", ["M", "Q"])
def test_realtime_signed_rows_use_declared_differences_even_when_positive(calendar, number, frequency):
    raw = raw_series(number, np.arange(10.0, 22.0), frequency)
    end = raw.values.index[-1].asfreq("M", "end")
    panel, report = bp.realtime_panel({number: raw}, calendar, end=end)
    assert np.allclose(panel[f"a6_{number:02d}"].dropna(), 1.0)
    note = report["rows"][number]["transform"]
    assert f"row {number}" in note and "fixed" in note and "T3" in note


@pytest.mark.parametrize("number", [22, 25, 64])
def test_paper_signed_rows_use_the_same_declared_differences(number):
    raw = raw_series(number, np.arange(10.0, 22.0))
    indicator = raw_series(11, np.arange(100.0, 112.0))
    audit = pd.DataFrame({"number": [11, number], "seasonal_adjustment": ["", ""]})
    panel, report = bp.paper_panel({11: indicator, number: raw}, audit, end=pd.Period("2002-12", "M"))
    assert np.allclose(panel[f"a6_{number:02d}"], 1.0)
    note = report["rows"][number]["transform"]
    assert f"row {number}" in note and "fixed" in note and "T3" in note


def test_positive_log_differences_and_other_transform_codes_are_unchanged():
    levels = pd.Series([100.0, 105.0, np.nan, 103.0, 106.0])
    for code, expected in [(0, levels), (2, np.log(levels).diff()), (3, levels.diff())]:
        actual, note = bp.transform(levels, code)
        pd.testing.assert_series_equal(actual, expected)
        assert note == f"T{code}"


def test_realtime_fuel_component_records_its_fixed_signed_policy(calendar):
    raw = raw_series(64, np.arange(100.0, 150.0))
    raw.kind = "components"
    raw.components = {"petrol": (raw.values, raw.available),
                      "diesel": (raw.values + np.sin(np.arange(50)), raw.available)}
    panel, report = bp.realtime_panel({64: raw}, calendar, end=raw.values.index[-1])
    assert panel.a6_64.notna().any()
    note = report["rows"][64]["transform"]
    assert "row 64" in note and "fixed" in note and "T3" in note
