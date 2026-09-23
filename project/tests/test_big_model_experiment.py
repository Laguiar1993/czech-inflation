"""Focused contracts for the bounded paper-style model experiment."""

import json

import numpy as np
import pandas as pd
import pytest


def test_panel_variants_partition_expectations_and_sentiment():
    from models.paper_big import panel_variants

    index = pd.period_range("2010-01", periods=3, freq="M")
    frame = pd.DataFrame(
        np.arange(27, dtype=float).reshape(3, 9),
        index=index,
        columns=[
            "ppi_mm_deep",
            "eurczk_mm",
            "median_cpi_mm",
            "esi",
            "conf_business",
            "de_esi",
            "price_expect_survey",
            "price_expect_survey_36m",
            "household_price_expect",
        ],
    )

    variants = panel_variants(frame)
    assert list(variants) == ["independent", "sentiment", "full"]
    assert list(variants["independent"]) == ["ppi_mm_deep", "eurczk_mm", "median_cpi_mm"]
    assert list(variants["sentiment"]) == [
        "ppi_mm_deep",
        "eurczk_mm",
        "median_cpi_mm",
        "esi",
        "conf_business",
        "de_esi",
    ]
    assert list(variants["full"]) == list(frame.columns)


def test_align_extended_headline_reindexes_and_sorts_monthly_panel():
    from big_model_experiment import align_extended_headline

    y = pd.Series(
        [2.0, 3.0, 4.0],
        index=pd.PeriodIndex(["2000-02", "2000-01", "2000-03"], freq="M"),
        name="cpi_mm",
    )
    x = pd.DataFrame(
        {"x": [9.0, 8.0, 7.0, 6.0]},
        index=pd.PeriodIndex(["1999-12", "2000-03", "2000-01", "2000-04"], freq="M"),
    )

    aligned_y, aligned_x = align_extended_headline(y, x)
    assert list(aligned_y.index) == list(pd.period_range("2000-01", "2000-03", freq="M"))
    assert list(aligned_x.index) == list(aligned_y.index)
    assert aligned_x.loc[pd.Period("2000-01", "M"), "x"] == 7.0
    assert pd.isna(aligned_x.loc[pd.Period("2000-02", "M"), "x"])


def test_manifest_records_fixed_horizons_and_panel_columns(tmp_path):
    from big_model_experiment import write_manifest

    path = write_manifest(
        tmp_path,
        script_path=tmp_path / "runner.py",
        model_path=tmp_path / "model.py",
        horizons=(1, 3, 6, 9, 12),
        oos_start="2018-01",
        min_train=60,
        panel_columns={"independent": ["x"], "sentiment": ["x", "esi"], "full": ["x", "esi", "exp"]},
        forecast_rows=10,
        summary_rows=4,
        failure_count=0,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["horizons"] == [1, 3, 6, 9, 12]
    assert payload["oos_start"] == "2018-01"
    assert payload["min_train"] == 60
    assert payload["panel_columns"]["sentiment"] == ["x", "esi"]
    assert payload["forecast_rows"] == 10


def test_quarterly_lci_is_published_after_quarter_end_and_held_between_releases():
    from big_model_experiment import quarterly_lci_to_monthly

    frame = pd.DataFrame(
        {"quarter": ["2020Q1", "2020Q2", "2021Q1", "2021Q2"], "value": [100.0, 110.0, 121.0, 132.0]}
    )
    series = quarterly_lci_to_monthly(frame)
    # 2021Q1 y/y is 21%; it first becomes eligible three months after the
    # quarter end (June), and remains the latest known value until Q2 arrives.
    assert series.loc[pd.Period("2021-06", "M")] == pytest.approx(21.0)
    assert series.loc[pd.Period("2021-07", "M")] == pytest.approx(21.0)
    assert series.loc[pd.Period("2021-09", "M")] == pytest.approx(20.0)


def test_ppi_predictor_names_expose_year_on_year_source_transform():
    from big_model_experiment import _rename_ppi_yoy_columns

    frame = pd.DataFrame(
        [[1.0, 2.0, 3.0]],
        index=pd.period_range("2020-01", periods=1, freq="M"),
        columns=["agri_ppi_mm", "ppi_mm", "ppi_services_mm"],
    )
    renamed = _rename_ppi_yoy_columns(frame)
    assert list(renamed.columns) == ["agri_ppi_yoy", "ppi_yoy", "ppi_services_yoy"]
    pd.testing.assert_frame_equal(renamed, frame.rename(columns={
        "agri_ppi_mm": "agri_ppi_yoy",
        "ppi_mm": "ppi_yoy",
        "ppi_services_mm": "ppi_services_yoy",
    }))


def test_manifest_error_text_redacts_api_keys():
    from big_model_experiment import _safe_error

    text = _safe_error(RuntimeError("https://example.test/?api_key=secret-value&x=1"))
    assert "secret-value" not in text
    assert "api_key=<redacted>" in text
