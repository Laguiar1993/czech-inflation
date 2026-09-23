"""Shapley-value decomposition of TVW-QRF point forecasts.

CNB WP 9/2026 Section 3.5: Tree SHAP Monte Carlo (Strumbelj & Kononenko,
2014) attributing each forecast to predictor contributions, grouped into
economic categories, tracked over time (their Figures 5/6). quantile_forest's
RandomForestQuantileRegressor isn't a class SHAP's fast TreeExplainer
recognises -- but Strumbelj & Kononenko's method is itself model-agnostic
permutation sampling, which is what shap.explainers.Permutation actually is,
so this is a faithful match to the paper's own cited method, not a fallback.

Explains the POINT forecast (quantiles dotted with TVWQRF's already-fit
weights), not each quantile separately as the paper does -- a reasonable
simplification for "why did the model call what it called", the practical
question this exists to answer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap

from models.horizon_models import TVWQRF, build_supervised

# Loose grouping mirroring the paper's G1-G7 categories, adapted to this
# project's actual predictor names (see local_adapter.py).
PREDICTOR_GROUPS = {
    "real_activity": ["ip_yoy", "constr_yoy", "unemployment_rate", "rushin",
                      "wage_mm_chowlin", "hh_loans_mm", "nfc_loans_mm"],
    "foreign_influence": ["de_ip_yoy", "de_retail_yoy", "de_esi", "de_food_hicp_mm",
                          "eurczk_mm", "usdczk_mm", "reer_ppi_mm", "reer_cpi_mm",
                          "pl_retail_conf", "import_price_mm", "trade_balance"],
    "confidence_sentiment": ["esi", "conf_business", "conf_consumer", "conf_economic_sentiment"],
    "ppi": ["ppi_mm_deep", "ppi_mm", "ppi_c_mm", "ppi_d_mm", "ppi_services_mm",
           "admin_mm", "core_ex_admin_mm"],
    "financial": ["pribor_3m", "czgb_10y"],
    "commodities_energy": ["brent_czk_mm", "brent_czk_mm_l1"],
    "inflation_expectations": ["price_expect_survey", "price_expect_survey_36m",
                               "household_price_expect", "cpi_breadth", "median_cpi_mm"],
}


def _group_of(col: str) -> str:
    for g, cols in PREDICTOR_GROUPS.items():
        if col in cols:
            return g
    return "other"


def explain_point_forecast(y_hist: pd.Series, X_hist: pd.DataFrame, h: int,
                           n_permutations: int = 64, seed: int = 0) -> dict:
    """Fit TVWQRF at this origin, explain its point forecast with
    permutation Shapley values. Background = X_hist's own pre-2021 rows
    (paper's spirit: a stable, pre-surge reference period), falling back to
    the full history if there isn't enough of it. Returns per-column and
    per-group |SHAP| shares plus the raw values."""
    Xt, yt, x_now, _ = build_supervised(y_hist, X_hist, h)
    model = TVWQRF()
    result = model.fit_predict(Xt, yt, x_now)
    weights = np.array([result["weights"][q] for q in model.q])

    def point_forecast(X: np.ndarray) -> np.ndarray:
        Q = model.model.predict(X, quantiles=list(model.q))
        return np.atleast_2d(Q) @ weights

    pre_surge_mask = X_hist.index < pd.Period("2021-06", freq="M")
    bg_idx = np.where(np.asarray(pre_surge_mask)[: len(Xt)])[0]
    bg = Xt[bg_idx] if len(bg_idx) >= 10 else Xt
    bg_sample = shap.sample(bg, min(50, len(bg)), random_state=seed)

    explainer = shap.explainers.Permutation(point_forecast, bg_sample, seed=seed)
    sv = explainer(x_now.reshape(1, -1), npermutations=n_permutations, silent=True)
    values = np.asarray(sv.values).reshape(-1)

    cols = list(X_hist.columns) + [f"y_l{i}" for i in range(3)] + ["month"]
    cols = cols[: len(values)]
    per_col = dict(zip(cols, values.tolist()))

    group_abs = {}
    for c, v in per_col.items():
        g = _group_of(c) if c not in (f"y_l{i}" for i in range(3)) and c != "month" else "inflation_persistence"
        group_abs[g] = group_abs.get(g, 0.0) + abs(v)
    total = sum(group_abs.values()) or 1.0
    group_share = {g: v / total for g, v in group_abs.items()}

    return {"point_forecast": result["point"], "per_predictor": per_col,
            "group_share": group_share, "base_value": float(np.mean(point_forecast(bg_sample)))}
