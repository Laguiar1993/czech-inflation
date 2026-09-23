"""CNB LUCI tidy step for Table A6 rows 15-16."""
import json

import pandas as pd
import pytest

from tools.paper_replication import cnb_luci as luci


def test_a_report_observes_quarters_up_to_two_before_its_own():
    assert luci.last_observed_quarter(pd.Timestamp("2026-08-13")) == pd.Period("2026Q1", freq="Q")
    assert luci.last_observed_quarter(pd.Timestamp("2026-02-12")) == pd.Period("2025Q3", freq="Q")


def test_availability_uses_listed_report_dates_then_the_declared_fallback():
    quarters = pd.PeriodIndex(["2025Q4", "2010Q1"], freq="Q")
    dates = luci.available_from(quarters, ["2026-08-13", "2026-05-14"])
    assert dates == [pd.Timestamp("2026-05-14"), pd.Timestamp("2010-08-15")]


def test_roman_quarter_labels():
    assert luci.roman_quarter("IV/2019") == pd.Period("2019Q4", freq="Q")
    assert luci.roman_quarter(None) is None
    assert luci.roman_quarter("LUCI") is None


def _ms(text):
    return int(pd.Timestamp(text).value // 10**6)


def _payload(stamps):
    return {"data": [{"indicators": [{"code": "A", "snapshots_data": [
        {"id": 95, "data": [[stamps[0], 1.0], [stamps[1], None]]},
        {"id": 93, "data": [[stamps[0], 9.0]]},
    ]}]}]}


def test_read_arad_takes_one_snapshot_dated_at_quarter_ends(tmp_path):
    path = tmp_path / "arad.json"
    path.write_text(json.dumps(_payload([_ms("2000-03-31"), _ms("2000-06-30")])), encoding="utf-8")
    frame = luci.read_arad(path, 95)
    assert frame.index.astype(str).tolist() == ["2000Q1", "2000Q2"]
    assert frame.A.iloc[0] == 1.0 and pd.isna(frame.A.iloc[1])
    assert luci.read_arad(path, 93).A.iloc[0] == 9.0
    path.write_text(json.dumps(_payload([_ms("2000-01-01"), _ms("2000-04-01")])), encoding="utf-8")
    with pytest.raises(ValueError):
        luci.read_arad(path, 95)
