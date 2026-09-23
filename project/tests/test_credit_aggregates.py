"""Regression tests for the ARAD client-loan aggregation."""

import pandas as pd
import pytest


def test_nfc_balance_uses_total_once_when_total_and_maturity_buckets_are_present():
    from data.local_adapter import _nfc_balance_from_pivot

    pivot = pd.DataFrame(
        {
            "nfc_total": [100.0],
            "nfc_short": [40.0],
            "nfc_medium": [30.0],
            "nfc_long": [30.0],
        },
        index=pd.period_range("2020-01", periods=1, freq="M"),
    )

    out = _nfc_balance_from_pivot(
        pivot,
        total_id="nfc_total",
        bucket_ids=("nfc_short", "nfc_medium", "nfc_long"),
    )
    assert out.iloc[0] == pytest.approx(100.0)


def test_nfc_balance_falls_back_to_three_maturity_buckets_without_total():
    from data.local_adapter import _nfc_balance_from_pivot

    pivot = pd.DataFrame(
        {
            "nfc_short": [40.0],
            "nfc_medium": [30.0],
            "nfc_long": [30.0],
        },
        index=pd.period_range("2020-01", periods=1, freq="M"),
    )

    out = _nfc_balance_from_pivot(
        pivot,
        total_id="nfc_total",
        bucket_ids=("nfc_short", "nfc_medium", "nfc_long"),
    )
    assert out.iloc[0] == pytest.approx(100.0)


def test_paper_panel_uses_the_nfc_total_once():
    from paper_replication_experiment import _nfc_balance_from_pivot

    pivot = pd.DataFrame(
        {
            "SUCM100311XXX101101": [100.0],
            "SUCM200311XXX101101": [40.0],
            "SUCM300311XXX101101": [30.0],
            "SUCM400311XXX101101": [30.0],
        },
        index=pd.period_range("2020-01", periods=1, freq="M"),
    )

    assert _nfc_balance_from_pivot(pivot).iloc[0] == pytest.approx(100.0)
