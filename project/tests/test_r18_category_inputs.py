"""R18 category source gates and offline snapshot integrity."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

MODULE = Path(__file__).resolve().parents[1] / "tools/research_r18/category_inputs.py"


def module():
    assert MODULE.exists(), "R18 category input module has not been implemented"
    spec = importlib.util.spec_from_file_location("r18_category_inputs_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_availability_respects_detail_not_flash_and_origin_calendar():
    mod = module()
    levels = pd.DataFrame({"actual_rent": [100.0, 101.0]}, index=pd.Index(["2026-01", "2026-02"], name="target_month"))
    availability = pd.DataFrame({"target_month": ["2026-01", "2026-02"], "available_from": ["2026-02-13", "2026-03-10"]})
    assert mod.levels_asof(levels, availability, "2026-02-12").empty
    assert mod.levels_asof(levels, availability, "2026-02-13").index.tolist() == ["2026-01"]
    assert mod.levels_asof(levels, availability, "2026-03-09").index.tolist() == ["2026-01"]
    assert mod.levels_asof(levels, availability, "2026-03-10").index.tolist() == ["2026-01", "2026-02"]


def test_missing_release_and_invalid_reference_timing_fail_closed():
    mod = module()
    levels = pd.DataFrame({"x": [100.0]}, index=pd.Index(["2026-01"], name="target_month"))
    with pytest.raises(ValueError, match="availability"):
        mod.levels_asof(levels, pd.DataFrame({"target_month": [], "available_from": []}), "2026-03-01")
    with pytest.raises(ValueError, match="reference month"):
        mod.levels_asof(levels, pd.DataFrame({"target_month": ["2026-01"], "available_from": ["2026-01-15"]}), "2026-03-01")


def test_frozen_package_has_broad_goods_services_housing_and_matches_old_five():
    mod = module()
    levels, meta, availability = mod.load_categories(primary=False)
    primary, _, _ = mod.load_categories(primary=True)
    assert levels.shape == (139, 37)
    assert primary.shape == (139, 18)
    assert set(meta.loc[meta.primary_measurement, "sector"]) == {"goods", "housing", "services"}
    assert levels.notna().all().all()
    assert levels.index[0] == "2015-01" and levels.index[-1] == "2026-07"
    old = pd.read_csv(MODULE.parents[2] / "data/core_split/monthly_levels.csv", index_col="target_month")
    pd.testing.assert_frame_equal(levels[old.columns], old, check_freq=False)
    assert (pd.to_datetime(availability.available_from) > pd.PeriodIndex(availability.target_month, freq="M").to_timestamp(how="end")).all()


def test_duplicate_source_rows_are_rejected():
    mod = module()
    raw = pd.DataFrame({"IndicatorType": ["6134", "6134"], "TYPUDAJE4A": ["IZ2015"] * 2,
                        "EKAKTIOCDS": ["0"] * 2, "UZ02P": ["CZ"] * 2,
                        "CASMKMQRM12": ["2015-01"] * 2, "CZCOICOP2.CZCOP1": ["04"] * 2,
                        "CZCOICOP2.CZCOP23": ["041"] * 2, "Hodnota": ["99.7"] * 2})
    with pytest.raises(ValueError, match="duplicate"):
        mod.extract_levels(raw, required_codes={"041": "actual_rent"})
