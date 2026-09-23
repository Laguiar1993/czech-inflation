"""
Local-first data adapter.

Pulls the bulk of the panel from the user's existing, actively-maintained
~/economic_db/czechia.duckdb (built by skills/em-macro-forecaster/scripts/
update_cz.py and friends) instead of the network-fragile scrapers in
data/fetchers.py. A few inputs aren't in that DB yet and are pulled live
(small, targeted calls):
  - CZSO weekly pump prices (CENPHMT) — needed for the h=0 fuel measurement
  - DE food HICP (Eurostat)           — foreign-influence food regressor
  - Brent (FRED)                      — fuel pass-through regressor
  - CNB's own Rushin weekly activity index, published directly by CNB
    (cnb.cz, XLSX, updated ~weekly) — pulled AS-IS rather than replicated;
    the user's own in-house PCA/PLS replica (build_cz_rushin_weekly.py) is
    a lower-fidelity approximation of the same thing CNB already publishes.
No Bloomberg — Phase 1 public-data sources only, per instruction.
"""
from __future__ import annotations
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import requests

DB_PATH = Path(os.environ.get("CZ_CPI_DB", Path.home() / "economic_db" / "czechia.duckdb"))
UA = {"User-Agent": "czk-cpi-nowcast/0.3 (local-adapter)"}


def _con(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise RuntimeError(f"czechia.duckdb not found at {DB_PATH} — run update_cz.py first")
    return duckdb.connect(str(DB_PATH), read_only=read_only)


# ---------------------------------------------------------------------------
# Administered-price announcements (data/admin_announcements.csv)
# ---------------------------------------------------------------------------
def load_admin_override_pp(target_month: pd.Period) -> float:
    """
    Sum of announced administered-price effects for target_month, in CPI-wide
    percentage points (weight_pp/100 * announced_change_pct per row, summed
    across every populated row for that month). Returns 0.0 if the file has
    no populated rows for the month -- i.e. this is a no-op adjustment until
    someone actually fills in an ERU/gazette decision, by design.

    Adapted from the original nowcast_h0() admin_override design: that model
    had four separate buckets (core/food/fuel/administered) so its override
    formula normalised by admin_weight to produce an equivalent admin_mm.
    The h0-hybrid architecture doesn't carry a separate administered bucket
    (folded into the QRF ex-fuel prediction) -- simpler to add the item's
    own whole-CPI contribution directly to the final nowcast than to force
    it through a bucket that no longer exists.
    """
    path = Path(__file__).parent / "admin_announcements.csv"
    df = pd.read_csv(path, comment="#")
    df = df[df["effect_month"] == str(target_month)]
    df = df.dropna(subset=["weight_pp", "announced_change_pct"])
    if df.empty:
        return 0.0
    return float((df["weight_pp"] / 100 * df["announced_change_pct"]).sum())


# ---------------------------------------------------------------------------
# Target: headline CPI m/m, NSA
# ---------------------------------------------------------------------------
def load_headline_cpi_mm() -> pd.Series:
    """CZSO open-data CEN0101E, households-total / all-items, chain-linked
    2015=100 index (cpi_czso.cpi_long). m/m from consecutive index levels."""
    con = _con()
    df = con.sql("""
        SELECT date, value FROM cpi_czso.cpi_long
        WHERE coicop_code = '0' AND base = 'base_2015_eq_100'
          AND hh_group_code = '0' AND subgroup_code = ''
        ORDER BY date
    """).df()
    con.close()
    if df.empty:
        raise RuntimeError("cpi_czso.cpi_long returned no headline rows — check filters")
    idx = pd.PeriodIndex(pd.to_datetime(df["date"]), freq="M")
    level = pd.Series(df["value"].values, index=idx).sort_index()
    mm = (100.0 * level.pct_change()).rename("cpi_mm")
    return mm.dropna()


# ---------------------------------------------------------------------------
# Component targets for the h=0 bridges: food + a combined core/administered
# residual.
#
# CZSO's own core/food/fuel/administered split (CNB analytical decomposition,
# Rychlé informace Tab. 5 -> cpi_czso.cpi_analytical) turns out to be a
# release-snapshot table, not a backfilled history: its "prev-month=100" base
# only carries ONE datapoint per historical pipeline run (9 points spanning
# 2019-2026), nowhere near enough to train a bridge regression. CNB ARAD
# doesn't carry CPI at all (verified 2026-04-22, see memory). So there is no
# continuous local source for the CNB 4-way split going back further than a
# handful of months.
#
# What IS continuous back to 2015-01 is CZSO's own COICOP division series
# (cpi_czso.cpi_long), which cleanly isolates food (division '01') AND fuel
# (subgroup '0722' under division '07', full 2015-01+ depth — verified
# 2026-09-05). The remainder bundles "core" and "administered" into one
# residual bridge target; CNB WP 9/2026 itself finds administered prices
# near-unforecastable from history (RMSE ~3.2 regardless of model), so
# folding it into core rather than fabricating a separate untrained model
# costs little. admin_override (announced tariff changes) still carves its
# slice out of this residual at h=0 — see components.nowcast_h0.
#
# core_admin MUST exclude fuel: every consumer (backtest_h0, backtest_h0_
# hybrid, backtest_4way, run_nowcast's h0 path) recombines it with a
# separately-measured fuel term at weight fuel_w, so a fuel-contaminated
# residual double-counts fuel in the recombined nowcast and noises up the
# ex-fuel QRF target. The pre-2026-09-05 version subtracted only food —
# caught by an external replication audit (Codex czech_cpi_experiment),
# verified against this code before fixing. cpi_weights has no '0722' row
# (division-level only), hence the config fallback for fuel_w.
# ---------------------------------------------------------------------------
def load_component_targets() -> pd.DataFrame:
    con = _con()
    food = con.sql("""
        SELECT date, value FROM cpi_czso.cpi_long
        WHERE coicop_code = '01' AND base = 'base_2015_eq_100'
          AND hh_group_code = '0' AND subgroup_code = ''
        ORDER BY date
    """).df()
    fuel = con.sql("""
        SELECT date, value FROM cpi_czso.cpi_long
        WHERE coicop_code = '07' AND subgroup_code = '0722'
          AND base = 'base_2015_eq_100' AND hh_group_code = '0'
        ORDER BY date
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(food["date"]), freq="M")
    food_level = pd.Series(food["value"].values, index=idx).sort_index()
    food_mm = 100.0 * food_level.pct_change()
    fuel_idx = pd.PeriodIndex(pd.to_datetime(fuel["date"]), freq="M")
    fuel_level = pd.Series(fuel["value"].values, index=fuel_idx).sort_index()
    fuel_mm = 100.0 * fuel_level.pct_change()

    headline_mm = load_headline_cpi_mm()
    food_w = latest_weight_permille("01") / 1000.0
    from config import COMPONENT_WEIGHTS_FALLBACK
    fuel_w = COMPONENT_WEIGHTS_FALLBACK["fuel"]

    out = pd.DataFrame(index=headline_mm.index)
    out["food"] = food_mm.reindex(out.index)
    out["fuel"] = fuel_mm.reindex(out.index)
    out["core_admin"] = (headline_mm - food_w * out["food"] - fuel_w * out["fuel"]) \
        / (1 - food_w - fuel_w)
    return out.dropna(how="all")


def load_fuel_mm_history() -> pd.Series:
    """Historical fuel CPI m/m, EVERY month fully realized (unlike the h=0
    nowcast use of fuel_mm_from_weekly, which handles a still-open partial
    month) -- for use as a genuine h>=1 FORECAST TARGET, not a real-time
    measurement. Uses the official per-regime petrol/diesel blend (models.components, v2.3)."""
    from models.components import fuel_mm_from_weekly
    w = fetch_weekly_fuels_live()
    last_full_month = w.index.max().to_period("M") - 1  # exclude the still-open current month
    months = pd.period_range(w.index.min().to_period("M") + 1, last_full_month, freq="M")
    rows = {}
    for m in months:
        try:
            mm, _ = fuel_mm_from_weekly(w, m)
            rows[m] = mm
        except Exception:
            continue
    return pd.Series(rows, name="fuel_mm").sort_index()


def load_admin_core_split() -> pd.DataFrame:
    """Genuine administered-vs-market CPI split from CZSO's own analytical
    breakdown release (cpi_czso.cpi_analytical). Correction to an earlier,
    too-hasty read of this table: the 3 distinct `base` values here are NOT
    sequential rebases of one series -- they're 3 DIFFERENT index types CZSO
    publishes side by side each month (yoy_prev_year_eq_100: 98 pts, YoY
    based, would need extra work to back out m/m; prev_month_eq_100: only 9
    pts, this is the sparse snapshot an earlier check in this project
    correctly flagged as unusable; dec_2023_eq_100: 26 pts, Jun-2024
    onward, a genuinely continuous FIXED-BASE level series). Use the last of
    these directly -- real, clean, no splicing needed, just short (2 years,
    not the 8 a naive first look across all 3 `base` values suggested)."""
    con = _con()
    df = con.sql("""
        SELECT date, series_code, idx_value FROM cpi_czso.cpi_analytical
        WHERE series_code IN ('goods_with_administrative_prices3',
                              'total_excl_goods_with_administrative_prices')
          AND base = 'dec_2023_eq_100'
        ORDER BY date
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(df["date"]), freq="M")
    piv = df.assign(period=idx).pivot_table(index="period", columns="series_code", values="idx_value").sort_index()

    out = pd.DataFrame(index=piv.index)
    out["admin_mm"] = 100.0 * piv["goods_with_administrative_prices3"].pct_change()
    out["core_ex_admin_mm"] = 100.0 * piv["total_excl_goods_with_administrative_prices"].pct_change()
    return out


def load_headline_cpi_mm_extended() -> pd.Series:
    """True CZ headline CPI m/m, extended back to 1991 via FRED/OECD MEI
    (CZECPIALLMINMEI) -- NOT a proxy: verified exact match (corr=1.0, mean/
    std diff=0.0) against CZSO's own cpi_long over the full 123-month
    overlap, since OECD's MEI database mirrors each country's own national
    CPI release rather than computing a separate harmonized measure (unlike
    HICP, which genuinely is a different basket -- excludes imputed rent --
    and was correctly pushed back on when tried as a training-target proxy
    earlier in this project). True CZSO data (load_headline_cpi_mm) wins
    wherever both exist; FRED only fills the pre-2015 span CZSO's own
    open-data extract doesn't reach. Tested: extending both training AND
    the backtest evaluation window to a paper-like ~15yr OOS span (vs this
    project's original ~8yr) moves h=3 TVW_QRF from 0.872 to 0.715 -- much
    closer to CNB WP 9/2026's own disclosed 0.669 -- while the surge
    (2021-06..2023-03) drops from 22% to 13% of the evaluated sample,
    confirming sample-composition was a real driver of the gap, not just
    sample depth alone."""
    from data.fetchers import fetch_fred
    fred_cpi = fetch_fred("CZECPIALLMINMEI")
    fred_cpi.index = fred_cpi.index.to_period("M")
    fred_mm = (100 * fred_cpi.pct_change()).rename("cpi_mm")
    return load_headline_cpi_mm().combine_first(fred_mm).sort_index()


def latest_weight_permille(coicop_code: str) -> float:
    con = _con()
    row = con.sql(f"""
        SELECT weight_per_mille FROM cpi_czso.cpi_weights
        WHERE country = 'CZ' AND coicop_code = '{coicop_code}'
        ORDER BY basis_year DESC LIMIT 1
    """).fetchone()
    con.close()
    if row is None:
        raise RuntimeError(f"no cpi_weights row for coicop_code={coicop_code!r}")
    return float(row[0])


# ---------------------------------------------------------------------------
# Regressor panel: PPI, ESI, inflation expectations, FX — all local
# ---------------------------------------------------------------------------
_PPI_CODES = {
    "PPI_AGRI": "agri_ppi_mm",
    "PPI_INDUSTRY": "ppi_mm",
    "PPI_C": "ppi_c_mm",          # manufacturing (NACE C) -> core goods pipeline
    "PPI_D": "ppi_d_mm",          # electricity/gas/steam (NACE D) -> energy/administered pipeline
    "PPI_E": "ppi_e_mm",          # water/sewerage/waste (NACE E)
    "PPI_CONSTR": "ppi_constr_mm",
    "PPI_SERVICES": "ppi_services_mm",  # core services pipeline
}


def _shift_to_availability(s: pd.Series | pd.DataFrame, lag_months: int) -> pd.Series | pd.DataFrame:
    """CZSO indexes RI releases by REFERENCE month, not by when the value was
    actually published -- but build_supervised's .loc[:origin] slicing treats
    a series' own index as its availability date. Left unshifted, a backtest
    origin of month M would see PPI/IP/etc. for reference month M itself,
    when in fact (verified against czso.*_ri's own release_date column,
    2026-08-21) PPI isn't first published until ~16-25 days into M+1 and
    IP/retail/construction not until ~36-41 days into M+1 -- both cross a
    month boundary, so origin M cannot legitimately see them yet. Shifting
    the index forward by the (whole-month, conservative) lag makes a
    reference-month-M value first visible at the correct later origin."""
    out = s.copy()
    out.index = out.index + lag_months
    return out


def load_ppi_yoy() -> pd.DataFrame:
    """PPI by NACE section, CZSO Rychlé informace (czso.ppi_ri) — the sectoral
    disaggregation CNB WP 9/2026 uses as its PPI predictor group, not just the
    headline agri/industry pair. The RI table publishes a same-period-year-
    ago=100 index; latest release per data_month wins on revision."""
    con = _con()
    df = con.sql(f"""
        SELECT data_month, code, yoy_index FROM czso.ppi_ri
        WHERE code IN ({",".join(f"'{c}'" for c in _PPI_CODES)})
        QUALIFY ROW_NUMBER() OVER (PARTITION BY data_month, code ORDER BY release_date DESC) = 1
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(df["data_month"]), freq="M")
    piv = df.assign(period=idx).pivot_table(index="period", columns="code", values="yoy_index", aggfunc="last")
    piv = _shift_to_availability(piv, 1)  # first published ~16-25 days into the following month
    return (piv.sort_index() - 100.0).rename(columns=_PPI_CODES)


def fetch_ppi_industry_yoy_deep_live() -> pd.Series:
    """Industry PPI YoY% spliced: Eurostat sts_inppd_m (CZ, back to 2000-01)
    for dates before CZSO's RI table starts (2015-01), CZSO RI (already-local
    ppi_mm, more current/authoritative) from 2015-01 on. Used only for the
    h>=1 backtest panel, which needs depth more than it needs the RI table's
    slightly tighter CZ-native accuracy — see README CZ source-priority note;
    this is the one deliberate exception to CZSO-over-Eurostat."""
    from data.fetchers import fetch_eurostat
    level = fetch_eurostat("sts_inppd_m", {"nace_r2": "B-E36", "geo": "CZ", "unit": "I21"}, start="2000-01")
    eurostat_yoy = _shift_to_availability(100 * (level / level.shift(12) - 1), 1)  # Eurostat STS PPI: same ~1-month-class lag as CZSO's own, not independently verified this session but not left unshifted either
    local_yoy = load_ppi_yoy()["ppi_mm"]  # already shifted inside load_ppi_yoy()
    return local_yoy.combine_first(eurostat_yoy).rename("ppi_mm_deep").sort_index()


def load_esi() -> pd.Series:
    """Economic Sentiment Indicator, CZ (Eurostat BS-ESI-I via eurostat.bcs_survey)."""
    con = _con()
    df = con.sql("""
        SELECT year, month, value FROM eurostat.bcs_survey WHERE indic_code = 'BS-ESI-I'
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(dict(year=df.year, month=df.month, day=1)), freq="M")
    return pd.Series(df["value"].values, index=idx, name="esi").sort_index()


def fetch_household_price_expectations_live() -> pd.Series:
    """EU harmonized consumer survey 'price trends over the next 12 months'
    balance (Eurostat ei_bsco_m, indic=BS-PT-NY) — household-level inflation
    expectations, distinct from the CNB FMIE professional/market survey
    already in the panel (load_inflation_expectations). Verified 2026-08:
    CZ Jun-2026 = 25.3 (SA)."""
    from data.fetchers import fetch_eurostat
    return fetch_eurostat("ei_bsco_m", {"geo": "CZ", "indic": "BS-PT-NY", "s_adj": "SA"}
                          ).rename("household_price_expect")


def _cpi_divisions_mm() -> pd.DataFrame:
    """Level index for each of the 13 non-headline COICOP divisions, m/m %."""
    con = _con()
    df = con.sql("""
        SELECT date, coicop_code, value FROM cpi_czso.cpi_long
        WHERE base = 'base_2015_eq_100' AND hh_group_code = '0' AND subgroup_code = ''
          AND coicop_code != '0'
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(df["date"]), freq="M")
    piv = df.assign(period=idx).pivot_table(index="period", columns="coicop_code", values="value").sort_index()
    return 100 * piv.pct_change()


def load_cpi_breadth() -> pd.Series:
    """Diffusion/breadth index: share of the 13 non-headline COICOP
    divisions posting a positive m/m print. Used by several regional Fed
    nowcasts as an inflation-breadth signal, orthogonal to the
    magnitude-based regressors elsewhere in this panel. Same-period
    correlation with headline CPI m/m: ~0.49 (tested 2026-08)."""
    mm = _cpi_divisions_mm()
    return ((mm > 0).sum(axis=1) / mm.notna().sum(axis=1)).rename("cpi_breadth")


def load_median_cpi_mm() -> pd.Series:
    """Weighted median of COICOP division m/m changes — reconstructs CNB's
    own 'medianova inflace' methodology (Zprava o inflaci II/2015; CNB Blog
    Dec-2023), which the bank has only ever published as one-off analytical
    pieces, never as an ongoing series (verified 2026-08: not on cnb.cz or
    czso.cz on any publication calendar). Designed in the literature
    specifically to strip out one-off spikes — directly relevant given this
    model's biggest misses are all January step-changes.
    Uses the latest known basket weights uniformly across history, same
    simplification config.COMPONENT_WEIGHTS_FALLBACK already makes
    elsewhere in this codebase, rather than a full basis-year-aware weight
    history."""
    mm = _cpi_divisions_mm()
    con = _con()
    weights = con.sql("""
        SELECT coicop_code, weight_per_mille FROM cpi_czso.cpi_weights
        WHERE country = 'CZ' AND basis_year = (
            SELECT MAX(basis_year) FROM cpi_czso.cpi_weights WHERE country = 'CZ')
    """).df()
    con.close()
    w = weights.set_index("coicop_code")["weight_per_mille"].reindex(mm.columns).fillna(0)

    def weighted_median(row):
        vals = row.dropna()
        if vals.empty:
            return np.nan
        ws = w.reindex(vals.index).fillna(0)
        order = vals.sort_values().index
        cum = ws.loc[order].cumsum()
        cutoff = ws.sum() / 2
        hit = vals.loc[order][cum.loc[order] >= cutoff]
        return hit.iloc[0] if len(hit) else vals.median()

    return mm.apply(weighted_median, axis=1).rename("median_cpi_mm")


def load_real_activity() -> pd.DataFrame:
    """CZ real-activity YoY%: industrial production, retail trade, construction
    output (all czso.*_ri, latest release per data_month), unemployment rate
    (czso.unemployment_ri, trend-cycle SA). CNB WP 9/2026's 'real activity CZ'
    predictor group — previously only Rushin represented this group here.

    construction_ri carries ~17 series under one table (output index, permits,
    completions, wages, employment...) keyed by a `code` column the query must
    filter on -- verified 2026-08-21 the query here had NO such filter, so
    QUALIFY's ROW_NUMBER tiebreak among same-release_date rows was picking an
    arbitrary one of those 17 (permits/wages/etc, not output) whenever a
    data_month's releases tied on date, which they usually do. Now pinned to
    code='index_stavební_produkce' + label_en='Očištěno o pracovní dny' (the
    working-day-adjusted headline construction output index) -- deterministic
    and sane (0/305 rows outside a plausible 50-150 YoY-index range) but only
    available from 2018-11 on; pre-2018-11 months come back NaN rather than
    the previous silently-wrong value from an unrelated series."""
    con = _con()
    ip = con.sql("""
        SELECT data_month, yoy_index FROM czso.ip_ri WHERE nace_code = 'BCD'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY data_month ORDER BY release_date DESC) = 1
    """).df()
    retail = con.sql("""
        SELECT data_month, yoy_index FROM czso.retail_ri WHERE code = '47'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY data_month ORDER BY release_date DESC) = 1
    """).df()
    constr = con.sql("""
        SELECT data_month, yoy_index FROM czso.construction_ri
        WHERE code = 'index_stavební_produkce' AND label_en = 'Očištěno o pracovní dny'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY data_month ORDER BY release_date DESC) = 1
    """).df()
    unemp = con.sql("""
        SELECT data_month, rate_pct FROM czso.unemployment_ri
        WHERE adjusted = 'trend_cycle' AND series = 'unemployment' AND gender = 'total'
    """).df()
    con.close()

    def _to_pmm(df, col, name):
        idx = pd.PeriodIndex(pd.to_datetime(df["data_month"]), freq="M")
        return pd.Series(df[col].values, index=idx, name=name).sort_index()

    # ip/retail/construction: first published ~36-41 days into the following
    # month (verified against release_date) -- crosses into month+2, a
    # 1-month shift alone would still be premature by up to ~10 days.
    # unemployment: true first-release lag isn't independently verifiable
    # (its release_date column is a single-backfill artifact, not a genuine
    # per-month history -- every historical row shares one pull date), so
    # this uses the same conservative 2-month shift as its RI-release
    # siblings rather than assume it's fine unshifted.
    return pd.concat([
        _shift_to_availability(_to_pmm(ip, "yoy_index", "ip_yoy") - 100.0, 2),
        _shift_to_availability(_to_pmm(retail, "yoy_index", "retail_yoy") - 100.0, 2),
        _shift_to_availability(_to_pmm(constr, "yoy_index", "constr_yoy") - 100.0, 2),
        _shift_to_availability(_to_pmm(unemp, "rate_pct", "unemployment_rate"), 2),
    ], axis=1)


def load_confidence_ri() -> pd.DataFrame:
    """CZSO-native confidence sub-indices (consumer/business/economic
    sentiment) — richer than the single Eurostat ESI level already used."""
    con = _con()
    df = con.sql("SELECT data_month, indicator, base_index FROM czso.confidence_ri").df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(df["data_month"]), freq="M")
    piv = df.assign(period=idx).pivot_table(index="period", columns="indicator", values="base_index")
    return piv.sort_index().add_prefix("conf_")


_ARAD_FINANCIAL = {
    "SFTP04M2206": "pribor_3m", "SVSDM12": "czgb_10y",
    "SREERM101": "reer_ppi", "SREERM103": "reer_cpi",  # monthly REER, 2020=100, overall-trade weights
}


def load_financial() -> pd.DataFrame:
    """3M PRIBOR + 10Y CZGB yield + REER (CPI- and PPI-deflated) from
    monetary.arad_data — CNB WP 9/2026's 'financial' predictor group; only
    the CNB policy rate was used before. Rates are levels; REER is an index
    (2020=100) so it's converted to m/m growth to match the rest of the
    panel's convention."""
    con = _con()
    df = con.sql(f"""
        SELECT indicator_id, period, value FROM monetary.arad_data
        WHERE indicator_id IN ({",".join(f"'{c}'" for c in _ARAD_FINANCIAL)})
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(df["period"]), freq="M")
    piv = df.assign(period=idx).pivot_table(index="period", columns="indicator_id", values="value")
    piv = piv.sort_index().rename(columns=_ARAD_FINANCIAL)
    for c in ("reer_ppi", "reer_cpi"):
        if c in piv.columns:
            piv[f"{c}_mm"] = 100.0 * piv[c].pct_change()
            piv = piv.drop(columns=c)
    return piv


def load_wage_mm_chowlin() -> pd.Series:
    """Monthly wage growth via Chow-Lin (1971) temporal disaggregation of
    CZSO's quarterly average-wage level, driven by monthly unemployment rate
    (trend_cycle, total) as the correlated high-frequency indicator. CZ wage
    data is genuinely quarterly-only at the source -- CNB WP 9/2026 doesn't
    wait for monthly data either, it disaggregates the same way (its own
    LUCI/ULC predictors, driven by their own indicator set). Disaggregate the
    LEVEL then difference afterward, not the other way around -- Chow-Lin's
    additivity constraint (interpolated months must average back to the
    quarterly actual) only holds on the level."""
    from tsdisagg import disaggregate_series
    con = _con()
    wages = con.sql("SELECT period, avg_wage_czk FROM czso.wages_headline WHERE avg_wage_czk IS NOT NULL ORDER BY period").df()
    unemp = con.sql("""
        SELECT data_month, rate_pct FROM czso.unemployment_ri
        WHERE series='unemployment' AND adjusted='trend_cycle' AND gender='total' ORDER BY data_month
    """).df()
    con.close()

    wages_df = wages.set_index(pd.PeriodIndex(pd.to_datetime(wages["period"]), freq="Q").to_timestamp())[["avg_wage_czk"]].asfreq("QS")
    unemp_df = unemp.set_index(pd.PeriodIndex(pd.to_datetime(unemp["data_month"]), freq="M").to_timestamp())[["rate_pct"]].asfreq("MS")

    monthly_level = disaggregate_series(wages_df, unemp_df, target_freq="MS", agg_func="mean",
                                        method="chow-lin", verbose=False)
    s = monthly_level.iloc[:, 0] if isinstance(monthly_level, pd.DataFrame) else monthly_level
    s.index = pd.PeriodIndex(s.index, freq="M")
    return (100 * s.pct_change()).rename("wage_mm_chowlin").sort_index()


_PL_DB_PATH = Path.home() / "economic_db" / "poland.duckdb"


def load_pl_retail_confidence() -> pd.Series:
    """PL retail-sector business confidence (GUS, SA) as a foreign-influence
    predictor for CZ inflation — CNB WP 9/2026 predictor 22 includes Poland
    alongside the (much heavier) Germany emphasis in its G2 group."""
    con = duckdb.connect(str(_PL_DB_PATH), read_only=True)
    df = con.sql("""
        SELECT year, month, indicator_sa FROM gus.business_confidence
        WHERE sector = 'retail'
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(dict(year=df.year, month=df.month, day=1)), freq="M")
    return pd.Series(df["indicator_sa"].values, index=idx, name="pl_retail_conf").sort_index()


_ARAD_HH_LOANS = "SUCM102211XXX101101"  # households, total client loans
_ARAD_NFC_LOAN_TOTAL = "SUCM100311XXX101101"  # NFC, total client loans
_ARAD_NFC_LOAN_BUCKETS = ("SUCM200311XXX101101", "SUCM300311XXX101101",
                          "SUCM400311XXX101101")  # NFC, by maturity bucket
_ARAD_NFC_LOANS = [_ARAD_NFC_LOAN_TOTAL, *_ARAD_NFC_LOAN_BUCKETS]


def _nfc_balance_from_pivot(
    piv: pd.DataFrame,
    total_id: str = _ARAD_NFC_LOAN_TOTAL,
    bucket_ids: tuple[str, ...] = _ARAD_NFC_LOAN_BUCKETS,
) -> pd.Series:
    """Return one NFC loan stock, never the total plus its buckets.

    The VST/ARAD layout contains a total row as well as three original-maturity
    rows.  When the total is present it is authoritative; the maturity rows are
    only a fallback for snapshots that lack the total row.
    """
    if total_id in piv.columns:
        return piv[total_id]
    missing = [col for col in bucket_ids if col not in piv.columns]
    if missing:
        raise KeyError(f"NFC total and maturity buckets missing from ARAD panel: {missing}")
    return piv[list(bucket_ids)].sum(axis=1, min_count=len(bucket_ids))


def load_credit_aggregates() -> pd.DataFrame:
    """Household + non-financial-corporation client loan balances (CNB ARAD,
    VST(ČNB)1-12 regulatory return) — CNB WP 9/2026's 'financial' group.
    The ARAD panel contains an NFC total plus three original-maturity buckets;
    use the total once and fall back to the three buckets only when the total is
    absent. Household total is confirmed against CNB's own published Jun-2026
    commentary (2,713bn CZK household loans -- exact match)."""
    con = _con()
    codes = [_ARAD_HH_LOANS] + _ARAD_NFC_LOANS
    df = con.sql(f"""
        SELECT indicator_id, period, value FROM monetary.arad_data
        WHERE indicator_id IN ({",".join(f"'{c}'" for c in codes)})
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(df["period"]), freq="M")
    piv = df.assign(period=idx).pivot_table(index="period", columns="indicator_id", values="value").sort_index()
    hh = piv[_ARAD_HH_LOANS]
    nfc = _nfc_balance_from_pivot(piv)
    return pd.DataFrame({
        "hh_loans_mm": 100.0 * hh.pct_change(),
        "nfc_loans_mm": 100.0 * nfc.pct_change(),
    })


_MONTH_CS_TO_NUM = {
    "leden": 1, "únor": 2, "březen": 3, "duben": 4,
    "květen": 5, "červen": 6, "červenec": 7, "srpen": 8,
    "září": 9, "říjen": 10, "listopad": 11, "prosinec": 12,
}


def fetch_import_prices_mm_live() -> pd.Series:
    """CZ import price index, m/m -- CZSO open-data sada CEN0301 (Indexy cen
    vývozu a dovozu zboží). Total aggregate ('Úhrn celkem'), m/m variant."""
    df = requests.get(
        "https://data.csu.gov.cz/opendata/sady/CEN0301/distribuce/csv",
        headers=UA, timeout=60,
    ).content
    import io as _io
    raw = pd.read_csv(_io.BytesIO(df))
    col_period = "Měsíce, měsíční kumulace, měsíce klouzavých průměrů, čtvrtletí, roky"
    sel = raw[
        (raw["Klasifikace CZ-CPA-Úhrn a sekce"] == "Úhrn celkem")
        & (raw["Ukazatel"] == "Index dovozních cen (%)")
        & (raw["Typ indexu"] == "Meziměsíční index")
    ][[col_period, "Hodnota"]].copy()

    def _parse(label: str):
        month_cs, year = label.split()
        return pd.Period(year=int(year), month=_MONTH_CS_TO_NUM[month_cs], freq="M")

    sel["period"] = sel[col_period].apply(_parse)
    sel = sel.drop_duplicates(subset="period")  # CASMKMQRM12 carries a '...K' duplicate label per month, same value
    s = sel.set_index("period")["Hodnota"].sort_index()
    return (s - 100.0).rename("import_price_mm")


_TRADE_BALANCE_CSV = Path(__file__).parent / "cz_trade_balance.csv"


def load_trade_balance() -> pd.Series:
    """CZ goods trade balance level (mil. CZK, FOB exports / CIF imports --
    CZSO's headline convention, not true FOB/FOB) -- CNB WP 9/2026's G2
    foreign-influence group. Cached to a small local CSV rather than
    re-downloading CZSO's ~570MB VZOOM sada (data/pull_cz_trade_balance.py
    regenerates it); the balance itself, not a growth rate, since a trade
    surplus/deficit LEVEL is the economically meaningful predictor here."""
    df = pd.read_csv(_TRADE_BALANCE_CSV)
    idx = pd.PeriodIndex(df["ym"], freq="M")
    return pd.Series(df["Hodnota"].values, index=idx, name="trade_balance").sort_index()


def fetch_de_macro_live() -> pd.DataFrame:
    """German IP/retail YoY% + ESI (Eurostat, geo=DE) — the 'foreign influence,
    esp. Germany' predictor group; only DE food HICP was used before. Same
    dataset codes and filters pull_eurostat_macro.py already uses for CZ."""
    from data.fetchers import fetch_eurostat
    ip = fetch_eurostat("sts_inpr_m", {"geo": "DE", "nace_r2": "B-D", "unit": "PCH_SM", "s_adj": "CA"})
    retail = fetch_eurostat("sts_trtu_m", {"geo": "DE", "nace_r2": "G47", "indic_bt": "VOL_SLS",
                                           "unit": "PCH_SM", "s_adj": "CA"})
    esi = fetch_eurostat("ei_bssi_m_r2", {"geo": "DE", "indic": "BS-ESI-I", "s_adj": "SA"})
    return pd.concat([ip.rename("de_ip_yoy"), retail.rename("de_retail_yoy"), esi.rename("de_esi")], axis=1)


def load_inflation_expectations(horizon_months: int = 12) -> pd.Series:
    """CNB FMIE survey mean CPI y/y expectation (consensus.inflation_expectations)."""
    con = _con()
    df = con.sql(f"""
        SELECT survey_date, value_pct FROM consensus.inflation_expectations
        WHERE target = 'cpi_headline_yoy' AND horizon_kind = 'rolling_months'
          AND horizon_value = {horizon_months} AND metric = 'mean'
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(df["survey_date"]), freq="M")
    name = "price_expect_survey" if horizon_months == 12 else f"price_expect_survey_{horizon_months}m"
    return pd.Series(df["value_pct"].values, index=idx, name=name).sort_index()


def load_fx_monthly_levels() -> pd.DataFrame:
    """EUR/CZK, USD/CZK monthly averages, level (monetary.fx_monthly)."""
    con = _con()
    df = con.sql("""
        SELECT year, month, currency_code, czk_per_unit FROM monetary.fx_monthly
        WHERE currency_code IN ('EUR', 'USD')
    """).df()
    con.close()
    idx = pd.PeriodIndex(pd.to_datetime(dict(year=df.year, month=df.month, day=1)), freq="M")
    return df.assign(period=idx).pivot_table(
        index="period", columns="currency_code", values="czk_per_unit").sort_index()


def load_fx_monthly_mm() -> pd.DataFrame:
    piv = load_fx_monthly_levels()
    return pd.DataFrame({
        "eurczk_mm": 100 * piv["EUR"].pct_change(),
        "usdczk_mm": 100 * piv["USD"].pct_change(),
    })


# ---------------------------------------------------------------------------
# Live pulls: not yet in czechia.duckdb (small, targeted; see README §6.4)
# ---------------------------------------------------------------------------
def fetch_weekly_fuels_live() -> pd.DataFrame:
    """CZSO weekly pump prices (CENPHMT DataStat CSV). Monday-observed
    snapshots, CZK/l. See config.CZSO_WEEKLY_FUELS_CSV for provenance."""
    from config import CZSO_WEEKLY_FUELS_CSV
    r = requests.get(CZSO_WEEKLY_FUELS_CSV, headers=UA, timeout=30)
    r.raise_for_status()
    raw = pd.read_csv(pd.io.common.BytesIO(r.content))
    lvl = raw[raw["Ukazatel"].str.contains("Kč/litr", na=False)].copy()
    lvl["date"] = pd.to_datetime(lvl["CASTPHM"] + "-1", format="%G-W%V-%u")
    piv = lvl.pivot_table(index="date", columns="Druh PHM", values="Hodnota", aggfunc="mean").sort_index()
    ren = {}
    for c in piv.columns:
        lc = str(c).lower()
        if "95" in lc or "natur" in lc:
            ren[c] = "petrol95"
        elif "naft" in lc:
            ren[c] = "diesel"
        elif "lpg" in lc:
            ren[c] = "lpg"
    return piv.rename(columns=ren)


CNB_RUSHIN_XLSX = "https://www.cnb.cz/export/sites/cnb/cs/ekonomicky-vyzkum/.galleries/rushin_index/rushin.xlsx"


def fetch_rushin_monthly_live() -> pd.Series:
    """CNB's own Rushin weekly economic-activity index (standardised score),
    pulled directly rather than replicated — see module docstring. Weekly
    since 2008-06; resampled to monthly mean for use as a real-activity
    regressor (CNB WP 9/2026's 'real activity CZ' predictor group)."""
    import io
    r = requests.get(CNB_RUSHIN_XLSX, headers=UA, timeout=30)
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content), sheet_name="data", usecols=[0, 1],
                       names=["date", "rushin"], skiprows=1)
    df = df.dropna(subset=["date", "rushin"])
    weekly = pd.Series(df["rushin"].values, index=pd.to_datetime(df["date"])).sort_index()
    return weekly.resample("ME").mean().to_period("M").rename("rushin")


def fetch_cnb_arad_direct(code: str, period_from: str = "2007-01-01") -> pd.Series:
    """Direct pull from CNB ARAD's own public REST API -- not the curated
    monetary.arad_data mirror (these CPI_MZM-family codes aren't in it).
    Endpoint and request shape (POST with BOTH query params AND a JSON body
    of [code] -- easy to miss, the query string alone returns indicators=null)
    reverse-engineered 2026-08-23 via live network inspection of arad's own
    web UI, then verified: values match the rendered UI table exactly
    (SCPIMZM02MOMPECNA May/Jun/Jul-2026 = 0.1/0.0/0.2, confirmed row-for-row).
    No auth required."""
    from_ms = int(pd.Timestamp(period_from).timestamp() * 1000)
    to_ms = int(pd.Timestamp.today().timestamp() * 1000)
    params = {"snList": "", "periodFrom": str(from_ms), "periodTo": str(to_ms),
             "roleId": "U", "type": "single", "setParams": "", "chartData": f"{code}:0"}
    r = requests.post("https://www.cnb.cz/aradb/api/v13/indicators-data-by-codes",
                      params=params, json=[code], headers=UA, timeout=30)
    r.raise_for_status()
    pts = r.json()["data"][0]["indicators"][0]["snapshots_data"][0]["data"]
    idx = pd.PeriodIndex([pd.Timestamp(ts, unit="ms") for ts, _ in pts], freq="M")
    return pd.Series([v for _, v in pts], index=idx, name=code).sort_index()


def fetch_cnb_core_inflation_mm_live() -> pd.Series:
    """CNB's own core inflation ('jádrová inflace'), SCPIMZM09MOMPECNA,
    2007-01 on -- an exclusion-based underlying-inflation measure (ex food/
    fuel/regulated), distinct from cpi_breadth (diffusion) and median_cpi_mm
    (trimmed-median) already in the panel."""
    return fetch_cnb_arad_direct("SCPIMZM09MOMPECNA").rename("cnb_core_inflation_mm")


def fetch_cnb_regulated_prices_mm_live() -> pd.Series:
    """CNB's own regulated/administered prices ('regulované ceny'),
    SCPIMZM02MOMPECNA, 2007-01 on. Resolves a gap this project's own history
    had walked back as 'not backfillable, only 9 sparse points exist' --
    this is a real, continuous 19.5-year monthly series, CNB-native rather
    than hand-assembled from CZSO COICOP subgroups."""
    return fetch_cnb_arad_direct("SCPIMZM02MOMPECNA").rename("cnb_regulated_prices_mm")


def fetch_de_food_hicp_live() -> pd.Series:
    """DE food HICP m/m (Eurostat prc_hicp_midx, CP01/DE) — dominant foreign-
    influence food regressor per BIS/CNB WP 9/2026; not in the local DB."""
    from data.fetchers import fetch_eurostat
    from config import EUROSTAT
    level = fetch_eurostat(*EUROSTAT["hicp_de_food"])
    return (100 * level.pct_change()).rename("de_food_hicp_mm")


def fetch_brent_czk_mm_live() -> pd.Series:
    """Brent (FRED DCOILBRENTEU, USD) converted to CZK via local FX, m/m %."""
    from data.fetchers import fetch_fred
    brent_usd = fetch_fred("DCOILBRENTEU").resample("ME").mean()
    fx = load_fx_monthly_levels()
    brent_m = brent_usd.copy()
    brent_m.index = brent_m.index.to_period("M")
    brent_czk = (brent_m * fx["USD"]).dropna()
    mm = (100 * brent_czk.pct_change()).rename("brent_czk_mm")
    return mm


def fetch_brent_czk_daily_live() -> pd.Series:
    """Daily Brent(CZK). NO LONGER a forecast input: the fuel tail
    projection was removed in v2.3 (FUEL_SPEC_v23.md) after a measured A/B
    showed it hurt. Kept for research/diagnostics only. FX held at the
    latest local monthly USD/CZK rate."""
    from data.fetchers import fetch_fred
    brent_usd_daily = fetch_fred("DCOILBRENTEU")
    usdczk_latest = load_fx_monthly_levels()["USD"].dropna().iloc[-1]
    return (brent_usd_daily * usdczk_latest).rename("brent_czk_daily")


_BRENT_FORWARD_CSV = Path(__file__).parent / "bbg_brent_forward_daily.csv"


def load_brent_forward_mm() -> pd.DataFrame:
    """~7-month and ~13-month Brent futures (Bloomberg CO7/CO13 Comdty),
    converted to CZK, m/m -- CNB WP 9/2026's forward-shift technique: "a
    futures contract observed at t for delivery in twelve months serves as
    the market's expectation for the price at t+12", used AS the predictor
    rather than spot. Unlike the paper we don't manually shift the series
    forward -- build_supervised's own h-step alignment (X_t predicts
    y_{t+h}) already does that for any column, so a genuinely
    forward-looking price series just needs to be added as-is and TOP_K
    correlation selection naturally favours the ~13m contract for h=12 and
    the ~7m contract for h=6. Cached CSV (data/bbg_brent_forward_daily.csv,
    pulled once via Bloomberg) rather than live -- no BBG access at
    inference time in this environment."""
    df = pd.read_csv(_BRENT_FORWARD_CSV, index_col=0)
    df.index = pd.PeriodIndex(pd.to_datetime(df.index), freq="M")
    monthly = df.groupby(level=0).mean()
    fx = load_fx_monthly_levels()["USD"]
    czk = monthly.multiply(fx, axis=0).dropna()
    return pd.DataFrame({
        "brent_fwd7m_czk_mm": 100 * czk["CO7 Comdty"].pct_change(),
        "brent_fwd13m_czk_mm": 100 * czk["CO13 Comdty"].pct_change(),
    })


_IP_SA_CSV = Path(__file__).parent / "cz_ip_sa_level.csv"


def load_ip_sa_mm() -> pd.Series:
    """Industrial production, total, CZSO's OWN seasonally + calendar
    adjusted series (PRU01C) -- not re-derived, CZSO does this at the
    source. 2000-01 onward, 15 years deeper than the YoY-only series
    (czso.ip_ri) this project had been using for ip_yoy."""
    df = pd.read_csv(_IP_SA_CSV)
    idx = pd.PeriodIndex(df["ym"], freq="M")
    s = pd.Series(df["Hodnota"].values, index=idx, name="ip_level").sort_index()
    return (100 * s.pct_change()).rename("ip_sa_mm")


_PPI_LEVEL_CSV = Path(__file__).parent / "cz_ppi_level_raw.csv"
_X13_PATH = os.environ.get("CZ_X13_PATH", str(Path.home() / "x13as" / "x13as" / "x13as.exe"))


def load_ppi_sa_mm() -> pd.Series:
    """PPI total, X-13ARIMA-SEATS seasonally adjusted, m/m -- CNB WP 9/2026
    seasonally adjusts every predictor before use (Section 4.1); this
    project picked transforms by intuition instead. PPI is the first
    candidate: genuinely NSA at the source (unlike the EC survey indices
    already SA'd by Eurostat before we ever see them), and our
    heaviest-used predictor across every horizon. Needs the genuine level
    index (data/cz_ppi_level_raw.csv, data/pull_cz_ppi_level.py) -- X-13
    does its own internal differencing and errors on an already-differenced
    (and thus sign-changing) series."""
    from statsmodels.tsa.x13 import x13_arima_analysis
    df = pd.read_csv(_PPI_LEVEL_CSV)
    monthly = df[df["code"].str.match(r"^\d{4}-\d{2}$")].drop_duplicates(subset="code")
    idx = pd.PeriodIndex(monthly["code"], freq="M").to_timestamp()
    s = pd.Series(monthly["Hodnota"].values, index=idx, name="ppi_level").sort_index()
    sa = x13_arima_analysis(s, x12path=_X13_PATH, prefer_x13=True).seasadj
    sa.index = pd.PeriodIndex(sa.index, freq="M")
    return (100 * sa.pct_change()).rename("ppi_sa_mm")


# ---------------------------------------------------------------------------
# Assembled panel
# ---------------------------------------------------------------------------
def fetch_eru_ipnc_mm_live() -> pd.DataFrame:
    """ERU's 'Indicative price band' (IPNC) for new fixed-rate electricity
    and gas offers -- eru.gov.cz/ipnc, two flat CSVs updated monthly.
    Verified 2026-08-22 (direct curl, independent of both WebFetch and the
    research agent that first flagged this source): file's own
    Last-Modified header (24 Jul 2026) predates the already-present
    2026-08 row, i.e. ERU pre-publishes each month's band ~1 week BEFORE
    that month starts -- a genuinely LEADING indicator, not lagging or
    even just contemporaneous. Only a 10-month rolling window is kept
    server-side (2025-11 on, as of this check), not a deep archive.

    Important scope note: this prices NEW offers (the unregulated/
    commercial component only), not the blended average across the whole
    customer base -- including households still on older fixed contracts
    -- that CPI actually measures. Treat as a leading regressor for the
    model to learn a lag/pass-through relationship from, NOT a direct
    measured pass-through the way fuel_mm_from_weekly is."""
    cols = ["month", "tariff_or_zone", "fixation_months", "lo_ex_vat", "hi_ex_vat", "lo_inc_vat", "hi_inc_vat"]
    out = {}
    for name, url in [("electricity", "https://eru.gov.cz/sites/default/files/obsah/prilohy/elektrina_2.csv"),
                      ("gas", "https://eru.gov.cz/sites/default/files/obsah/prilohy/plyn_1.csv")]:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        import io
        df = pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig")
        df.columns = cols
        df["period"] = pd.PeriodIndex(pd.to_datetime(df["month"]), freq="M")
        # simple mean across all tariff/zone x fixation-length rows per
        # month -- no data exists on which combination is actually most
        # common among real customers, so an unweighted average is the
        # honest choice rather than a spuriously precise one.
        midpoint = df.groupby("period").apply(lambda g: (g["lo_inc_vat"] + g["hi_inc_vat"]).mean() / 2,
                                               include_groups=False)
        out[name] = 100 * midpoint.sort_index().pct_change()
    return pd.DataFrame({"eru_electricity_ipnc_mm": out["electricity"],
                         "eru_gas_ipnc_mm": out["gas"]})


def fetch_szif_milk_price_live() -> dict:
    """SZIF's weekly dairy price bulletin (szif.gov.cz/cs/cenovy-servis,
    'Mleko - hlaseni od prvnich kupujicich') -- a legally mandated report
    under EU Reg. 2019/1746, not a discretionary release. Verified
    2026-08-22: bulletin for the 10-16 Aug 2026 reference week was
    published 18 Aug 2026 -- a genuine ~2-day lag, direct food-CPI analog
    to the existing fuel weekly-price mechanism.

    LIVE-ONLY for now: the page only surfaces a link to the CURRENT
    bulletin, keyed by an opaque CMS document id, not a predictable
    date-based URL like ERU's or OTE's -- no historical archive found yet,
    so this cannot backfill a time series without more discovery work.
    Returns a single reading (composite mean across all non-suppressed
    items in the bulletin, Kc/kg) plus the reference period it covers."""
    import pdfplumber, io, re

    page = requests.get("https://szif.gov.cz/cs/cenovy-servis", headers=UA, timeout=30)
    page.raise_for_status()
    m = re.search(r'href="(/cs/CmDocument\?rid=%2Fapa_anon%2Fcs%2Fzpravy%2Ftis%2Fcenovy_servis%2F01%2F[^"]+\.pdf)"',
                  page.text)
    if not m:
        raise RuntimeError("SZIF milk bulletin link (folder 01) not found on cenovy-servis page -- site layout may have changed")
    pdf_url = "https://szif.gov.cz" + m.group(1).replace("&amp;", "&")

    r = requests.get(pdf_url, headers=UA, timeout=30)
    r.raise_for_status()
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = pdf.pages[0].extract_text()
        table = pdf.pages[0].extract_tables()[0]

    period_m = re.search(r'Obdob[ií]:\s*(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}\.\d{2}\.\d{4})', text)
    period_start, period_end = period_m.groups() if period_m else (None, None)
    prices = []
    for row in table[1:]:
        # pdfplumber splits this table into 4 grid columns from the visual
        # borders; the price itself is column index 1, not the last column
        # (verified against the actual extracted row structure, not assumed).
        val = (row[1] or "").replace(",", ".").strip()
        try:
            prices.append(float(val))
        except ValueError:
            continue  # '-' = suppressed for data protection, or a header/blank row
    return {"period_start": period_start, "period_end": period_end,
            "composite_mean_czk_kg": sum(prices) / len(prices) if prices else None,
            "n_items": len(prices)}


def fetch_ote_electricity_spot_daily_live(start: str = "2025-10-01") -> pd.Series:
    """OTE day-ahead electricity spot market BASE LOAD index (EUR/MWh),
    ote-cr.cz -- genuinely day-ahead: auction for delivery day D closes
    12:00 on D-1, so a value for day D is known the day before. Verified
    2026-08-22 (direct curl + pandas, real file content, not a description):
    daily XLSX at a predictable URL, magic-byte confirmed valid, real
    BASE/PEAK/OFFPEAK indices extracted successfully.

    Only a rolling window is kept server-side, not a deep archive --
    confirmed 2025-10-01 resolves, 2025-09-01 does not (as of this check).
    `start` defaults to that confirmed boundary; pulling this loops one
    HTTP request per calendar day in [start, today], so keep the window
    reasonable rather than guessing further back and eating 404s."""
    import io
    dates = pd.date_range(start, pd.Timestamp.today(), freq="D")
    vals = {}
    for d in dates:
        url = (f"https://www.ote-cr.cz/pubweb/attachments/01/{d.year}/month{d.month:02d}/"
              f"day{d.day:02d}/DT_15MIN_{d.day:02d}_{d.month:02d}_{d.year}_CZ.xlsx")
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code != 200 or not r.content.startswith(b"PK"):
            continue  # not yet published (future/weekend gap) or off the rolling window
        try:
            df = pd.read_excel(io.BytesIO(r.content), sheet_name=0, header=None, nrows=8)
            base_row = df[df[0].astype(str).str.contains("BASE LOAD", na=False)]
            if len(base_row):
                vals[d] = float(base_row.iloc[0, 1])
        except Exception:
            continue
    return pd.Series(vals, name="ote_base_eur_mwh").sort_index()


def load_all() -> tuple[pd.Series, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (y, X, comp, weekly) — same shape run_nowcast.main() expects."""
    y = load_headline_cpi_mm()
    comp = load_component_targets()

    ppi = load_ppi_yoy()
    esi = load_esi()
    expect = load_inflation_expectations(12)
    expect_36m = load_inflation_expectations(36)
    fx = load_fx_monthly_mm()
    de_food = fetch_de_food_hicp_live()
    brent_czk_mm = fetch_brent_czk_mm_live()
    rushin = fetch_rushin_monthly_live()
    ppi_deep = fetch_ppi_industry_yoy_deep_live()
    activity = load_real_activity()
    confidence = load_confidence_ri()
    financial = load_financial()
    de_macro = fetch_de_macro_live()
    household_expect = fetch_household_price_expectations_live()
    breadth = load_cpi_breadth()
    median_cpi = load_median_cpi_mm()
    pl_retail = load_pl_retail_confidence()
    wage_mm = load_wage_mm_chowlin()
    admin_core = load_admin_core_split()
    credit = load_credit_aggregates()
    import_prices = fetch_import_prices_mm_live()
    trade_balance = load_trade_balance()
    brent_fwd = load_brent_forward_mm()
    cnb_core = fetch_cnb_core_inflation_mm_live()
    cnb_regulated = fetch_cnb_regulated_prices_mm_live()

    X = pd.concat([
        ppi,
        esi,
        expect,
        expect_36m,
        fx,
        de_food,
        brent_czk_mm,
        brent_czk_mm.shift(1).rename("brent_czk_mm_l1"),
        rushin,
        ppi_deep,
        activity,
        confidence,
        financial,
        de_macro,
        household_expect,
        breadth,
        median_cpi,
        pl_retail,
        wage_mm,
        admin_core,
        credit,
        import_prices,
        trade_balance,
        brent_fwd,
        cnb_core,
        cnb_regulated,
    ], axis=1).sort_index()
    # pd.concat(axis=1) on series of different length/span does not guarantee
    # a monotonic result index — and X.loc[:origin] in the backtest silently
    # returns wrong (future-leaking) rows on a non-monotonic index instead of
    # raising, so this sort is load-bearing, not cosmetic.

    weekly = fetch_weekly_fuels_live()
    return y.sort_index(), X, comp.sort_index(), weekly


def fetch_cnb_daily_eur_fixings(year: int) -> pd.Series:
    """CNB daily EUR/CZK fixings for one calendar year, from the bank's own
    year file (pipe-delimited, decimal comma, dd.mm.yyyy; header names the
    columns, e.g. '1 EUR'). Used for the month-to-date FX feature of a month
    the monthly-average table does not yet carry (TIMING_SPEC_v25 T6). The
    monthly table remains the source for complete months, so the backtest
    is untouched."""
    r = requests.get("https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/"
                     "kurzy-devizoveho-trhu/rok.txt", params={"rok": int(year)},
                     headers=UA, timeout=30)
    r.raise_for_status()
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    cols = lines[0].split("|")
    i = cols.index("1 EUR")
    dates, vals = [], []
    for ln in lines[1:]:
        parts = ln.split("|")
        if len(parts) <= i:
            continue
        dates.append(pd.to_datetime(parts[0], format="%d.%m.%Y"))
        vals.append(float(parts[i].replace(",", ".")))
    return pd.Series(vals, index=pd.DatetimeIndex(dates), name="eurczk_fixing").sort_index()
