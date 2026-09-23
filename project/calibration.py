"""PIT calibration test (Kolmogorov-Smirnov) + CRPS scoring.

CNB WP 9/2026 formally tests whether the QRF's forecast distribution is
calibrated (PIT values ~ Uniform(0,1), tested via Rossi & Sekhposyan 2019's
KS-based procedure) and scores the full distribution with CRPS, rather than
just checking a single 5-95% coverage rate the way this project's own
band-coverage check does. This module adds both, reusing the qrf_bands
side-channel run_nowcast.py/backtest_h0_hybrid.py already populate (each
entry already carries the 7 quantile points TVWQRF computes internally:
0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95 -- just not all exposed together
until now).

Usage:
    from calibration import pit_values, ks_uniformity_test, crps_approx
    pits = pit_values(qrf_bands, actuals)          # {(h, period): pit}
    ks_stat, ks_pval = ks_uniformity_test(list(pits.values()))
    crps = crps_approx(qrf_bands, actuals)          # {(h, period): crps}
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def _full_quantile_grid(band: dict) -> tuple[np.ndarray, np.ndarray]:
    """Reconstruct all 7 points TVWQRF computes (5% tail points TVWQRF
    already fits internally, plus the TVW3 quantile set) from one qrf_bands
    entry. Returns (alphas, values), sorted."""
    alphas = [0.05] + list(band["quantiles"].keys()) + [0.95]
    values = [band["p05_p95"][0]] + list(band["quantiles"].values()) + [band["p05_p95"][1]]
    order = np.argsort(alphas)
    return np.asarray(alphas)[order], np.asarray(values)[order]


def pit_value(band: dict, actual: float) -> float:
    """F_t(actual): piecewise-linear interpolation through the 7 fitted
    quantile points, clipped to [0, 1] for actuals beyond the 5%/95% points
    (an honest floor/ceiling, not an extrapolation -- CRPS below still
    penalises being that far out)."""
    alphas, values = _full_quantile_grid(band)
    if not np.all(np.diff(values) >= 0):
        values = np.maximum.accumulate(values)  # QRF quantile crossing is rare but possible; enforce monotonicity
    return float(np.clip(np.interp(actual, values, alphas), 0.0, 1.0))


def pit_values(qrf_bands: dict, actuals: pd.Series) -> dict:
    """qrf_bands: {(h, period): band_dict} as populated by tvwqrf_fn.
    actuals: Series indexed by period, the realised y. Returns {(h, period): pit}."""
    out = {}
    for (h, period), band in qrf_bands.items():
        if period in actuals.index and pd.notna(actuals[period]):
            out[(h, period)] = pit_value(band, float(actuals[period]))
    return out


def ks_uniformity_test(pits: list[float]) -> tuple[float, float]:
    """Kolmogorov-Smirnov test of PIT values against Uniform(0,1) --
    Rossi & Sekhposyan (2019)'s calibration check. Returns (statistic,
    p-value); p < 0.05 rejects calibration (the model's distributional
    forecast is systematically off, not just its point forecast)."""
    if len(pits) < 5:
        raise ValueError(f"too few PIT values ({len(pits)}) for a meaningful KS test")
    res = stats.kstest(pits, "uniform")
    return float(res.statistic), float(res.pvalue)


def crps_approx(qrf_bands: dict, actuals: pd.Series) -> dict:
    """CRPS via the standard finite-quantile approximation: 2 * mean over
    the fitted quantile grid of the pinball (quantile) loss. Matches the
    'CRPS Approximation' the paper reports (Table 3/A3) -- same idea,
    applied to our own 7-point grid rather than theirs."""
    out = {}
    for (h, period), band in qrf_bands.items():
        if period not in actuals.index or pd.isna(actuals[period]):
            continue
        y = float(actuals[period])
        alphas, values = _full_quantile_grid(band)
        pinball = np.where(y >= values, alphas * (y - values), (1 - alphas) * (values - y))
        out[(h, period)] = float(2.0 * pinball.mean())
    return out


def summarize(qrf_bands: dict, actuals: pd.Series, h: int | None = None) -> dict:
    """Convenience: filter qrf_bands to one horizon (or all), run both
    checks, return a compact summary dict ready to print."""
    bands = {k: v for k, v in qrf_bands.items() if h is None or k[0] == h}
    pits = pit_values(bands, actuals)
    if len(pits) < 5:
        return {"n": len(pits), "ks_stat": None, "ks_pval": None, "crps_mean": None}
    ks_stat, ks_pval = ks_uniformity_test(list(pits.values()))
    crps = crps_approx(bands, actuals)
    return {
        "n": len(pits),
        "ks_stat": round(ks_stat, 4),
        "ks_pval": round(ks_pval, 4),
        "calibrated_at_5pct": ks_pval >= 0.05,
        "crps_mean": round(float(np.mean(list(crps.values()))), 4),
    }
