"""energy_accounting.py -- bottom-up VALIDATION of the energy-policy ledger.

Purpose (step 1 of the post-review plan): prove the ledger MACHINERY can
compute the 2021-2023 regulated-price episode from sourced policy numbers,
by reconstructing household paid-price LEVELS per fuel and comparing the
implied regulated m/m path against CNB's realized regulated series.

THIS IS ACCOUNTING VERIFICATION, NOT FITTING: every parameter comes from
data/energy_accounting_params.csv with a source and a status flag; nothing
is tuned to the target path. Parameters flagged `gap-approx` are documented
placeholders inside publicly stated ranges -- where they drive a miss, the
CONCLUSION is "source this number before November", never "adjust it until
the backcast matches". No output of this script feeds any forecast.

v2.4 (7 Sep 2026): the merged formula corrections from Codex round 4 and
the Fable L-list are applied -- commodity cap = cap/VAT with network billed
on top (L2), POZE carried ex-VAT at 495 (599 was VAT-inclusive), the 2022
regulated-component changes made persistent and sourced from ERU (elec
+3.7%, gas +2.4%; L3/L7). This is still NOT a validated reconstruction:
the representative-household bridge, the 0.55/0.70 bill shares, the
1.8/2.2 crisis ramps and the regulated-basket weights remain declared
approximations, and CZSO's own expenditure accounting for the saving
tariff (October-2022 methodology note) is the replacement to build.

Level composition per fuel (monthly, 2021-01..2024-06):
  elec_paid  = min(commodity, cap) + network + POZE, then VAT, minus
               saving-tariff credit spread over its months (converted to
               CZK/MWh via typical consumption);
  gas_paid   = min(commodity, cap) + network, then VAT;
  heat_paid  = slow administrative path (no policy events modelled here).
Regulated index = weighted average of fuel indices + non-energy admin
(assumed flat -- its normal repricing is the seasonal baseline's job).

Usage: python energy_accounting.py
"""
from __future__ import annotations
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import local_adapter as la

HERE = os.path.dirname(os.path.abspath(__file__))


def load_params() -> pd.DataFrame:
    p = pd.read_csv(os.path.join(HERE, "data", "energy_accounting_params.csv"))
    p["applies_from"] = pd.PeriodIndex(p["applies_from"], freq="M")
    p["applies_to"] = pd.PeriodIndex(p["applies_to"], freq="M")
    return p


def pval(p: pd.DataFrame, name: str, month: pd.Period, default=np.nan) -> float:
    r = p[(p["param"] == name) & (p["applies_from"] <= month) & (p["applies_to"] >= month)]
    return float(r["value"].iloc[0]) if len(r) else default


def build_paths() -> pd.DataFrame:
    p = load_params()
    months = pd.period_range("2021-01", "2024-06", freq="M")

    base_e = pval(p, "avg_household_elec_price_2021", pd.Period("2021-06", "M"))
    base_g = pval(p, "avg_household_gas_price_2021", pd.Period("2021-06", "M"))
    # decompose 2021 baseline: commodity ~55% of elec bill, network ~45%-POZE;
    # declared structural assumption (ERU price-structure publications)
    e_comm0 = 0.55 * base_e / 1.21          # ex-VAT commodity
    e_netw0 = base_e / 1.21 - e_comm0 - pval(p, "poze_fee", pd.Period("2021-06", "M"))
    g_comm0 = 0.70 * base_g / 1.21
    g_netw0 = base_g / 1.21 - g_comm0

    cons = pval(p, "avg_household_elec_consumption", pd.Period("2022-10", "M"))
    credit_total = pval(p, "saving_tariff_credit_elec", pd.Period("2022-10", "M"))
    credit_per_mwh = credit_total / (cons * 3 / 12)  # spread over Oct-Dec

    rows = []
    for m in months:
        vat = 1 + (pval(p, "vat_waiver_elec_gas", m, default=pval(p, "vat_rate_standard", m)) / 100)
        # commodity path: baseline until the Jan-2022 supplier repricing, then
        # flat at the repriced level until the cap binds. The change comes
        # from the params CSV at its anchor month (/code-review removed a
        # dead branch whose 1.33/1.55 literals shadowed these CSV values,
        # violating the "every parameter comes from the CSV" contract).
        jan22 = pd.Period("2022-01", "M")
        if m >= jan22:
            e_comm = e_comm0 * (1 + pval(p, "supplier_elec_commodity_change", jan22, 0) / 100)
            g_comm = g_comm0 * (1 + pval(p, "supplier_gas_commodity_change", jan22, 0) / 100)
        else:
            e_comm, g_comm = e_comm0, g_comm0
        # crisis escalation through 2022 (spot-linked cohort + list rises):
        # declared coarse ramp sourced qualitatively (DPI cohort, further list
        # changes) -- flagged approximation, NOT fitted
        if m >= pd.Period("2022-07", "M"):
            e_comm = max(e_comm, e_comm0 * 1.8)
            g_comm = max(g_comm, g_comm0 * 2.2)
        cap_e = pval(p, "cap_elec_incl_vat", m)
        cap_g = pval(p, "cap_gas_incl_vat", m)
        # v2.4 (Codex R4 / L2): the decree caps the COMMODITY element; the
        # ceiling is cap / VAT-in-force -- network charges are billed on top,
        # never netted out of the ceiling
        if not np.isnan(cap_e):
            e_comm = min(e_comm, cap_e / vat)
        if not np.isnan(cap_g):
            g_comm = min(g_comm, cap_g / vat)
        # v2.4 (L7 + L3): regulated-component changes are PERSISTENT level
        # shifts (the params windows now run to 2099-12), and gas moves too
        e_netw = e_netw0 * (1 + pval(p, "eru_regulated_component_change_2022", m, 0) / 100)
        g_netw = g_netw0 * (1 + pval(p, "eru_regulated_gas_component_change_2022", m, 0) / 100)
        # POZE is carried EX-VAT (495 CZK/MWh; 599 was the VAT-inclusive
        # figure -- Codex R4) and taxed once with the rest of the bill
        poze = pval(p, "poze_waived", m,
                    default=pval(p, "poze_fee", m,
                                 default=pval(p, "poze_fee_reinstated", m, 495.0)))
        credit = credit_per_mwh if pd.Period("2022-10", "M") <= m <= pd.Period("2022-12", "M") else 0.0

        e_paid = (e_comm + e_netw + poze) * vat - credit
        g_paid = (g_comm + g_netw) * vat
        rows.append({"month": m, "elec": e_paid, "gas": g_paid})

    df = pd.DataFrame(rows).set_index("month")
    df["heat"] = 100.0  # flat placeholder (no events modelled)
    return df


def main():
    p = load_params()
    gaps = p[p["status"] != "sourced"]
    print(f"parameters: {len(p)} total, {len(gaps)} flagged gap-approx "
          f"(refine before November): {list(gaps['param'])}")

    paths = build_paths()
    we = pval(p, "weight_elec_in_regulated", pd.Period("2022-01", "M"))
    wg = pval(p, "weight_gas_in_regulated", pd.Period("2022-01", "M"))
    wh = pval(p, "weight_heat_in_regulated", pd.Period("2022-01", "M"))
    wn = 1 - we - wg - wh
    idx = (we * paths["elec"] / paths["elec"].iloc[0]
           + wg * paths["gas"] / paths["gas"].iloc[0]
           + wh * paths["heat"] / paths["heat"].iloc[0]
           + wn * 1.0) * 100
    implied_mm = 100 * idx.pct_change()

    reg = la.fetch_cnb_regulated_prices_mm_live()
    key_months = ["2021-11", "2022-01", "2022-10", "2023-01", "2024-01"]
    print("\n=== VALIDATION: implied vs realized CNB regulated m/m (pp) ===")
    print(f"{'month':8s} {'implied':>8s} {'realized':>9s} {'verdict'}")
    out = []
    for ms in key_months:
        m = pd.Period(ms, "M")
        imp = implied_mm.get(m, np.nan)
        act = reg.get(m, np.nan)
        verdict = ("sign+size OK" if np.isfinite(imp) and np.isfinite(act)
                   and np.sign(imp) == np.sign(act) and abs(imp - act) <= max(3, 0.35 * abs(act))
                   else "MISS -> trace to gap-approx param")
        print(f"{ms:8s} {imp:8.1f} {act:9.1f}  {verdict}")
        out.append({"month": ms, "implied_mm": imp, "realized_mm": act, "verdict": verdict})
    pd.DataFrame(out).to_csv(os.path.join(HERE, "output", "energy_accounting_validation.csv"), index=False)
    print("\nsaved -> output/energy_accounting_validation.csv")
    print("Reminder: misses are SOURCING tasks, never tuning targets.")


if __name__ == "__main__":
    main()
