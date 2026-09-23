"""Food sub-class (ECOICOP 4-digit) CPI series and basket weights for the
category-level food experiment (FOOD_CATEGORY_SPEC.md).

Series: cpi_czso.cpi_long, division 01, subgroup codes 0111-0119 and 012,
base 2015 = 100, all households, monthly from 2015-01 (m/m from 2015-02).
Weights: data/baskets/spot_kos{regime}.xlsx (CZSO consumer basket, per
mille of the total basket), rows E01.11..E01.19 and E01.2; regime = even
start year of the two-year weight window (cz_struct._regime).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSES = ["0111", "0112", "0113", "0114", "0115", "0116", "0117", "0118", "0119", "012"]
LABELS = {"0111": "bread & cereals", "0112": "meat", "0113": "fish", "0114": "milk, cheese, eggs",
          "0115": "oils & fats", "0116": "fruit", "0117": "vegetables", "0118": "sugar & sweets",
          "0119": "other food", "012": "non-alcoholic beverages"}
# basket files code classes as "E01.11" (2018-2024 files) or "01.11" (2014,
# 2016, 2026); the loader strips the prefix and matches the numeric form
_ECOICOP = {c: ("01." + c[2:]) if c.startswith("011") else "01.2" for c in CLASSES}


def load_class_levels() -> pd.DataFrame:
    from data import local_adapter as la
    con = la._con()
    df = con.sql("""
        SELECT date, subgroup_code, value FROM cpi_czso.cpi_long
        WHERE coicop_code = '01' AND base = 'base_2015_eq_100' AND hh_group_code = '0'
          AND subgroup_code IN ('0111','0112','0113','0114','0115','0116','0117','0118','0119','012','')
        ORDER BY date""").df()
    con.close()
    df["p"] = pd.PeriodIndex(pd.to_datetime(df["date"]), freq="M")
    df["subgroup_code"] = df["subgroup_code"].replace({"": "01"})
    piv = df.pivot_table(index="p", columns="subgroup_code", values="value", aggfunc="last").sort_index()
    return piv


def load_class_mm() -> pd.DataFrame:
    lv = load_class_levels()
    return 100.0 * lv.pct_change()


def load_class_weights() -> pd.DataFrame:
    """Rows = regime start year, columns = class codes, values = per-mille
    weight in the total basket."""
    out = {}
    for f in sorted(os.listdir(os.path.join(HERE, "data", "baskets"))):
        if not f.startswith("spot_kos") or not f.endswith(".xlsx"):
            continue
        regime = int(f[8:12])
        x = pd.read_excel(os.path.join(HERE, "data", "baskets", f), header=None)
        codes = x[0].astype(str).str.strip().str.lstrip("E")
        w = pd.to_numeric(x[4], errors="coerce")
        row = {}
        for c, e in _ECOICOP.items():
            hit = w[codes == e]
            row[c] = float(hit.iloc[0]) if len(hit) else np.nan
        row["01"] = float(w[codes == "01"].iloc[0])
        row["011"] = float(w[codes == "01.1"].iloc[0])
        out[regime] = row
    return pd.DataFrame(out).T.sort_index()


def price_updated_shares(levels: pd.DataFrame, weights: pd.DataFrame, regime_fn,
                         as_of_fn=None, available_from_fn=None) -> pd.DataFrame:
    """Share of each class in the food division for month t: basket weight
    times the class's price relative since the December before the regime
    started (the Laspeyres price-update), normalised over the classes.
    Publication gate (Codex R6): with `as_of_fn(t)` and
    `available_from_fn(regime)` given, a basket not yet published at the
    clock is replaced by the previous one (January origins use the old
    basket, as the model's own weight solver does)."""
    rows = {}
    for t in levels.index[1:]:
        reg = regime_fn(t)
        if as_of_fn is not None and available_from_fn is not None:
            if pd.Timestamp(as_of_fn(t)) < pd.Timestamp(available_from_fn(reg)):
                reg = reg - 2
        if reg not in weights.index:
            reg = weights.index[weights.index <= reg].max() if (weights.index <= reg).any() else weights.index.min()
        ref = pd.Period(f"{reg - 1}-12", freq="M")
        prev = t - 1
        s = {}
        for c in CLASSES:
            if ref in levels.index and prev in levels.index:
                s[c] = weights.loc[reg, c] * levels.loc[prev, c] / levels.loc[ref, c]
            else:
                s[c] = weights.loc[reg, c]
        tot = sum(s.values())
        rows[t] = {c: v / tot for c, v in s.items()}
    return pd.DataFrame(rows).T


def aggregate_mm(class_mm: pd.DataFrame, shares: pd.DataFrame) -> pd.Series:
    common = class_mm.index.intersection(shares.index)
    return (class_mm.loc[common, CLASSES] * shares.loc[common, CLASSES]).sum(axis=1)
