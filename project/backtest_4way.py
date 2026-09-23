"""backtest_4way.py — genuine separately-forecast food/fuel/core(+admin)
components for h>=1, recombined via basket weights, vs. the pure top-down
headline model already validated (run_nowcast.py).

Why: CNB WP 9/2026 forecasts core/food/fuel/administered SEPARATELY at
every horizon, each with dynamics suited to that component, then
recombines -- this project's h>=1 (run_nowcast.py) has always been a
single top-down model on headline. h=0-hybrid already does a component
split, but only nowcasts (h=0); this extends the SAME idea to h=1/3/6/12
using QRF-forecast components instead of BridgeOLS single-fit, since h>=1
needs to forecast fuel/food/core rather than measure/bridge them from
already-known recent data.

Depth constraint (unlike headline, which now goes to 1991 via
load_headline_cpi_mm_extended): COICOP-level food is capped at 2015-01
(CZSO's open-data extract), and the weekly-fuel-derived target at 2016-02
(CENPHMT open-data start) -- there is no equivalent deep source for
components the way there is for headline. So this backtest necessarily
runs on the SHALLOWER ~2016-2026 window, not the full 1991+ depth. Genuine
administered-price data (26mo, 2024-06+) is far too short to fold into
this backtest as its own separately-modelled target; core and administered
stay combined here, same as h0-hybrid.

Usage: python backtest_4way.py [--h 3]
"""
from __future__ import annotations
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CFG, COMPONENT_WEIGHTS_FALLBACK
from data import local_adapter as la
from models.horizon_models import TVWQRF, build_supervised
from backtest.engine import run_backtest

N_TREES = int(os.environ.get("QRF_TREES", CFG.qrf_trees))
TOP_K = int(os.environ.get("TOP_K_FEATURES", 6))  # fewer than the headline model's 8 -- each component gets a narrower, component-appropriate panel
MIN_TRAIN = int(os.environ.get("MIN_TRAIN", 36))
STALE_TOLERANCE = 2

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)


def build_targets_and_panel():
    y = la.load_headline_cpi_mm()
    comp = la.load_component_targets()
    fuel = la.load_fuel_mm_history()

    food_w = la.latest_weight_permille("01") / 1000.0
    fuel_w = COMPONENT_WEIGHTS_FALLBACK["fuel"]
    core_admin_w = 1 - food_w - fuel_w

    y_full, X_full, _, _ = la.load_all()
    X_full = X_full.sort_index()
    return y, comp, fuel, food_w, fuel_w, core_admin_w, X_full


def component_predictor_sets(X: pd.DataFrame) -> dict:
    """Per-component candidate predictor lists, matching the paper's own
    logic (food <- agri/foreign food prices; fuel <- oil/FX; core+admin <-
    the broad domestic macro panel already used for the headline model)."""
    all_cols = set(X.columns)
    return {
        "food": [c for c in ["agri_ppi_mm", "de_food_hicp_mm", "ppi_mm", "eurczk_mm",
                             "median_cpi_mm", "cpi_breadth"] if c in all_cols],
        "fuel": [c for c in ["brent_czk_mm", "brent_czk_mm_l1", "eurczk_mm", "usdczk_mm",
                             "ppi_mm_deep"] if c in all_cols],
        "core_admin": [c for c in ["ppi_mm_deep", "esi", "price_expect_survey",
                                   "price_expect_survey_36m", "rushin", "ip_yoy",
                                   "constr_yoy", "unemployment_rate", "conf_business",
                                   "conf_consumer", "pribor_3m", "czgb_10y",
                                   "de_ip_yoy", "de_retail_yoy", "household_price_expect",
                                   "cpi_breadth", "median_cpi_mm"] if c in all_cols],
    }


def make_tvwqrf_fn(candidate_cols: list[str]):
    def fn(y_hist, X_hist, h):
        Xc = X_hist[[c for c in candidate_cols if c in X_hist.columns]]
        edge = Xc.index.max()
        fresh = [c for c in Xc.columns if Xc[c].last_valid_index() is not None
                and Xc[c].last_valid_index() >= edge - STALE_TOLERANCE]
        Xf = Xc[fresh] if fresh else Xc
        if Xf.shape[1] > TOP_K:
            target = y_hist.shift(-h)
            corr = Xf.apply(lambda c: c.corr(target)).abs().dropna().sort_values(ascending=False)
            Xf = Xf[corr.head(TOP_K).index.tolist()]
        Xt, yt, x_now, _ = build_supervised(y_hist, Xf, h)
        return TVWQRF(n_estimators=N_TREES).fit_predict(Xt, yt, x_now)["point"]
    return fn


def main(h: int):
    y, comp, fuel, food_w, fuel_w, core_admin_w, X = build_targets_and_panel()
    pred_sets = component_predictor_sets(X)

    print(f"food: n={comp['food'].dropna().shape[0]}  {comp['food'].dropna().index.min()}..{comp['food'].dropna().index.max()}")
    print(f"fuel: n={fuel.shape[0]}  {fuel.index.min()}..{fuel.index.max()}")
    print(f"core_admin: n={comp['core_admin'].dropna().shape[0]}  weights food={food_w:.3f} fuel={fuel_w:.3f} core_admin={core_admin_w:.3f}")

    oos_start = "2018-01"  # component depth (fuel 2016-02) gates this; matches the pre-extension baseline window for a fair comparison
    results = {}
    for name, target in [("food", comp["food"]), ("fuel", fuel), ("core_admin", comp["core_admin"])]:
        fn = make_tvwqrf_fn(pred_sets[name])
        bt = run_backtest(target.dropna(), X, h, oos_start, {"TVW_QRF": fn}, min_train=MIN_TRAIN)
        results[name] = bt
        resid = bt["actual"] - bt["TVW_QRF"]
        print(f"  {name} component h={h}: n={len(bt)}  RMSE={np.sqrt((resid**2).mean()):.3f}")

    common_idx = results["food"].index.intersection(results["fuel"].index).intersection(results["core_admin"].index)
    recombined = (food_w * results["food"].loc[common_idx, "TVW_QRF"]
                 + fuel_w * results["fuel"].loc[common_idx, "TVW_QRF"]
                 + core_admin_w * results["core_admin"].loc[common_idx, "TVW_QRF"])
    actual_headline = y.reindex(common_idx)
    resid = actual_headline - recombined
    rmse = np.sqrt((resid**2).mean())
    print(f"\n4-WAY RECOMBINED h={h}: n={len(common_idx)}  {common_idx.min()}..{common_idx.max()}  RMSE={rmse:.3f}")

    out = pd.DataFrame({"actual": actual_headline, "recombined_4way": recombined,
                        "food_pred": results["food"].loc[common_idx, "TVW_QRF"],
                        "fuel_pred": results["fuel"].loc[common_idx, "TVW_QRF"],
                        "core_admin_pred": results["core_admin"].loc[common_idx, "TVW_QRF"]})
    out.to_csv(os.path.join(OUT, f"backtest_4way_h{h}.csv"))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--h", type=int, default=3)
    args = ap.parse_args()
    main(args.h)
