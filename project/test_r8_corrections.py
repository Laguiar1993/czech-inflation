"""v2.7.1, Codex R8 corrections: (1) the announced energy shock is stored as
per-fuel changes and its headline effect never depends on the administered
weight; (2) the basket item weights used are the ones published at the
clock; (3) documented rows that fire require the call's weight (fail loud);
(4) the food producer-price column follows the CZSO month exceptions;
(5) legacy reconstructed rows keep their block-unit semantics."""
import numpy as np
import pandas as pd
import pytest

import cz_struct as S

COLS = ["announced_regulated_mm_est_pct", "available_from", "provenance", "elec_pct", "gas_pct", "heat_pct"]


def _ann(monkeypatch, rows):
    df = pd.DataFrame(rows)
    for c in COLS:
        if c not in df.columns:
            df[c] = np.nan
    df["p"] = pd.PeriodIndex(df["effective_month"], freq="M")
    df["available_from"] = pd.to_datetime(df["available_from"])
    monkeypatch.setattr(S, "_ANN", df.set_index("p")[COLS])


def test_headline_effect_is_weight_independent(monkeypatch):
    _ann(monkeypatch, [{"effective_month": "2022-01", "available_from": "2021-12-01", "provenance": "sourced_retrospective",
                        "elec_pct": 42.3881, "gas_pct": 68.4562, "heat_pct": 0.0}])
    t = pd.Period("2022-01", "M"); clock = pd.Timestamp("2022-01-31 23:59")
    pp = S._gate_headline_pp(t, clock, "documented")
    for w in (0.10, 0.138, 0.20):
        assert abs(S._gate_value(t, clock, "documented", w_adm=w) * w - pp) < 1e-12


def test_admin_forecast_adds_exactly_the_headline_effect_over_the_weight(monkeypatch):
    _ann(monkeypatch, [{"effective_month": "2022-01", "available_from": "2021-12-01", "provenance": "sourced_retrospective",
                        "elec_pct": 42.3881, "gas_pct": 68.4562, "heat_pct": 0.0}])
    idx = pd.period_range("2012-01", "2021-12", freq="M")
    reg = pd.Series(np.where(idx.month == 1, 1.5, 0.2), index=idx)
    t = pd.Period("2022-01", "M"); clock = pd.Timestamp("2022-01-31 23:59")
    base = S.admin_forecast(reg, t, as_of=clock, announce_mode="verified_only", w_adm=0.14)
    pp = S._gate_headline_pp(t, clock, "documented")
    for w in (0.12, 0.16):
        fired = S.admin_forecast(reg, t, as_of=clock, announce_mode="documented", w_adm=w)
        assert abs(w * (fired - base) - pp) < 1e-12
    with pytest.raises(ValueError):
        S.admin_forecast(reg, t, as_of=clock, announce_mode="documented")


def test_item_weights_follow_basket_publication(monkeypatch):
    _ann(monkeypatch, [{"effective_month": "2022-01", "available_from": "2021-12-01", "provenance": "sourced_retrospective",
                        "elec_pct": 42.3881, "gas_pct": 68.4562, "heat_pct": 0.0}])
    t = pd.Period("2022-01", "M")
    before = S._gate_headline_pp(t, pd.Timestamp("2022-01-31 23:59"), "documented")
    after = S._gate_headline_pp(t, pd.Timestamp("2022-02-20 23:59"), "documented")   # 2022 basket published 14 Feb 2022
    assert abs(before - (38.545494 * 42.3881 + 21.844207 * 68.4562) / 1000) < 1e-9
    assert abs(after - (39.641749 * 42.3881 + 18.954230 * 68.4562) / 1000) < 1e-9
    assert S._energy_item_weights_at(pd.Period("2027-01", "M"), pd.Timestamp("2026-12-01")) == S._ENERGY_ITEM_WEIGHTS[2026]


def test_legacy_reconstructed_rows_keep_block_units(monkeypatch):
    _ann(monkeypatch, [{"effective_month": "2023-01", "announced_regulated_mm_est_pct": 16.5, "available_from": "2022-10-05", "provenance": "reconstructed"},
                       {"effective_month": "2024-01", "announced_regulated_mm_est_pct": 3.0, "available_from": "2023-11-30", "provenance": "reconstructed"}])
    assert S._gate_value(pd.Period("2023-01", "M"), pd.Timestamp("2023-01-31"), "reconstructed_scenario") == 16.5
    assert S._gate_fires(pd.Period("2023-01", "M"), pd.Timestamp("2023-01-31"), "reconstructed_scenario")
    assert np.isnan(S._gate_value(pd.Period("2024-01", "M"), pd.Timestamp("2024-01-31"), "reconstructed_scenario"))
    assert np.isnan(S._gate_value(pd.Period("2023-01", "M"), pd.Timestamp("2023-01-31"), "documented", w_adm=0.15))


def test_food_ppi_follows_the_czso_month_exceptions():
    # reference month January publishes on the 25th of February (16 + 9)
    feb = pd.Period("2026-02", "M")
    assert S._classify_missing("food_ppi_l1", feb, pd.Timestamp("2026-02-20 10:00")) == "NOT_DUE"
    assert S._classify_missing("food_ppi_l1", feb, pd.Timestamp("2026-02-25 10:00")) == "STALE"
    # March and April +4, June and December +1, other months the 16th
    assert S._classify_missing("food_ppi_l1", pd.Period("2026-04", "M"), pd.Timestamp("2026-04-19 10:00")) == "NOT_DUE"
    assert S._classify_missing("food_ppi_l1", pd.Period("2026-04", "M"), pd.Timestamp("2026-04-20 10:00")) == "STALE"
    assert S._classify_missing("food_ppi_l1", pd.Period("2026-07", "M"), pd.Timestamp("2026-07-16 10:00")) == "NOT_DUE"
    assert S._classify_missing("food_ppi_l1", pd.Period("2026-07", "M"), pd.Timestamp("2026-07-17 10:00")) == "STALE"
    assert S._classify_missing("food_ppi_l1", pd.Period("2026-08", "M"), pd.Timestamp("2026-08-15 10:00")) == "NOT_DUE"
    assert S._classify_missing("food_ppi_l1", pd.Period("2026-08", "M"), pd.Timestamp("2026-08-16 10:00")) == "STALE"
    # the live mask applies the same rule
    frame = pd.DataFrame({"food_ppi_l1": [1.0]}, index=pd.PeriodIndex([feb], freq="M"))
    assert np.isnan(S._mask_row_by_availability(frame, feb, pd.Timestamp("2026-02-24 23:59")).loc[feb, "food_ppi_l1"])
    assert S._mask_row_by_availability(frame, feb, pd.Timestamp("2026-02-25 10:00")).loc[feb, "food_ppi_l1"] == 1.0
