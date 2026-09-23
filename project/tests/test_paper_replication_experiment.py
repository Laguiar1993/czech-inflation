"""Wiring tests for the CNB A6 paper-comparison lane."""

import numpy as np
import pandas as pd


def test_a6_dictionary_has_72_unique_numbers():
    from paper_replication_experiment import A6

    assert len(A6) == 72
    assert [row.number for row in A6] == list(range(1, 73))


def test_paper_policies_keep_hard_data_and_remove_expectations():
    from paper_replication_experiment import _policy_panel

    index = pd.period_range("2020-01", periods=4, freq="M")
    panel = pd.DataFrame({"a6_11": [1, 2, 3, 4], "a6_70": [2, 2, 2, 2], "a6_29": [1, 1, 1, 1]}, index=index)
    audit = pd.DataFrame(
        {
            "number": [11, 70, 29],
            "kind": ["hard", "expectation", "survey"],
        }
    )
    assert list(_policy_panel(panel, audit, "paper_independent").columns) == ["a6_11"]
    assert list(_policy_panel(panel, audit, "paper_sentiment").columns) == ["a6_11", "a6_29"]
    assert list(_policy_panel(panel, audit, "paper_full").columns) == ["a6_11", "a6_70", "a6_29"]


def test_signed_trade_transform_is_finite_across_zero():
    from paper_replication_experiment import _signed_log_difference

    s = pd.Series([-10.0, -1.0, 0.0, 1.0, 10.0])
    out = _signed_log_difference(s)
    assert np.isfinite(out.dropna()).all()
    assert out.iloc[2] != 0.0


def test_period_index_accepts_existing_monthly_periods():
    from paper_replication_experiment import _period_index

    source = pd.period_range("2020-01", periods=3, freq="M")
    out = _period_index(source)
    assert isinstance(out, pd.PeriodIndex)
    assert out.tolist() == source.tolist()


def test_missing_german_retail_confidence_is_not_replaced_by_retail_growth():
    from paper_replication_experiment import build_paper_panel

    _, _, audit, _ = build_paper_panel()
    row = audit.loc[audit["number"].eq(20)].iloc[0]
    assert row["status_in_run"] == "missing"
    assert pd.isna(row["source_column"])
