"""
backtest_h0.py — historical evaluation of the h=0 component nowcast.

h=0 has never been backtested in this repo: run_nowcast.py only ever calls
it once, live, on the current month. This reconstructs, for each historical
month, what the SAME bottom-up nowcast (fuel measured from a genuinely
partial-month weekly-price view + food/core+administered bridges refit on
an expanding window) would have produced — then compares it to h=1's
already-backtested numbers over the identical months, both against actual
CZSO prints.

Honest limitation (matches the original README's own "Real-time vintages"
gap, which it flags as unbuilt): fuel is a genuine partial-month
reconstruction (only the historical Mondays that would have existed by a
fixed mid-month cutoff, exactly like the live fuel_mm_from_weekly path).
The bridge regressors (PPI, ESI, expectations) are NOT vintage-corrected
for publication lag — they use each series' presently-known value, which
for slow movers like PPI can be ~1-2 months fresher than what would
genuinely have been on hand in real time. Bridge COEFFICIENTS, though, are
refit on an honest expanding window: only comp/X data strictly before the
target month ever enters a given month's fit.

Usage: python backtest_h0.py
"""
from __future__ import annotations
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import COMPONENT_WEIGHTS_FALLBACK
from models.components import BridgeOLS, aggregate, fuel_mm_from_weekly
from data import local_adapter as la

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)

MIN_BRIDGE_TRAIN = 24  # months of comp history before trusting a bridge fit
CUTOFF_WEEK = 3        # Mondays of the target month treated as "observed by mid-month"
CORE_ADMIN_COLS = ["ppi_mm", "ppi_c_mm", "ppi_d_mm", "ppi_services_mm", "price_expect_survey", "rushin"]


def weekly_and_brent_asof(weekly: pd.DataFrame, brent_daily: pd.Series,
                          month: pd.Period) -> tuple[pd.DataFrame, pd.Series]:
    """Truncate both series to simulate the information set a mid-month
    nowcast would have had: prior months fully observed, target month
    limited to its first CUTOFF_WEEK Mondays (and Brent to that same date)."""
    before = weekly[weekly.index.to_period("M") < month]
    this_month = weekly[weekly.index.to_period("M") == month].sort_index().head(CUTOFF_WEEK)
    w = pd.concat([before, this_month]).sort_index()
    asof_date = this_month.index.max() if len(this_month) else (month - 1).end_time
    return w, brent_daily.loc[:asof_date]


def main():
    y = la.load_headline_cpi_mm()
    comp = la.load_component_targets()
    ppi = la.load_ppi_yoy()
    esi = la.load_esi()
    expect = la.load_inflation_expectations(12)
    de_food = la.fetch_de_food_hicp_live()
    rushin = la.fetch_rushin_monthly_live()
    X = pd.concat([ppi, esi, expect, de_food, rushin], axis=1).sort_index()

    weekly_full = la.fetch_weekly_fuels_live()
    brent_daily_full = la.fetch_brent_czk_daily_live()

    food_w = la.latest_weight_permille("01") / 1000.0
    fuel_w = COMPONENT_WEIGHTS_FALLBACK["fuel"]
    core_admin_w = 1 - food_w - fuel_w
    weights = {"food": food_w, "fuel": fuel_w, "core_admin": core_admin_w}

    core_admin_cols = [c for c in CORE_ADMIN_COLS if c in X.columns]
    last_weekly_month = weekly_full.index.max().to_period("M")

    rows = []
    for t in comp.index:
        train_idx = comp.index[comp.index < t]
        if len(train_idx) < MIN_BRIDGE_TRAIN or t not in y.index or t > last_weekly_month:
            continue
        try:
            food_b = BridgeOLS().fit(comp.loc[train_idx, "food"],
                                     X.loc[train_idx, ["agri_ppi_mm", "de_food_hicp_mm"]])
            core_admin_b = BridgeOLS().fit(comp.loc[train_idx, "core_admin"], X.loc[train_idx, core_admin_cols])
            food_mm = food_b.predict_period(t)
            core_admin_mm = core_admin_b.predict_period(t)

            weekly_t, brent_t = weekly_and_brent_asof(weekly_full, brent_daily_full, t)
            fuel_mm, fdiag = fuel_mm_from_weekly(weekly_t, t)
        except Exception as e:
            print(f"  skip {t}: {e}")
            continue

        comp_mm = {"food": food_mm, "fuel": fuel_mm, "core_admin": core_admin_mm}
        rows.append({"period": t, "actual": y.loc[t], "h0": aggregate(comp_mm, weights),
                     "fuel_frac_obs": fdiag["fraction_observed"],
                     **{f"comp_{k}": v for k, v in comp_mm.items()}})

    bt0 = pd.DataFrame(rows).set_index("period").sort_index()
    bt0["resid"] = bt0["actual"] - bt0["h0"]
    bt0.to_csv(os.path.join(OUT, "backtest_h0.csv"))

    rmse = np.sqrt((bt0["resid"] ** 2).mean())
    mae = bt0["resid"].abs().mean()
    print(f"h=0 backtest: n={len(bt0)}  {bt0.index.min()}..{bt0.index.max()}  "
          f"RMSE={rmse:.3f}  MAE={mae:.3f}  bias={bt0['resid'].mean():.3f}")
    print("\n-- 10 biggest misses --")
    print(bt0.reindex(bt0["resid"].abs().sort_values(ascending=False).index)
          .head(10)[["actual", "h0", "resid", "fuel_frac_obs"]].round(2).to_string())

    # Compare to h=1 over the SAME months, both vs the same actuals.
    h1_path = os.path.join(OUT, "backtest_forecasts_h1.csv")
    if os.path.exists(h1_path):
        bt1 = pd.read_csv(h1_path, index_col="period")
        bt1.index = pd.PeriodIndex(bt1.index, freq="M")
        common = bt0.index.intersection(bt1.index)
        if len(common):
            r0 = bt0.loc[common, "actual"] - bt0.loc[common, "h0"]
            r1 = bt1.loc[common, "actual"] - bt1.loc[common, "TVW_QRF"]
            print(f"\n-- h=0 vs h=1 TVW_QRF, same {len(common)} months --")
            print(f"h=0  RMSE={np.sqrt((r0**2).mean()):.3f}  MAE={r0.abs().mean():.3f}")
            print(f"h=1  RMSE={np.sqrt((r1**2).mean()):.3f}  MAE={r1.abs().mean():.3f}")
    return bt0


if __name__ == "__main__":
    main()
