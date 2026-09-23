"""Shared input loaders for CZ-STRUCT and the enrichment research driver.

Moved without changing numerical transformations from backtest_h0_enriched.
Availability shifts are model conventions, not independently recorded vintages.
"""
from __future__ import annotations
import os
import duckdb
import numpy as np
import pandas as pd
from data import local_adapter as la

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AGRI_BASKET = [  # staple farmgate products, long coverage, food-CPI relevant
    # exact Reprezentant labels from CEN0203B (verified 2026-09-05; note the
    # double space in the pigs label -- these are matched verbatim)
    "Pšenice potravinářská [t]",
    "Mléko kravské Q. tř. j. [tis. l.]",
    "Vejce slepičí konzumní tříděná [tis. ks]",
    "Prasata jatečná  j.tř. SEU v JUT [t]",
    "Kuřata jatečná v živém I.tř.j [t]",
    "Brambory pozdní konzumní [t]",
    "Jablka konzumní [t]",
]


def load_agri_price_mm() -> pd.Series:
    raw = pd.read_csv(os.path.join(HERE, "data", "cz_agri_prices_raw.csv"))
    monthly = raw[raw["CASMKMQR"].astype(str).str.match(r"^\d{4}-\d{2}$")].copy()
    # national rows carry NaN in the kraj (region) code; regional rows would
    # otherwise get silently averaged into the pivot
    monthly = monthly[monthly["UZ02HU.KRAJ"].isna()]
    monthly = monthly[monthly["Reprezentant"].isin(AGRI_BASKET)]
    monthly["p"] = pd.PeriodIndex(monthly["CASMKMQR"], freq="M")
    piv = monthly.pivot_table(index="p", columns="Reprezentant", values="Hodnota").sort_index()
    logmm = 100.0 * np.log(piv).diff()
    mm = logmm.mean(axis=1, skipna=True)
    # published ~25 days into M+1 -> label u holds agri(u-1). v2.4: shift the
    # LABELS (freq="M"), not the values within the index -- a positional
    # shift dropped the newest month at the edge (Fable D1 / Codex R4 P0).
    return mm.shift(1, freq="M").rename("agri_price_mm")


def load_heating_oil_mm() -> pd.Series:
    raw = pd.read_csv(os.path.join(HERE, "data", "cz_heating_oil_weekly_raw.csv"))
    lvl = raw[raw["Ukazatel"].str.startswith("Průměrná cena")].copy()
    # CasT2 like '2016-W01' or textual weeks; parse year+week
    wk = lvl["CasT2"].astype(str).str.extract(r"(\d{4})-?W?(\d{2})")
    ok = wk.notna().all(axis=1)
    lvl, wk = lvl[ok], wk[ok]
    dt = pd.to_datetime(wk[0] + "-W" + wk[1] + "-1", format="%G-W%V-%u", errors="coerce")
    s = pd.Series(lvl["Hodnota"].values, index=dt).dropna().sort_index()
    m = s.resample("ME").mean()
    m.index = m.index.to_period("M")
    return (100.0 * m.pct_change()).rename("heating_oil_mm")


def load_housing_channel() -> pd.DataFrame:
    con = duckdb.connect(str(la.DB_PATH), read_only=True)
    hpi = con.sql("""
        SELECT quarter_end, value FROM czso.hpi
        WHERE category='old_apts' AND region='cr_total' AND index_type='yoy_pct'
        ORDER BY quarter_end""").df()
    constr = con.sql("""
        SELECT "CASQKQ" AS q, "Hodnota_num" AS v FROM czso.cen0202a
        WHERE "TYPUDAJESTAV"='IZ2015' AND "STAVDILA"='0'
          AND "CASQKQ" SIMILAR TO '[0-9]{4}-Q[0-9]K?'
        ORDER BY q""").df()
    con.close()

    hq = pd.Series(hpi["value"].values,
                   index=pd.PeriodIndex(pd.to_datetime(hpi["quarter_end"]), freq="Q"))
    constr["q"] = constr["q"].str.replace("K", "", regex=False)
    cq = pd.Series(constr["v"].values, index=pd.PeriodIndex(constr["q"], freq="Q")).sort_index()
    cq = cq.groupby(level=0).last()
    cq_yoy = 100.0 * (cq / cq.shift(4) - 1.0)

    def q_to_m(sq: pd.Series, lag_m: int, name: str) -> pd.Series:
        sm = sq.copy()
        sm.index = sq.index.asfreq("M", how="end")
        sm = sm.resample("M").ffill()
        return sm.shift(lag_m).rename(name)

    return pd.concat([q_to_m(hq.dropna(), 3, "hpi_yoy"),
                      q_to_m(cq_yoy.dropna(), 2, "constr_ppi_yoy")], axis=1)


def load_services_cpi_mm() -> pd.Series:
    con = duckdb.connect(str(la.DB_PATH), read_only=True)
    df = con.sql("""
        SELECT date, value FROM cpi_czso.cpi_services
        WHERE base='base_2015_eq_100' AND hh_group_code='0'
        ORDER BY date""").df()
    con.close()
    s = pd.Series(df["value"].values,
                  index=pd.PeriodIndex(pd.to_datetime(df["date"]), freq="M")).sort_index()
    s = s.groupby(level=0).last()
    return (100.0 * s.pct_change()).rename("services_cpi_mm")


def load_m3_yoy() -> pd.Series:
    con = duckdb.connect(str(la.DB_PATH), read_only=True)
    df = con.sql("""
        SELECT period, value FROM monetary.arad_data
        WHERE indicator_id='SMV5M108' ORDER BY period""").df()
    con.close()
    s = pd.Series(df["value"].values,
                  index=pd.PeriodIndex(pd.to_datetime(df["period"]), freq="M")).sort_index()
    s = s.groupby(level=0).last()
    return (100.0 * (s / s.shift(12) - 1.0)).shift(1).rename("m3_yoy")
