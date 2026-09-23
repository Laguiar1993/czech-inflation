"""backtest_h0_enriched.py -- mechanism-picked panel enrichment A/B.

Adds six columns to the h0-hybrid predictor panel, each matched to a basket
mechanism (NOT panel-stuffing -- this repo already showed blind widening
hurts the correlation selector; the PCA path compresses, and every addition
here has a named channel):
  services_cpi_mm  CZSO services CPI m/m (cpi_czso.cpi_services) -- the
                   trend/persistence carrier BBIM (BoE SWP 1143) and CNB
                   WP 9/2026 both use; same-release timing convention as
                   the existing cpi_breadth/median_cpi_mm columns.
  agri_price_mm    equal-weight mean of log m/m across a staple farmgate
                   basket (CZSO CEN0203B: food wheat, milk, eggs, slaughter
                   pigs/cattle/chickens, potatoes) -- the classic food-
                   pipeline lead; +1m availability shift (published ~M+25d).
  heating_oil_mm   CZSO CEN0201F weekly ex-tax heating oil -> monthly mean
                   m/m (CPI item 0453); weekly publication, no shift.
  hpi_yoy          CZSO realized apartment prices (old_apts, CR total, yoy)
                   quarterly -> monthly ffill, +3m availability shift --
                   the acquisition-approach imputed-rents driver.
  constr_ppi_yoy   construction works price index (czso.cen0202a, IZ2015)
                   yoy, quarterly -> monthly ffill, +2m shift -- the other
                   acquisition-approach input.
  m3_yoy           CNB ARAD SMV5M108 M3 yoy, +1m shift -- demand-block
                   member (Szafranek/BBIM lineage).

Runs the champion PCA TVW-QRF and the X13_QRF variant on the ENRICHED panel
over the identical origins as backtest_h0_hybrid / backtest_h0_variants,
recombines with measured fuel, and prints the A/B against the stored
baselines. Usage: python backtest_h0_enriched.py
"""
from __future__ import annotations
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.components import fuel_mm_from_weekly
from backtest.engine import run_backtest
from backtest_h0 import weekly_and_brent_asof
from backtest_h0_hybrid import build_panel, tvwqrf_fn
from backtest_h0_variants import x13_qrf_fn
from data import local_adapter as la

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
warnings.filterwarnings("ignore")

# Compatibility re-exports: research callers keep their original imports.
from data.struct_inputs import (
    AGRI_BASKET, load_agri_price_mm, load_heating_oil_mm,
    load_housing_channel, load_services_cpi_mm, load_m3_yoy,
)


def main():
    y, y_ex_fuel, X, fuel_w = build_panel()
    extras = pd.concat([load_services_cpi_mm(), load_agri_price_mm(),
                        load_heating_oil_mm(), load_housing_channel(),
                        load_m3_yoy()], axis=1).sort_index()
    print(f"extras coverage:")
    for c in extras.columns:
        s = extras[c].dropna()
        print(f"  {c:16s} {s.index.min()}..{s.index.max()}  n={len(s)}")

    # SHORT = transmission lags of weeks-to-months (defensible at h0/h1);
    # FULL adds the slow-transmission block (M3, housing) whose literature
    # home is h>=6 -- included to answer "does it hurt the nowcast?"
    SHORT = ["services_cpi_mm", "agri_price_mm", "heating_oil_mm"]
    X_short = pd.concat([X, extras[SHORT].reindex(X.index)], axis=1)
    X_full = pd.concat([X, extras.reindex(X.index)], axis=1)
    print(f"panel {X.shape[1]} -> short {X_short.shape[1]} / full {X_full.shape[1]} cols")

    bt_s = run_backtest(y_ex_fuel, X_short, 1, "2018-01",
                        {"TVW_QRF_ENRS": tvwqrf_fn, "X13_ENRS": x13_qrf_fn}, min_train=36)
    bt_f = run_backtest(y_ex_fuel, X_full, 1, "2018-01",
                        {"TVW_QRF_ENRF": tvwqrf_fn, "X13_ENRF": x13_qrf_fn}, min_train=36)
    bt = bt_s.join(bt_f.drop(columns="actual"))
    models = ["TVW_QRF_ENRS", "X13_ENRS", "TVW_QRF_ENRF", "X13_ENRF"]
    print(f"{len(bt)} origins, {bt.index.min()}..{bt.index.max()}")

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
    out.to_csv(os.path.join(OUT, "backtest_h0_enriched.csv"))

    champ = pd.read_csv(os.path.join(OUT, "backtest_h0_hybrid.csv"), index_col="period")
    champ.index = pd.PeriodIndex(champ.index, freq="M")
    var = pd.read_csv(os.path.join(OUT, "backtest_h0_variants.csv"), index_col="period")
    var.index = pd.PeriodIndex(var.index, freq="M")
    out["h0_TVWQRF_base"] = champ["h0_hybrid"].reindex(out.index)
    out["h0_X13_base"] = var["h0_X13_QRF"].reindex(out.index)

    print(f"\nA/B (n={len(out)}, {out.index.min()}..{out.index.max()}):")
    for c in ["h0_TVWQRF_base", "h0_TVW_QRF_ENRS", "h0_TVW_QRF_ENRF",
              "h0_X13_base", "h0_X13_ENRS", "h0_X13_ENRF"]:
        if c not in out.columns:
            continue
        r = out[c] - out["actual"]
        print(f"  {c:18s} RMSE={np.sqrt(np.nanmean(r ** 2)):.3f}  MAE={np.nanmean(np.abs(r)):.3f}")
    return out


if __name__ == "__main__":
    main()
