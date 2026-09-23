"""Independent R20 review probes; implementations and frozen sources stay intact."""
from pathlib import Path
import math
import sys

import numpy as np
import pandas as pd
import pytest

from models.current_path import BLOCKS, MODELS, forecast_current_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def example():
    from forecast_independent import fixture_frames
    from models.food_path_r14 import load_inputs

    frames = fixture_frames()
    food, available, _ = load_inputs()
    pump = pd.read_csv(ROOT / "data/research_r14/fuel/pump_weekly.csv",
                       index_col=0, parse_dates=True, float_precision="round_trip")
    h0 = pd.read_csv(ROOT / "output/independent_nowcast_forecasts.csv",
                     index_col="period", float_precision="round_trip").iloc[0]
    origin = pd.Period(h0.name, "M")
    clock = pd.Timestamp(h0.as_of_eve).tz_localize("Europe/Prague")
    point = float(h0.HARD_BASE)
    result = forecast_current_path(frames, food, available, pump, origin, clock, point)
    return frames, food, available, pump, origin, clock, point, result


def test_review_real_fixture_accounts_for_every_horizon(example):
    frames, _, _, _, origin, _, point, result = example
    table = result["monthly"]
    assert len(table) == 39
    assert not table.duplicated(["origin", "h", "model"]).any()
    assert set(table.model) == set(MODELS)
    for _, rows in table.groupby("model"):
        rows = rows.set_index("h")
        assert rows.index.tolist() == list(range(13))
        assert rows.loc[0, "mm_forecast"] == point
        for h in range(13):
            row = rows.loc[h]
            if h:
                values = [row["contribution_" + block] for block in BLOCKS]
                assert row.mm_forecast == pytest.approx(math.fsum(values), abs=1e-12)
                assert math.fsum(row[c] for c in rows if c.startswith("weight_")) == pytest.approx(1.)
            window = pd.period_range(origin + h - 11, origin + h, freq="M")
            rates = [frames["headline"].iloc[:, 0].loc[m] if m < origin
                     else rows.loc[(m - origin).n, "mm_forecast"] for m in window]
            annual = 100 * (math.prod(1 + value / 100 for value in rates) - 1)
            assert row.yy_exante == pytest.approx(annual, abs=1e-11)


def test_review_one_origin_matches_frozen_components(example):
    *_, origin, clock, point, result = example
    sources = dict(zip(MODELS, (
        "output/research_r15/native_forecasts.csv",
        "output/research_r14b/integration/native_forecasts.csv",
        "output/research_r16/native_forecasts.csv")))
    for model, source in sources.items():
        frozen = pd.read_csv(ROOT / source, float_precision="round_trip")
        frozen = frozen.loc[frozen.model.eq(model) & frozen.origin.eq(str(origin))].set_index("h").sort_index()
        actual = result["monthly"].loc[result["monthly"].model.eq(model)].set_index("h").sort_index()
        assert actual.index.equals(frozen.index)
        for column in ["mm_forecast"] + [c for c in actual if c.startswith(("value_", "weight_", "contribution_"))]:
            np.testing.assert_array_equal(np.isfinite(actual[column]), np.isfinite(frozen[column]))
            np.testing.assert_allclose(actual[column], frozen[column], atol=1e-8, rtol=0, equal_nan=True)


def test_review_full_path_excludes_future_values(example):
    frames, food, available, pump, origin, clock, point, baseline = example
    frames = {name: frame.copy() for name, frame in frames.items()}
    for frame in frames.values():
        if isinstance(frame.index, pd.PeriodIndex):
            frame.loc[frame.index >= origin, :] = 9999.
    food = food.copy()
    food.loc[food.index >= origin, :] = 9999.
    for column in food:
        release = pd.to_datetime(available[column], utc=True)
        food.loc[release.gt(clock), column] = 9999.
    pump = pump.copy()
    pump.loc[pump.index + pd.Timedelta(days=7) > clock.tz_localize(None), :] = 9999.
    actual = forecast_current_path(frames, food, available, pump, origin, clock, point)
    pd.testing.assert_frame_equal(actual["monthly"], baseline["monthly"], check_exact=True)


def test_review_h0_contributions_preserved_for_all_models(example):
    frames, food, available, pump, origin, clock, point, _ = example
    contributions = dict.fromkeys(BLOCKS, 0.)
    contributions["core"] = point
    result = forecast_current_path(frames, food, available, pump, origin, clock, point, contributions)
    for row in result["monthly"].query("h == 0").itertuples():
        assert row.mm_forecast == point
        for block, value in contributions.items():
            assert getattr(row, "contribution_" + block) == value


@pytest.mark.parametrize("invalid", ["missing_core", "duplicate_components"])
def test_review_invalid_relevant_monthly_inputs_fail(example, invalid):
    frames, food, available, pump, origin, clock, point, _ = example
    frames = {name: frame.copy() for name, frame in frames.items()}
    if invalid == "missing_core":
        frames["core"].loc[origin - 1, :] = np.nan
    else:
        frames["components"] = pd.concat([frames["components"], frames["components"].loc[[origin - 1]]]).sort_index()
    with pytest.raises(ValueError):
        forecast_current_path(frames, food, available, pump, origin, clock, point)


@pytest.mark.parametrize("missing", ["one_row", "all_rows"])
def test_review_parity_rejects_incomplete_annual_reference(monkeypatch, tmp_path, missing):
    """A partial inner join must not receive a successful parity certificate."""
    import forecast_independent
    import models.food_path_r14
    from tools.current_path import audit_parity

    actual = pd.DataFrame([dict(origin="2019-02", h=h, model=model,
                                mm_forecast=.2, yy_exante=2.4)
                           for model in MODELS for h in range(13)])
    annual = actual.iloc[:-1].copy() if missing == "one_row" else actual.iloc[:0].copy()
    points = pd.DataFrame({"as_of_eve": ["2019-03-10T23:59:00"], "HARD_BASE": [.2]},
                          index=pd.Index(["2019-02"], name="period"))

    def source(path, *args, **kwargs):
        name = str(path).replace("\\", "/")
        if name.endswith("independent_nowcast_forecasts.csv"):
            return points.copy()
        if name.endswith("research_r18/path_v2/forecasts.csv"):
            return annual.copy()
        if name.endswith("pump_weekly.csv"):
            return pd.DataFrame()
        return actual.copy()

    monkeypatch.setattr(forecast_independent, "fixture_frames", lambda: {})
    monkeypatch.setattr(models.food_path_r14, "load_inputs", lambda: (None, None, None))
    monkeypatch.setattr(audit_parity.pd, "read_csv", source)
    monkeypatch.setattr(audit_parity, "forecast_current_path", lambda *args, **kwargs: {"monthly": actual.copy()})
    monkeypatch.setattr(sys, "argv", ["audit_parity", "--output", str(tmp_path / "audit")])
    with pytest.raises((ValueError, AssertionError), match="(?i)(annual|year|39|coverage|reference|parity)"):
        audit_parity.main()
