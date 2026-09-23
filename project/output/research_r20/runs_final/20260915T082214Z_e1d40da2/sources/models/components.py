"""
Component-based current-month nowcast (h=0), Cleveland-Fed style adapted to the
CNB decomposition: CPI = w_core*core + w_food*food + w_admin*admin + w_fuel*fuel.

Rationale (Bańbura et al., ECB WP 2930; Knotek-Zaman 2017): shocks and policy
measures are component-specific; the aggregate nowcast is far more accurate
when the volatile, observable components (fuel) are measured rather than
modelled, and the persistent component (core) is extrapolated.

Component treatment:
  fuel   -> MEASURED: CZSO weekly pump prices -> month-to-date mean vs prior
            month mean, official basket petrol/diesel blend; unobserved
            weeks carried flat from the last observation (v2.3: the Brent
            tail projection was removed after a measured A/B showed it hurt).
  food   -> bridge regression on agri PPI, food-commodity index, DE food HICP,
            month dummies (strong seasonality in NSA m/m).
  core   -> AR + bridge on price-expectation surveys and core PPI pipeline;
            dominated by persistence + January repricing dummy.
  admin  -> random walk on the January-step profile + ANNOUNCEMENT OVERRIDE:
            regulated energy tariffs (ERÚ), fees etc. are known in advance —
            inject them via `admin_override` rather than estimating them.
            (CNB WP 9/2026, Table A1: administrative prices are essentially
            unforecastable from history — RMSE ~3.2 regardless of model.)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Fuel: weekly pump prices -> CPI item 0722 m/m
# ---------------------------------------------------------------------------
# Official petrol share of the priced fuel pair, per even-year basket regime:
# w(07.222 petrol 95+98) / (w(07.222) + w(07.221 diesel)) from the archived
# CZSO baskets (data/baskets/spot_kos{year}.xlsx; FUEL_SPEC_v23.md). LPG and
# oils are excluded because the weekly survey prices petrol95 and diesel.
OFFICIAL_PETROL_SHARE = {2014: 0.755824, 2016: 0.755823, 2018: 0.670840,
                         2020: 0.670837, 2022: 0.670837, 2024: 0.585321,
                         2026: 0.586409}


def petrol_share_for_regime(regime_start: int) -> float:
    """Share for an even-year basket regime; falls back to the nearest
    earlier regime with a sourced value (earliest overall before 2014).
    Publication gating (which regime a caller may use at its as_of) is the
    caller's job -- cz_struct gates with _basket_available_from."""
    if regime_start in OFFICIAL_PETROL_SHARE:
        return OFFICIAL_PETROL_SHARE[regime_start]
    earlier = [r for r in OFFICIAL_PETROL_SHARE if r <= regime_start]
    return OFFICIAL_PETROL_SHARE[max(earlier) if earlier
                                 else min(OFFICIAL_PETROL_SHARE)]


def fuel_mm_from_weekly(weekly: pd.DataFrame, ref_month: pd.Period,
                        petrol_share: float | None = None) -> tuple[float, dict]:
    """
    CPI fuel m/m (%) for ref_month from weekly CZK/l prices.

    CZSO's monthly fuel price ~ average of weekly observations in the month.
    m/m = 100 * (mean_t / mean_{t-1} - 1), blended petrol/diesel with the
    OFFICIAL basket share (v2.3/F2; pass petrol_share explicitly to apply
    publication gating, else the ref_month regime's share is looked up).
    Unobserved weeks are carried flat from the last observed weekly price
    (v2.3/F1: the Brent tail projection was removed -- measured A/B on all
    90 backtest origins showed it HURT, EOM RMSE 0.612 vs 0.322 without;
    its beta was a monthly pass-through misapplied to 10-day windows).
    Returns (mm_pct, diagnostics).
    """
    if petrol_share is None:
        rg = ref_month.year - (ref_month.year % 2)
        petrol_share = petrol_share_for_regime(rg)
    w = weekly.copy()
    w["blend"] = petrol_share * w["petrol95"] + (1 - petrol_share) * w["diesel"]
    cur = w.loc[w.index.to_period("M") == ref_month, "blend"]
    prev = w.loc[w.index.to_period("M") == (ref_month - 1), "blend"]
    if prev.empty:
        raise ValueError("no prior-month weekly fuel data")
    # expected observations = number of Mondays in ref_month (CZSO surveys Mondays)
    days = pd.date_range(ref_month.start_time, ref_month.end_time, freq="D")
    n_expected = int((days.dayofweek == 0).sum())
    frac_obs = min(len(cur) / n_expected, 1.0)
    diag = {"weeks_observed": int(len(cur)), "fraction_observed": round(frac_obs, 2),
            "petrol_share": round(float(petrol_share), 6)}
    if cur.empty:
        cur_mean = prev.iloc[-1]        # nothing observed yet: flat carry
    elif frac_obs < 1.0:
        tail = cur.iloc[-1]             # unobserved weeks: flat carry
        cur_mean = frac_obs * cur.mean() + (1 - frac_obs) * tail
        diag["tail_projection"] = round(float(tail), 2)
    else:
        cur_mean = cur.mean()
    mm = 100.0 * (cur_mean / prev.mean() - 1.0)
    diag["cur_mean"], diag["prev_mean"] = round(float(cur_mean), 2), round(float(prev.mean()), 2)
    return float(mm), diag

# ---------------------------------------------------------------------------
# Generic monthly bridge (food, core): OLS with month dummies + HF regressors
# ---------------------------------------------------------------------------
class BridgeOLS:
    """
    y_t (component m/m, NSA) = month dummies + sum_j beta_j x_{j,t or t-1} + ar1.
    Regressors must be aligned to what is OBSERVABLE at nowcast time (encode
    publication lags upstream: e.g. use PPI_{t-1} because PPI_t is unpublished
    when the CPI nowcast for t is made mid-month).
    """
    def __init__(self, use_ar1: bool = True):
        self.use_ar1 = use_ar1
        self.coef_ = None
        self.cols_ = None

    def _design(self, y: pd.Series, X: pd.DataFrame) -> tuple[np.ndarray, pd.Index, list]:
        D = pd.get_dummies(pd.Series(y.index.month, index=y.index), prefix="m", dtype=float)
        Z = pd.concat([D, X], axis=1)
        if self.use_ar1:
            Z["ar1"] = y.shift(1)
        Z = Z.dropna()
        idx = Z.index.intersection(y.dropna().index)
        return Z.loc[idx].values, idx, list(Z.columns)

    def fit(self, y: pd.Series, X: pd.DataFrame) -> "BridgeOLS":
        Zv, idx, cols = self._design(y, X)
        yv = y.loc[idx].values
        self.coef_, *_ = np.linalg.lstsq(Zv, yv, rcond=None)
        self.cols_ = cols
        self._y, self._X = y, X
        return self

    def predict_period(self, p: pd.Period) -> float:
        row = {}
        for c in self.cols_:
            if c.startswith("m_"):
                row[c] = 1.0 if int(c[2:]) == p.month else 0.0
            elif c == "ar1":
                row[c] = self._y.get(p - 1, np.nan)
            else:
                row[c] = self._X[c].get(p, np.nan)
        v = np.array([row[c] for c in self.cols_], dtype=float)
        if np.isnan(v).any():  # fall back: last available value per column
            for i, c in enumerate(self.cols_):
                if np.isnan(v[i]) and c in self._X:
                    v[i] = self._X[c].dropna().iloc[-1]
                elif np.isnan(v[i]) and c == "ar1":
                    v[i] = self._y.dropna().iloc[-1]
        return float(v @ self.coef_)

# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def aggregate(components_mm: dict[str, float], weights: dict[str, float]) -> float:
    wsum = sum(weights[k] for k in components_mm)
    return sum(weights[k] * v for k, v in components_mm.items()) / wsum


def nowcast_h0(weights: dict, fuel_mm: float, food_mm: float, core_mm: float,
               admin_mm: float, admin_override: float | None = None) -> dict:
    """Assemble the h=0 nowcast; admin_override injects announced tariff changes."""
    comp = {"core": core_mm, "food": food_mm, "fuel": fuel_mm,
            "administered": admin_override if admin_override is not None else admin_mm}
    return {"components_mm": comp, "cpi_mm": aggregate(comp, weights),
            "contributions": {k: weights[k] * v for k, v in comp.items()}}
