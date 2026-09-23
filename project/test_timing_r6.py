"""Codex R6 poison tests (v2.6): the live row mask follows the release
calendar for CPI-family lags; month-to-date FX never uses the call day's
fixing; the food block reports its method; the alcohol pre-anchor is the
sourced basket share."""
import numpy as np
import pandas as pd

import cz_struct as S
from data import local_adapter as la


def _frame():
    idx = pd.period_range("2025-01", "2026-03", freq="M")
    f = pd.DataFrame(1.0, index=idx, columns=["core_l1", "food_l1", "services_l1", "state",
                                              "eurczk_mm_x_state", "exp12", "core_l2"])
    return f


def test_mask_uses_release_calendar_for_cpi_family_lags():
    # target February 2026: the CPI-family inputs of January 2026 are public
    # from the detailed release on 13 February 2026, not from the 11th
    t = pd.Period("2026-02", "M")
    early = S._mask_row_by_availability(_frame(), t, pd.Timestamp("2026-02-12 10:00"))
    late = S._mask_row_by_availability(_frame(), t, pd.Timestamp("2026-02-13 09:00"))
    for col in ("core_l1", "food_l1", "services_l1", "state", "eurczk_mm_x_state"):
        assert np.isnan(early.loc[t, col]), col
        assert late.loc[t, col] == 1.0, col
    # the classifier agrees with the mask on the same clock
    assert S._classify_missing("core_l1", t, pd.Timestamp("2026-02-12 10:00")) == "NOT_DUE"
    assert S._classify_missing("core_l1", t, pd.Timestamp("2026-02-13 09:00")) == "STALE"
    # non-CPI columns keep their documented day rules
    assert early.loc[t, "core_l2"] == 1.0 and np.isnan(early.loc[t, "exp12"])


def test_mtd_fx_excludes_the_call_days_fixing(monkeypatch):
    fixings = pd.Series([25.0, 25.2, 25.4], index=pd.DatetimeIndex(["2026-09-01", "2026-09-02", "2026-09-03"]))
    monkeypatch.setattr(la, "fetch_cnb_daily_eur_fixings", lambda year: fixings)
    prev = pd.Series({pd.Period("2026-08", "M"): 25.0})
    v10, n10 = S._eurczk_mtd_mm(pd.Period("2026-09", "M"), pd.Timestamp("2026-09-03 10:00"), prev)
    v_next, n_next = S._eurczk_mtd_mm(pd.Period("2026-09", "M"), pd.Timestamp("2026-09-04 08:00"), prev)
    assert n10 == 2 and abs(v10 - 100 * (25.1 / 25.0 - 1)) < 1e-9      # 3 Sep fixing not yet used
    assert n_next == 3 and abs(v_next - 100 * (25.2 / 25.0 - 1)) < 1e-9
    v0, n0 = S._eurczk_mtd_mm(pd.Period("2026-09", "M"), pd.Timestamp("2026-09-01 12:00"), prev)
    assert n0 == 0 and np.isnan(v0)


def test_food_forecast_reports_method_and_history():
    idx = pd.period_range("2015-02", "2026-07", freq="M")
    rng = np.random.default_rng(0)
    food = pd.Series(rng.normal(0.2, 0.8, len(idx)), index=idx, name="food")
    feats = pd.DataFrame({"food_l1": S._lag(food, 1, idx), "food_l12": S._lag(food, 12, idx)}, index=idx)
    t = pd.Period("2026-07", "M")
    out = S.food_forecast(food, feats, t, as_of=t.to_timestamp(how="end"))
    assert np.isfinite(out)
    assert S.FOOD_DIAG["method"] in ("x13", "fallback")
    assert S.FOOD_DIAG["history_end"] == "2026-06" and S.FOOD_DIAG["n_obs"] == len(food[:"2026-06"])
    if S.FOOD_DIAG["method"] == "fallback":
        assert S.FOOD_DIAG["x13_error"]
    else:
        assert S.FOOD_DIAG["x13_error"] == ""


def test_alcohol_preanchor_is_the_sourced_basket_share():
    assert abs(S._ALC_TOBACCO_WEIGHT_PREANCHOR - 0.09498) < 1e-9
    src = open(S.__file__, encoding="utf-8").read()
    assert '"alc": 0.087' not in src


def test_announcement_check_status_reads_last_batch(tmp_path):
    p = tmp_path / "checks.csv"
    pd.DataFrame({"check_ts": ["2026-09-01T10:00:00+00:00"] * 2 + ["2026-09-05T08:00:00+00:00"] * 3,
                  "source_id": ["a", "b", "a", "b", "c"],
                  "verdict": ["FIRST", "FIRST", "UNCHANGED", "CHANGED", "UNVERIFIED"]}).to_csv(p, index=False)
    st = S._announcement_check_status(pd.Timestamp("2026-09-07 09:00"), path=str(p))
    assert abs(st["announcement_check_age_days"] - 2.04) < 0.01
    assert st["announcement_changed"] == 1 and st["announcement_unverified"] == 1
    # a check made after the clock is invisible to that call
    st2 = S._announcement_check_status(pd.Timestamp("2026-09-03 09:00"), path=str(p))
    assert st2["announcement_changed"] == 0 and abs(st2["announcement_check_age_days"] - 1.96) < 0.01
    st3 = S._announcement_check_status(pd.Timestamp("2026-09-07"), path=str(tmp_path / "missing.csv"))
    assert np.isnan(st3["announcement_check_age_days"])
