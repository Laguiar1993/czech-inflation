"""Frozen core-split sources, strict calendars and origin-available base weights."""
import hashlib
import importlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest


CATEGORIES = ["actual_rent", "imputed_rent", "catering", "accommodation", "package_holidays"]
FROZEN = Path(__file__).resolve().parent / "data" / "core_split"


def api():
    try:
        module = importlib.import_module("data.core_split")
    except ModuleNotFoundError:
        pytest.fail("Frozen core-split input loader is not implemented")
    assert hasattr(module, "load_frozen"), "Frozen core-split input loader is not implemented"
    return module


def copy_frozen(tmp_path):
    return Path(shutil.copytree(FROZEN, tmp_path / "frozen"))


def rehash(root, filename):
    path = root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    data = (root / filename).read_bytes()
    manifest["files"][filename] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_frozen_sources_are_narrow_contiguous_and_described():
    result = api().load_frozen()
    assert set(result) == {"levels", "broad_yoy", "weights", "metadata"}
    levels = result["levels"]
    assert list(levels) == CATEGORIES
    pd.testing.assert_index_equal(levels.index, pd.period_range("2015-01", "2026-07", freq="M", name="target_month"))
    assert levels.shape == (139, 5)
    assert levels.loc["2015-01", "actual_rent"] == pytest.approx(99.7)
    broad = result["broad_yoy"]
    assert list(broad) == ["goods", "services"]
    pd.testing.assert_index_equal(broad.index, pd.period_range("2003-01", "2026-07", freq="M", name="target_month"))
    assert broad.loc["2003-01", "goods"] == pytest.approx(-2.3)
    assert len(result["weights"]) == 35
    metadata = result["metadata"]
    assert metadata["broad_yoy"]["series"] == {"SCPICLEM02YOYPECNA": "goods", "SCPICLEM03YOYPECNA": "services"}
    assert metadata["broad_yoy"]["seasonal_adjustment"] == "NSA"
    assert "tax" in metadata["broad_yoy"]["tax_treatment"].lower()
    assert "midnight" in metadata["weights"]["intraday_note"].lower()
    assert "not" in metadata["weights"]["publication_status"].lower()
    assert "base" in metadata["weights"]["not_current_shares"].lower()
    assert metadata["services_proxy_audit"]["division_codes"] == ["06", "08", "10", "11", "12", "13"]
    assert metadata["services_proxy_audit"]["official_services_index"] is False


def test_all_canonical_values_reconcile_to_the_retained_source_extracts():
    result = api().load_frozen()
    for code, name in result["metadata"]["broad_yoy"]["series"].items():
        raw = json.loads((FROZEN / "raw" / f"{code}.json").read_text(encoding="utf-8"))
        indicator = raw["data"][0]["indicators"][0]
        assert indicator["code"] == code
        points = indicator["snapshots_data"][0]["chart_data"]
        index = pd.PeriodIndex(pd.to_datetime([p[0] for p in points], format="%m.%Y"), freq="M", name="target_month")
        expected = pd.Series([p[1] for p in points], index=index, name=name, dtype=float)
        pd.testing.assert_series_equal(result["broad_yoy"][name], expected)
    raw = pd.read_csv(FROZEN / "raw" / "selected_category_levels.csv", dtype={"subgroup_code": str})
    mapping = result["metadata"]["levels"]["series"]
    raw = raw.loc[raw.base.eq("base_2015_eq_100") & raw.subgroup_code.isin(mapping)]
    assert len(raw) == 695
    assert not raw.duplicated(["date", "subgroup_code"]).any()
    expected = raw.pivot(index="date", columns="subgroup_code", values="value").rename(columns=mapping)[CATEGORIES]
    expected.index = pd.PeriodIndex(pd.to_datetime(expected.index), freq="M", name="target_month")
    expected.columns.name = None
    pd.testing.assert_frame_equal(result["levels"], expected.astype(float))
    basket = pd.read_csv(FROZEN / "raw" / "basket_selected_rows.csv")
    for row in result["weights"].itertuples():
        hit = basket.loc[basket.source_file.eq(row.source_file) & basket.sheet_name.eq(row.source_sheet)
                         & basket.excel_row.eq(int(row.source_cell[1:]))]
        assert len(hit) == 1
        assert float(hit.column_5.iloc[0]) == row.weight_permille


def test_archived_proxy_arithmetic_proof_supports_the_recorded_audit_facts():
    result = api().load_frozen()
    proof = pd.read_csv(FROZEN / "audit" / "arithmetic_proof.csv")
    facts = result["metadata"]["services_proxy_audit"]
    assert len(proof) == facts["arithmetic_rows"] == 834
    assert (proof.stored_value - proof.arithmetic_mean).abs().max() < 1e-10
    level_rows = proof.loc[proof.base.eq("base_2015_eq_100")]
    assert level_rows.n.eq(6).all()
    assert proof.difference_to_arithmetic.abs().max() == pytest.approx(facts["maximum_absolute_difference"], abs=1e-18)


@pytest.mark.parametrize("filename", ["monthly_levels.csv", "broad_yoy.csv", "selected_basket_weights.csv", "canonical_metadata.json", "raw/SCPICLEM02YOYPECNA.json", "audit/arithmetic_proof.csv"])
def test_any_consumed_or_evidence_file_tamper_is_rejected(tmp_path, filename):
    api()
    root = copy_frozen(tmp_path)
    with (root / filename).open("ab") as handle:
        handle.write(b"\nTAMPER")
    with pytest.raises(ValueError, match="SHA256|hash|integrity"):
        api().load_frozen(root)


def test_manifest_cannot_omit_a_canonical_input(tmp_path):
    api()
    root = copy_frozen(tmp_path)
    path = root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["files"]["monthly_levels.csv"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest|integrity"):
        api().load_frozen(root)


@pytest.mark.parametrize("filename", ["monthly_levels.csv", "broad_yoy.csv"])
@pytest.mark.parametrize("edge", ["first", "last"])
def test_declared_source_coverage_rejects_cropped_calendar_edges(tmp_path, filename, edge):
    api()
    root = copy_frozen(tmp_path)
    frame = pd.read_csv(root / filename)
    frame = frame.iloc[1:] if edge == "first" else frame.iloc[:-1]
    frame.to_csv(root / filename, index=False)
    rehash(root, filename)
    with pytest.raises(ValueError, match="coverage|month|calendar"):
        api().load_frozen(root)


@pytest.mark.parametrize("filename", ["monthly_levels.csv", "broad_yoy.csv"])
@pytest.mark.parametrize("damage", ["duplicate", "missing_month", "unsorted", "invalid_month", "missing_value", "empty"])
def test_loaded_calendars_are_never_silently_repaired(tmp_path, filename, damage):
    api()
    root = copy_frozen(tmp_path)
    frame = pd.read_csv(root / filename)
    if damage == "duplicate":
        frame = pd.concat([frame.iloc[:3], frame.iloc[[2]], frame.iloc[3:]], ignore_index=True)
    elif damage == "missing_month":
        frame = frame.drop(index=2)
    elif damage == "unsorted":
        frame = frame.iloc[::-1]
    elif damage == "invalid_month":
        frame.loc[2, "target_month"] = "2015-03-17"
    elif damage == "missing_value":
        frame.iloc[2, 1] = np.nan
    else:
        frame = frame.iloc[:0]
    frame.to_csv(root / filename, index=False)
    rehash(root, filename)
    with pytest.raises(ValueError, match="month|calendar|finite|missing|empty|contiguous|duplicate|order"):
        api().load_frozen(root)


@pytest.mark.parametrize("filename,value", [("monthly_levels.csv", 0.0), ("monthly_levels.csv", -1.0), ("monthly_levels.csv", np.inf), ("broad_yoy.csv", -100.0), ("broad_yoy.csv", -101.0), ("broad_yoy.csv", np.inf)])
def test_invalid_level_or_gross_inflation_is_rejected(tmp_path, filename, value):
    api()
    root = copy_frozen(tmp_path)
    frame = pd.read_csv(root / filename)
    frame.iloc[2, 1] = value
    frame.to_csv(root / filename, index=False)
    rehash(root, filename)
    with pytest.raises(ValueError, match="positive|finite|100|gross"):
        api().load_frozen(root)


def test_monthly_rates_are_percentage_changes_invariant_to_each_series_rebasing():
    levels = api().load_frozen()["levels"]
    got = api().monthly_rates(levels)
    assert got.iloc[0].isna().all()
    assert got.iloc[1:].notna().all().all()
    assert got.loc["2015-02", "actual_rent"] == pytest.approx(100 * (99.9 / 99.7 - 1))
    factors = pd.Series([0.01, 2., 7.5, 100., 0.003], index=CATEGORIES)
    pd.testing.assert_frame_equal(got, api().monthly_rates(levels * factors), atol=1e-12, rtol=1e-12)


@pytest.mark.parametrize("damage", ["gap", "duplicate", "missing", "zero", "datetime_index"])
def test_monthly_rates_validate_before_change_and_never_fill(damage):
    levels = api().load_frozen()["levels"]
    if damage == "gap":
        levels = levels.drop(levels.index[2])
    elif damage == "duplicate":
        levels = pd.concat([levels.iloc[:3], levels.iloc[[2]], levels.iloc[3:]])
    elif damage == "missing":
        levels.iloc[2, 1] = np.nan
    elif damage == "zero":
        levels.iloc[2, 1] = 0.0
    else:
        levels.index = levels.index.to_timestamp()
    with pytest.raises(ValueError, match="PeriodIndex|contiguous|duplicate|finite|positive"):
        api().monthly_rates(levels)


def test_weights_switch_at_the_approved_local_midnight_boundary():
    weights = api().load_frozen()["weights"]
    before = api().weights_at(weights, "2026-01", "2026-02-12 23:59:59")
    at = api().weights_at(weights, pd.Period("2026-01", "M"), "2026-02-13 00:00:00")
    assert list(at.index) == CATEGORIES
    assert at.loc["actual_rent"] == pytest.approx(34.497805 / 1000)
    assert before.loc["actual_rent"] == pytest.approx(33.184542 / 1000)
    assert at.attrs["effective_year"] == 2026
    assert before.attrs["effective_year"] == 2024
    assert 0 < at.sum() < 1
    # UTC clocks are interpreted against Czech local midnight, never stripped.
    pd.testing.assert_series_equal(at, api().weights_at(weights, "2026-01", "2026-02-12T23:00:00Z"))
    pd.testing.assert_series_equal(before, api().weights_at(weights, "2026-01", "2026-02-12T22:59:59Z"))


def test_future_weight_values_and_even_early_published_future_years_do_not_leak():
    weights = api().load_frozen()["weights"]
    original = api().weights_at(weights, "2024-01", "2024-02-14 23:59:59")
    poisoned = weights.copy()
    poisoned.loc[poisoned.effective_year.ge(2024), "weight_permille"] *= 1.4
    pd.testing.assert_series_equal(original, api().weights_at(poisoned, "2024-01", "2024-02-14 23:59:59"))
    # A later clock alone must not make the 2026 basket effective for a 2025 origin.
    old = api().weights_at(weights, "2025-12", "2026-03-01")
    assert old.attrs["effective_year"] == 2024
    poisoned.loc[poisoned.effective_year.eq(2026), "availability_assumption_date"] = "2023-01-01"
    assert api().weights_at(poisoned, "2025-12", "2026-03-01").attrs["effective_year"] == 2024


def test_weights_choose_latest_known_effective_regime_even_when_rows_are_shuffled():
    weights = api().load_frozen()["weights"]
    got = api().weights_at(weights.sample(frac=1, random_state=7), "2023-12", "2024-03-01")
    assert got.attrs["effective_year"] == 2022
    assert got.loc["imputed_rent"] == pytest.approx(122.207014 / 1000)


@pytest.mark.parametrize("damage", ["duplicate", "missing_group", "unknown_group", "zero", "negative", "nonfinite", "sum_at_least_one", "odd_regime", "fractional_regime", "missing_date", "mixed_date", "intraday_date"])
def test_invalid_weight_regime_is_rejected(damage):
    weights = api().load_frozen()["weights"]
    if damage == "duplicate":
        weights = pd.concat([weights, weights.iloc[[0]]], ignore_index=True)
    elif damage == "missing_group":
        weights = weights.iloc[1:].copy()
    elif damage == "unknown_group":
        weights.loc[0, "series_name"] = "cultural_services"
    elif damage in {"zero", "negative", "nonfinite"}:
        weights.loc[0, "weight_permille"] = {"zero": 0.0, "negative": -1.0, "nonfinite": np.inf}[damage]
    elif damage == "sum_at_least_one":
        weights.loc[weights.effective_year.eq(2014), "weight_permille"] = 200.0
    elif damage in {"odd_regime", "fractional_regime"}:
        weights["effective_year"] = weights.effective_year.astype(float)
        weights.loc[weights.effective_year.eq(2014), "effective_year"] = 2015 if damage == "odd_regime" else 2014.5
    elif damage == "missing_date":
        weights.loc[0, "availability_assumption_date"] = None
    elif damage == "mixed_date":
        weights.loc[0, "availability_assumption_date"] = "2014-02-13"
    else:
        weights.loc[weights.effective_year.eq(2014), "availability_assumption_date"] = "2014-02-12 09:00:00"
    with pytest.raises(ValueError, match="weight|regime|categor|date|group"):
        api().weights_at(weights, "2026-01", "2026-03-01")


def test_no_known_weight_regime_raises_instead_of_using_future_basket():
    weights = api().load_frozen()["weights"]
    for origin, clock in [("2013-12", "2015-01-01"), ("2014-01", "2014-02-11")]:
        with pytest.raises(ValueError, match="known|available|eligible"):
            api().weights_at(weights, origin, clock)
