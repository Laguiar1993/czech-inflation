"""v2.7 (ANNOUNCEMENT_ADOPTION_v27) + v2.7.1 (Codex R8 corrections): the
documented gate mode admits sourced_retrospective and prospective rows from
their availability date, never reconstructed ones; several rows for one month
resolve to the latest published on or before the clock; verified_only still
admits nothing. Documented rows are stored as per-fuel changes and priced in
headline units with the basket available at the clock; the block value uses
the CALL's administered weight."""
import numpy as np
import pandas as pd

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


def test_documented_admits_sourced_from_its_date_and_never_reconstructed(monkeypatch):
    _ann(monkeypatch, [
        {"effective_month": "2022-01", "announced_regulated_mm_est_pct": 16.5, "available_from": "2021-12-15", "provenance": "reconstructed"},
        {"effective_month": "2022-01", "available_from": "2021-12-01", "provenance": "sourced_retrospective",
         "elec_pct": 42.3881, "gas_pct": 68.4562, "heat_pct": 0.0}])
    t = pd.Period("2022-01", "M")
    pp = (38.545494 * 42.3881 + 21.844207 * 68.4562) / 1000.0      # 2020 basket: the 2022 one publishes 14 Feb 2022
    assert np.isnan(S._gate_value(t, pd.Timestamp("2021-11-30 23:59"), "documented", w_adm=0.14))
    assert abs(S._gate_value(t, pd.Timestamp("2021-12-01 23:59"), "documented", w_adm=0.14) - pp / 0.14) < 1e-9
    assert abs(S._gate_value(t, pd.Timestamp("2022-01-31 23:59"), "documented", w_adm=0.14) - pp / 0.14) < 1e-9   # reconstructed 16.5 never wins
    assert np.isnan(S._gate_value(t, pd.Timestamp("2022-01-31 23:59"), "verified_only"))
    assert S._gate_value(t, pd.Timestamp("2022-01-31 23:59"), "reconstructed_scenario") == 16.5


def test_latest_admitted_row_on_or_before_the_clock_governs(monkeypatch):
    _ann(monkeypatch, [
        {"effective_month": "2027-01", "available_from": "2026-11-28", "provenance": "prospective", "elec_pct": 30.0, "gas_pct": 0.0, "heat_pct": 0.0},
        {"effective_month": "2027-01", "available_from": "2026-12-20", "provenance": "prospective", "elec_pct": 40.0, "gas_pct": 0.0, "heat_pct": 0.0}])
    t = pd.Period("2027-01", "M")
    assert abs(S._gate_headline_pp(t, pd.Timestamp("2026-12-10"), "documented") - 43.034809 * 30 / 1000) < 1e-9
    assert abs(S._gate_headline_pp(t, pd.Timestamp("2026-12-31"), "documented") - 43.034809 * 40 / 1000) < 1e-9


def test_below_threshold_and_undated_rows_do_not_fire(monkeypatch):
    _ann(monkeypatch, [
        {"effective_month": "2025-01", "available_from": "2024-11-29", "provenance": "sourced_retrospective", "elec_pct": -10.0, "gas_pct": -8.0, "heat_pct": 0.0},
        {"effective_month": "2024-01", "available_from": pd.NaT, "provenance": "sourced_retrospective", "elec_pct": 80.0, "gas_pct": 0.0, "heat_pct": 0.0}])
    assert np.isnan(S._gate_value(pd.Period("2025-01", "M"), pd.Timestamp("2025-01-31"), "documented", w_adm=0.15))
    assert not S._gate_fires(pd.Period("2025-01", "M"), pd.Timestamp("2025-01-31"), "documented")
    assert np.isnan(S._gate_value(pd.Period("2024-01", "M"), pd.Timestamp("2024-01-31"), "documented", w_adm=0.15))


def test_repository_file_fires_only_in_2022_and_2023():
    S._ANN = None
    ann = S._announcements()
    fired = [str(p) for p in sorted(set(ann.index)) if S._gate_fires(p, p.to_timestamp(how="end"), "documented")]
    assert fired == ["2022-01", "2023-01"], fired
    pp22 = S._gate_headline_pp(pd.Period("2022-01", "M"), pd.Timestamp("2022-01-31 23:59"), "documented")
    pp23 = S._gate_headline_pp(pd.Period("2023-01", "M"), pd.Timestamp("2023-01-31 23:59"), "documented")
    assert abs(pp22 - 3.129) < 0.005 and abs(pp23 - 3.664) < 0.005, (pp22, pp23)
    # the 2023 entry needs the December 2022 index, released 11 January 2023
    assert np.isnan(S._gate_headline_pp(pd.Period("2023-01", "M"), pd.Timestamp("2023-01-10 23:59"), "documented"))
    # no sourced row stores a block-unit magnitude any more
    src = ann[ann["provenance"] == "sourced_retrospective"]
    assert src["announced_regulated_mm_est_pct"].isna().all()
    assert src[["elec_pct", "gas_pct", "heat_pct"]].notna().all().all()
