"""
backtest_h0_hybrid.py — h=0 with fuel measured (as backtest_h0.py) but food
+ core/administered replaced by a single TVW-QRF prediction of the ex-fuel
component, instead of two linear bridges.

Why: backtest_h0.py showed h=0's linear bridges (RMSE 0.940) losing to h=1's
TVW-QRF (RMSE 0.791) on the identical months — fuel's mechanical precision
isn't enough to make up for a weaker model on the other ~96.5% of the
basket. This keeps h=0's one genuine edge (real intra-month fuel prices,
via the same partial-month reconstruction) and swaps its weak link for the
model that's already proven to work better at this specific job.

Technical note: h=0 nowcasting a not-yet-closed month is structurally
identical to h=1 forecasting from the last CLOSED month — build_supervised
with h=0 would leak the target into its own y_l0 feature (x_now would
resolve to the last KNOWN month, not the open one). So the ex-fuel
component is predicted with the exact h=1 direct-forecast setup
(build_supervised(..., h=1)), just retargeted at (food+core_admin) instead
of headline.

Usage: python backtest_h0_hybrid.py
"""
from __future__ import annotations
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CFG, COMPONENT_WEIGHTS_FALLBACK
from models.components import fuel_mm_from_weekly
from models.horizon_models import TVWQRF, build_supervised
from backtest.engine import run_backtest
from backtest_h0 import weekly_and_brent_asof
from data import local_adapter as la

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)

N_TREES = int(os.environ.get("QRF_TREES", CFG.qrf_trees))
TOP_K = int(os.environ.get("TOP_K_FEATURES", 8))
MIN_TRAIN = int(os.environ.get("MIN_TRAIN", 36))


NARROW_COLS = [  # the original checkpointed panel -- tvwqrf_raw_fn restricts
    "ppi_mm_deep", "esi", "price_expect_survey", "price_expect_survey_36m",
    "eurczk_mm", "usdczk_mm", "de_food_hicp_mm", "brent_czk_mm", "brent_czk_mm_l1",
    "rushin", "ip_yoy", "retail_yoy", "constr_yoy", "unemployment_rate",
    "conf_business", "conf_consumer", "conf_economic_sentiment",
    "pribor_3m", "czgb_10y", "de_ip_yoy", "de_retail_yoy", "de_esi",
    "household_price_expect", "cpi_breadth", "median_cpi_mm",
]


def build_panel():
    """Shared by both backtest and live-forecast modes."""
    y = la.load_headline_cpi_mm()
    comp = la.load_component_targets()

    food_w = la.latest_weight_permille("01") / 1000.0
    fuel_w = COMPONENT_WEIGHTS_FALLBACK["fuel"]
    core_admin_w = 1 - food_w - fuel_w
    ex_fuel_food_share = food_w / (food_w + core_admin_w)
    y_ex_fuel = (ex_fuel_food_share * comp["food"] + (1 - ex_fuel_food_share) * comp["core_admin"]).dropna()

    # Same deep panel as run_nowcast.py's h>=1 backtest.
    ppi_deep = la.fetch_ppi_industry_yoy_deep_live()
    esi = la.load_esi()
    expect = la.load_inflation_expectations(12)
    expect_36m = la.load_inflation_expectations(36)
    fx = la.load_fx_monthly_mm()
    de_food = la.fetch_de_food_hicp_live()
    brent_mm = la.fetch_brent_czk_mm_live()
    rushin = la.fetch_rushin_monthly_live()
    activity = la.load_real_activity()
    confidence = la.load_confidence_ri()
    financial = la.load_financial()
    de_macro = la.fetch_de_macro_live()
    household_expect = la.fetch_household_price_expectations_live()
    breadth = la.load_cpi_breadth()
    median_cpi = la.load_median_cpi_mm()
    # CNB WP 9/2026-inspired additions (Poland retail confidence, Chow-Lin
    # wages, real admin-price split, credit aggregates, REER, import prices,
    # trade balance) measurably HURT this pipeline under correlation-based
    # TOP_K selection (0.691 -> 0.715 at TOP_K=8) -- same finding as
    # run_nowcast.py's h>=1 panel, same fix: NARROW_COLS keeps
    # tvwqrf_raw_fn on exactly the original checkpointed set, while the
    # PCA-factor tvwqrf_fn below (2026-08-22, promoted default) uses the
    # full wider panel, including REER (previously dropped here entirely).
    pl_retail = la.load_pl_retail_confidence()
    wage_mm = la.load_wage_mm_chowlin()
    admin_core = la.load_admin_core_split()
    credit = la.load_credit_aggregates()
    import_prices = la.fetch_import_prices_mm_live()
    trade_balance = la.load_trade_balance()
    # cnb_core_inflation_mm / cnb_regulated_prices_mm deliberately NOT wired
    # into this X -- tested 2026-08-23, RMSE 0.759->0.794 (worse). Both are
    # redundant-by-construction with THIS specific target: core inflation is
    # headline minus food/fuel/regulated (a restatement, not new information)
    # and regulated_prices overlaps directly with core_admin, which is part
    # of what y_ex_fuel literally is. See run_nowcast.py's extra_cols comment
    # for the full reasoning. Fetchers stay in local_adapter.py -- the
    # regulated-prices series belongs in the admin_announcements.csv
    # mechanism, not the generic PCA predictor pool.
    X = pd.concat([ppi_deep, esi, expect, expect_36m, fx, de_food, brent_mm,
                   brent_mm.shift(1).rename("brent_czk_mm_l1"), rushin,
                   activity, confidence, financial, de_macro,
                   household_expect, breadth, median_cpi,
                   pl_retail, wage_mm, admin_core, credit,
                   import_prices, trade_balance], axis=1).sort_index()
    return y, y_ex_fuel, X, fuel_w


STALE_TOLERANCE = 2  # months a column may lag X_hist's own edge and still be selectable
N_FACTORS = int(os.environ.get("N_FACTORS", 5))
MIN_FACTOR_HISTORY = 36


def tvwqrf_raw_fn(y_hist, X_hist, h):
    # See run_nowcast.py's tvwqrf_raw_fn for why: a stale column pins x_now
    # to its last-fresh row for every later origin, freezing the forecast.
    X_hist = X_hist[[c for c in NARROW_COLS if c in X_hist.columns]]
    edge = X_hist.index.max()
    fresh_cols = [c for c in X_hist.columns
                 if X_hist[c].last_valid_index() is not None
                 and X_hist[c].last_valid_index() >= edge - STALE_TOLERANCE]
    X_fresh = X_hist[fresh_cols] if fresh_cols else X_hist

    X_sel = X_fresh
    if X_fresh.shape[1] > TOP_K:
        target = y_hist.shift(-h)
        corr = X_fresh.apply(lambda c: c.corr(target)).abs().dropna().sort_values(ascending=False)
        X_sel = X_fresh[corr.head(TOP_K).index.tolist()]
    Xt, yt, x_now, _ = build_supervised(y_hist, X_sel, h)
    return TVWQRF(n_estimators=N_TREES).fit_predict(Xt, yt, x_now)["point"]


def tvwqrf_fn(y_hist, X_hist, h):
    """PCA-factor TVW-QRF, ported from run_nowcast.py 2026-08-22 after that
    file's version cut h1 RMSE 0.667->0.534, h3 0.729->0.620 (beats the
    paper's 0.669) -- see run_nowcast.py's tvwqrf_fn docstring for the full
    mechanism (per-origin StandardScaler+PCA refit, no-look-ahead; mean-
    imputation on eligible columns instead of the paper's EM/Kalman, since
    that's too slow to refit at every origin; part of the win is mechanical
    -- build_supervised drops any row where any raw feature is NaN, this
    doesn't). Promoted straight to primary here per instruction, backtested
    against tvwqrf_raw_fn below rather than assumed -- the ex-fuel target
    and panel width both differ from run_nowcast.py's headline case."""
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA

    edge = X_hist.index.max()
    eligible = [c for c in X_hist.columns
               if X_hist[c].last_valid_index() is not None
               and X_hist[c].last_valid_index() >= edge - STALE_TOLERANCE
               and X_hist[c].notna().sum() >= MIN_FACTOR_HISTORY]
    if len(eligible) < 2:
        return tvwqrf_raw_fn(y_hist, X_hist, h)

    panel = X_hist[eligible]
    imputed = panel.fillna(panel.mean())
    n_factors = max(1, min(N_FACTORS, len(eligible) - 1, imputed.shape[0] - 1))
    scaler = StandardScaler().fit(imputed.values)
    pca = PCA(n_components=n_factors, random_state=CFG.seed).fit(scaler.transform(imputed.values))
    factors = pd.DataFrame(pca.transform(scaler.transform(imputed.values)),
                           index=imputed.index,
                           columns=[f"pc{i + 1}" for i in range(n_factors)])
    Xt, yt, x_now, _ = build_supervised(y_hist, factors, h)
    return TVWQRF(n_estimators=N_TREES).fit_predict(Xt, yt, x_now)["point"]


FRESHNESS_COLS = ["ppi_mm_deep", "esi", "eurczk_mm", "usdczk_mm", "de_food_hicp_mm"]


def live_forecast():
    """The actual forward-looking h0-hybrid call for the current month —
    same architecture as the backtest, but fit on all available data and
    applied to a period that hasn't happened yet. Includes the
    admin_announcements override, a no-op until that file is populated.

    Also fingerprints how fresh each tracked high-frequency input was as of
    this call (last_valid_index per FRESHNESS_COLS, plus the weekly-fuel and
    daily-Brent as-of dates) -- track_nowcast() below uses this to tell two
    consecutive runs apart without needing a real news-decomposition model."""
    y, y_ex_fuel, X, fuel_w = build_panel()
    ex_fuel_live = tvwqrf_fn(y_ex_fuel, X, 1)

    weekly = la.fetch_weekly_fuels_live()
    brent_daily = la.fetch_brent_czk_daily_live()
    ref = pd.Timestamp.today().to_period("M")
    fuel_mm, fdiag = fuel_mm_from_weekly(weekly, ref)

    admin_pp = la.load_admin_override_pp(ref)
    h0 = fuel_w * fuel_mm + (1 - fuel_w) * ex_fuel_live + admin_pp
    print(f"LIVE h=0 HYBRID for {ref}: {h0:.2f}%  "
          f"(fuel={fuel_mm:.2f}% w={fuel_w:.3f}, ex_fuel={ex_fuel_live:.2f}% w={1-fuel_w:.3f}, "
          f"admin_override={admin_pp:+.2f}pp)")

    freshness = {c: (str(X[c].last_valid_index()) if c in X.columns and X[c].last_valid_index() is not None else None)
                 for c in FRESHNESS_COLS}
    freshness["weekly_fuel"] = str(weekly.index.max().date()) if len(weekly) else None
    freshness["brent_daily"] = str(brent_daily.index.max().date()) if brent_daily is not None and len(brent_daily) else None

    return {"target_period": str(ref), "h0_hybrid": h0, "fuel_mm": fuel_mm,
            "ex_fuel_pred": ex_fuel_live, "admin_override_pp": admin_pp, "freshness": freshness}


def track_nowcast():
    """Append one row to output/nowcast_history.csv per call -- the
    lightweight version of Fed-style continuous nowcasting (idea 4 in the
    status memo): re-run live_forecast() whenever this is invoked (manually,
    or on a schedule external to this script -- no scheduler is set up here)
    and log the result. Dedups against the last logged row for the SAME
    target_period: if h0_hybrid is unchanged AND every freshness date is
    identical, nothing actually could have moved between runs, so skip
    rather than log a noise row. When something did change, prints which
    inputs advanced -- a poor-man's news decomposition, not a real one
    (that needs the Kalman/DFM rebuild from idea 2, which this isn't)."""
    fc = live_forecast()
    row = {"run_ts": pd.Timestamp.now().isoformat(timespec="seconds"),
           "target_period": fc["target_period"], "h0_hybrid": fc["h0_hybrid"],
           "fuel_mm": fc["fuel_mm"], "ex_fuel_pred": fc["ex_fuel_pred"],
           "admin_override_pp": fc["admin_override_pp"], **fc["freshness"]}
    hist_path = os.path.join(OUT, "nowcast_history.csv")

    if os.path.exists(hist_path):
        hist = pd.read_csv(hist_path)
        same_target = hist[hist["target_period"] == row["target_period"]]
        if len(same_target):
            last = same_target.iloc[-1]
            fresh_cols = list(fc["freshness"].keys())
            changed = [c for c in fresh_cols if str(last.get(c)) != str(row.get(c))]
            value_changed = not np.isclose(last["h0_hybrid"], row["h0_hybrid"], atol=1e-9)
            if not changed and not value_changed:
                print(f"track_nowcast: no change for {row['target_period']} since last logged run "
                      f"({last['run_ts']}) -- skipped")
                return None
            print(f"track_nowcast: logging new entry for {row['target_period']}  "
                  f"h0_hybrid {last['h0_hybrid']:.2f}% -> {row['h0_hybrid']:.2f}%  "
                  f"(inputs advanced: {', '.join(changed) if changed else 'none -- value moved on unchanged inputs, re-check the model'})")
        else:
            print(f"track_nowcast: first entry for {row['target_period']}")
        hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
    else:
        print(f"track_nowcast: creating {hist_path}, first entry for {row['target_period']}")
        hist = pd.DataFrame([row])

    hist.to_csv(hist_path, index=False)
    return row


def main():
    y, y_ex_fuel, X, fuel_w = build_panel()
    print("Backtesting ex-fuel TVW-QRF component (TVW_QRF=PCA-factor, TVW_QRF_RAW=checkpointed correlation-select)...")
    bt_exfuel = run_backtest(y_ex_fuel, X, 1, "2018-01",
                             {"TVW_QRF": tvwqrf_fn, "TVW_QRF_RAW": tvwqrf_raw_fn}, min_train=MIN_TRAIN)
    print(f"  {len(bt_exfuel)} origins, {bt_exfuel.index.min()}..{bt_exfuel.index.max()}")
    for col in ["TVW_QRF", "TVW_QRF_RAW"]:
        r = bt_exfuel[col] - bt_exfuel["actual"]
        print(f"  ex-fuel component {col:12s} RMSE={np.sqrt((r**2).mean()):.3f}  MAE={r.abs().mean():.3f}")

    # Fuel: identical partial-month reconstruction as backtest_h0.py.
    weekly_full = la.fetch_weekly_fuels_live()
    brent_daily_full = la.fetch_brent_czk_daily_live()
    last_weekly_month = weekly_full.index.max().to_period("M")

    rows = []
    for t in bt_exfuel.index:
        if t not in y.index or t > last_weekly_month:
            continue
        try:
            weekly_t, brent_t = weekly_and_brent_asof(weekly_full, brent_daily_full, t)
            fuel_mm, _ = fuel_mm_from_weekly(weekly_t, t)
        except Exception as e:
            print(f"  skip {t}: {e}")
            continue
        ex_fuel_pred = bt_exfuel.loc[t, "TVW_QRF"]
        ex_fuel_pred_raw = bt_exfuel.loc[t, "TVW_QRF_RAW"]
        h0 = fuel_w * fuel_mm + (1 - fuel_w) * ex_fuel_pred
        h0_raw = fuel_w * fuel_mm + (1 - fuel_w) * ex_fuel_pred_raw
        rows.append({"period": t, "actual": y.loc[t], "h0_hybrid": h0, "h0_hybrid_raw": h0_raw,
                     "ex_fuel_pred": ex_fuel_pred, "ex_fuel_actual": bt_exfuel.loc[t, "actual"],
                     "fuel_mm": fuel_mm})

    bth = pd.DataFrame(rows).set_index("period").sort_index()
    bth["resid"] = bth["actual"] - bth["h0_hybrid"]
    bth["resid_raw"] = bth["actual"] - bth["h0_hybrid_raw"]
    bth.drop(columns=["h0_hybrid_raw", "resid_raw"]).to_csv(os.path.join(OUT, "backtest_h0_hybrid.csv"))

    rmse = np.sqrt((bth["resid"] ** 2).mean())
    mae = bth["resid"].abs().mean()
    rmse_raw = np.sqrt((bth["resid_raw"] ** 2).mean())
    mae_raw = bth["resid_raw"].abs().mean()
    print(f"\nh=0 HYBRID backtest: n={len(bth)}  {bth.index.min()}..{bth.index.max()}  "
          f"RMSE={rmse:.3f}  MAE={mae:.3f}  bias={bth['resid'].mean():.3f}")
    print(f"h=0 HYBRID (raw-select, for comparison): RMSE={rmse_raw:.3f}  MAE={mae_raw:.3f}  "
          f"bias={bth['resid_raw'].mean():.3f}")
    print("\n-- 10 biggest misses --")
    print(bth.reindex(bth["resid"].abs().sort_values(ascending=False).index)
          .head(10)[["actual", "h0_hybrid", "resid"]].round(2).to_string())

    # Compare all three: h0 linear-bridge, h0 hybrid, h1 pure top-down.
    h0_path = os.path.join(OUT, "backtest_h0.csv")
    h1_path = os.path.join(OUT, "backtest_forecasts_h1.csv")
    if os.path.exists(h0_path) and os.path.exists(h1_path):
        bt0 = pd.read_csv(h0_path, index_col="period"); bt0.index = pd.PeriodIndex(bt0.index, freq="M")
        bt1 = pd.read_csv(h1_path, index_col="period"); bt1.index = pd.PeriodIndex(bt1.index, freq="M")
        common = bth.index.intersection(bt0.index).intersection(bt1.index)
        if len(common):
            r_h0 = bt0.loc[common, "actual"] - bt0.loc[common, "h0"]
            r_h1 = bt1.loc[common, "actual"] - bt1.loc[common, "TVW_QRF"]
            r_hy = bth.loc[common, "resid"]
            print(f"\n-- three-way comparison, same {len(common)} months --")
            for name, r in [("h0 linear-bridge", r_h0), ("h1 pure top-down", r_h1), ("h0 HYBRID", r_hy)]:
                print(f"  {name:20s} RMSE={np.sqrt((r**2).mean()):.3f}  MAE={r.abs().mean():.3f}")
    return bth


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="print the current live forecast instead of backtesting")
    ap.add_argument("--track", action="store_true", help="live forecast + append to output/nowcast_history.csv (dedups no-change reruns)")
    args = ap.parse_args()
    if args.track:
        track_nowcast()
    elif args.live:
        live_forecast()
    else:
        main()
