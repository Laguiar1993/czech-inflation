"""Build the CNB WP 9/2026 Table A6 audit and two separate input panels.

Status of each of the 72 predictors (``a6_status``):

* ``exact``: an official series on disk whose identity matches the paper's
  description (current vintage).  Only these enter ``exact_inputs_long.csv``.
* ``validated_proxy``: no exact series on disk, but a candidate passed its
  declared validation (a Bloomberg mirror is never promoted to exact).
* ``candidate_unvalidated``: only a candidate or local proxy without passing
  validation, or with no official comparator.
* ``unavailable``: nothing usable on disk.

``historical_coverage_gap`` is reported separately: the series that sets the
status starts after the paper's first month (2002-05).  Every input is a
current vintage; none is an original real-time publication vintage.

Bloomberg candidates and local proxies go to ``candidate_inputs_long.csv`` with
``bbg__``/``local__`` column names, so they cannot be mistaken for exact inputs.
``exact_source_checks.csv`` records the agreement between each extended official
source and the CZSO series it replaces.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.paper_replication.a6_catalog import PAPER_SAMPLE, ROWS, ecfin_nsa_code  # noqa: E402
from tools.paper_replication.import_bloomberg_candidates import REGISTRY, sha256_file  # noqa: E402

DATA = ROOT / "data" / "paper_replication"
CANDIDATE_DIR = DATA / "bloomberg_candidates_20260911_full_refresh"
VALIDATION_DIR = ROOT / "output" / "cnb_paper_candidate_validation_20260912"
EUROSTAT_DIR = DATA / "official_eurostat_20260912" / "tidy"
EUROSTAT_PPI_DIR = DATA / "official_eurostat_20260912_ppi" / "tidy"
CZSO_DIR = DATA / "official_czso_20260912"
CZSO_AGRI_DIR = DATA / "official_czso_20260912_agri"
ECFIN_LONG = DATA / "official_bcs_ecfin_2608" / "ecfin_bcs_long.csv"
OLD_AUDIT = ROOT / "output" / "cnb_paper_replication_20260910" / "a6_variable_audit.csv"
DEFAULT_OUTPUT = ROOT / "output" / "cnb_paper_a6_audit_20260912"
DEFAULT_INPUTS = DATA / "a6_inputs_20260912"
PAPER_START, PAPER_END = (pd.Period(p, freq="M") for p in PAPER_SAMPLE)
STATUSES = ("exact", "validated_proxy", "candidate_unvalidated", "unavailable")

EXACT_RULES = {
    "ec_bcs_next_month": ("EC survey results for M are published at the end of M; usable from day 1 of M+1", None),
    "lfs_t32": ("Monthly unemployment published about 30 days after the period", 32),
    "hicp_t18": ("HICP flash at month end, final value in mid M+1", 18),
    "czso_ip_t41": ("CZSO industry release on the 37th day plus at most 3 days of exceptions", 41),
    "czso_import_prices_t45": ("CZSO import-price release on the 41st day plus at most 3 days", 45),
    "czso_ppi_t26": ("CZSO producer prices on the 16th day after the period, up to 9 days later in January", 26),
    "cnb_rushin_t14": ("Monthly mean of weekly Rushin estimates; the last week is published about a week later", 14),
    "arad_rates_t1": ("Market rate known on the last day of the month", 1),
    "arad_reer_t20": ("REER published in the following month", 20),
    "arad_loans_t31": ("Client-loan stocks published about a month after the period", 31),
    "czso_fuel_t7": ("Weekly fuel survey published within days; monthly average after the last week", 7),
    "cnb_fmie_next_month": ("FMIE survey for M published in M; usable from day 1 of M+1", None),
}

# Seasonal-adjustment treatment for hard rows; survey rows are derived from ECFIN.
ADJUSTMENT = {
    11: "Eurostat SA; do not re-adjust", 24: "Eurostat SA; do not re-adjust",
    12: "CZSO seasonally and calendar adjusted; do not re-adjust",
    13: "NSA count; one-sided X-13 required (paper)", 14: "q/q growth estimate; adjustment not applicable",
    15: "unknown", 16: "unknown", 17: "NSA; one-sided X-13 required (paper)",
    23: "NSA index; one-sided X-13 required (paper)", 25: "NSA; one-sided X-13 required (paper)",
    26: "NSA m/m change; one-sided X-13 required (paper)",
    43: "year-on-year change; adjustment not applicable", 44: "year-on-year change; adjustment not applicable",
    **{n: "NSA index; one-sided X-13 required (paper)" for n in range(45, 53)},
    **{n: "financial price; X-13 per paper, little seasonality expected" for n in (53, 54, 55, 56, 57)},
    58: "NSA stock; one-sided X-13 required (paper)", 59: "NSA stock; one-sided X-13 required (paper)",
    **{n: "market price; X-13 per paper, little seasonality expected" for n in (60, 61, 62, 63, 65, 66)},
    64: "NSA fuel prices; one-sided X-13 required (paper)",
    69: "survey expectation; X-13 per paper", 70: "survey expectation; X-13 per paper",
}

USER_BLOOMBERG = "User instruction 12 Sep 2026: use the Bloomberg series in model runs; status unchanged."
ROW_NOTES = {
    4: "EC 2608 archive holds identical SA and NSA values for this question; the Nov-2025 EC annex printed "
       "different SA values, so the paper's vintage may differ.",
    5: "Bloomberg labels EUR1CZ NSA, but its values equal the EC SA series in every month.",
    10: "EUA2CZ equals CONS_2 (financial situation next 12 months); EUA4CZ equals CONS_4 (general economic "
        "situation next 12 months) and is rejected.",
    11: "The 20260910 panel column unemployment_rate does not reproduce Eurostat une_rt_m at any monthly shift.",
    13: "CZGRIDX behaves as a monthly count (monthly yoy MAE 0.16 against the current CZSO release, 9 months; "
        "0.48 against the 2014-2023 release series); the official count level is not on disk.",
    14: "Frozen-panel rushin equals the monthly mean of Bloomberg weekly estimates; the paper imputes "
        "pre-2008 values with the Chen-Labonne factor procedure.",
    17: "LCTQCZI y/y growth equals Eurostat NULC_PER NSA growth (MAE 0.07 pp); Eurostat publishes Czech nominal "
        "ULC only as growth rates; Chow-Lin monthly disaggregation not implemented.",
    22: "The 20260910 panel column pl_retail_conf is not the EC Polish retail confidence indicator.",
    25: "Source identity of the FOB/FOB balance unconfirmed; transform 2 is undefined for a signed balance.",
    27: "Eurostat EA20 used for the paper period; Bloomberg and ECFIN follow the current composition (EA21).",
    28: "Eurostat EA20 used for the paper period; Bloomberg and ECFIN follow the current composition (EA21).",
    33: "Bloomberg labels EUR3CZ NSA, but its values equal the EC SA series in every month.",
    34: "Bloomberg labels EUR4CZ NSA, but its values equal the EC SA series in every month.",
    35: "Bloomberg labels EUR5CZ NSA, but its values equal the EC SA series in every month.",
    36: "Bloomberg labels EURTCZ NSA, but its values equal the EC SA series in every month.",
    38: "Transform corrected to 3; the 20260910 runner used 0.",
    43: "CZSO CEN02A published y/y from 2015-01; 2011-01 to 2014-12 chained from CEN02032 month-on-month "
        "indices. The 20260910 panel column agri_ppi_mm holds y/y changes stored one month late.",
    44: "Eurostat domestic producer prices, y/y (B-E36), from 1991; agreement with CZSO's published y/y is in "
        "exact_source_checks.csv. The 20260910 panel column ppi_mm_deep is stored one month late.",
    45: "Eurostat domestic producer price index (2021=100) from 1990; growth equals the CZSO CEN0201A total.",
    46: "Eurostat section B from 1990; growth equals the CZSO CEN0201A section total. The 20260910 runner read "
        "a sub-division row for this section.",
    47: "Eurostat section C from 1990; growth equals the CZSO CEN0201A section total. The 20260910 runner read "
        "a sub-division row for this section.",
    48: "Eurostat section D from 1990; growth equals the CZSO CEN0201A section total. The 20260910 runner read "
        "a sub-group row for this section.",
    49: "Eurostat E36 from 1990; growth equals the CZSO CEN0201A section E total.",
    50: "CZSO CEN02032 month-on-month index, animal production (fish separate), from 2010-01.",
    51: "CZSO CEN02032 month-on-month index, crop production, from 2010-01.",
    52: "CZSO CEN02032 month-on-month index, agricultural production including fish, from 2010-01.",
    54: "Bloomberg daily fixings reproduce the ARAD monthly average (MAE 0.0005 pp); the month-end fixing is the "
        "candidate; the ARAD end-of-month series is not on disk (API key required).",
    58: "ARAD VST total from 2005-01; LONSCZNF (ECB/MFI perimeter, EUR) tracks its growth with month-end FX and "
        "starts 2002-01 as a labelled proxy.",
    60: "CO1 month mean versus Europe Brent spot: level MAE 0.91 USD, growth correlation 0.97; paper series "
        "identity not stated. " + USER_BLOOMBERG,
    61: "TTF day-ahead fair value from 2011-02. " + USER_BLOOMBERG,
    62: "Bloomberg industrial metals spot index. " + USER_BLOOMBERG,
    63: "Bloomberg agriculture spot index. " + USER_BLOOMBERG,
    64: "CZSO CEN0101J monthly prices of all four fuels, 2001-01 to 2025-12 (discontinued); the weekly CENPHMT "
        "set carries Natural 95, diesel and LPG only. The principal component is not computed here.",
    65: "Refinitiv 12-month contract unavailable; TTFGCY1 is a Year-1 strip fair value from 2013-04. " + USER_BLOOMBERG,
    66: "Refinitiv 12-month contract unavailable; FSBTY1 is a Year-1 strip fair value from 2013-07. " + USER_BLOOMBERG,
    69: "FMIE values carry survey months, not publication timestamps.",
    70: "FMIE values carry survey months, not publication timestamps.",
}

CANDIDATE_STATISTIC = {"PRIB03M Index": "month_last", "CZRUSHIN Index": "week_mean"}
LANE_RANK = {"identical_mirror": 0, "validated_mirror": 1, "validated_proxy": 2, "candidate_unvalidated": 3,
             "rejected": 4, "none": 5}
PPI_SECTIONS = {45: ("B-E36", None), 46: ("B", "B"), 47: ("C", "C"), 48: ("D", "D"), 49: ("E36", "E")}
AGRI_GROUPS = {50: ("130000", "614508", "Index cen zemědělských výrobců - živočišná výroba bez ryb"),
               51: ("100000", "614509", "Index cen zemědělských výrobců - rostlinná výroba"),
               52: ("0", "614507", "Index cen zemědělských výrobců včetně ryb")}


@dataclass
class Component:
    label: str
    source_id: str
    source_file: str
    series: pd.Series
    value_kind: str
    rule: str
    segment: bool = False   # True: pieces of one series; False: all components are required


def period_series(values, periods) -> pd.Series:
    s = pd.Series(pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(),
                  index=pd.PeriodIndex([str(p) for p in periods], freq="M"))
    return s[~s.index.duplicated(keep="last")].dropna().sort_index()


def available_from(rule: str, period: pd.Period) -> pd.Timestamp:
    days = EXACT_RULES[rule][1]
    if days is None:
        return (period + 1).start_time.normalize()
    return period.end_time.normalize() + pd.Timedelta(days=days)


def load_context(root: Path = ROOT) -> dict:
    data = root / "data" / "paper_replication"
    panel = pd.read_csv(data / "paper_predictor_panel.csv", parse_dates=["date"])
    panel.index = panel.date.dt.to_period("M")
    return {
        "tidy": {p.stem: pd.read_csv(p) for p in (data / EUROSTAT_DIR.relative_to(DATA)).glob("*.csv")},
        "ppi": pd.read_csv(data / EUROSTAT_PPI_DIR.relative_to(DATA) / "sts_inppd_m_cz.csv"),
        "cen02a": pd.read_csv(data / CZSO_DIR.relative_to(DATA) / "CEN02A.csv"),
        "cen02032": pd.read_csv(data / CZSO_AGRI_DIR.relative_to(DATA) / "CEN02032.csv"),
        "cen0101j": pd.read_csv(data / CZSO_DIR.relative_to(DATA) / "CEN0101J.csv"),
        "arad": pd.read_csv(data / "arad_selected.csv"),
        "panel": panel,
        "ip": pd.read_csv(root / "data" / "cz_ip_sa_level.csv"),
        "imports": pd.read_csv(root / "data" / "research_r14b" / "imports" / "imports_monthly_verified.csv"),
        "ecfin": pd.read_csv(data / ECFIN_LONG.relative_to(DATA), usecols=["series_code", "period", "value"]),
        "czso_ppi_raw": root / "data" / "cz_ppi_product_raw.csv",
    }


def _monthly_rows(periods: pd.Series) -> pd.Series:
    text = periods.astype(str)
    return text.str.len().eq(7) & text.str[4].eq("-") & ~text.str.contains("Q")


def _cen02a(frame: pd.DataFrame, indicator: str, kind: str) -> pd.Series:
    sub = frame[_monthly_rows(frame["CASMQRMPK"]) & frame["Ukazatel"].eq(indicator) & frame["TYPUDAJEVYR"].eq(kind)]
    return period_series(sub["Hodnota"], sub["CASMQRMPK"])


def _cen02032(frame: pd.DataFrame, group: str) -> pd.Series:
    sub = frame[_monthly_rows(frame["CASMKMQR"]) & frame["APIZZ"].astype(str).eq(group)
                & frame["TYPUDAJEZEM4"].eq("IM")]
    s = period_series(sub["Hodnota"], sub["CASMKMQR"])
    full = pd.period_range(s.index.min(), s.index.max(), freq="M")
    if not s.index.equals(full):
        raise ValueError(f"CEN02032 group {group} has gaps")
    return s


def _eurostat_ppi(frame: pd.DataFrame, nace: str, unit: str) -> pd.Series:
    sub = frame[frame.nace_r2.eq(nace) & frame.unit.eq(unit)]
    return period_series(sub.value, sub.time)


def czso_ppi_sections(path: Path) -> dict[str, pd.Series]:
    """CZSO CEN0201A section totals: the row with no finer classification level."""
    d = pd.read_csv(path, usecols=["CZCPA3.CZCPA_U1", "CZCPA3.CZCPA_U2", "TYPUDAJE5A", "CASMKMQRM12", "Hodnota"],
                    low_memory=False)
    d = d[d["TYPUDAJE5A"].eq("IZ2015") & _monthly_rows(d["CASMKMQRM12"])]
    out = {}
    for nace, section in PPI_SECTIONS.values():
        if section is None:
            sub = d[d["CZCPA3.CZCPA_U1"].isna()]
        else:
            sub = d[d["CZCPA3.CZCPA_U1"].eq(section) & d["CZCPA3.CZCPA_U2"].isna()]
        out[nace] = period_series(sub["Hodnota"], sub["CASMKMQRM12"])
    return out


def _arad(frame: pd.DataFrame, code: str) -> pd.Series:
    sub = frame[frame.indicator_id.eq(code)]
    return period_series(sub.value, pd.to_datetime(sub.period).dt.to_period("M"))


def exact_components(number: int, ctx: dict) -> list[Component]:
    row = next(r for r in ROWS if r.number == number)
    tidy = ctx["tidy"]
    if row.eurostat:
        dataset, indic = row.eurostat.split(":")
        frame = tidy[dataset]
        geo = "EA20" if row.geo == "EA" else row.geo
        mask = frame.indic.eq(indic) & frame.s_adj.eq("SA") & frame.geo.eq(geo)
        if "unit" in frame.columns and not indic.endswith(("-BAL", "-PC")):
            mask &= frame.unit.eq("BAL")
        sub = frame[mask]
        kind = "percent_of_firms" if indic.endswith("-PC") else "balance"
        return [Component("", f"eurostat:{dataset}:{indic}:SA:{geo}", f"official_eurostat_20260912/tidy/{dataset}.csv",
                          period_series(sub.value, sub.time), kind, "ec_bcs_next_month")]
    if number in (11, 24):
        frame = tidy["une_rt_m_cz_de"]
        geo = "CZ" if number == 11 else "DE"
        sub = frame[frame.geo.eq(geo) & frame.s_adj.eq("SA") & frame.age.eq("TOTAL") & frame.sex.eq("T")
                    & frame.unit.eq("PC_ACT")]
        return [Component("", f"eurostat:une_rt_m:SA:TOTAL:T:PC_ACT:{geo}", "official_eurostat_20260912/tidy/une_rt_m_cz_de.csv",
                          period_series(sub.value, sub.time), "percent", "lfs_t32")]
    if number == 12:
        ip = ctx["ip"]
        return [Component("", "czso:PRU01C:sa_calendar_adjusted_level", "data/cz_ip_sa_level.csv",
                          period_series(ip.Hodnota, ip.ym), "index_level", "czso_ip_t41")]
    if number == 14:
        panel = ctx["panel"]
        return [Component("", "cnb:rushin:monthly_mean_of_weekly", "paper_predictor_panel.csv:rushin",
                          period_series(panel.rushin, panel.index), "qoq_growth_estimate", "cnb_rushin_t14")]
    if number == 23:
        frame = tidy["prc_hicp_minr_de_total"]
        sub = frame[frame.unit.eq("I25")]
        return [Component("", "eurostat:prc_hicp_minr:TOTAL:I25:DE", "official_eurostat_20260912/tidy/prc_hicp_minr_de_total.csv",
                          period_series(sub.value, sub.time), "index_level", "hicp_t18")]
    if number == 26:
        imports = ctx["imports"]
        return [Component("", "czso:CEN0303:sitc_total:mm_pct", "data/research_r14b/imports/imports_monthly_verified.csv",
                          period_series(imports.import_mm, imports.source_month), "mm_change_pct", "czso_import_prices_t45")]
    if number == 43:
        official = _cen02a(ctx["cen02a"], "Index cen zemědělských výrobců včetně ryb", "IR") - 100.0
        mm = _cen02032(ctx["cen02032"], "0")
        chained = (mm / 100.0).cumprod()
        early = (100.0 * (chained / chained.shift(12) - 1.0)).dropna()
        early = early[early.index < official.index.min()]
        return [Component("2015_on", "czso:CEN02A:614507:IR", "official_czso_20260912/CEN02A.csv", official,
                          "yoy_change_pct", "czso_ppi_t26", segment=True),
                Component("2011_2014", "czso:CEN02032:0:IM:chained_yoy", "official_czso_20260912_agri/CEN02032.csv",
                          early, "yoy_change_pct", "czso_ppi_t26", segment=True)]
    if number == 44:
        return [Component("", "eurostat:sts_inppd_m:PRC_PRR_DOM:B-E36:PCH_SM:CZ",
                          "official_eurostat_20260912_ppi/tidy/sts_inppd_m_cz.csv",
                          _eurostat_ppi(ctx["ppi"], "B-E36", "PCH_SM"), "yoy_change_pct", "czso_ppi_t26")]
    if number in PPI_SECTIONS:
        nace = PPI_SECTIONS[number][0]
        return [Component("", f"eurostat:sts_inppd_m:PRC_PRR_DOM:{nace}:I21:CZ",
                          "official_eurostat_20260912_ppi/tidy/sts_inppd_m_cz.csv",
                          _eurostat_ppi(ctx["ppi"], nace, "I21"), "index_level", "czso_ppi_t26")]
    if number in AGRI_GROUPS:
        group = AGRI_GROUPS[number][0]
        return [Component("", f"czso:CEN02032:{group}:IM", "official_czso_20260912_agri/CEN02032.csv",
                          _cen02032(ctx["cen02032"], group), "mm_index_previous_month_100", "czso_ppi_t26")]
    arad = {53: ("SVSDM12", "percent", "arad_rates_t1"), 55: ("SFTP01M11", "percent", "arad_rates_t1"),
            56: ("SREERM101", "index_level", "arad_reer_t20"), 57: ("SREERM103", "index_level", "arad_reer_t20"),
            58: ("SUCM100311XXX101101", "stock_czk", "arad_loans_t31"), 59: ("SUCM102211XXX101101", "stock_czk", "arad_loans_t31")}
    if number in arad:
        code, kind, rule = arad[number]
        return [Component("", f"cnb_arad:{code}", "arad_selected.csv", _arad(ctx["arad"], code), kind, rule)]
    if number == 64:
        frame = ctx["cen0101j"]
        fuels = {722201: "petrol95", 722202: "petrol98_super_plus", 722101: "diesel", 722301: "lpg"}
        out = []
        for code, name in fuels.items():
            sub = frame[frame["CENPHM1"].astype(int).eq(code)]
            out.append(Component(name, f"czso:CEN0101J:{code:07d}", "official_czso_20260912/CEN0101J.csv",
                                 period_series(sub["Hodnota"], sub["CasM"]), "price_czk_per_litre", "czso_fuel_t7"))
        return out
    if number in (69, 70):
        column = "price_expect_survey_36m" if number == 69 else "price_expect_survey"
        panel = ctx["panel"]
        return [Component("", f"cnb_fmie:mean:{36 if number == 69 else 12}m", f"paper_predictor_panel.csv:{column}",
                          period_series(panel[column], panel.index), "percent", "cnb_fmie_next_month")]
    return []


def _agreement(a: pd.Series, b: pd.Series) -> dict:
    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if joined.empty:
        return {"n": 0}
    diff = (joined.a - joined.b).abs()
    return {"n": int(len(joined)), "first": str(joined.index.min()), "last": str(joined.index.max()),
            "mae": float(diff.mean()), "max_abs": float(diff.max()),
            "corr": float(joined.a.corr(joined.b)) if len(joined) > 2 else np.nan}


def source_checks(ctx: dict) -> pd.DataFrame:
    """Agreement between each extended official source and the CZSO series it replaces."""
    def dlog(s):
        return 100.0 * np.log(s / s.shift(1))

    rows = []
    sections = czso_ppi_sections(ctx["czso_ppi_raw"])
    for number, (nace, _) in PPI_SECTIONS.items():
        rows.append({"a6_number": number, "exact_source": f"Eurostat sts_inppd_m {nace} I21",
                     "comparator": "CZSO CEN0201A section total (2015=100)", "basis": "100*dlog",
                     **_agreement(dlog(_eurostat_ppi(ctx["ppi"], nace, "I21")), dlog(sections[nace]))})
    rows.append({"a6_number": 44, "exact_source": "Eurostat sts_inppd_m B-E36 PCH_SM",
                 "comparator": "CZSO CEN02A industrial producer prices y/y", "basis": "y/y %",
                 **_agreement(_eurostat_ppi(ctx["ppi"], "B-E36", "PCH_SM"),
                              _cen02a(ctx["cen02a"], "Index cen průmyslových výrobců", "IR") - 100.0)})
    for number, (group, _, indicator) in AGRI_GROUPS.items():
        rows.append({"a6_number": number, "exact_source": f"CZSO CEN02032 group {group} IM",
                     "comparator": f"CZSO CEN02A {indicator} IM", "basis": "m/m index",
                     **_agreement(_cen02032(ctx["cen02032"], group), _cen02a(ctx["cen02a"], indicator, "IM"))})
    mm = _cen02032(ctx["cen02032"], "0")
    chained = (mm / 100.0).cumprod()
    rows.append({"a6_number": 43, "exact_source": "CZSO CEN02032 agriculture incl. fish, chained y/y",
                 "comparator": "CZSO CEN02A agriculture incl. fish y/y", "basis": "y/y %",
                 **_agreement((100.0 * (chained / chained.shift(12) - 1.0)).dropna(),
                              _cen02a(ctx["cen02a"], "Index cen zemědělských výrobců včetně ryb", "IR") - 100.0)})
    return pd.DataFrame(rows)


def _coverage(components: list[Component]) -> dict:
    series = [c.series.dropna() for c in components if len(c.series.dropna())]
    if not series:
        return {"first": None, "last": None, "months_in_window": 0, "missing_in_window": None}
    if all(c.segment for c in components):
        joined = pd.concat(series).sort_index()
        joined = joined[~joined.index.duplicated()]
        first, last, index = joined.index.min(), joined.index.max(), joined.index
    else:
        first, last = max(s.index.min() for s in series), min(s.index.max() for s in series)
        index = series[0].index
        for s in series[1:]:
            index = index.intersection(s.index)
    window = pd.period_range(PAPER_START, PAPER_END, freq="M")
    present = window.isin(index)
    return {"first": str(first), "last": str(last), "months_in_window": int(present.sum()),
            "missing_in_window": int((~present).sum())}


def lane_status(verdict: str) -> str:
    if verdict.startswith("identical"):
        return "identical_mirror"
    if verdict.startswith("validated_mirror"):
        return "validated_mirror"
    if verdict in ("validated_proxy", "concept_match"):
        return "validated_proxy"
    if verdict in ("matches_other_official_series", "mismatch") or verdict.startswith("diagnostic"):
        return "rejected"
    return "candidate_unvalidated"


def candidate_verdicts(validation_dir: Path) -> dict[str, tuple[str, str]]:
    """Best lane status and the verdicts behind it, per ticker."""
    bcs = pd.read_csv(validation_dir / "bcs_candidate_verdicts.csv")
    hard = pd.read_csv(validation_dir / "hard_candidate_checks.csv")
    out: dict[str, tuple[str, str]] = {}
    for ticker, verdicts in [(t, [v]) for t, v in zip(bcs.ticker, bcs.verdict)] + \
            [(t, g.verdict.tolist()) for t, g in hard.groupby("ticker")]:
        statuses = [lane_status(v) for v in verdicts]
        best = min(statuses, key=LANE_RANK.get)
        previous = out.get(ticker)
        if previous is None or LANE_RANK[best] < LANE_RANK[previous[0]]:
            out[ticker] = (best, "; ".join(sorted(set(verdicts))))
    return out


def survey_adjustment(ecfin: pd.DataFrame, code: str) -> str:
    wide = ecfin[ecfin.series_code.isin([code, ecfin_nsa_code(code)])].pivot(index="period", columns="series_code", values="value")
    if wide.shape[1] < 2:
        return "EC SA series; NSA counterpart not in archive"
    both = wide.dropna()
    same = float((both.iloc[:, 0] - both.iloc[:, 1]).abs().lt(0.051).mean())
    if same >= 0.999:
        return "EC publishes identical SA and NSA values (no adjustment applied); X-13 per paper"
    return "EC seasonally adjusted balance; do not re-adjust"


def build(output: Path = DEFAULT_OUTPUT, inputs: Path = DEFAULT_INPUTS, validation_dir: Path = VALIDATION_DIR,
          candidate_dir: Path = CANDIDATE_DIR, root: Path = ROOT) -> dict:
    output, inputs = Path(output), Path(inputs)
    output.mkdir(parents=True, exist_ok=False)
    inputs.mkdir(parents=True, exist_ok=False)
    ctx = load_context(root)
    verdicts = candidate_verdicts(validation_dir)
    cands = pd.read_csv(candidate_dir / "candidate_periods_long.csv", dtype={"period": str})
    old = pd.read_csv(OLD_AUDIT).set_index("number") if OLD_AUDIT.exists() else pd.DataFrame()
    old_transforms = {}
    try:
        from paper_replication_experiment import A6 as runner_rows  # current runner after the row-38 correction
        old_transforms = {r.number: r.transform for r in runner_rows}
    except Exception:  # pragma: no cover - runner import problems are reported, not fatal
        pass

    audit_rows, exact_rows, candidate_rows = [], [], []
    for row in ROWS:
        components = exact_components(row.number, ctx)
        components = [c for c in components if len(c.series)]
        coverage = _coverage(components)
        tickers = [t for t, c in REGISTRY.items() if row.number in c.a6 and c.role in ("a6_candidate", "a6_challenger", "a6_benchmark")]
        lanes = []
        for ticker in tickers:
            lane, detail = verdicts.get(ticker, ("candidate_unvalidated", "not validated"))
            if row.geo == "EA" and lane == "identical_mirror":
                lane = "validated_proxy"  # equals the current-composition euro area, not EA20
            if REGISTRY[ticker].role == "a6_benchmark":
                lane = "candidate_unvalidated" if lane != "rejected" else lane
            lanes.append((ticker, lane, detail))
            statistic = CANDIDATE_STATISTIC.get(ticker, "month_mean" if REGISTRY[ticker].frequency == "daily" else "as_reported")
            sub = cands[cands.ticker.eq(ticker) & cands.statistic.eq(statistic)]
            for _, obs in sub.iterrows():
                candidate_rows.append({"a6_number": row.number, "column": f"bbg__{obs.alias}__{statistic}", "ticker": ticker,
                                       "statistic": statistic, "period": obs.period, "value": obs.value,
                                       "available_from_assumed": obs.available_from_assumed,
                                       "candidate_lane_status": lane, "validation_verdicts": detail})
        local_proxy = None
        if row.number == 25:
            panel = ctx["panel"]
            local_proxy = "paper_predictor_panel.csv:trade_balance"
            for period, value in panel["trade_balance"].dropna().items():
                candidate_rows.append({"a6_number": 25, "column": "local__trade_balance__as_stored", "ticker": None,
                                       "statistic": "as_stored", "period": str(period), "value": value,
                                       "available_from_assumed": None, "candidate_lane_status": "candidate_unvalidated",
                                       "validation_verdicts": "no official comparator; timing convention unverified"})
        usable = [l for l in lanes if l[1] != "rejected"]
        best_lane = min((l[1] for l in usable), key=LANE_RANK.get, default="none")
        if components:
            status = "exact"
        elif best_lane in ("identical_mirror", "validated_mirror", "validated_proxy"):
            status = "validated_proxy"
        elif usable or local_proxy:
            status = "candidate_unvalidated"
        else:
            status = "unavailable"
        if status == "validated_proxy":
            chosen = [l[0] for l in usable if l[1] == best_lane][0]
            stat = CANDIDATE_STATISTIC.get(chosen, "month_mean" if REGISTRY[chosen].frequency == "daily" else "as_reported")
            sub = cands[cands.ticker.eq(chosen) & cands.statistic.eq(stat)]
            first = sub.period.min() if len(sub) else None
            gap = bool(first) and (pd.Period(first, freq="Q").asfreq("M", "start") if "Q" in first else pd.Period(first, freq="M")) > PAPER_START
        else:
            first = coverage["first"]
            gap = bool(first) and pd.Period(first, freq="M") > PAPER_START
        for comp in components:
            for period, value in comp.series.items():
                exact_rows.append({"a6_number": row.number, "component": comp.label, "source_id": comp.source_id,
                                   "source_file": comp.source_file, "period": str(period), "value": float(value),
                                   "value_kind": comp.value_kind, "availability_rule": comp.rule,
                                   "available_from_assumed": available_from(comp.rule, period).date().isoformat(),
                                   "vintage": "current"})
        if row.eurostat and row.ecfin:
            adjustment = survey_adjustment(ctx["ecfin"], row.ecfin)
        else:
            adjustment = ADJUSTMENT.get(row.number, "unknown")
        audit_rows.append({
            "number": row.number, "group": row.group, "description": row.description,
            "transform_paper": row.transform, "transform_runner_20260910": int(old.loc[row.number, "transform"]) if row.number in old.index else None,
            "transform_runner_now": old_transforms.get(row.number), "kind": row.kind, "geo": row.geo, "geo_basis": row.geo_basis,
            "official_source": row.official_source, "a6_status": status, "historical_coverage_gap": gap,
            "status_first_period": first, "exact_source_ids": "; ".join(sorted({c.source_id for c in components})),
            "exact_first_period": coverage["first"], "exact_last_period": coverage["last"],
            "exact_months_in_paper_window": coverage["months_in_window"],
            "exact_missing_in_paper_window": coverage["missing_in_window"],
            "seasonal_adjustment": adjustment,
            "bloomberg_candidates": "; ".join(f"{t} ({l})" for t, l, _ in lanes),
            "candidate_lane_best": best_lane, "local_proxy": local_proxy,
            "status_20260910": old.loc[row.number, "status_in_run"] if row.number in old.index else None,
            "source_20260910": old.loc[row.number, "source_column"] if row.number in old.index else None,
            "vintage_status": "current vintage; no original publication vintages",
            "structural_issues": " | ".join(row.issues), "notes": ROW_NOTES.get(row.number, ""),
        })

    audit = pd.DataFrame(audit_rows)
    assert len(audit) == 72 and audit.a6_status.isin(STATUSES).all()
    exact = pd.DataFrame(exact_rows)
    candidates = pd.DataFrame(candidate_rows)
    checks = source_checks(ctx)
    summary = (audit.groupby(["a6_status", "historical_coverage_gap"]).number.agg(["count", lambda s: " ".join(map(str, s))])
               .rename(columns={"<lambda_0>": "rows"}).reset_index())
    paths = {"audit": output / "a6_audit.csv", "summary": output / "status_summary.csv",
             "source_checks": output / "exact_source_checks.csv",
             "exact": inputs / "exact_inputs_long.csv", "candidates": inputs / "candidate_inputs_long.csv"}
    audit.to_csv(paths["audit"], index=False)
    summary.to_csv(paths["summary"], index=False)
    checks.to_csv(paths["source_checks"], index=False)
    exact.to_csv(paths["exact"], index=False)
    candidates.to_csv(paths["candidates"], index=False)
    rules = pd.DataFrame([{"rule": k, "text": v[0], "days_after_period_end": v[1]} for k, v in EXACT_RULES.items()])
    rules.to_csv(inputs / "exact_availability_rules.csv", index=False)
    manifest = {
        "tool": "build_a6_audit", "created_at": datetime.now(timezone.utc).isoformat(),
        "paper_sample": list(PAPER_SAMPLE),
        "status_counts": audit.a6_status.value_counts().to_dict(),
        "coverage_gap_rows": audit.loc[audit.historical_coverage_gap, "number"].tolist(),
        "exact_rows": sorted(exact.a6_number.unique().tolist()),
        "candidate_rows": sorted(candidates.a6_number.unique().tolist()) if len(candidates) else [],
        "inputs": {str(p): sha256_file(p) for p in [validation_dir / "bcs_candidate_verdicts.csv",
                                                      validation_dir / "hard_candidate_checks.csv",
                                                      candidate_dir / "candidate_periods_long.csv"]},
        "outputs": {k: {"file": str(p), "sha256": sha256_file(p)} for k, p in paths.items()},
        "tool_sha256": sha256_file(Path(__file__)),
        "rules": "Exact inputs are official series only. Bloomberg series never enter the exact panel.",
    }
    for folder in (output, inputs):
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    args = parser.parse_args(argv)
    manifest = build(args.output, args.inputs)
    print(json.dumps({k: manifest[k] for k in ("status_counts", "coverage_gap_rows")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
