"""
CZK CPI nowcast — main entry point.

Usage (with internet + keys):   python run_nowcast.py
Validation on synthetic data:   python run_nowcast.py --synthetic

Pipeline:
  1. Load data (public fetchers, or Bloomberg adapter when USE_BBG=1)
  2. h=0 component nowcast (fuel measured from weekly prices; food/core bridges;
     administered via announcement override)
  3. h in {1,3,6,12} TVW-QRF + benchmarks, expanding-window backtest
  4. Charts + CSVs to ./output
"""
from __future__ import annotations
import argparse
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CFG, COMPONENT_WEIGHTS_FALLBACK
from models.components import (BridgeOLS, aggregate, fuel_mm_from_weekly, nowcast_h0)
from models.horizon_models import (TVWQRF, ar_forecast, arima_forecast,
                                   build_supervised, inv_rmse_weights, rw_forecast,
                                   uc_forecast)
from models.bvar import minnesota_bvar_forecast
from backtest.engine import run_backtest, summarize, residual_zscore
import calibration

# Minnesota BVAR endogenous set: esi (activity/demand proxy), eurczk_mm (FX
# pass-through), pribor_3m (rate, delta=1.0 random-walk prior -- the one
# level/persistent series in the set, vs the other two which are already-
# stationary growth rates). All three verified deep (300+ months, back to
# 1995-2000) 2026-08-27 -- no shallow-history trap here the way SA's own
# RI-sourced activity series had.
BVAR_VARS = ["esi", "eurczk_mm", "pribor_3m"]
BVAR_DELTA = {"pribor_3m": 1.0}

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)


# ---------------------------------------------------------------------------
# Synthetic data generator — validates the full pipeline end-to-end without
# network access. Mimics Czech CPI structure: persistent core, seasonal food,
# Brent-driven fuel, steppy administered prices, plus a 2021-23-style surge.
# ---------------------------------------------------------------------------
def make_synthetic(seed=CFG.seed):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2005-01", "2026-07", freq="M")
    n = len(idx)
    month = idx.month.values

    brent_mm = rng.normal(0.3, 6.0, n)
    surge = np.where((idx >= "2021-06") & (idx <= "2023-03"), 1.0, 0.0)

    core = 0.15 + 0.25 * (month == 1) + 0.45 * surge
    core_s = np.zeros(n)
    for t in range(n):
        core_s[t] = 0.55 * (core_s[t - 1] if t else 0.2) + 0.45 * core[t] + rng.normal(0, 0.12)

    food = (0.1 + 0.5 * np.sin(2 * np.pi * (month - 2) / 12) * 0.4
            + 0.6 * surge + rng.normal(0, 0.55, n))
    fuel = 0.35 * brent_mm + 0.25 * np.roll(brent_mm, 1) + rng.normal(0, 1.6, n) + 1.2 * surge
    admin = np.where(month == 1, rng.normal(1.2, 0.8, n), rng.normal(0.05, 0.25, n)) + 1.5 * surge

    w = COMPONENT_WEIGHTS_FALLBACK
    cpi = (w["core"] * core_s + w["food"] * food + w["fuel"] * fuel
           + w["administered"] * admin)
    y = pd.Series(cpi, index=idx, name="cpi_mm")

    X = pd.DataFrame({
        "brent_czk_mm": brent_mm,
        "brent_czk_mm_l1": np.roll(brent_mm, 1),
        "agri_ppi_mm": 0.5 * np.roll(food, 1) + rng.normal(0, 0.4, n),
        "ppi_mm": 0.4 * np.roll(core_s, 1) + 0.2 * brent_mm + rng.normal(0, 0.3, n),
        "de_food_hicp_mm": 0.6 * np.roll(food, 1) + rng.normal(0, 0.3, n),
        "price_expect_survey": 10 + 30 * pd.Series(core_s).rolling(3, min_periods=1).mean().values
                               + rng.normal(0, 3, n),
        "esi": 100 - 25 * surge + rng.normal(0, 2, n),
        "eurczk_mm": rng.normal(0, 0.8, n),
    }, index=idx)

    comp = pd.DataFrame({"core": core_s, "food": food, "fuel": fuel,
                         "administered": admin}, index=idx)

    # weekly fuel prices consistent with the monthly fuel component
    wk_idx = pd.date_range("2026-05-04", "2026-08-17", freq="W-MON")
    base = 38.0
    lvl = base * np.cumprod(1 + rng.normal(0.001, 0.008, len(wk_idx)))
    weekly = pd.DataFrame({"petrol95": lvl, "diesel": lvl * 1.05 + rng.normal(0, 0.2, len(wk_idx))},
                          index=wk_idx)
    return y, X, comp, weekly


# ---------------------------------------------------------------------------
def load_real_data():
    """
    Local-first: the bulk of the panel (headline CPI, food division, PPI,
    ESI, CNB FMIE inflation expectations, FX) comes from the user's own
    actively-maintained ~/economic_db/czechia.duckdb rather than re-scraping
    it here. Three inputs aren't mirrored there yet and are pulled live:
    CZSO weekly pump prices, DE food HICP, Brent (FRED) — see
    data/local_adapter.py.
    """
    from data import local_adapter as la
    return la.load_all()


# ---------------------------------------------------------------------------
N_TREES = int(os.environ.get("QRF_TREES", CFG.qrf_trees))  # CNB WP 9/2026 spec: 500
HORIZONS = tuple(int(x) for x in os.environ.get("HORIZONS", "1,3,6").split(","))
OOS_START = os.environ.get("OOS_START", CFG.oos_start)
# CZSO's own open-data CPI series (cpi_czso.cpi_long) starts 2015-01 — that's
# the real floor on OOS depth, not any regressor's history (deepening PPI/FX
# below doesn't buy back years the target itself doesn't have). The lever
# that DOES extend usable backtest coverage within 2015-2026 is min_train:
# the default 60 pushes the first origin to ~2020-02; lowering it recovers
# 2018-2019 as pre-surge OOS months, diluting the 2021-23 surge's weight in
# the loss. 36 is a floor, not a recommendation — thinner windows widen the
# TVW-QRF validation split's own variance.
MIN_TRAIN = int(os.environ.get("MIN_TRAIN", 36))
# Unset (default) = expanding window, matching CNB WP 9/2026. Set to trade
# long-run stability for turning-point responsiveness — old-regime months
# stop diluting the fit (see the Oct-2022 surge-reversal miss).
MAX_TRAIN = int(os.environ["MAX_TRAIN"]) if os.environ.get("MAX_TRAIN") else None


def main(synthetic: bool):
    global OUT
    if synthetic:
        # Synthetic runs used to overwrite the live backtest CSVs in output/,
        # which mid-session made a smoke test's synthetic actuals (std ~0.31)
        # look like a corrupted live target (2026-09-05 false alarm -- see
        # config.qrf_max_features note). Keep them physically separate.
        OUT = os.path.join(OUT, "synthetic")
        os.makedirs(OUT, exist_ok=True)
    y, X, comp, weekly = make_synthetic() if synthetic else load_real_data()
    tag = "synthetic" if synthetic else "live"
    print(f"[{tag}] sample {y.index[0]}..{y.index[-1]}  n={len(y)}")

    # h>=1 top-down target only -- extends y back to 1991 via FRED/OECD MEI
    # (verified exact match to CZSO's own data, not a proxy -- see
    # local_adapter.load_headline_cpi_mm_extended). h=0's component-based
    # nowcast doesn't consume y directly (comp/food/core_admin drive it), so
    # this can't touch it -- deliberately NOT reassigning the shared `y`
    # name so that stays true by construction, not by care taken elsewhere.
    if synthetic:
        y_h1plus = y
    else:
        from data import local_adapter as la_ext
        y_h1plus = la_ext.load_headline_cpi_mm_extended()

    # ---- h=0 component nowcast --------------------------------------------
    ref = y.index[-1] + 1 if synthetic else pd.Timestamp.today().to_period("M")
    brent_daily = None
    if not synthetic:
        from data import local_adapter as la
        brent_daily = la.fetch_brent_czk_daily_live()
    fuel_mm, fdiag = fuel_mm_from_weekly(weekly, ref)

    if comp is not None and "core_admin" in comp.columns:
        # Local data supports food / core+administered, not the full CNB
        # 4-way split (see data/local_adapter.load_component_targets for
        # why) — fuel above is measured, not bridge-regressed.
        food_b = BridgeOLS().fit(comp["food"], X[["agri_ppi_mm", "de_food_hicp_mm"]])
        # ppi_mm = headline industry; ppi_c/services = sectoral disaggregation
        # (core goods / core services pipeline pressure, CNB WP 9/2026's PPI
        # predictor group); ppi_d = electricity/gas producer prices, feeding
        # the administered/utility side folded into this bucket.
        core_admin_cols = ["ppi_mm", "ppi_c_mm", "ppi_d_mm", "ppi_services_mm"]
        if "price_expect_survey" in X:
            core_admin_cols.append("price_expect_survey")
        if "rushin" in X:  # CNB's own weekly activity index -> output-gap proxy
            core_admin_cols.append("rushin")
        core_admin_b = BridgeOLS().fit(comp["core_admin"], X[core_admin_cols])
        food_mm = food_b.predict_period(ref)
        core_admin_mm = core_admin_b.predict_period(ref)

        food_w, fuel_w = COMPONENT_WEIGHTS_FALLBACK["food"], COMPONENT_WEIGHTS_FALLBACK["fuel"]
        comp_mm = {"food": food_mm, "fuel": fuel_mm, "core_admin": core_admin_mm}
        weights = {"food": food_w, "fuel": fuel_w, "core_admin": 1 - food_w - fuel_w}
        h0 = {"components_mm": comp_mm, "cpi_mm": aggregate(comp_mm, weights),
              "contributions": {k: weights[k] * v for k, v in comp_mm.items()}}
    elif comp is not None:  # synthetic path: full core/food/fuel/administered
        food_b = BridgeOLS().fit(comp["food"], X[["agri_ppi_mm", "de_food_hicp_mm"]])
        core_b = BridgeOLS().fit(comp["core"], X[["ppi_mm", "price_expect_survey"]]
                                 if "price_expect_survey" in X else X[["ppi_mm"]])
        food_mm = food_b.predict_period(ref)
        core_mm = core_b.predict_period(ref)
        admin_mm = float(comp["administered"].tail(12).drop(
            comp["administered"].tail(12).index[comp["administered"].tail(12).index.month == 1],
            errors="ignore").mean())
        h0 = nowcast_h0(COMPONENT_WEIGHTS_FALLBACK, fuel_mm, food_mm, core_mm, admin_mm)
    else:  # aggregate-only fallback
        food_mm = core_mm = admin_mm = float(y.tail(6).mean())
        h0 = nowcast_h0(COMPONENT_WEIGHTS_FALLBACK, fuel_mm, food_mm, core_mm, admin_mm)
    print(f"h=0 nowcast for {ref}: CPI m/m = {h0['cpi_mm']:.2f}%  "
          f"components={ {k: round(v,2) for k,v in h0['components_mm'].items()} }  fuel_diag={fdiag}")

    # ---- horizon backtest --------------------------------------------------
    # The h=0 bridges above use the full (short-history, sectoral) panel —
    # fitting once needs little data. The h>=1 backtest instead re-fits at
    # every rolling origin, so it wants DEPTH over breadth: a lean panel
    # (ppi_mm_deep splices in Eurostat pre-2015 so it isn't capped at CZSO
    # RI's 2015-01 start) beats the richer-but-shorter sectoral/agri set.
    X_backtest = X
    deep_cols: list[str] = []  # populated below for real data; stays empty
                               # (no-op restriction) in synthetic mode, where
                               # tvwqrf_fn/tvwqrf_pca_fn use X_backtest as-is
    if not synthetic and "ppi_mm_deep" in X.columns:
        deep_cols = [
            "ppi_mm_deep", "esi", "price_expect_survey", "price_expect_survey_36m",
            "eurczk_mm", "usdczk_mm", "de_food_hicp_mm", "brent_czk_mm", "brent_czk_mm_l1",
            "rushin",                                              # real activity CZ
            "ip_yoy", "constr_yoy", "unemployment_rate",           # real activity CZ
            "conf_business", "conf_consumer", "conf_economic_sentiment",  # confidence/sentiment
            "pribor_3m", "czgb_10y",                               # financial
            "de_ip_yoy", "de_retail_yoy", "de_esi",                # foreign influence (Germany)
            "household_price_expect",                              # household (vs market) inflation expectations
            "cpi_breadth", "median_cpi_mm",                        # diffusion index + reconstructed underlying inflation
        ]
        # CNB WP 9/2026-inspired additions (Poland retail confidence, Chow-
        # Lin wages, real admin-price split, credit aggregates, REER, import
        # prices, trade balance, forward-shifted Brent) have now been tried
        # TWICE under this correlation-based TOP_K selector and hurt both
        # times: raw (h=1 0.766->0.807, h=3 0.872->0.886, h=6 0.936->0.973)
        # and, 2026-08-21, ADF/KPSS-transform-selected via
        # stationarity.transform_panel() -- on the CURRENT (post-bias-fix)
        # checkpoint, h=1 0.667->0.665 (negligible), h=3 0.729->0.745,
        # h=6 0.673->0.692, h=12 0.699->0.713 (all worse). Two independent
        # negative results with the input form as the only thing that
        # changed between them means the input form wasn't the bottleneck --
        # it's the flat per-origin correlation filter itself. With the
        # candidate pool now ~36 wide instead of ~24, more chances for a
        # spuriously-correlated column to win one of only TOP_K=8 slots in a
        # ~100-origin sample, displacing genuinely useful ones. Both source
        # papers actually use PCA-derived factors as the model input, not
        # raw-predictor correlation selection at all -- that's the
        # structural difference still untested, not predictor prep.
        # transform_panel() itself stays in stationarity.py; not applied by
        # default here since the extras it would clean up aren't in play.
        #
        # X_backtest below is deliberately the WIDER 36-column set (deep_cols
        # + extra_cols) so tvwqrf_pca_fn has the full candidate pool to
        # extract factors from -- tvwqrf_fn (the correlation-selected path)
        # narrows back down to just deep_cols as its own first step, so its
        # behaviour is unchanged from the checkpointed version.
        extra_cols = ["pl_retail_conf", "wage_mm_chowlin", "admin_mm", "core_ex_admin_mm",
                      "hh_loans_mm", "nfc_loans_mm", "import_price_mm", "trade_balance",
                      "brent_fwd7m_czk_mm", "brent_fwd13m_czk_mm", "reer_ppi_mm", "reer_cpi_mm"]
        # cnb_core_inflation_mm / cnb_regulated_prices_mm (fetched into X below
        # via local_adapter.load_all -- real, verified, CNB-native ARAD series,
        # 2007-2026) deliberately excluded here, not forgotten: core inflation
        # is headline CPI minus food/fuel/regulated, i.e. a smoothed restatement
        # of the same target through a different lens rather than new
        # information; regulated_prices overlaps even more directly since h0's
        # own core_admin target is DEFINED as core+regulated. Tested together
        # in the generic PCA pool 2026-08-23: h0_hybrid RMSE 0.759->0.794,
        # worse, exactly as this reasoning predicts. Not a look-ahead issue
        # (both publish alongside headline, same as everything else sliced to
        # the last closed month) -- an information-redundancy one. The
        # regulated-prices series is still genuinely useful, just not here:
        # see the admin_announcements.csv thread for the right home for it.
        X_backtest = X[[c for c in deep_cols + extra_cols if c in X.columns]]

    # Pre-selection: with ~20 candidate regressors and only ~80-130 OOS
    # origins, feeding the QRF everything raw diluted signal from the
    # predictors that matter (see the earlier full-vs-selected comparison —
    # h=1/h=3 got WORSE once the panel widened past ~9 columns). CNB WP
    # 9/2026 and Linzenich & Meunier both pre-select before the model sees
    # the panel; this proxies that with a simple per-origin correlation
    # filter, computed strictly inside y_hist/X_hist so it can't look ahead.
    TOP_K = int(os.environ.get("TOP_K_FEATURES", 8))

    # Side-channel: tvwqrf_fn's return value is a single float (the point
    # forecast, per the models-dict interface run_backtest expects) — the
    # 5-95% quantile band it also computes would otherwise be thrown away.
    # Stash it here, keyed by (h, target_period); target_period is inferred
    # from y_hist's last index (== origin) since run_backtest doesn't pass
    # the period itself into the model callable.
    qrf_bands: dict[tuple[int, pd.Period], dict] = {}

    STALE_TOLERANCE = 2  # months a column may lag X_hist's own edge and still be selectable

    def tvwqrf_raw_fn(y_hist, X_hist, h):
        """Correlation-selected raw-predictor TVW-QRF -- the original
        checkpointed approach, retained as TVW_QRF_RAW for comparison after
        2026-08-22 promoted the PCA-factor variant (below) to be the primary
        TVW_QRF: full-sample RMSE h1 0.667->0.534, h3 0.729->0.620 (beats
        the paper's own 0.669), h6 0.673->0.662 (~matches paper's 0.661),
        h12 0.699->0.679 -- consistent gains at every horizon, gains that
        hold or strengthen ex-surge, DM-significant at p<0.01 for 3 of 4
        horizons ex-surge. See tvwqrf_fn below for why."""
        if deep_cols:
            X_hist = X_hist[[c for c in deep_cols if c in X_hist.columns]]

        # A column whose latest value predates X_hist's edge by more than
        # this pins build_supervised's x_now to that column's last-fresh
        # row for EVERY later origin, freezing the forecast (found twice
        # this session: PPI's interrupted backfill, then de_food_hicp_mm's
        # Eurostat freeze). Fix at the mechanism, not per-column: make a
        # stale column ineligible for selection rather than trust
        # correlation alone to avoid picking it.
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
        return TVWQRF(n_estimators=N_TREES).fit_predict(Xt, yt, x_now)

    N_FACTORS = int(os.environ.get("N_FACTORS", 5))
    MIN_FACTOR_HISTORY = 36  # matches MIN_TRAIN's own bar for "enough data to trust"

    def tvwqrf_fn(y_hist, X_hist, h):
        """PCA-factor TVW-QRF, promoted to the primary TVW_QRF 2026-08-22:
        standardize + extract N_FACTORS principal components from X_hist,
        feed THOSE (not raw columns) to TVW-QRF -- what CNB WP 9/2026 and
        Szafranek (NBP WP 262) actually do, instead of this project's own
        correlation-based TOP_K proxy for their pre-selection (still
        available as TVW_QRF_RAW). Fit strictly inside X_hist/y_hist per
        origin (StandardScaler + PCA refit every call), same no-look-ahead
        discipline tvwqrf_raw_fn's per-origin correlation filter already had.

        Classical PCA needs a rectangular, fully-observed matrix, but this
        panel is genuinely ragged (25 to 400+ valid points per column,
        different start dates) -- the paper's own DFM-style factor models
        handle that via EM/Kalman, which is too slow to refit at every
        origin here. Two deliberate simplifications instead: (1) a column
        needs >=MIN_FACTOR_HISTORY valid points AND to be fresh at the edge
        (same STALE_TOLERANCE bar as tvwqrf_raw_fn) to be eligible at all --
        this permanently excludes admin_mm/core_ex_admin_mm (~25 points
        even at the latest origin available) and dynamically excludes
        everything else until each column individually crosses the bar;
        (2) remaining gaps in the eligible columns are mean-imputed
        (each column's own in-sample mean, not a global one) rather than
        row-dropped, since complete-case dropna across ~20+ differently-
        dated columns would gut the usable sample -- standard practice
        when a full EM-based factor model isn't in budget, not what either
        paper actually does, and noted here so it isn't mistaken for that.
        Part of why it wins is mechanical, not just cleaner factors:
        build_supervised drops any row where ANY feature is NaN, so the raw
        path loses rows whenever any of its 8 selected columns has a gap;
        mean-imputation here means training on substantially more of the
        available history for the same tree ensemble."""
        from sklearn.preprocessing import StandardScaler
        from sklearn.decomposition import PCA

        edge = X_hist.index.max()
        eligible = [c for c in X_hist.columns
                   if X_hist[c].last_valid_index() is not None
                   and X_hist[c].last_valid_index() >= edge - STALE_TOLERANCE
                   and X_hist[c].notna().sum() >= MIN_FACTOR_HISTORY]
        if len(eligible) < 2:
            result = tvwqrf_raw_fn(y_hist, X_hist, h)  # not enough eligible columns yet
        else:
            panel = X_hist[eligible]
            imputed = panel.fillna(panel.mean())
            n_factors = max(1, min(N_FACTORS, len(eligible) - 1, imputed.shape[0] - 1))
            scaler = StandardScaler().fit(imputed.values)
            pca = PCA(n_components=n_factors, random_state=CFG.seed).fit(scaler.transform(imputed.values))
            factors = pd.DataFrame(pca.transform(scaler.transform(imputed.values)),
                                   index=imputed.index,
                                   columns=[f"pc{i + 1}" for i in range(n_factors)])
            Xt, yt, x_now, _ = build_supervised(y_hist, factors, h)
            # band_max_features: second mf=1/3 forest for the distributional
            # output only (band/PIT/CRPS) -- the point stays the mf=1.0
            # forest's. Only wired here, not in the other QRF variants, since
            # this model's qrf_bands side-channel is the only band consumer.
            result = TVWQRF(n_estimators=N_TREES,
                            band_max_features=CFG.qrf_band_max_features).fit_predict(Xt, yt, x_now)
        qrf_bands[(h, y_hist.index[-1] + h)] = result
        return result["point"]

    def tvwqrf_sqpca_fn(y_hist, X_hist, h):
        """Squared-PCA variant (Hauzenberger/Huber/Klieber 2023, IJF 39(2)):
        element-wise square the STANDARDIZED panel (X**2, not raw X) before
        the same eigendecomposition -- standardized inputs are zero-mean/
        unit-variance, so squaring collapses tranquil-period fluctuation
        toward zero and amplifies large deviations, letting factors stay
        near-silent normally and "switch on" during regime breaks (2020
        COVID, 2021-23 inflation surge -- exactly CZ's own history). Paper's
        own horse race: best/near-best 1-quarter-ahead point forecaster
        (~24% RMSE improvement vs AR, q=5), by far the strongest inflation
        correlate during recessions. Does NOT widen factor count (unlike
        the paper's other "quadratic" variant, X concatenated with X**2) --
        added as a genuinely new competing model, not a replacement for
        tvwqrf_fn above; same eligibility/imputation logic, only the PCA
        input differs. Not wired into qrf_bands (that dict backs the
        existing calibration.py pass for the primary TVW_QRF specifically;
        this is a separate, second model's bands, not tracked there)."""
        from sklearn.preprocessing import StandardScaler
        from sklearn.decomposition import PCA

        edge = X_hist.index.max()
        eligible = [c for c in X_hist.columns
                   if X_hist[c].last_valid_index() is not None
                   and X_hist[c].last_valid_index() >= edge - STALE_TOLERANCE
                   and X_hist[c].notna().sum() >= MIN_FACTOR_HISTORY]
        if len(eligible) < 2:
            return tvwqrf_raw_fn(y_hist, X_hist, h)["point"]
        panel = X_hist[eligible]
        imputed = panel.fillna(panel.mean())
        n_factors = max(1, min(N_FACTORS, len(eligible) - 1, imputed.shape[0] - 1))
        scaler = StandardScaler().fit(imputed.values)
        standardized = scaler.transform(imputed.values) ** 2
        pca = PCA(n_components=n_factors, random_state=CFG.seed).fit(standardized)
        factors = pd.DataFrame(pca.transform(standardized), index=imputed.index,
                               columns=[f"pc{i + 1}" for i in range(n_factors)])
        Xt, yt, x_now, _ = build_supervised(y_hist, factors, h)
        return TVWQRF(n_estimators=N_TREES).fit_predict(Xt, yt, x_now)["point"]

    def tvwqrf_wideraw_fn(y_hist, X_hist, h):
        """Wide-raw kitchen-sink TVW-QRF -- no PCA, no correlation filter.
        Same eligibility/imputation logic as tvwqrf_fn (mean-imputed columns
        from the WIDE deep_cols+extra_cols panel), but hands the imputed raw
        columns straight to the forest instead of extracting PCA factors
        first. Directly tests Medeiros/Montes Schutte/Soussi's "Global
        Inflation Forecasting" (2026 draft) finding: in their 91-country
        panel, RF fed the full raw predictor set beat both a linear model on
        the same raw set (EN) and a compact 2-factor summary, a margin they
        attribute explicitly to "both superior variable selection and
        nonlinearities" from RF's own bagged, random-subspace split
        selection -- no upfront filter needed. No standardization: unlike
        PCA (variance-sensitive), a tree's threshold splits are invariant to
        monotonic per-column rescaling, so it would be dead code here.
        max_features=1/3 explicit: this variant exists to test the paper's
        subspace mechanism, so it must not silently follow the config
        default (1.0) -- see _mf1 below for the all-features control.

        TESTED 2026-09-05 (full live backtest, same 175 origins as commit
        7840f70): competitive at h=1 only (0.553; the _mf1 control 0.533
        ties the PCA champion's 0.534), clearly behind the PCA-factor
        champions at h>=3 (h3 0.680 vs 0.620, h6 0.645-0.653 vs sqPCA
        0.610, h12 0.666-0.691 vs sqPCA 0.638-0.659). No pairwise DM
        significant anywhere (p 0.15-0.61), either vs the champion or
        between the mf variants -- so the paper's "hand the tree
        everything" neither beats nor statistically trails PCA factors
        here, and the subspace-vs-imputation attribution is a wash. Kept
        env-gated (WIDE_RAW=1) rather than default: two extra wide 500-tree
        fits per origin buy no measurable edge."""
        edge = X_hist.index.max()
        eligible = [c for c in X_hist.columns
                   if X_hist[c].last_valid_index() is not None
                   and X_hist[c].last_valid_index() >= edge - STALE_TOLERANCE
                   and X_hist[c].notna().sum() >= MIN_FACTOR_HISTORY]
        if len(eligible) < 2:
            return tvwqrf_raw_fn(y_hist, X_hist, h)["point"]
        panel = X_hist[eligible]
        imputed = panel.fillna(panel.mean())
        Xt, yt, x_now, _ = build_supervised(y_hist, imputed, h)
        return TVWQRF(n_estimators=N_TREES, max_features=1 / 3).fit_predict(Xt, yt, x_now)["point"]

    def tvwqrf_wideraw_mf1_fn(y_hist, X_hist, h):
        """Attribution control for TVW_QRF_WIDERAW: identical wide-raw
        imputed panel, but max_features=1.0 (the old every-tree-sees-every-
        column behaviour). The historical "wide raw panel diluted signal"
        result changed two things at once vs today's WIDERAW (dropna->mean-
        imputation AND all-features->random-subspace splits); this control
        isolates which one matters. If WIDERAW beats this, the subspace
        mechanism is doing real work; if they tie, the gain (if any) was
        just imputation/row-count."""
        edge = X_hist.index.max()
        eligible = [c for c in X_hist.columns
                   if X_hist[c].last_valid_index() is not None
                   and X_hist[c].last_valid_index() >= edge - STALE_TOLERANCE
                   and X_hist[c].notna().sum() >= MIN_FACTOR_HISTORY]
        if len(eligible) < 2:
            return tvwqrf_raw_fn(y_hist, X_hist, h)["point"]
        panel = X_hist[eligible]
        imputed = panel.fillna(panel.mean())
        Xt, yt, x_now, _ = build_supervised(y_hist, imputed, h)
        return TVWQRF(n_estimators=N_TREES, max_features=1.0).fit_predict(Xt, yt, x_now)["point"]

    def bvar_fn(y_hist, X_hist, h):
        panel = pd.concat([y_hist.rename("cpi_mm"), X_hist[BVAR_VARS]], axis=1).dropna()
        return minnesota_bvar_forecast(panel, "cpi_mm", h, delta=BVAR_DELTA)

    models = {"RW": lambda yh, Xh, h: rw_forecast(yh, h),
              "AR3": lambda yh, Xh, h: ar_forecast(yh, h),
              "ARIMA313": lambda yh, Xh, h: arima_forecast(yh, h),
              "TVW_QRF": tvwqrf_fn,
              "TVW_QRF_sqPCA": tvwqrf_sqpca_fn,
              "TVW_QRF_RAW": lambda yh, Xh, h: tvwqrf_raw_fn(yh, Xh, h)["point"],
              "BVAR": bvar_fn}
    if os.environ.get("WIDE_RAW"):
        # Kitchen-sink pair, tested 2026-09-05 and found neutral-at-best
        # (see tvwqrf_wideraw_fn docstring) -- opt-in like LQR_ENSEMBLE/UC.
        models["TVW_QRF_WIDERAW"] = tvwqrf_wideraw_fn
        models["TVW_QRF_WIDERAW_MF1"] = tvwqrf_wideraw_mf1_fn
    if os.environ.get("LQR_ENSEMBLE"):
        # CNB WP 9/2026's actual linear benchmark (500 bootstrapped median
        # quantile regressions, 4 random predictors + 3 lags each) -- ~3s/
        # origin at 500 models, so opt-in rather than always-on.
        from models.lqr_ensemble import lqr_ensemble_fn
        models["LQR_ENSEMBLE"] = lqr_ensemble_fn
    ENSEMBLE_MODELS = ["RW", "AR3", "ARIMA313", "TVW_QRF"]
    ENSEMBLE_UC_MODELS = None
    if os.environ.get("TEST_UC"):
        # Tested 2026-08-21: Szafranek (NBP WP 262) finds a non-mean-
        # reverting ensemble member (his ANN; separately a BVAR with a tight
        # steady-state prior) beats mean-reverting linear models specifically
        # during regime breaks. Local-level UCM (Stock-Watson 2007 UC-SV
        # minus stochastic vol) is the same property with no new dependency.
        # Result, full sample: h1 0.694->0.692, h3 0.737->0.730 (both
        # negligible), h6 0.689->0.691, h12 0.646->0.658 (both worse, h12
        # notably so -- a martingale trend has nothing to revert to and CPI
        # m/m over 12mo clearly does have a stable central tendency AR3
        # correctly anchors to). UC solo never beats TVW_QRF/ARIMA313 at any
        # horizon. Net: doesn't earn a place in the default ensemble.
        # Left opt-in (like LQR_ENSEMBLE) rather than deleted, in case a
        # future predictor-panel change shifts this.
        models["UC"] = lambda yh, Xh, h: uc_forecast(yh, h)
        ENSEMBLE_UC_MODELS = ENSEMBLE_MODELS + ["UC"]
    ENSEMBLE_TRAIL = int(os.environ.get("ENSEMBLE_TRAIL", 12))

    def walk_forward_ensemble(bt: pd.DataFrame, members: list[str], trail: int = ENSEMBLE_TRAIL) -> pd.Series:
        """Inverse-trailing-RMSE blend of `members`. Weights at row i use
        only errors from rows strictly before i — expanding once past the
        warm-up, then a fixed trailing window — so this cannot look ahead."""
        errs = {m: (bt[m] - bt["actual"]) for m in members}
        out = pd.Series(index=bt.index, dtype=float)
        for i in range(len(bt)):
            if i < 6:  # not enough trailing history for a meaningful RMSE yet
                w = {m: 1 / len(members) for m in members}
            else:
                lo = max(0, i - trail)
                w = inv_rmse_weights({m: errs[m].iloc[lo:i].values for m in members})
            out.iloc[i] = sum(w[m] * bt[m].iloc[i] for m in members)
        return out

    # CZ's 2021-06..2023-03 energy-crisis surge (same window flagged in
    # make_synthetic and the README) dominates squared-error loss in a short
    # OOS sample — report both full-sample and ex-surge, as CNB WP 9/2026 does.
    SURGE_START, SURGE_END = "2021-06", "2023-03"

    all_summ = {}
    bt_store = {}
    live_rows = []
    for h in HORIZONS:
        bt = run_backtest(y_h1plus, X_backtest, h, OOS_START, models, min_train=MIN_TRAIN, max_train=MAX_TRAIN)
        bt["ENSEMBLE"] = walk_forward_ensemble(bt, ENSEMBLE_MODELS)
        if ENSEMBLE_UC_MODELS is not None:
            bt["ENSEMBLE_UC"] = walk_forward_ensemble(bt, ENSEMBLE_UC_MODELS)
        bt_store[h] = bt
        summ = summarize(bt, benchmark="AR3", h=h)
        ex_surge = bt.drop(index=bt.loc[SURGE_START:SURGE_END].index)
        summ_ex_surge = summarize(ex_surge, benchmark="AR3", h=h)
        all_summ[h] = summ
        summ.to_csv(os.path.join(OUT, f"backtest_metrics_h{h}.csv"))
        summ_ex_surge.to_csv(os.path.join(OUT, f"backtest_metrics_ex_surge_h{h}.csv"))
        bt.to_csv(os.path.join(OUT, f"backtest_forecasts_h{h}.csv"))
        print(f"\n== h={h} (full sample, n={len(bt)}) ==\n{summ.round(3)}")

        # Quantile-band calibration: did the model's own 5-95% uncertainty
        # band actually cover the realized outcome, or was it confidently
        # wrong? (h0's own live band isn't backtested — this is the h>=1
        # rolling-origin band, the only one we have OOS coverage for.)
        band_rows = []
        for t in bt.index:
            r = qrf_bands.get((h, t))
            if r is None:
                continue
            lo, hi = r["p05_p95"]
            band_rows.append({"period": t, "actual": bt.loc[t, "actual"],
                              "p05": lo, "p95": hi,
                              "covered": lo <= bt.loc[t, "actual"] <= hi})
        jan_widening = None
        if band_rows:
            band_df = pd.DataFrame(band_rows).set_index("period")
            coverage = band_df["covered"].mean()
            print(f"-- h={h} TVW-QRF 5-95% band coverage: {coverage:.0%} (target ~90%, n={len(band_df)}) --")
            band_df.to_csv(os.path.join(OUT, f"qrf_band_coverage_h{h}.csv"))

            calib = calibration.summarize(qrf_bands, y_h1plus, h=h)
            if calib["ks_stat"] is not None:
                verdict = "calibrated" if calib["calibrated_at_5pct"] else "NOT calibrated"
                print(f"   PIT/KS test: stat={calib['ks_stat']}  p={calib['ks_pval']}  "
                      f"({verdict} at 5%, n={calib['n']})  |  CRPS (mean)={calib['crps_mean']}")

            # January-specific band: the band is undercovered everywhere, but
            # the actual misses concentrate in January (basket reweighting +
            # administered-price resets, structurally invisible to this
            # model). A uniform recalibration would either overwiden normal
            # months or underwiden January -- widen January specifically,
            # by the ratio of its own empirical residual spread to the rest
            # of the year's, rather than guessing a fixed multiplier.
            is_jan = band_df.index.month == 1
            resid = band_df["actual"] - (band_df["p05"] + band_df["p95"]) / 2
            jan_resid_std = resid[is_jan].std()
            other_resid_std = resid[~is_jan].std()
            if is_jan.sum() >= 3 and pd.notna(jan_resid_std) and other_resid_std:
                jan_widening = jan_resid_std / other_resid_std
                jan_cov = band_df.loc[is_jan, "covered"].mean()
                other_cov = band_df.loc[~is_jan, "covered"].mean()
                print(f"   January coverage: {jan_cov:.0%} (n={is_jan.sum()})  vs  "
                      f"other months: {other_cov:.0%} (n={(~is_jan).sum()})  "
                      f"-> January band needs {jan_widening:.1f}x width to match")
        print(f"-- h={h} (ex-surge {SURGE_START}..{SURGE_END}, n={len(ex_surge)}) --\n{summ_ex_surge.round(3)}")

        # ---- LIVE forecast: an actual forward-looking call, not a backtest.
        # Every model above only ever ran inside run_backtest, evaluated
        # against months where the actual was already known. This is the
        # first point in the pipeline that calls the same fitted models on
        # TODAY's data to predict a period that hasn't happened yet.
        live_target = y_h1plus.index[-1] + h
        live_fc = {}
        for name, fn in models.items():
            try:
                live_fc[name] = fn(y_h1plus, X_backtest, h)
            except Exception as e:
                live_fc[name] = float("nan")
        band = qrf_bands.get((h, live_target))
        band_lo, band_hi = band["p05_p95"] if band else (None, None)
        if band and live_target.month == 1 and jan_widening:
            mid = (band_lo + band_hi) / 2
            half = (band_hi - band_lo) / 2 * jan_widening
            band_lo, band_hi = mid - half, mid + half
        band_txt = f"[{band_lo:.2f}, {band_hi:.2f}]" if band else "n/a"
        jan_note = f" (January-widened {jan_widening:.1f}x)" if band and live_target.month == 1 and jan_widening else ""
        rmse_h = summ.loc["TVW_QRF", "RMSE"]
        cov_txt = f"{coverage:.0%}" if band_rows else "n/a"
        print(f"++ h={h} LIVE forecast for {live_target}: "
              f"TVW_QRF={live_fc['TVW_QRF']:.2f}%  (5-95% band {band_txt}{jan_note})  "
              f"AR3={live_fc['AR3']:.2f}%  ARIMA={live_fc['ARIMA313']:.2f}%  RW={live_fc['RW']:.2f}%  "
              f"| historical @ h={h}: RMSE={rmse_h:.2f}pp, band coverage={cov_txt} ++")
        if os.environ.get("SHAPLEY"):
            import shapley
            X_sel = X_backtest
            edge = X_sel.index.max()
            fresh = [c for c in X_sel.columns
                    if X_sel[c].last_valid_index() is not None
                    and X_sel[c].last_valid_index() >= edge - STALE_TOLERANCE]
            X_sel = X_sel[fresh] if fresh else X_sel
            if X_sel.shape[1] > TOP_K:
                corr = X_sel.apply(lambda c: c.corr(y_h1plus.shift(-h))).abs().dropna().sort_values(ascending=False)
                X_sel = X_sel[corr.head(TOP_K).index.tolist()]
            expl = shapley.explain_point_forecast(y_h1plus, X_sel, h, n_permutations=32)
            shares = sorted(expl["group_share"].items(), key=lambda kv: -kv[1])
            print(f"   Shapley (why): " + ", ".join(f"{g}={s:.0%}" for g, s in shares[:4]))
        live_rows.append({"h": h, "target_period": str(live_target), **live_fc,
                          "band_p05": band_lo, "band_p95": band_hi,
                          "historical_rmse": rmse_h, "historical_band_coverage": coverage if band_rows else None})

    pd.DataFrame(live_rows).to_csv(os.path.join(OUT, "live_forecast.csv"), index=False)

    # ---- charts ------------------------------------------------------------
    plt.style.use("seaborn-v0_8-whitegrid")
    # h=3 is the canonical chart horizon, but don't crash a partial run
    # (e.g. HORIZONS=1 smoke test) just because 3 wasn't in the set
    h = 3 if 3 in bt_store else sorted(bt_store)[0]
    bt = bt_store[h]
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(bt.index.to_timestamp(), bt["actual"], color="crimson", lw=1.6, label="Actual CPI m/m")
    ax.plot(bt.index.to_timestamp(), bt["TVW_QRF"], color="navy", lw=1.3, label="TVW-QRF (h=3)")
    ax.plot(bt.index.to_timestamp(), bt["AR3"], color="grey", lw=1.0, ls="--", label="AR(3)")
    ax.set_title(f"CZ CPI m/m — model vs actual, expanding-window OOS ({tag} data)")
    ax.set_ylabel("% m/m"); ax.legend()
    last = bt.dropna().iloc[-1]
    ax.annotate(f"last: act {last['actual']:.2f} / model {last['TVW_QRF']:.2f}",
                xy=(0.99, 0.02), xycoords="axes fraction", ha="right", fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "cpi_model_vs_actual.png"), dpi=140)

    z = residual_zscore(bt, "TVW_QRF")
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.plot(z.index.to_timestamp(), z, color="darkgreen", lw=1.2)
    for lvl, c in [(1, "orange"), (2, "red")]:
        ax.axhline(lvl, color=c, ls=":", lw=0.8); ax.axhline(-lvl, color=c, ls=":", lw=0.8)
    ax.set_title("Nowcast residual z-score (24m rolling) — surprise indicator")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "residual_zscore.png"), dpi=140)

    rr = (bt[["TVW_QRF", "AR3", "RW"]].sub(bt["actual"], axis=0) ** 2)
    roll = np.sqrt(rr.rolling(12).mean())
    fig, ax = plt.subplots(figsize=(11, 3.6))
    for c, col in zip(["navy", "grey", "sienna"], roll.columns):
        ax.plot(roll.index.to_timestamp(), roll[col], color=c, lw=1.1, label=col)
    ax.set_title("Rolling 12m RMSE — model stability"); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "rolling_rmse.png"), dpi=140)

    # component contribution chart for the h=0 nowcast
    fig, ax = plt.subplots(figsize=(7, 4))
    contr = pd.Series(h0["contributions"]).sort_values()
    contr.plot(kind="barh", ax=ax, color=["#888" if v < 0 else "#2a6" for v in contr])
    ax.set_title(f"h=0 nowcast {ref}: contributions to CPI m/m = {h0['cpi_mm']:.2f}%")
    ax.set_xlabel("pp contribution")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "h0_contributions.png"), dpi=140)

    pd.Series(h0["components_mm"]).to_csv(os.path.join(OUT, "h0_nowcast_components.csv"))
    print(f"\nOutputs written to {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    main(ap.parse_args().synthetic)
