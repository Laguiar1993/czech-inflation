"""backtest_h0_variants.py -- four new ex-fuel component models, recombined
with measured fuel exactly like backtest_h0_hybrid, so every row is
comparable to the champion's output/backtest_h0_hybrid.csv.

Models (all forecast the corrected ex-fuel target, h=1 setup, same origins):
  WIDERAW  -- raw imputed eligible panel straight into TVW-QRF, no PCA
              (Medeiros et al "Global Inflation Forecasting": RF's embedded
              selection >= upfront factor compression; run at the validated
              max_features=1.0 config default).
  CSR      -- complete subset regressions (EGT 2013), k in {1,2,3} chosen on
              a 24-month validation tail inside each origin.
  BBIM     -- blockwise monotone boosted trees (BoE SWP 1143 mechanism),
              blocks: trend / global_supply / domestic_supply / demand / fx
              / other, monotone signs on economically-signed columns.
  X13_QRF  -- per-origin X-13 on the ex-fuel target history (one-sided by
              construction: fitted only on data through the origin), champion
              TVW-QRF on the SA series, seasonal factor for the target month
              added back (mean of that calendar month's factor, last 3 fitted
              years). Motivated by this repo's own 4-way result (X-13 on the
              food target cut its RMSE 26%). Scored against NSA actuals.

Usage: python backtest_h0_variants.py
"""
from __future__ import annotations
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CFG
from models.components import fuel_mm_from_weekly
from models.horizon_models import TVWQRF, build_supervised
from models.csr import csr_forecast
from models.bbim_lite import bbim_forecast
from backtest.engine import run_backtest
from backtest_h0 import weekly_and_brent_asof
from backtest_h0_hybrid import build_panel, tvwqrf_fn, STALE_TOLERANCE, MIN_FACTOR_HISTORY
from data import local_adapter as la

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
N_TREES = int(os.environ.get("QRF_TREES", CFG.qrf_trees))

warnings.filterwarnings("ignore")


def _eligible_imputed(X_hist: pd.DataFrame) -> pd.DataFrame | None:
    edge = X_hist.index.max()
    eligible = [c for c in X_hist.columns
                if X_hist[c].last_valid_index() is not None
                and X_hist[c].last_valid_index() >= edge - STALE_TOLERANCE
                and X_hist[c].notna().sum() >= MIN_FACTOR_HISTORY]
    if len(eligible) < 2:
        return None
    panel = X_hist[eligible]
    return panel.fillna(panel.mean())


def wideraw_fn(y_hist, X_hist, h):
    imputed = _eligible_imputed(X_hist)
    if imputed is None:
        return tvwqrf_fn(y_hist, X_hist, h)
    Xt, yt, x_now, _ = build_supervised(y_hist, imputed, h)
    return TVWQRF(n_estimators=N_TREES).fit_predict(Xt, yt, x_now)["point"]


def csr_fn(y_hist, X_hist, h):
    imputed = _eligible_imputed(X_hist)
    if imputed is None:
        return tvwqrf_fn(y_hist, X_hist, h)
    return csr_forecast(y_hist, imputed, h)


# --- BBIM block + monotone-sign maps over this panel's column names -------
_TREND = {"price_expect_survey", "price_expect_survey_36m", "household_price_expect",
          "median_cpi_mm", "cpi_breadth"}
_GSUP = {"brent_czk_mm", "brent_czk_mm_l1", "de_food_hicp_mm", "import_prices_mm"}
_DSUP = {"ppi_mm_deep", "wage_mm"}
_DEM = {"esi", "conf_business", "conf_consumer", "conf_economic_sentiment",
        "retail_yoy", "ip_yoy", "constr_yoy", "rushin", "de_ip_yoy",
        "de_retail_yoy", "de_esi", "pl_retail_conf", "unemployment_rate"}
_FX = {"eurczk_mm", "usdczk_mm"}
_POS = _TREND | _GSUP | _DSUP | _FX | {"esi", "retail_yoy", "ip_yoy", "rushin"}
_NEG = {"unemployment_rate"}


def _block_of(col: str) -> str:
    if col.startswith("y_l") or col == "month" or col in _TREND:
        return "trend"
    if col in _GSUP:
        return "global_supply"
    if col in _DSUP or col.startswith("ppi"):
        return "domestic_supply"
    if col in _DEM or col.startswith(("conf_", "credit")):
        return "demand"
    if col in _FX:
        return "fx"
    return "other"


def _mono_of(col: str) -> int:
    if col in _NEG:
        return -1
    if col in _POS or col.startswith("ppi"):
        return 1
    return 0


def bbim_fn(y_hist, X_hist, h):
    imputed = _eligible_imputed(X_hist)
    if imputed is None:
        return tvwqrf_fn(y_hist, X_hist, h)
    return bbim_forecast(y_hist, imputed, h, _block_of, _mono_of)


def x13_qrf_fn(y_hist, X_hist, h):
    from statsmodels.tsa.x13 import x13_arima_analysis
    try:
        ts = y_hist.copy()
        ts.index = ts.index.to_timestamp()
        res = x13_arima_analysis(ts, x12path=la._X13_PATH, prefer_x13=True)
        sa = res.seasadj
        sa.index = y_hist.index
        seas = (y_hist - sa).dropna()
        tgt_month = (y_hist.index.max() + h).month
        s_m = seas[seas.index.month == tgt_month]
        s_add = float(s_m.iloc[-3:].mean()) if len(s_m) else 0.0
        return tvwqrf_fn(sa.dropna(), X_hist, h) + s_add
    except Exception as e:
        print(f"    x13 fallback at {y_hist.index.max()}: {type(e).__name__}")
        return tvwqrf_fn(y_hist, X_hist, h)


def main():
    y, y_ex_fuel, X, fuel_w = build_panel()
    print(f"panel: {X.shape[1]} columns; target n={len(y_ex_fuel)}")
    models = {"WIDERAW": wideraw_fn, "CSR": csr_fn, "BBIM": bbim_fn, "X13_QRF": x13_qrf_fn}
    bt = run_backtest(y_ex_fuel, X, 1, "2018-01", models, min_train=36)
    print(f"{len(bt)} origins, {bt.index.min()}..{bt.index.max()}")
    for col in models:
        r = bt[col] - bt["actual"]
        print(f"  ex-fuel {col:8s} RMSE={np.sqrt(np.nanmean(r ** 2)):.3f}  MAE={np.nanmean(np.abs(r)):.3f}")

    weekly_full = la.fetch_weekly_fuels_live()
    brent_daily_full = la.fetch_brent_czk_daily_live()
    last_weekly_month = weekly_full.index.max().to_period("M")

    rows = []
    for t in bt.index:
        if t not in y.index or t > last_weekly_month:
            continue
        try:
            weekly_t, brent_t = weekly_and_brent_asof(weekly_full, brent_daily_full, t)
            fuel_mm, _ = fuel_mm_from_weekly(weekly_t, t)
        except Exception:
            continue
        row = {"period": t, "actual": y.loc[t], "fuel_mm": fuel_mm}
        for col in models:
            row[f"h0_{col}"] = fuel_w * fuel_mm + (1 - fuel_w) * bt.loc[t, col]
        rows.append(row)
    out = pd.DataFrame(rows).set_index("period").sort_index()

    champ_path = os.path.join(OUT, "backtest_h0_hybrid.csv")
    if os.path.exists(champ_path):
        champ = pd.read_csv(champ_path, index_col="period")
        champ.index = pd.PeriodIndex(champ.index, freq="M")
        out["h0_TVWQRF"] = champ["h0_hybrid"].reindex(out.index)

    out.to_csv(os.path.join(OUT, "backtest_h0_variants.csv"))
    print(f"\nh=0 recombined (n={len(out)}, {out.index.min()}..{out.index.max()}):")
    for col in [c for c in out.columns if c.startswith("h0_")]:
        r = out[col] - out["actual"]
        print(f"  {col:12s} RMSE={np.sqrt(np.nanmean(r ** 2)):.3f}  MAE={np.nanmean(np.abs(r)):.3f}")
    return out


if __name__ == "__main__":
    main()
