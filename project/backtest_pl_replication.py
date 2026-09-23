"""
backtest_pl_replication.py — robustness check, NOT a production PL model.

Question: does the CZ finding ("directional hit-rate vs survey rises
monotonically with surprise size, 25%->70% across quartiles") replicate on
a different country's data, or was it a small-sample (n=16 big-surprise)
CZ-specific artifact? Poland chosen (not Hungary, per user) because
poland.duckdb already has CZ-parity depth (GUS/NBP native pulls, own
Rushin, consensus survey, bond yields) — no new plumbing needed.

Deliberately lean: a single top-down TVW-QRF h=1 model (no fuel/component
split, no hybrid) — proportionate to a replication check, not a rebuild of
the CZ effort. Same TOP_K correlation pre-selection, same TVWQRF class,
same run_backtest engine, reused as-is from the CZ build.

Usage: python backtest_pl_replication.py
"""
from __future__ import annotations
import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CFG
from models.horizon_models import TVWQRF, build_supervised
from backtest.engine import run_backtest

DB = r"C:\Users\luis_\economic_db\poland.duckdb"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)

N_TREES = int(os.environ.get("QRF_TREES", CFG.qrf_trees))
TOP_K = int(os.environ.get("TOP_K_FEATURES", 8))
MIN_TRAIN = int(os.environ.get("MIN_TRAIN", 36))


def load_panel():
    con = duckdb.connect(DB, read_only=True)
    # code=6656078 ("Grand total") is the long-history headline series
    # (2010-01+); code=14916914 ("0 - TOTAL") is a separate, more-current
    # 3-month snapshot (Jan-Mar 2026) -- union both for max freshness.
    y_df = con.sql("""
        SELECT date, value FROM cpi_pl.cpi_long WHERE code='6656078' AND measure_id=2
        UNION
        SELECT date, value FROM cpi_pl.cpi_long WHERE code='14916914' AND measure_id=2
    """).df()
    ppi = con.sql("SELECT year, month, mom_pct FROM gus.ppi_ri").df()
    biz = con.sql("""
        SELECT year, month, avg(indicator_sa) v FROM gus.business_confidence
        WHERE sector='manufacturing' GROUP BY 1,2
    """).df()
    cons = con.sql("""
        SELECT date, value FROM gus.consumer_confidence WHERE indicator='bwuk'
    """).df()
    core = con.sql("""
        SELECT year, month, core_ex_food_energy_mom_pct, trimmed_mean_mom_pct
        FROM nbp.core_inflation_monthly
    """).df()
    fx = con.sql("SELECT year_month, code, avg_mid FROM monetary.fx_monthly WHERE code IN ('EUR','USD')").df()
    yld = con.sql("SELECT year, month, yield_pct FROM monetary.bond_yields WHERE tenor='10y_govt'").df()
    rushin = con.sql("SELECT date, pc1_std FROM main.pl_rushin_monthly").df()
    wages = con.sql("SELECT year, month, yoy_pct FROM gus.wages_nom_yoy").df()
    expect = con.sql("""
        SELECT survey_date, value_pct FROM consensus.inflation_expectations
        WHERE target='cpi_headline_yoy' AND horizon_kind != 'fixed_year'
    """).df()
    con.close()

    def pmm(df, col_y="year", col_m="month"):
        return pd.PeriodIndex(pd.to_datetime(dict(year=df[col_y], month=df[col_m], day=1)), freq="M")

    y = pd.Series(y_df["value"].values, index=pd.PeriodIndex(pd.to_datetime(y_df["date"]), freq="M")).sort_index()
    y = (y - 100.0).rename("cpi_mm")

    ppi_s = pd.Series(ppi["mom_pct"].values, index=pmm(ppi), name="ppi_mm").groupby(level=0).mean().sort_index()
    biz_s = pd.Series(biz["v"].values, index=pmm(biz), name="biz_conf").sort_index()
    cons_s = pd.Series(cons["value"].values, index=pd.PeriodIndex(pd.to_datetime(cons["date"]), freq="M"),
                       name="cons_conf").sort_index()
    core_ex = pd.Series(core["core_ex_food_energy_mom_pct"].values, index=pmm(core), name="core_ex_fe_mm").sort_index()
    trim = pd.Series(core["trimmed_mean_mom_pct"].values, index=pmm(core), name="trimmed_mean_mm").sort_index()
    yld_s = pd.Series(yld["yield_pct"].values, index=pmm(yld), name="pl10y").sort_index()
    rushin_s = pd.Series(rushin["pc1_std"].values, index=pd.PeriodIndex(pd.to_datetime(rushin["date"]), freq="M"),
                         name="rushin").sort_index()
    wages_s = pd.Series(wages["yoy_pct"].values, index=pmm(wages), name="wages_yoy").sort_index()
    expect_s = pd.Series(expect["value_pct"].values,
                         index=pd.PeriodIndex(pd.to_datetime(expect["survey_date"]), freq="M"),
                         name="expect").groupby(level=0).mean().sort_index()

    fx_piv = fx.assign(period=pd.PeriodIndex(fx["year_month"], freq="M")).pivot_table(
        index="period", columns="code", values="avg_mid").sort_index()
    fx_mm = pd.DataFrame({"eurpln_mm": 100 * fx_piv["EUR"].pct_change(), "usdpln_mm": 100 * fx_piv["USD"].pct_change()})

    X = pd.concat([ppi_s, biz_s, cons_s, core_ex, trim, yld_s, rushin_s, wages_s, expect_s, fx_mm], axis=1).sort_index()
    return y, X


def main():
    y, X = load_panel()
    print(f"y: {y.index.min()}..{y.index.max()} n={len(y)}")
    print(f"X columns: {X.columns.tolist()}")

    def tvwqrf_fn(y_hist, X_hist, h):
        X_sel = X_hist
        if X_hist.shape[1] > TOP_K:
            target = y_hist.shift(-h)
            corr = X_hist.apply(lambda c: c.corr(target)).abs().dropna().sort_values(ascending=False)
            X_sel = X_hist[corr.head(TOP_K).index.tolist()]
        Xt, yt, x_now, _ = build_supervised(y_hist, X_sel, h)
        return TVWQRF(n_estimators=N_TREES).fit_predict(Xt, yt, x_now)["point"]

    bt = run_backtest(y, X, 1, "2018-01", {"TVW_QRF": tvwqrf_fn}, min_train=MIN_TRAIN)
    bt.to_csv(os.path.join(OUT, "backtest_pl_h1.csv"))
    resid = bt["actual"] - bt["TVW_QRF"]
    print(f"\nPL h=1 backtest: n={len(bt)}  {bt.index.min()}..{bt.index.max()}  "
          f"RMSE={np.sqrt((resid**2).mean()):.3f}  MAE={resid.abs().mean():.3f}")
    return bt


if __name__ == "__main__":
    main()
