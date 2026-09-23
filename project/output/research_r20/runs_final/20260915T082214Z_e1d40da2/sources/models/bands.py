"""Calibrated uncertainty bands for the frozen trio (BANDS_SPEC_v1.md).

Bands are quantiles of a model's OWN past first-release errors
(e = forecast - print, release-eve clock) added to the point forecast with
the v2.0 sign convention: lo_q = f - Q(1 - q), hi_q = f - Q(q), so an
upward-biased model gets a band shifted down. Every function takes the
error history already restricted to what the caller's clock allows; the
caller (the study or the live call) is responsible for the as-of cut.

Variants (declared, no parameter tuned after the run):
  V0 unconditional expanding empirical quantiles (min 24 errors);
  V1 January / non-January pools (January min 5, else the non-January
     pool scaled by the RMS ratio when >= 3 January errors, else V0);
  V2 state x January cells (min 8 per cell, fallback V1);
  V3 Student-t(5) centred on the pool mean with the pool RMS as scale,
     pools as in V1;
  V4 V1 pools with exponential recency weights, half-life 36 months.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

LEVELS = {50: (0.25, 0.75), 80: (0.10, 0.90), 90: (0.05, 0.95)}
VARIANTS = ("V0", "V1", "V2", "V3", "V4")
MIN_V0 = 24
MIN_JAN = 5
MIN_JAN_SCALE = 3
MIN_CELL = 8
HALF_LIFE = 36.0
T_DF = 5


def _wquantile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    """Weighted quantile (Hyndman-Fan type 7 on the weighted CDF)."""
    order = np.argsort(x)
    x, w = x[order], w[order]
    cw = np.cumsum(w) / w.sum()
    return float(np.interp(q, cw - 0.5 * w / w.sum(), x))


class ErrorPool:
    """A sample of past errors with optional weights; produces quantiles,
    the PIT of a realised error and the CRPS of a realised error."""

    def __init__(self, e: np.ndarray, w: np.ndarray | None = None, t_scale: bool = False):
        self.e = np.asarray(e, dtype=float)
        self.w = np.ones_like(self.e) if w is None else np.asarray(w, dtype=float)
        self.t_scale = t_scale
        self.mu = float(np.average(self.e, weights=self.w)) if len(self.e) else np.nan
        self.rms = float(np.sqrt(np.average(self.e ** 2, weights=self.w))) if len(self.e) else np.nan

    def quantile(self, q: float) -> float:
        if self.t_scale:
            return self.mu + self.rms * float(stats.t.ppf(q, T_DF)) / np.sqrt(T_DF / (T_DF - 2))
        return _wquantile(self.e, self.w, q)

    def cdf(self, x: float) -> float:
        if self.t_scale:
            z = (x - self.mu) / (self.rms / np.sqrt(T_DF / (T_DF - 2)))
            return float(stats.t.cdf(z, T_DF))
        return float(np.sum(self.w * (self.e <= x)) / self.w.sum())

    def crps(self, y: float) -> float:
        """CRPS of the predictive distribution of the ERROR at the realised
        error y: E|X - y| - 0.5 E|X - X'|."""
        if self.t_scale:
            # CRPS = integral of the Brier score over thresholds, computed
            # numerically on a wide grid (the t distribution's tails are
            # covered to 12 scale units; truncation error < 1e-4)
            sc = self.rms / np.sqrt(T_DF / (T_DF - 2))
            grid = self.mu + sc * np.linspace(-12, 12, 4801)
            F = stats.t.cdf((grid - self.mu) / sc, T_DF)
            return float(np.trapezoid((F - (grid >= y)) ** 2, grid))
        w = self.w / self.w.sum()
        e = self.e
        term1 = float(np.sum(w * np.abs(e - y)))
        term2 = 0.5 * float(np.sum(w[:, None] * w[None, :] * np.abs(e[:, None] - e[None, :])))
        return term1 - term2

    def __len__(self):
        return len(self.e)


def build_pool(errors: pd.DataFrame, variant: str, month: int, state: float | None) -> tuple[ErrorPool | None, str]:
    """`errors`: DataFrame indexed by origin Period with columns e, month,
    state (float 0/1 or NaN), age_months (>= 1, months between origin and
    the call). Returns (pool, note)."""
    if errors is None or len(errors) < MIN_V0:
        return None, "insufficient_history"
    e_all = errors["e"].values.astype(float)
    if variant == "V0":
        return ErrorPool(e_all), "V0"
    jan = errors["month"].values == 1
    want_jan = month == 1
    if variant in ("V1", "V3", "V4"):
        pool_idx = jan if want_jan else ~jan
        if want_jan and pool_idx.sum() < MIN_JAN:
            if pool_idx.sum() >= MIN_JAN_SCALE:
                # scale the non-January pool by the RMS ratio
                rj = np.sqrt(np.mean(e_all[jan] ** 2)); rn = np.sqrt(np.mean(e_all[~jan] ** 2))
                scaled = e_all[~jan] * (rj / rn if rn > 0 else 1.0)
                return ErrorPool(scaled, t_scale=(variant == "V3")), f"{variant}_jan_scaled"
            return ErrorPool(e_all, t_scale=(variant == "V3")), f"{variant}_fallback_V0"
        e = e_all[pool_idx]
        if variant == "V4":
            age = errors["age_months"].values.astype(float)[pool_idx]
            w = 0.5 ** (age / HALF_LIFE)
            return ErrorPool(e, w), "V4"
        return ErrorPool(e, t_scale=(variant == "V3")), variant
    if variant == "V2":
        if state is None or not np.isfinite(state) or errors["state"].isna().all():
            return build_pool(errors, "V1", month, state)
        cell = (jan == want_jan) & (errors["state"].values == float(state))
        if cell.sum() >= MIN_CELL:
            return ErrorPool(e_all[cell]), "V2"
        pool, note = build_pool(errors, "V1", month, state)
        return pool, f"V2_fallback_{note}"
    raise ValueError(variant)


def band(f: float, pool: ErrorPool, level: int) -> tuple[float, float]:
    ql, qh = LEVELS[level]
    return f - pool.quantile(qh), f - pool.quantile(ql)


def error_history(bt: pd.DataFrame, actual: pd.Series, col: str) -> pd.DataFrame:
    """Release-eve first-release errors of a backtest column with the fields
    build_pool needs (month, state left for the caller)."""
    e = (bt[col] - actual.reindex(bt.index)).dropna()
    out = pd.DataFrame({"e": e.values, "month": [p.month for p in e.index]}, index=e.index)
    return out
