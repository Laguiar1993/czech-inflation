"""The Bloomberg capture is imported as a separate, unvalidated candidate panel."""
import hashlib
import json

import pandas as pd
import pytest

from tools.paper_replication import import_bloomberg_candidates as imp

TICKERS = {"EUR3CZ Index": "czech_retail_orders_expectations_next3m", "PRIB03M Index": "pribor_3m",
           "EEUR3CZ Index": "czech_retail_orders_expectations_literal_candidate"}


def _snapshot(tmp_path):
    folder = tmp_path / "snap"
    (folder / "raw").mkdir(parents=True)
    dates = pd.to_datetime(["2026-06-30", "2026-07-01", "2026-07-15", "2026-07-31",
                            "2026-08-03", "2026-08-31", "2026-09-02"])
    daily = pd.DataFrame({"EUR3CZ Index": [14.0, None, None, 14.1, None, 12.4, None],
                          "PRIB03M Index": [3.5, 3.6, 3.7, 3.9, 3.9, 3.8, 3.86]}, index=dates)
    daily.to_csv(folder / "daily.csv", index_label="observation_date")
    request = {"retrieved_at": "2026-09-11T10:27:41+00:00", "end_date": "2026-09-10",
               "tickers": TICKERS, "status": "partial"}
    (folder / "request.json").write_text(json.dumps(request), encoding="utf-8")
    metadata = {
        "EUR3CZ Index": {"fields": {"EUR3CZ Index": {"name": "EC Retail Trade Confidence Cze",
                                                      "seasonality_and_transformation": "% Balance/Diffusion Index NSA"}}},
        "PRIB03M Index": {"fields": {"PRIB03M Index": {"name": "Czech Interbank Offered Rates", "crncy": "CZK"}}},
    }
    (folder / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (folder / "errors.json").write_text(json.dumps([{"ticker": "EEUR3CZ Index", "stage": "bdh"}]), encoding="utf-8")
    pd.DataFrame([{"ticker": "EUR3CZ Index", "status": "ok"}, {"ticker": "PRIB03M Index", "status": "ok"},
                  {"ticker": "EEUR3CZ Index", "status": "error", "error": "No historical data"}]).to_csv(
        folder / "coverage.csv", index=False)
    (folder / "raw" / "pribor_3m_bdh.csv").write_text("raw", encoding="utf-8")
    hashes = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in folder.rglob("*") if p.is_file()}
    (folder / "MANIFEST.json").write_text(json.dumps({"sha256": hashes}), encoding="utf-8")
    return folder


def test_import_builds_a_separate_candidate_panel(tmp_path):
    out = tmp_path / "out"
    manifest = imp.import_snapshot(_snapshot(tmp_path), out)
    long = pd.read_csv(out / "candidate_periods_long.csv", dtype={"period": str})

    retail = long[long.ticker.eq("EUR3CZ Index")].set_index("period")
    assert retail.statistic.unique().tolist() == ["as_reported"]
    assert retail.value.to_dict() == {"2026-06": 14.0, "2026-07": 14.1, "2026-08": 12.4}
    assert retail.loc["2026-08", "available_from_assumed"] == "2026-09-01"
    assert retail.loc["2026-08", "bdp_seasonality"].endswith("NSA")  # label preserved, not interpreted
    assert set(long.validation_status) == {"unvalidated_candidate"}

    pribor = long[long.ticker.eq("PRIB03M Index")].set_index(["statistic", "period"])
    assert pribor.loc[("month_mean", "2026-07"), "value"] == pytest.approx((3.6 + 3.7 + 3.9) / 3)
    assert pribor.loc[("month_last", "2026-08"), "value"] == 3.8
    assert pribor.loc[("month_last", "2026-08"), "available_from_assumed"] == "2026-09-01"
    assert "2026-09" not in set(long.period)  # month-to-date quotes are not monthly observations

    wide = pd.read_csv(out / "candidate_monthly_wide.csv")
    assert all(col == "period" or col.startswith("bbg__") for col in wide.columns)
    catalog = pd.read_csv(out / "candidate_catalog.csv").set_index("ticker")
    assert catalog.loc["EEUR3CZ Index", "import_status"] == "no_data"
    assert catalog.loc["EEUR3CZ Index", "role"] == "invalid_ticker"
    assert manifest["tickers_with_data"] == 2 and manifest["tool"] == imp.TOOL


def test_tampered_snapshot_is_rejected(tmp_path):
    folder = _snapshot(tmp_path)
    (folder / "daily.csv").write_text((folder / "daily.csv").read_text() + "\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        imp.import_snapshot(folder, tmp_path / "out")


def test_unlisted_snapshot_file_is_rejected(tmp_path):
    folder = _snapshot(tmp_path)
    (folder / "extra.csv").write_text("x")
    with pytest.raises(ValueError, match="unlisted"):
        imp.import_snapshot(folder, tmp_path / "out")


def test_existing_folder_is_replaced_only_when_it_is_this_tools_output(tmp_path):
    folder, out = _snapshot(tmp_path), tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("user file")
    with pytest.raises(FileExistsError):
        imp.import_snapshot(folder, out, replace=True)
    assert (out / "keep.txt").exists()
    other = tmp_path / "own"
    imp.import_snapshot(folder, other)
    imp.import_snapshot(folder, other, replace=True)


def test_monthly_statistics_must_be_dated_at_period_end():
    cand = imp.Candidate((33,), "a6_candidate", "monthly", "ec_bcs_next_month")
    series = pd.Series([1.0], index=pd.to_datetime(["2026-08-15"]))
    with pytest.raises(ValueError, match="period end"):
        imp.monthly_rows("X Index", "x", cand, series, pd.Timestamp("2026-09-10"))


def test_registry_covers_the_full_refresh_request():
    path = imp.DEFAULT_SNAPSHOT / "request.json"
    if not path.exists():
        pytest.skip("11 September snapshot not present")
    requested = json.loads(path.read_text(encoding="utf-8"))["tickers"]
    assert set(requested) == set(imp.REGISTRY)
    assert imp.REGISTRY["EEUR3CZ Index"].role == "invalid_ticker"
    assert imp.REGISTRY["EUR3CZ Index"].a6 == (33,)
    assert {t for t, c in imp.REGISTRY.items() if 10 in c.a6} == {"EUA2CZ Index", "EUA4CZ Index"}
