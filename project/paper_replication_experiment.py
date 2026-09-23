"""Closest-data replication of CNB Working Paper 9/2026, Table A6.

This is a research lane kept separate from the operating independent nowcast.
It reconstructs the paper's direct h-step TVW-QRF design on the frozen local
panel, records every A6 predictor as ``exact``, ``proxy`` or ``missing``, and
reports the resulting score beside the paper's published benchmark.  The
runner does not claim an exact replication when a source, transformation,
vintage, seasonal-adjustment procedure or quantile-forest implementation is
different.

The paper window is May 2002--September 2025, with an expanding fit through
December 2010 and h in {3, 6, 9, 12}.  The default panel below uses the exact
NSA Czech headline m/m target available in this repository.  The paper's
sentence that all series were X-13-adjusted is preserved as an unresolved
comparison flag: no X-13 executable or vintaged adjusted target is bundled,
and the published RMSE scale is much more consistent with the NSA target.

Inputs are frozen CSV snapshots under ``data/paper_replication``.  The
optional Bloomberg snapshot is used only for a labelled market-proxy lane;
the hard-data independent policy excludes survey predictors but may include
market prices if those files are present.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from models.paper_big import (
    POLICIES,
    SklearnLeafTVWQRF,
    direct_tvwqrf_forecast,
)


HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "paper_replication"
TARGET_PATH = DATA / "headline_extended_and_states.csv"
PANEL_PATH = DATA / "paper_predictor_panel.csv"
DEFAULT_OUTPUT = HERE / "output" / "cnb_paper_replication_20260910"


@dataclass(frozen=True)
class A6Variable:
    number: int
    group: str
    description: str
    transform: int
    kind: str  # hard, survey, expectation
    source: str
    status: str  # exact, proxy, missing
    source_column: str | None = None
    note: str = ""


def _a6_rows() -> list[A6Variable]:
    """Return the paper's 72 predictors and their local mapping status."""

    rows: list[A6Variable] = []

    def add(n, group, description, transform, kind, source, status, column=None, note=""):
        rows.append(A6Variable(n, group, description, transform, kind, source, status, column, note))

    # The detailed EC question balances are not present in the local Eurostat
    # snapshot.  They are deliberately listed rather than replaced by a broad
    # ESI value; broad aggregates are added below as clearly labelled proxies.
    g1 = [
        (1, "Production observed over past 3 months"),
        (2, "Production expectations over next 3 months"),
        (3, "Business situation over past 3 months"),
        (4, "Demand evolution over past 3 months"),
        (5, "Business activity or sales over past 3 months"),
        (6, "Building activity over past 3 months"),
        (7, "Building activity limited by labour shortage"),
        (8, "Building activity limited by material or equipment shortage"),
        (9, "Building activity limited by financial constraints"),
        (10, "Financial situation expected over next 13 months"),
    ]
    for n, desc in g1:
        add(n, "G1", desc, 0 if n in (1, 2) else 3, "survey", "Eurostat BCS detailed CZ question", "missing")
    add(11, "G1", "Czech unemployment", 0, "hard", "CZSO unemployment_ri", "exact", "unemployment_rate")
    add(12, "G1", "Czech industrial production index", 0, "hard", "CZSO PRU01C seasonally adjusted level", "exact", "ip_level")
    add(13, "G1", "Czech building permits converted to monthly counts", 0, "hard", "CZSO building permits / Bloomberg candidate", "proxy", "building_permits_index",
        "Local table contains an index proxy and a gap. User-supplied CZGRIDX remains pending a direct-count versus cumulative-count definition audit; if cumulative, difference within calendar year before use.")
    add(14, "G1", "CNB Rushin activity index", 0, "hard", "CNB Rushin XLS snapshot", "proxy", "rushin",
        "Series is exact in concept but local history begins in 2008 and has no vintaged release archive.")
    for n, desc in [(15, "CNB LUCI total"), (16, "CNB LUCI wages and labour costs"), (17, "Nominal unit labour costs")]:
        note = "Quarterly LCI proxy exists but is not the named series."
        if n == 17:
            note = "Selected quarterly Bloomberg candidate is LCTQCZI Index; LCTOCZI Index is annual only. Apply prospective Chow–Lin disaggregation after definition and vintage checks."
        add(n, "G1", desc, 0, "hard", "CNB LUCI/ULC", "missing", note=note)

    for n, desc, tr in [
        (18, "German industrial confidence", 0),
        (19, "German services confidence", 3),
        (20, "German retail confidence", 3),
        (21, "German construction confidence", 3),
    ]:
        add(n, "G2", desc, tr, "survey", "Eurostat BCS detailed DE question", "missing")
    add(22, "G2", "Polish retail confidence", 2, "survey", "GUS/Eurostat retail confidence", "proxy", "pl_retail_conf",
        "Frozen panel has a short Polish retail-confidence series, not the full paper vintage.")
    add(23, "G2", "German HICP", 2, "hard", "ECB HICP mirror, DE total", "proxy", "de_hicp_total",
        "Total HICP starts in 2014 in the local mirror; earlier history is unavailable.")
    add(24, "G2", "German unemployment", 0, "hard", "Eurostat/Destatis", "missing")
    add(25, "G2", "Czech balance of trade, FOB/FOB", 2, "hard", "CZSO trade balance", "proxy", "trade_balance",
        "Signed balance cannot be log-differenced without a paper-documented sign convention; a signed log transform is used.")
    add(26, "G2", "Czech import prices", 2, "hard", "CZSO import price index", "proxy", "import_price_mm",
        "Frozen source stores the published m/m index change rather than the underlying level.")
    add(27, "G2", "Euro-area domestic inflation expectations balance", 0, "expectation", "Eurostat consumer survey", "missing")
    add(28, "G2", "Euro-area perceived inflation balance", 0, "expectation", "Eurostat consumer survey", "missing")

    for n, desc, tr in [
        (29, "Czech industrial confidence", 3),
        (30, "Czech demand expectations next 3 months", 3),
        (31, "Czech employment expectations next 3 months", 3),
        (32, "Czech services confidence", 0),
        (33, "Orders placed with suppliers next 3 months", 3),
        (34, "Business activity expectations next 3 months", 3),
        (35, "Employment expectations next 3 months", 3),
        (36, "Czech retail confidence", 3),
        (37, "Construction employment expectations", 3),
        # Table A6 prints transform 3 for row 38 (PDF text layer and rendered
        # page checked 12 Sep 2026); the earlier transcription had 0.
        (38, "Czech construction confidence", 3),
        (39, "Financial situation over last 13 months", 3),
        (40, "Savings over next 13 months", 3),
        (41, "Unemployment expectations over next 13 months", 3),
        (42, "Major purchases over next 13 months", 3),
    ]:
        add(n, "G3", desc, tr, "survey", "Eurostat BCS detailed CZ question", "missing")

    add(43, "G4", "Agricultural PPI year-on-year", 0, "hard", "CZSO agricultural PPI", "exact", "agri_ppi_mm")
    add(44, "G4", "Industrial PPI year-on-year", 0, "hard", "CZSO industrial PPI", "exact", "ppi_mm_deep")
    for n, desc, col in [
        (45, "Total industrial PPI", "ppi_total_level"),
        (46, "Industrial mineral resources", "ppi_mineral_level"),
        (47, "Industrial manufactured goods", "ppi_manufactured_level"),
        (48, "Industrial electricity, gas and steam", "ppi_energy_level"),
        (49, "Industrial water supply", "ppi_water_level"),
    ]:
        add(n, "G4", desc, 2, "hard", "CZSO CEN0201A fixed-base PPI", "exact", col)
    for n, desc, _kind in [
        (50, "Agricultural animal-based products", "animal"),
        (51, "Agricultural plant-based products", "plant"),
        (52, "Agricultural production and fish", "agriculture/fish"),
    ]:
        add(n, "G4", desc, 2, "hard", "CZSO agricultural PPI", "missing", note="Farm-gate proxy exists but is not the official aggregate PPI.")

    add(53, "G5", "Ten-year Czech government yield monthly average", 0, "hard", "CNB ARAD SVSDM12", "exact", "czgb_10y")
    add(54, "G5", "Three-month PRIBOR end-of-month", 0, "hard", "CNB ARAD/Bloomberg PRIB03M", "proxy", "pribor_eom",
        "Static Bloomberg end-of-month values are available; ARAD local series is monthly average.")
    add(55, "G5", "Two-week CNB repo rate end-of-month", 0, "hard", "CNB ARAD SFTP01M11", "exact", "repo_rate")
    add(56, "G5", "REER deflated by PPI", 2, "hard", "CNB ARAD SREERM101", "exact", "reer_ppi_level")
    add(57, "G5", "REER deflated by CPI", 2, "hard", "CNB ARAD SREERM103", "exact", "reer_cpi_level")
    add(58, "G5", "NFC client-loan balance", 2, "hard", "CNB ARAD client loans", "proxy", "nfc_loans_level",
        "ARAD VST has a total plus three maturity rows; the total is used once. It covers commercial banks and foreign bank branches excluding CNB, so full-MFI coverage remains a comparison caveat.")
    add(59, "G5", "Household client-loan balance", 2, "hard", "CNB ARAD SUCM102211XXX101101", "exact", "hh_loans_level")

    add(60, "G6", "Brent crude spot USD/barrel", 0, "hard", "Brent daily snapshot", "exact", "brent_spot_usd")
    add(61, "G6", "Average European natural-gas price", 2, "hard", "TTF/European gas snapshot", "proxy", "gas_spot_proxy",
        "Year-1 TTF forward is used as a market proxy; a historical spot series is not frozen.")
    add(62, "G6", "Industrial-metals price index", 2, "hard", "Global commodity index", "missing")
    add(63, "G6", "Food-commodity price index", 2, "hard", "Global commodity index", "missing")
    add(64, "G6", "First principal component of four Czech fuel prices", 2, "hard", "CZSO weekly petrol95/petrol98/diesel/LPG", "proxy", "fuel_pca_3type_level",
        "The frozen local file has petrol95, diesel and LPG; CZSO's CENPHMT weekly survey contains petrol98, which remains to be imported and clock-checked before this becomes an exact four-price PCA.")
    add(65, "G6", "Refinitiv natural-gas forward", 0, "hard", "Refinitiv/TTF forward", "proxy", "gas_fwd1y_level",
        "TTFGCY1 Bloomberg Year-1 generic begins in 2013; exact Refinitiv vintages are unavailable.")
    add(66, "G6", "Refinitiv Brent forward", 0, "hard", "Refinitiv/ICE Brent forward", "proxy", "brent_fwd1y_level",
        "FSBTY1 Bloomberg Year-1 generic begins in 2013; exact Refinitiv vintages are unavailable.")

    add(67, "G7", "Selling-price expectations next 3 months", 3, "expectation", "Eurostat BCS detailed question", "missing")
    add(68, "G7", "Construction-price expectations next 3 months", 3, "expectation", "Eurostat BCS detailed question", "missing")
    add(69, "G7", "Financial-market inflation expectation at 3 years", 0, "expectation", "CNB FMIE", "proxy", "price_expect_survey_36m",
        "Frozen FMIE history is a survey-month snapshot without exact release timestamps.")
    add(70, "G7", "Financial-market inflation expectation at 1 year", 0, "expectation", "CNB FMIE", "proxy", "price_expect_survey",
        "Frozen FMIE history is a survey-month snapshot without exact release timestamps.")
    add(71, "G7", "Perceived inflation balance", 0, "expectation", "Eurostat consumer survey", "missing")
    add(72, "G7", "Expected domestic inflation balance", 0, "expectation", "Eurostat consumer survey", "proxy", "household_price_expect",
        "Household 12-month price-trend balance is not the paper's Euro-area balance.")
    assert len(rows) == 72
    return rows


A6 = _a6_rows()
A6_BY_NUMBER = {row.number: row for row in A6}


def _period_index(values: Iterable[object]) -> pd.PeriodIndex:
    """Normalize dates/periods to a monthly ``PeriodIndex``.

    ARAD exports are parsed as monthly periods before being passed through
    this helper, while CSV/JSON sources usually provide timestamps.  Pandas
    cannot feed ``Period`` objects to ``to_datetime`` directly, so handle an
    existing ``PeriodIndex`` (or a mixed iterable) explicitly.
    """
    vals = list(values)
    if not vals:
        return pd.PeriodIndex([], freq="M")
    if isinstance(values, pd.PeriodIndex):
        return values.asfreq("M")
    if all(isinstance(v, pd.Period) for v in vals):
        return pd.PeriodIndex(vals, freq="M")
    return pd.PeriodIndex(pd.to_datetime(vals), freq="M")


def _monthly_series(values: pd.Series, *, name: str | None = None) -> pd.Series:
    out = pd.to_numeric(values, errors="coerce").copy()
    out.index = _period_index(out.index)
    out = out.groupby(level=0).last().sort_index()
    return out.rename(name or values.name)


def _read_base() -> tuple[pd.Series, pd.DataFrame]:
    target = pd.read_csv(TARGET_PATH)
    target.index = pd.PeriodIndex(target.pop("period").astype(str), freq="M")
    y = pd.to_numeric(target.pop("headline_mm_extended"), errors="coerce").rename("cpi_mm")
    base = pd.read_csv(PANEL_PATH, parse_dates=["date"])
    base.index = pd.PeriodIndex(base.pop("date"), freq="M")
    base = base.apply(pd.to_numeric, errors="coerce").groupby(level=0).last().sort_index()
    y = y.groupby(level=0).last().sort_index()
    return y, base


def _read_arad() -> pd.DataFrame:
    path = DATA / "arad_selected.csv"
    if not path.exists():
        return pd.DataFrame()
    d = pd.read_csv(path, parse_dates=["period"])
    d["period"] = pd.PeriodIndex(d["period"], freq="M")
    # The exported database can contain more than one snapshot.  A paper
    # comparison uses the last locally saved value for each indicator/month;
    # this is explicitly not a real-time vintage reconstruction.
    d = d.sort_values(["indicator_id", "period", "snapshot_id"], na_position="first")
    return d.drop_duplicates(["indicator_id", "period"], keep="last")


def _pivot_arad(d: pd.DataFrame, indicator: str, name: str) -> pd.Series:
    if d.empty:
        return pd.Series(dtype=float, name=name)
    s = d[d.indicator_id.eq(indicator)].set_index("period")["value"]
    return _monthly_series(s, name=name)


_ARAD_NFC_LOAN_TOTAL = "SUCM100311XXX101101"
_ARAD_NFC_LOAN_BUCKETS = (
    "SUCM200311XXX101101",
    "SUCM300311XXX101101",
    "SUCM400311XXX101101",
)


def _nfc_balance_from_pivot(
    piv: pd.DataFrame,
    total_id: str = _ARAD_NFC_LOAN_TOTAL,
    bucket_ids: tuple[str, ...] = _ARAD_NFC_LOAN_BUCKETS,
) -> pd.Series:
    """Return one NFC loan stock, never the total plus its buckets."""
    if total_id in piv.columns:
        return piv[total_id]
    missing = [col for col in bucket_ids if col not in piv.columns]
    if missing:
        raise KeyError(f"NFC total and maturity buckets missing from ARAD panel: {missing}")
    return piv[list(bucket_ids)].sum(axis=1, min_count=len(bucket_ids))


def _read_bcs() -> pd.DataFrame:
    path = DATA / "bcs_aggregate_surveys.csv"
    if not path.exists():
        return pd.DataFrame()
    d = pd.read_csv(path)
    d["period"] = pd.PeriodIndex(pd.to_datetime(dict(year=d.year, month=d.month, day=1)), freq="M")
    return d


def _read_ppi_levels() -> pd.DataFrame:
    path = HERE / "data" / "cz_ppi_product_raw.csv"
    if not path.exists():
        return pd.DataFrame()
    d = pd.read_csv(path, usecols=["CZCPA3.CZCPA_U1", "CZCPA3.CZCPA_U2", "TYPUDAJE5A", "CASMKMQRM12", "Hodnota"], low_memory=False)
    d = d[d["TYPUDAJE5A"].eq("IZ2015")].copy()
    # Keep only exact monthly observations, excluding K (calendar-adjusted),
    # quarters and annual aggregates.
    d = d[d["CASMKMQRM12"].astype(str).str.fullmatch(r"\d{4}-\d{2}")]
    d["period"] = pd.PeriodIndex(d["CASMKMQRM12"].astype(str), freq="M")
    d["value"] = pd.to_numeric(d["Hodnota"], errors="coerce")
    out = {}
    for code, name in [(None, "ppi_total_level"), ("B", "ppi_mineral_level"), ("C", "ppi_manufactured_level"), ("D", "ppi_energy_level"), ("E", "ppi_water_level")]:
        sub = d[d["CZCPA3.CZCPA_U1"].isna()] if code is None else d[d["CZCPA3.CZCPA_U1"].eq(code)]
        if sub.empty:
            continue
        # The source has one national row per month for this hierarchy level.
        s = sub.groupby("period")["value"].last().sort_index()
        out[name] = s
    return pd.DataFrame(out).sort_index()


def _read_activity() -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    ip = DATA / "czso_ip_release.csv"
    if ip.exists():
        d = pd.read_csv(ip, parse_dates=["release_date", "data_month"])
        sub = d[d.nace_code.eq("BCD")].sort_values(["data_month", "release_date"]).drop_duplicates("data_month", keep="last")
        # A6 asks for a level.  The release table only stores YoY indexes, so
        # the CZSO SA level file is preferred and handled below.
    level_path = HERE / "data" / "cz_ip_sa_level.csv"
    if level_path.exists():
        d = pd.read_csv(level_path)
        # Pass raw values rather than a Series so pandas does not align the
        # source's 0..n index against the new monthly PeriodIndex (which would
        # silently turn every observation into NaN).
        s = pd.Series(
            pd.to_numeric(d["Hodnota"], errors="coerce").to_numpy(),
            index=pd.PeriodIndex(d["ym"].astype(str), freq="M"),
            name="ip_level",
        )
        out["ip_level"] = s.groupby(level=0).last().sort_index()

    c = DATA / "czso_construction_release.csv"
    if c.exists():
        d = pd.read_csv(c, parse_dates=["release_date", "data_month"])
        # The current table's permit index code is truncated in older pulls;
        # matching the stable prefix avoids encoding-dependent labels.
        sub = d[d.code.astype(str).str.startswith("počet_vydaných_stavebních_povo")].sort_values(["data_month", "release_date"])
        sub = sub.drop_duplicates("data_month", keep="last")
        if not sub.empty:
            out["building_permits_index"] = pd.Series(
                pd.to_numeric(sub.yoy_index, errors="coerce").to_numpy(),
                index=pd.PeriodIndex(sub.data_month, freq="M"),
                name="building_permits_index",
            ).sort_index()
    return out


def _read_de_hicp_total() -> pd.Series:
    path = HERE / "data" / "hicp_components_ecb_mirror.csv"
    if not path.exists():
        return pd.Series(dtype=float, name="de_hicp_total")
    d = pd.read_csv(path, usecols=["REF_AREA", "ICP_ITEM", "TIME_PERIOD", "OBS_VALUE"])
    d = d[d.REF_AREA.eq("DE") & d.ICP_ITEM.eq("000000")].copy()
    if d.empty:
        return pd.Series(dtype=float, name="de_hicp_total")
    s = pd.Series(pd.to_numeric(d.OBS_VALUE, errors="coerce").to_numpy(), index=pd.PeriodIndex(d.TIME_PERIOD.astype(str), freq="M"), name="de_hicp_total")
    return s.groupby(level=0).last().sort_index()


def _read_brent() -> pd.Series:
    path = HERE / "data" / "research_r14" / "fuel" / "brent_daily.csv"
    if not path.exists():
        return pd.Series(dtype=float, name="brent_spot_usd")
    d = pd.read_csv(path, parse_dates=["date"])
    d["period"] = pd.PeriodIndex(d.date, freq="M")
    return d.groupby("period")["brent_usd"].mean().rename("brent_spot_usd").sort_index()


def _read_fuel_pca() -> pd.Series:
    path = DATA / "cz_fuel_weekly_source.csv"
    if not path.exists():
        return pd.Series(dtype=float, name="fuel_pca_3type_level")
    d = pd.read_csv(path)
    d = d[d.Indicator.astype(str).str.startswith("Average consumer fuel prices")].copy()
    wanted = {"Petrol 95 O Natural": "petrol95", "Diesel": "diesel", "LPG": "lpg"}
    d = d[d["Fuel type"].isin(wanted)]
    if d.empty:
        return pd.Series(dtype=float, name="fuel_pca_3type_level")
    # Week labels are ISO-like "Week N, YYYY".  Monday is sufficient for a
    # monthly average; the source itself is a Monday snapshot.
    m = d["Weeks"].astype(str).str.extract(r"Week\s+(\d+),\s*(\d{4})")
    d["period"] = pd.PeriodIndex(pd.to_datetime(m[1] + "-" + m[0] + "-1", format="%Y-%W-%w"), freq="M")
    d["fuel"] = d["Fuel type"].map(wanted)
    d["value"] = pd.to_numeric(d.Hodnota, errors="coerce")
    wide = d.pivot_table(index="period", columns="fuel", values="value", aggfunc="mean").sort_index()
    wide = wide.dropna(how="all")
    if wide.empty:
        return pd.Series(dtype=float, name="fuel_pca_3type_level")
    # Standardise each available type over the frozen sample, then orient the
    # first component positively with the cross-sectional price mean.
    z = (wide - wide.mean()) / wide.std(ddof=0)
    z = z.dropna(how="any")
    if z.empty:
        return pd.Series(dtype=float, name="fuel_pca_3type_level")
    from sklearn.decomposition import PCA

    pca = PCA(n_components=1, random_state=42).fit(z.to_numpy())
    pc = pd.Series(pca.transform(z.to_numpy())[:, 0], index=z.index, name="fuel_pca_3type_level")
    if pc.corr(z.mean(axis=1)) < 0:
        pc = -pc
    return pc


def _read_bloomberg_monthly() -> pd.DataFrame:
    path = HERE / "data" / "market_snapshots" / "20260909_bloomberg_y1" / "monthly_complete.csv"
    if not path.exists():
        return pd.DataFrame()
    d = pd.read_csv(path)
    d["period"] = pd.PeriodIndex(d.month.astype(str), freq="M")
    d["mean"] = pd.to_numeric(d["mean"], errors="coerce")
    d["last"] = pd.to_numeric(d["last"], errors="coerce")
    out = {}
    for ticker, name, field in [
        ("FSBTY1 Index", "brent_fwd1y_level", "mean"),
        ("TTFGCY1 Index", "gas_fwd1y_level", "mean"),
        ("TTFGCY1 Index", "gas_spot_proxy", "mean"),
        ("CO1 Comdty", "brent_spot_bbg", "mean"),
        ("PRIB03M Index", "pribor_eom", "last"),
    ]:
        sub = d[d.series.eq(ticker)]
        if not sub.empty:
            out[name] = sub.groupby("period")[field].last().sort_index()
    return pd.DataFrame(out).sort_index()


def build_paper_panel() -> tuple[pd.Series, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Build target, A6-mapped panel, variable audit and source metadata."""

    y, base = _read_base()
    arad = _read_arad()
    activity = _read_activity()
    ppi = _read_ppi_levels()
    bcs = _read_bcs()
    extras: dict[str, pd.Series | pd.DataFrame] = {
        **activity,
        "de_hicp_total": _read_de_hicp_total(),
        "brent_spot_usd": _read_brent(),
        "fuel_pca_3type_level": _read_fuel_pca(),
        "repo_rate": _pivot_arad(arad, "SFTP01M11", "repo_rate"),
        "reer_ppi_level": _pivot_arad(arad, "SREERM101", "reer_ppi_level"),
        "reer_cpi_level": _pivot_arad(arad, "SREERM103", "reer_cpi_level"),
        "hh_loans_level": _pivot_arad(arad, "SUCM102211XXX101101", "hh_loans_level"),
        "czgb_10y": _pivot_arad(arad, "SVSDM12", "czgb_10y"),
    }
    nfc_ids = [_ARAD_NFC_LOAN_TOTAL, *_ARAD_NFC_LOAN_BUCKETS]
    nfc = [_pivot_arad(arad, i, i) for i in nfc_ids]
    nfc = [s for s in nfc if not s.empty]
    if nfc:
        nfc_panel = pd.concat(nfc, axis=1)
        extras["nfc_loans_level"] = _nfc_balance_from_pivot(nfc_panel).rename("nfc_loans_level")

    bb = _read_bloomberg_monthly()
    if not bb.empty:
        for col in bb.columns:
            extras[col] = bb[col]
    # Broad survey aggregates are kept as proxies outside the exact A6 list.
    # Use stable names so policy filtering can identify them as survey inputs.
    if not bcs.empty:
        code_map = {
            "BS-ICI-BAL": "bcs_cz_industrial_conf",
            "BS-SCI-BAL": "bcs_cz_services_conf",
            "BS-RCI-BAL": "bcs_cz_retail_conf",
            "BS-CCI-BAL": "bcs_cz_construction_conf",
            "BS-CSMCI-BAL": "bcs_cz_consumer_conf",
            "BS-ESI-I": "bcs_cz_esi",
        }
        bcs_p = bcs.assign(name=bcs.indic_code.map(code_map)).dropna(subset=["name"])
        piv = bcs_p.pivot_table(index="period", columns="name", values="value", aggfunc="last")
        for col in piv.columns:
            extras[col] = piv[col]

    # Existing frozen panel supplies many exact/project variables and proxies.
    combined = base.copy()
    for name, value in extras.items():
        if isinstance(value, pd.DataFrame):
            combined = pd.concat([combined, value], axis=1)
        else:
            combined[name] = value
    if not ppi.empty:
        combined = pd.concat([combined, ppi], axis=1)
    combined = combined.loc[:, ~combined.columns.duplicated()].sort_index()

    # Map broad BCS proxies and existing aliases to the A6 source columns.
    source_alias = {
        "ip_level": "ip_level",
        "bcs_cz_industrial_conf": "bcs_cz_industrial_conf",
        "bcs_cz_services_conf": "bcs_cz_services_conf",
        "bcs_cz_retail_conf": "bcs_cz_retail_conf",
        "bcs_cz_construction_conf": "bcs_cz_construction_conf",
    }
    mapped: dict[str, pd.Series] = {}
    audit_rows: list[dict[str, object]] = []
    for row in A6:
        source = row.source_column
        available = source is not None and source in combined.columns
        if row.number == 29:
            source, available = "bcs_cz_industrial_conf", "bcs_cz_industrial_conf" in combined.columns
        elif row.number == 32:
            source, available = "bcs_cz_services_conf", "bcs_cz_services_conf" in combined.columns
        elif row.number == 36:
            source, available = "bcs_cz_retail_conf", "bcs_cz_retail_conf" in combined.columns
        elif row.number == 38:
            source, available = "bcs_cz_construction_conf", "bcs_cz_construction_conf" in combined.columns
        elif row.number == 18:
            source, available = "de_esi", "de_esi" in combined.columns
        elif row.number == 22:
            source, available = "pl_retail_conf", "pl_retail_conf" in combined.columns
        elif row.number == 60 and "brent_spot_bbg" in combined.columns:
            source, available = "brent_spot_bbg", True
        # Broad/current panel mappings for A6's hard fields.
        fallback = {
            11: "unemployment_rate", 14: "rushin", 43: "agri_ppi_mm", 44: "ppi_mm_deep",
            53: "czgb_10y", 69: "price_expect_survey_36m", 70: "price_expect_survey",
            72: "household_price_expect", 25: "trade_balance", 26: "import_price_mm",
            23: "de_hicp_total", 64: "fuel_pca_3type_level", 65: "gas_fwd1y_level",
            66: "brent_fwd1y_level", 61: "gas_spot_proxy", 54: "pribor_eom",
            55: "repo_rate", 56: "reer_ppi_level", 57: "reer_cpi_level",
            58: "nfc_loans_level", 59: "hh_loans_level", 12: "ip_level",
            13: "building_permits_index",
        }
        if not available and row.number in fallback:
            source = fallback[row.number]
            available = source in combined.columns
        # Some broad local aggregates are useful, honest proxies for a missing
        # detailed A6 question.  Keep the distinction in the audit rather than
        # dropping them solely because the exact source was unavailable.
        status = "proxy" if available and row.status == "missing" else row.status
        if available:
            mapped[f"a6_{row.number:02d}"] = pd.to_numeric(combined[source], errors="coerce")
        audit_rows.append({
            "number": row.number, "group": row.group, "description": row.description,
            "transform": row.transform, "kind": row.kind, "source": row.source,
            "source_column": source if available else row.source_column,
            "status_declared": row.status, "status_in_run": status if available else "missing",
            "n_finite": int(pd.to_numeric(combined[source], errors="coerce").notna().sum()) if available else 0,
            "first_available": str(pd.to_numeric(combined[source], errors="coerce").dropna().index.min()) if available and pd.to_numeric(combined[source], errors="coerce").notna().any() else None,
            "last_available": str(pd.to_numeric(combined[source], errors="coerce").dropna().index.max()) if available and pd.to_numeric(combined[source], errors="coerce").notna().any() else None,
            "note": row.note,
        })
    a6_panel = pd.DataFrame(mapped).reindex(pd.period_range(min(y.index.min(), combined.index.min()), max(y.index.max(), combined.index.max()), freq="M"))
    audit = pd.DataFrame(audit_rows)
    meta = {
        "target": "headline_mm_extended (NSA official national CPI m/m)",
        "paper_target_seasonality": "unresolved; paper says all series X-13 adjusted, but no executable/vintaged SA target is bundled",
        "panel_source": str(PANEL_PATH),
        "a6_variables": 72,
        "mapped_columns": int(a6_panel.shape[1]),
        "exact_declared": int(audit.status_in_run.eq("exact").sum()),
        "proxy_declared": int(audit.status_in_run.eq("proxy").sum()),
        "missing": int(audit.status_in_run.eq("missing").sum()),
        "market_snapshot": str(HERE / "data" / "market_snapshots" / "20260909_bloomberg_y1"),
        "source_aliases": source_alias,
    }
    return y, a6_panel, audit, meta


def _signed_log_difference(series: pd.Series) -> pd.Series:
    """A finite log-like change for a signed balance (paper transform 2).

    For strictly positive price/index levels the ordinary log difference is
    used.  Trade balances can cross zero, so the only deterministic extension
    that preserves sign is sign(x)*log1p(abs(x)), differenced.  This is a
    declared approximation, not a claim about the paper's undocumented
    treatment.
    """

    s = pd.to_numeric(series, errors="coerce")
    if (s.dropna() > 0).all():
        return np.log(s.where(s > 0)).diff()
    transformed = np.sign(s) * np.log1p(np.abs(s))
    return transformed.diff()


def transform_a6_panel(panel: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    """Apply the A6 transform codes to the mapped raw panel."""

    out = pd.DataFrame(index=panel.index)
    for _, row in audit.iterrows():
        num = int(row.number)
        key = f"a6_{num:02d}"
        if key not in panel.columns or row["status_in_run"] == "missing":
            continue
        s = pd.to_numeric(panel[key], errors="coerce")
        # Existing *_yoy/mm columns are already published changes.  Applying
        # another difference would be a silent double transformation, so keep
        # them as supplied and record the approximation in the column name.
        source = str(row["source_column"] or "")
        if source.endswith("_yoy") or source.endswith("_mm") or source in {"trade_balance", "import_price_mm"}:
            transformed = s
        elif int(row["transform"]) == 0:
            transformed = s
        elif int(row["transform"]) == 2:
            transformed = _signed_log_difference(s)
        elif int(row["transform"]) == 3:
            transformed = s.diff()
        else:
            raise ValueError(f"unknown A6 transform {row['transform']}")
        out[f"a6_{num:02d}"] = transformed
    return out


def _policy_panel(transformed: pd.DataFrame, audit: pd.DataFrame, policy: str) -> pd.DataFrame:
    if policy not in ("paper_independent", "paper_sentiment", "paper_full"):
        raise ValueError(policy)
    status = audit.set_index("number")
    keep = []
    for col in transformed.columns:
        n = int(col.split("_")[-1])
        kind = str(status.loc[n, "kind"])
        if policy == "paper_full":
            keep.append(col)
        elif policy == "paper_sentiment":
            # Keep activity/confidence balances but remove inflation
            # expectations and the FMIE/household expectation variables.
            if kind != "expectation":
                keep.append(col)
        else:
            if kind == "hard":
                keep.append(col)
    return transformed.loc[:, keep]


def _rw(y: pd.Series) -> float:
    return float(y.dropna().iloc[-1])


def _ar3(y: pd.Series, h: int) -> float:
    yv = y.dropna().astype(float)
    p = 3
    if len(yv) <= p + h:
        return _rw(yv)
    lags = pd.concat([yv.shift(i) for i in range(p)], axis=1)
    lags.columns = [f"l{i}" for i in range(p)]
    df = pd.concat([yv.shift(-h).rename("target"), lags], axis=1).dropna()
    if len(df) < p + 5:
        return _rw(yv)
    design = np.column_stack([np.ones(len(df)), df[[f"l{i}" for i in range(p)]].to_numpy()])
    beta = np.linalg.lstsq(design, df.target.to_numpy(), rcond=None)[0]
    now = yv.iloc[-1 : -(p + 1) : -1].to_numpy()
    return float(np.r_[1.0, now] @ beta)


def _run_one(y, X, horizon, policy, *, oos_start, oos_end, min_train, trees, stale_tolerance):
    target_periods = y.loc[pd.Period(oos_start, freq="M") : pd.Period(oos_end, freq="M")].index
    rows = []
    for target_period in target_periods:
        origin = target_period - int(horizon)
        yh = y.loc[:origin]
        Xh = X.loc[:origin]
        # The paper's initial training sample ends in Dec-2010.  Use the
        # declared min_train to enforce a common starting point while still
        # allowing the mapped panel's earlier target history to be sliced by
        # the caller before this function.
        if len(yh.dropna()) < min_train + horizon:
            continue
        detail = direct_tvwqrf_forecast(
            yh,
            Xh,
            horizon,
            origin=origin,
            min_history=min_train,
            stale_tolerance=stale_tolerance,
            y_lags=0,
            include_month=False,
            qrf_factory=SklearnLeafTVWQRF,
            qrf_options={"n_estimators": trees, "min_samples_leaf": 3, "max_features": 1.0},
        )
        er = detail.get("estimator_result", {})
        rows.append({
            "period": str(target_period), "horizon": horizon, "policy": policy,
            "model": "TVW3_leaf_QRF", "actual": float(y.loc[target_period]),
            "forecast": detail.get("forecast", np.nan), "qrf_median": er.get("median", np.nan),
            "qrf_p05": (er.get("p05_p95") or (np.nan, np.nan))[0],
            "qrf_p95": (er.get("p05_p95") or (np.nan, np.nan))[1],
            "status": detail.get("status"), "fallback_used": detail.get("fallback_used", False),
            "n_train": detail.get("n_train", np.nan), "n_features": len(detail.get("selected_columns", [])),
            "engine": detail.get("engine"), "error": detail.get("error"),
        })
    return pd.DataFrame(rows)


def score_forecasts(forecasts: pd.DataFrame) -> pd.DataFrame:
    if forecasts.empty:
        return pd.DataFrame()
    rows = []
    for keys, g in forecasts.groupby(["horizon", "policy", "model"], dropna=False):
        valid = g.dropna(subset=["actual", "forecast"])
        if valid.empty:
            continue
        e = valid.forecast.to_numpy() - valid.actual.to_numpy()
        rows.append({
            "horizon": int(keys[0]), "policy": keys[1], "model": keys[2], "n": len(valid),
            "rmse": float(np.sqrt(np.mean(e**2))), "mae": float(np.mean(np.abs(e))),
            "bias": float(np.mean(e)), "fallback_rate": float(valid.fallback_used.mean()),
        })
    return pd.DataFrame(rows).sort_values(["horizon", "rmse", "policy"]).reset_index(drop=True)


def _benchmark_rows(y, horizons, *, oos_start, oos_end, train_start):
    rows = []
    for h in horizons:
        periods = y.loc[pd.Period(oos_start, freq="M") : pd.Period(oos_end, freq="M")].index
        for t in periods:
            origin = t - int(h)
            yh = y.loc[pd.Period(train_start, freq="M") : origin]
            if len(yh.dropna()) < 24 + h:
                continue
            for name, fn in [("RW", lambda z: _rw(z)), ("AR3", lambda z: _ar3(z, h))]:
                rows.append({"period": str(t), "horizon": h, "policy": "common", "model": name,
                             "actual": float(y.loc[t]), "forecast": float(fn(yh)), "fallback_used": False,
                             "status": "benchmark", "n_train": np.nan, "n_features": np.nan, "engine": "closed_form"})
    return pd.DataFrame(rows)


def _hash(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def run_experiment(
    *, output_dir: Path = DEFAULT_OUTPUT, horizons: Sequence[int] = (3, 6, 9, 12),
    train_start: str = "2002-05", fit_end: str = "2010-12", oos_start: str = "2011-01",
    oos_end: str = "2025-09", min_train: int = 96, trees: int = 200,
    stale_tolerance: int = 2, policies: Sequence[str] = ("paper_independent", "paper_sentiment", "paper_full"),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    y, raw_panel, audit, panel_meta = build_paper_panel()
    # Slice target and features to the paper's declared first observation.  The
    # feature-preparation layer itself enforces origin-only eligibility.
    start = pd.Period(train_start, freq="M")
    end = pd.Period(oos_end, freq="M")
    y = y.loc[start:end]
    raw_panel = raw_panel.loc[start:end]
    transformed = transform_a6_panel(raw_panel, audit)
    forecasts = [_benchmark_rows(y, horizons, oos_start=oos_start, oos_end=oos_end, train_start=train_start)]
    for policy in policies:
        X = _policy_panel(transformed, audit, policy)
        for h in horizons:
            # Make the paper fit end explicit: target rows after fit_end are
            # forecast origins; training labels use only origin-h and earlier.
            rows = _run_one(y, X, int(h), policy, oos_start=oos_start, oos_end=oos_end,
                            min_train=min_train, trees=trees, stale_tolerance=stale_tolerance)
            if not rows.empty:
                forecasts.append(rows)
    all_forecasts = pd.concat(forecasts, ignore_index=True) if forecasts else pd.DataFrame()
    scores = score_forecasts(all_forecasts)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output_dir / "a6_variable_audit.csv", index=False)
    transformed.to_csv(output_dir / "a6_transformed_panel.csv", index_label="period")
    all_forecasts.to_csv(output_dir / "forecasts.csv", index=False)
    scores.to_csv(output_dir / "summary.csv", index=False)
    source_snapshot = pd.concat([y.rename("cpi_mm"), raw_panel], axis=1)
    source_snapshot.to_csv(output_dir / "input_snapshot.csv", index_label="period")
    metadata = {
        **panel_meta,
        "train_start": train_start, "fit_end": fit_end, "oos_start": oos_start, "oos_end": oos_end,
        "horizons": [int(h) for h in horizons], "min_train": min_train, "trees": trees,
        "stale_tolerance": stale_tolerance, "policies": list(policies),
        "qrf_engine": "SklearnLeafTVWQRF (leaf-weighted approximation; quantile-forest package unavailable)",
        "a6_audit_sha256": _hash(output_dir / "a6_variable_audit.csv"),
        "input_snapshot_sha256": _hash(output_dir / "input_snapshot.csv"),
        "paper_benchmark_tvw3_rmse": {"h3": 0.669, "h6": 0.661, "h9": 0.712, "h12": 0.662},
        "method_notes": [
            "Target is NSA official Czech CPI m/m; paper's target X-13 status is unresolved.",
            "Panel contains exact/proxy/missing A6 mappings; no claim of 72-variable replication.",
            "A6 transforms are applied to mapped levels; source columns already carrying _mm/_yoy are retained to avoid double differencing.",
            "No survey variable enters paper_independent; paper_full is a diagnostic comparison.",
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return all_forecasts, scores, audit, metadata


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--trees", type=int, default=200)
    p.add_argument("--min-train", type=int, default=96)
    p.add_argument("--oos-start", default="2011-01")
    p.add_argument("--oos-end", default="2025-09")
    p.add_argument("--horizons", type=int, nargs="+", default=[3, 6, 9, 12])
    p.add_argument("--policies", nargs="+", choices=["paper_independent", "paper_sentiment", "paper_full"], default=["paper_independent", "paper_sentiment", "paper_full"])
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _, scores, audit, _ = run_experiment(output_dir=args.output_dir, horizons=args.horizons,
                                         oos_start=args.oos_start, oos_end=args.oos_end,
                                         min_train=args.min_train, trees=args.trees,
                                         policies=args.policies)
    print("A6 availability:")
    print(audit[["number", "status_in_run", "source_column", "n_finite", "first_available", "last_available"]].to_string(index=False))
    print("\nScores:")
    print(scores.to_string(index=False))
    print(f"\nwrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
