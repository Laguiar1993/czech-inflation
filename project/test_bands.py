"""BANDS_SPEC_v1: error pools, sign convention, V1 fallbacks, and the live
helper's as-of restriction. Points are never touched by any of this."""
import numpy as np
import pandas as pd

import cz_struct as S
from models.bands import ErrorPool, build_pool, band, MIN_V0


def _hist(errors, months, start="2019-02"):
    idx = pd.period_range(start, periods=len(errors), freq="M")
    return pd.DataFrame({"e": errors, "month": months, "state": np.nan,
                         "age_months": list(range(len(errors), 0, -1))}, index=idx)


def test_band_sign_convention_shifts_a_biased_model_down():
    # a model that is always +0.3 too high: the band must sit below the point
    pool = ErrorPool(np.full(40, 0.3) + np.linspace(-0.05, 0.05, 40))
    lo, hi = band(1.0, pool, 80)
    assert hi < 1.0 and lo < hi
    assert abs((lo + hi) / 2 - 0.7) < 0.03


def test_empirical_quantile_and_pit_are_consistent():
    e = np.linspace(-1, 1, 101)
    pool = ErrorPool(e)
    assert abs(pool.quantile(0.5)) < 1e-9
    assert abs(pool.cdf(0.0) - 0.505) < 0.01
    assert abs(pool.crps(0.0) - (np.mean(np.abs(e)) - 0.5 * np.mean(np.abs(e[:, None] - e[None, :])))) < 1e-12


def test_v0_needs_24_errors_and_v1_january_fallbacks():
    h = _hist(np.random.RandomState(0).normal(0, 0.3, 23), [((i % 12) + 2 - 1) % 12 + 1 for i in range(23)])
    pool, note = build_pool(h, "V0", 5, None)
    assert pool is None and note == "insufficient_history"
    h = _hist(np.random.RandomState(1).normal(0, 0.3, 40), [((i + 1) % 12) + 1 for i in range(40)])   # 3 Januaries
    pool, note = build_pool(h, "V1", 1, None)
    assert note == "V1_jan_scaled" and len(pool) == int((h["month"] != 1).sum())
    h2 = h.copy(); h2.loc[h2.index[:6], "month"] = 1                                          # 8 Januaries now
    pool, note = build_pool(h2, "V1", 1, None)
    assert note == "V1" and len(pool) == int((h2["month"] == 1).sum())
    pool, note = build_pool(h2, "V1", 6, None)
    assert note == "V1" and len(pool) == int((h2["month"] != 1).sum())


def test_v4_weights_recent_errors_more():
    e = np.r_[np.full(30, -1.0), np.full(30, 1.0)]         # old errors negative, recent positive
    h = _hist(e, [6] * 60)
    pool, _ = build_pool(h, "V4", 6, None)
    assert pool.quantile(0.5) > 0.0                        # the recent half dominates


def test_live_helper_uses_only_first_releases_public_at_the_clock():
    t = pd.Period("2024-05", "M")
    pts = {"base_ridge": 0.4, "past_full": 0.4, "past_half": 0.4}
    # the April-2024 print's first release was 13 May 2024 09:00 (release calendar)
    early = S._live_trio_bands(t, pd.Timestamp("2024-05-12 23:59"), pts)   # April print not yet out
    late = S._live_trio_bands(t, pd.Timestamp("2024-05-14 23:59"), pts)    # April print out
    assert early["band_variant"] == "V1" and early["band_status"] == "uncalibrated"
    assert early["band_n_pool"] >= MIN_V0 and late["band_n_pool"] == early["band_n_pool"] + 1
    for k in ("base_ridge", "past_full", "past_half"):
        assert early[f"h0_{k}_lo80"] < early[f"h0_{k}_hi80"]
        assert early[f"h0_{k}_lo90"] <= early[f"h0_{k}_lo80"] and early[f"h0_{k}_hi90"] >= early[f"h0_{k}_hi80"]


def test_live_helper_never_raises():
    out = S._live_trio_bands(pd.Period("2019-03", "M"), pd.Timestamp("2019-03-31"), {"base_ridge": 0.1, "past_full": 0.1, "past_half": 0.1})
    assert out["band_status"].startswith("unavailable") and np.isnan(out["h0_base_ridge_lo80"])
