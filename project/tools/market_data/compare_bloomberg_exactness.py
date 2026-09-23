"""Exact-equality tests between Bloomberg series and the series the Czech CPI models read today.

  python tools/market_data/compare_bloomberg_exactness.py --output output/bloomberg_probe_comparison_20260912/exactness

Uses every data/market_snapshots/20260912_bloomberg_probe* folder (a later round overrides an earlier one for the same
ticker) and the 11 Sep wide daily snapshot for the commodity and CNB-paper candidate tickers. Each test runs on the
transform the model uses (published rate, level, monthly mean, month-end value, log change).

Verdicts:
  exact              every overlapping observation equal (gap <= 1e-6, or the stated exact tolerance)
  extremely similar  at least 90% of observations equal once the reference is rounded to the decimals Bloomberg
                     publishes and no gap above 1.5 units of that decimal; or, where no published precision applies,
                     at least 95% of observations within the stated tolerance and none above five tolerances
  similar            correlation of the model transform at least 0.98
  different          anything else
Nothing here changes a model input.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_bloomberg_probe as cmp  # noqa: E402

ROOT = cmp.ROOT
DB_PATH = Path(os.environ.get("CZ_CPI_DB", Path.home() / "economic_db" / "czechia.duckdb"))
SNAPSHOTS = ROOT / "data/market_snapshots"
WIDE_DAILY = SNAPSHOTS / "20260911_bloomberg_full_refresh/daily.csv"
LEVEL_TICKERS = {"0": "CZCPI Index", "01": "CZCPF Index", "02": "CZCPA Index", "03": "CZCPC Index", "04": "CZCPH Index",
                 "05": "CZCPN Index", "06": "CZCPHE Index", "07": "CZCPTR Index", "08": "CZCPP Index", "09": "CZCPR Index",
                 "10": "CZCPE Index", "11": "CZCPSH Index", "12": "CZCP12 Index", "13": "CZCP13 Index"}
ROWS: list[dict] = []


def load_raw() -> dict[str, pd.Series]:
    raw: dict[str, pd.Series] = {}
    wide = pd.read_csv(WIDE_DAILY, parse_dates=["observation_date"]).set_index("observation_date")
    for column in wide.columns:
        s = wide[column].dropna().sort_index()
        if len(s):
            raw[column] = s
    folders = sorted(SNAPSHOTS.glob("20260912_bloomberg_probe*"), key=lambda p: int(re.sub(r"\D", "", p.name.split("probe")[-1]) or 1))
    for folder in folders:
        if (folder / "history_long.csv").exists():
            for ticker, g in pd.read_csv(folder / "history_long.csv", parse_dates=["observation_date"]).groupby("ticker"):
                s = pd.Series(g.value.to_numpy(float), index=pd.DatetimeIndex(g.observation_date)).sort_index()
                raw[ticker] = s[~s.index.duplicated(keep="last")]
    return raw


def month_last(s):
    return None if s is None else s.groupby(s.index.to_period("M")).last()


def month_mean(s):
    return None if s is None else s.groupby(s.index.to_period("M")).mean()


def quarter_last(s):
    return None if s is None else s.groupby(s.index.to_period("Q")).last()


def pct(s, k=1):
    return None if s is None else 100.0 * (s / s.shift(k) - 1.0)


def dlog(s):
    return None if s is None else 100.0 * np.log(s).diff()


def assess(area, model_use, reference, ticker, transform, bbg, ref, *, decimals=None, tol=None, exact_tol=1e-6, note=""):
    base = dict(area=area, model_use=model_use, reference=reference, ticker=ticker, transform=transform)
    if bbg is None or ref is None or bbg.dropna().empty or ref.dropna().empty:
        ROWS.append(dict(base, n=0, verdict="not testable", note=note or "series unavailable"))
        return
    j = pd.concat([bbg.rename("b"), ref.rename("r")], axis=1, sort=True).dropna()
    if len(j) < 8:
        ROWS.append(dict(base, n=len(j), verdict="not testable", note=note or "fewer than 8 overlapping observations"))
        return
    gap = (j.b - j.r).abs()
    exact = gap <= exact_tol
    years = np.asarray(j.index.year)
    windows = {}
    for label, start in (("2000on", 2000), ("2015on", 2015)):
        mask = years >= start
        windows[f"exact_share_{label}"] = round(float(exact[mask].mean()), 4) if mask.any() else np.nan
        windows[f"max_abs_gap_{label}"] = float(gap[mask].max()) if mask.any() else np.nan
    rounded = (j.b - j.r.round(decimals)).abs() <= exact_tol if decimals is not None else None
    within = gap <= tol + 1e-12 if tol is not None else None
    corr = float(j.corr().iloc[0, 1]) if j.b.std() > 0 and j.r.std() > 0 else np.nan
    if exact.all():
        verdict = "exact"
    elif decimals is not None and rounded.mean() >= 0.90 and gap.max() <= 1.5 * 10.0 ** -decimals + 1e-9:
        verdict = "extremely similar"
    elif tol is not None and within.mean() >= 0.95 and gap.max() <= 5 * tol + 1e-12:
        verdict = "extremely similar"
    elif np.isfinite(corr) and corr >= 0.98:
        verdict = "similar"
    else:
        verdict = "different"
    largest = gap.loc[~exact].sort_values(ascending=False).index[:3]
    ROWS.append(dict(base, first=str(j.index.min())[:10], last=str(j.index.max())[:10], n=len(j),
                     exact_share=round(float(exact.mean()), 4),
                     equal_after_rounding=round(float(rounded.mean()), 4) if rounded is not None else np.nan,
                     within_tol=round(float(within.mean()), 4) if within is not None else np.nan, tol=tol,
                     mean_abs_gap=float(gap.mean()), max_abs_gap=float(gap.max()),
                     corr=round(corr, 4) if np.isfinite(corr) else np.nan, **windows, verdict=verdict,
                     largest_gaps="; ".join(f"{str(i)[:10]}: {j.b[i]:.6g} vs {j.r[i]:.6g}" for i in largest), note=note))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")
    raw = load_raw()
    m = lambda t: month_last(raw.get(t))  # noqa: E731
    con = duckdb.connect(str(DB_PATH), read_only=True)
    q = lambda sql: con.sql(sql).df()  # noqa: E731
    fx = cmp.fixture
    features = pd.read_csv(cmp.FIX / "core_features.csv", index_col=0)
    features.index = pd.PeriodIndex(features.index, freq="M")

    # --- CPI, import and producer prices --------------------------------------------------------------------------
    A = "CPI and prices"
    assess(A, "nowcast, bridge, R14B: CNB core m/m", "fixture cnb_core_mm (ARAD SCPIMZM09MOMPECNA)", "CZCIXM Index",
           "published m/m", m("CZCIXM Index"), fx("cnb_core_mm.csv"), decimals=1)
    assess(A, "nowcast, bridge, R14B: CNB regulated m/m", "fixture cnb_regulated_mm (ARAD SCPIMZM02MOMPECNA)", "CZCIRM Index",
           "published m/m", m("CZCIRM Index"), fx("cnb_regulated_mm.csv"), decimals=1)
    headline = fx("target_headline_cpi_mm.csv")
    for ticker in ("CZCIPM Index", "CZCPMOM Index"):
        assess(A, "nowcast target, bridge, paths: headline m/m", "fixture target_headline_cpi_mm (m/m of CZSO 2015=100 index)",
               ticker, "published m/m", m(ticker), headline, decimals=1)
    assess(A, "nowcast, bridge: food (01) m/m", "fixture component_food_fuel_mm.food (CZSO)", "CZCPFMOM Index", "published m/m",
           m("CZCPFMOM Index"), fx("component_food_fuel_mm.csv", "food"), decimals=1)
    assess(A, "nowcast, bridge: alcohol and tobacco (02) m/m", "fixture alcohol_tobacco (CZSO)", "CZCPAMOM Index", "published m/m",
           m("CZCPAMOM Index"), fx("alcohol_tobacco.csv"), decimals=1)
    assess(A, "nowcast, bridge: fuel item (07.22) m/m", "fixture component_food_fuel_mm.fuel (CZSO)", "CP7FCZ Index",
           "HICP fuels, m/m from level", pct(m("CP7FCZ Index")), fx("component_food_fuel_mm.csv", "fuel"), tol=0.1)
    cpi = q("SELECT date, coicop_code, base, value FROM cpi_czso.cpi_long WHERE subgroup_code='' AND hh_group_code='0'")
    cpi["m"] = pd.PeriodIndex(pd.to_datetime(cpi.date), freq="M")
    czso = {(c, b): g.set_index("m").value.sort_index() for (c, b), g in cpi.groupby(["coicop_code", "base"])}
    assess(A, "headline y/y", "CZSO published y/y (cpi_czso.cpi_long yoy_pct minus 100)", "CZCPYOY Index", "published y/y",
           m("CZCPYOY Index"), czso[("0", "yoy_pct")] - 100.0, decimals=1)
    for code, ticker in LEVEL_TICKERS.items():
        assess(A, f"CZSO CPI index level, COICOP {code}", "CZSO 2025=100 index (cpi_czso.cpi_long)", ticker, "level",
               m(ticker), czso[(code, "base_2025_eq_100")], decimals=1)
    groups = pd.read_csv(ROOT / "data/core_split/monthly_levels.csv", dtype={"target_month": str})
    groups.index = pd.PeriodIndex(groups.pop("target_month"), freq="M")
    for ticker, column in (("CP41CZ Index", "actual_rent"), ("CP1SCZ Index", "catering"), ("CP96CZ Index", "package_holidays"),
                           ("CP1ACZ Index", "accommodation")):
        assess(A, f"R10 category model: {column} m/m", "m/m of CZSO group level (data/core_split)", ticker, "HICP, m/m from level",
               pct(m(ticker)), pct(groups[column]), tol=0.1)
    imports = features.import_l2.copy()
    imports.index = imports.index - 2
    assess(A, "nowcast import_l2", "fixture import_l2 shifted back 2 months (CZSO CEN0301)", "CZEIIMOM Index", "published m/m",
           m("CZEIIMOM Index"), imports, decimals=1)
    sitc = pd.read_csv(ROOT / "data/czso_import_prices_sitc_monthly.csv")
    sitc = pd.Series(sitc.value.to_numpy(float), index=pd.PeriodIndex(sitc.month, freq="M"))
    assess(A, "path_live E7 import prices m/m", "CZSO CEN0303 (data/czso_import_prices_sitc_monthly.csv)", "CZEIIMOM Index",
           "published m/m", m("CZEIIMOM Index"), sitc, decimals=1)
    ref, src = cmp.a6_row(26, "cnb_arad")
    assess(A, "CNB paper row 26 import prices", f"{src} minus 100", "CZEIIMOM Index", "published m/m", m("CZEIIMOM Index"),
           ref - 100.0, decimals=1)
    assess(A, "food block: food-products PPI m/m", "m/m of CZSO CEN0201B index (data/cz_ppi_product_raw.csv)", "CZPPA10M Index",
           "published m/m", m("CZPPA10M Index"), cmp.food_ppi_mm(), decimals=1)
    ref, src = cmp.a6_row(44)
    assess(A, "CNB paper row 44 PPI y/y", src, "EUPPCZY Index", "published y/y", m("EUPPCZY Index"), ref, decimals=1)
    ref45, src45 = cmp.a6_row(45)
    assess(A, "CNB paper row 45 domestic PPI", f"m/m of {src45}", "EUPPCZM Index", "published m/m", m("EUPPCZM Index"), pct(ref45), decimals=1)
    for number, mm_ticker, level_ticker in ((45, "CZPPMOM Index", "PPTXCZ Index"), (46, "CZPPBM Index", "EPP00BCZ Index"),
                                            (47, "CZPPCM Index", None), (48, "CZPPDM Index", "EPP00DCZ Index"),
                                            (49, "CZPPEM Index", "EPP036CZ Index")):
        ref, src = cmp.a6_row(number)
        assess(A, f"CNB paper row {number} domestic PPI", f"m/m of {src}", mm_ticker, "CZSO published m/m", m(mm_ticker), pct(ref), decimals=1)
        if level_ticker:
            assess(A, f"CNB paper row {number} domestic PPI", src, level_ticker, "index level", m(level_ticker), ref, decimals=1)
            assess(A, f"CNB paper row {number} domestic PPI", f"m/m of {src}", level_ticker, "m/m from level", pct(m(level_ticker)),
                   pct(ref), tol=0.1)

    # --- surveys and labour -------------------------------------------------------------------------------------------
    S = "Surveys and labour"
    assess(S, "nowcast household_exp", "fixture core_features.household_exp (Eurostat BS-PT-NY)", "EUA8CZ Index", "level",
           m("EUA8CZ Index"), features.household_exp, decimals=1)
    for number, ticker in ((72, "EUA8CZ Index"), (71, "EUA7CZ Index")):
        ref, src = cmp.a6_row(number)
        assess(S, f"CNB paper row {number}", src, ticker, "level", m(ticker), ref, decimals=1)
    esi = q("SELECT year, month, value FROM eurostat.bcs_survey WHERE indic_code='BS-ESI-I'")
    esi = pd.Series(esi.value.to_numpy(float), index=pd.PeriodIndex(pd.to_datetime(dict(year=esi.year, month=esi.month, day=1)), freq="M"))
    esi = esi[~esi.index.duplicated(keep="last")].sort_index()
    assess(S, "nowcast esi (frozen fixture)", "fixture core_features.esi", "EUESCZ Index", "level", m("EUESCZ Index"), features.esi, decimals=1)
    assess(S, "path drivers esi (live database)", "eurostat.bcs_survey BS-ESI-I (czechia.duckdb)", "EUESCZ Index", "level",
           m("EUESCZ Index"), esi, decimals=1)
    ecfin = pd.read_csv(ROOT / "data/paper_replication/official_bcs_ecfin_2608/ecfin_bcs_long.csv", low_memory=False)
    ecfin = ecfin[ecfin.series_code.eq("CZ.ESI")]
    ecfin = pd.Series(ecfin.value.to_numpy(float), index=pd.PeriodIndex(ecfin.period, freq="M")).sort_index()
    assess(S, "survey nowcasts, path drivers: esi", "ECFIN official CZ.ESI, August 2026 download (official_bcs_ecfin_2608)",
           "EUESCZ Index", "level", m("EUESCZ Index"), ecfin[~ecfin.index.duplicated(keep="last")], decimals=1)
    # CNB-paper survey rows validated as Bloomberg mirrors on 12 Sep, plus German unemployment and HICP, tested against the
    # exact inputs the paper model reads; the note counts model months that the Bloomberg history does not cover.
    verdicts = pd.read_csv(ROOT / "output/cnb_paper_candidate_validation_20260912/bcs_candidate_verdicts.csv")
    paper_rows = [(int(r.a6_numbers), r.ticker) for r in verdicts.itertuples() if pd.notna(r.a6_numbers) and r.verdict == "identical_SA"]
    for number, ticker in paper_rows + [(24, "UMRTDE Index"), (23, "GRCPHCPI Index")]:
        ref, src = cmp.a6_row(number)
        bbg = m(ticker)
        note = ""
        if bbg is not None and len(ref):
            missing = ref.index.difference(bbg.dropna().index)
            note = f"model months not on Bloomberg: {len(missing)}" + (f" ({missing.min()}..{missing.max()})" if len(missing) else "")
        assess(S, f"CNB paper row {number}", src, ticker, "level", bbg, ref, decimals=1, note=note)
    ref, src = cmp.a6_row(11)
    assess(S, "CNB paper row 11 unemployment", src, "UMRTCZ Index", "level", m("UMRTCZ Index"), ref, decimals=1)
    un = q("SELECT data_month, rate_pct, release_date FROM czso.unemployment_ri WHERE series='unemployment' AND adjusted='trend_cycle' AND gender='total'")
    un = un.sort_values(["data_month", "release_date"]).drop_duplicates("data_month", keep="last")
    un = pd.Series(un.rate_pct.to_numpy(float), index=pd.PeriodIndex(pd.to_datetime(un.data_month), freq="M")).sort_index()
    assess(S, "path lines un_d (monthly change)", "first difference of CZSO 15-64 trend-cycle (czso.unemployment_ri)", "UMRTCZ Index",
           "first difference", m("UMRTCZ Index").diff() if m("UMRTCZ Index") is not None else None, un.diff(), tol=0.05)
    wages = q("SELECT period, nom_yoy_pct, avg_wage_czk FROM czso.wages_headline")
    wages["q"] = pd.PeriodIndex(pd.to_datetime(wages.period), freq="Q")
    wages = wages.drop_duplicates("q", keep="last").set_index("q").sort_index()
    assess(S, "path_live E6 wages y/y", "czso.wages_headline nom_yoy_pct", "CZNWYOY Index", "published y/y (quarter)",
           quarter_last(raw.get("CZNWYOY Index")), wages.nom_yoy_pct, decimals=1)
    assess(S, "wage level", "czso.wages_headline avg_wage_czk", "CZNWWAGE Index", "level (quarter)",
           quarter_last(raw.get("CZNWWAGE Index")), wages.avg_wage_czk, decimals=0)
    lci = pd.read_csv(ROOT / "data/eurostat_lci_cz_quarterly.csv")
    lci = pd.Series(lci.value.to_numpy(float), index=pd.PeriodIndex(lci.quarter, freq="Q"))
    assess(S, "path_step4 labour cost index y/y", "Eurostat lc_lci_r2_q D11 B-S NSA, y/y (data/eurostat_lci_cz_quarterly.csv)",
           "LNTNCZ Index", "y/y from level (4 quarters)", pct(quarter_last(raw.get("LNTNCZ Index")), 4), pct(lci, 4), tol=0.2)
    hpi = q("SELECT quarter_end, value FROM czso.hpi WHERE category='old_apts' AND region='cr_total' AND index_type='yoy_pct'")
    hpi = pd.Series(hpi.value.to_numpy(float), index=pd.PeriodIndex(pd.to_datetime(hpi.quarter_end), freq="Q"))
    hpi = hpi[~hpi.index.duplicated(keep="last")].sort_index()
    if hpi.median() > 50:
        hpi = hpi - 100.0
    assess(S, "housing channel hpi_yoy", "CZSO prices of old apartments, CR total, y/y (czso.hpi)", "HOPICZI Index",
           "y/y from level (4 quarters)", pct(quarter_last(raw.get("HOPICZI Index")), 4), hpi, tol=0.5)

    # --- money, rates, FX, commodities ---------------------------------------------------------------------------------
    M = "Money, rates, FX, commodities"
    arad = q("SELECT indicator_id, period, value, snapshot_id FROM monetary.arad_data")
    arad = arad.sort_values(["indicator_id", "period", "snapshot_id"]).drop_duplicates(["indicator_id", "period"], keep="last")

    def arad_series(code):
        g = arad[arad.indicator_id.eq(code)]
        return pd.Series(g.value.to_numpy(float), index=pd.PeriodIndex(pd.to_datetime(g.period), freq="M")).sort_index()

    m3 = arad_series("SMV5M108")
    assess(M, "slow block m3_yoy", "y/y of ARAD SMV5M108", "CZMSM3Y Index", "published y/y", m("CZMSM3Y Index"), pct(m3, 12), decimals=1)
    assess(M, "slow block m3_yoy", "y/y of ARAD SMV5M108", "CZMSM3 Index", "y/y from level", pct(m("CZMSM3 Index"), 12), pct(m3, 12), tol=0.05)
    prib = raw.get("PRIB03M Index")
    assess(M, "path_live, gap model: 3M PRIBOR monthly average", "ARAD SFTP04M2206 (monetary.arad_data)", "PRIB03M Index",
           "monthly mean of daily", month_mean(prib), arad_series("SFTP04M2206"), decimals=2)
    for number, ticker, how in ((54, "PRIB03M Index", "last"), (55, "CZBRREPO Index", "last"), (53, "GTCZK10Y Govt", "mean")):
        ref, src = cmp.a6_row(number)
        series = month_last(raw.get(ticker)) if how == "last" else month_mean(raw.get(ticker))
        assess(M, f"CNB paper row {number}", src, ticker, "last value of the month" if how == "last" else "monthly mean of daily",
               series, ref, decimals=2)
    cnb_fx = pd.read_csv(ROOT / "data/research_r14/fuel/fx_daily.csv", parse_dates=["date"]).set_index("date")
    recent = pd.read_csv(ROOT / "data/cnb_daily_eur_fixings_20260912/eurczk_daily.csv", parse_dates=["date"]).set_index("date").eurczk
    cnb_eur = pd.concat([cnb_fx.eurczk.dropna(), recent.dropna()]).groupby(level=0).last()
    fxm = q("SELECT year, month, czk_per_unit FROM monetary.fx_monthly WHERE currency_code='EUR'")
    fxm = pd.Series(fxm.czk_per_unit.to_numpy(float), index=pd.PeriodIndex(pd.to_datetime(dict(year=fxm.year, month=fxm.month, day=1)), freq="M"))
    fxm = fxm[~fxm.index.duplicated(keep="last")].sort_index()
    # The CNB publishes the monthly average to three decimals. The frozen path input `eurczk` equals monetary.fx_monthly and
    # the nowcast fixture eurczk_mm equals its m/m (both checked 12 Sep 2026: 100% identical).
    monthly_average = lambda s: None if s is None else month_mean(s).round(3)  # noqa: E731
    for ticker in ("EURCZK CNB Curncy", "EURCZKF Curncy", "EURCZK F143 Curncy", "EURCZK BFIX Curncy", "EURCZK Curncy"):
        b = raw.get(ticker)
        assess(M, "weekly lane, R14 fuel: CNB EUR/CZK fixing (daily)", "CNB daily fixing (R14 fx_daily + 2018+ capture)", ticker,
               "daily level, CZK", b, cnb_eur, decimals=3, tol=0.005)
        assess(M, "independent path eurczk, path drivers: CNB monthly average", "monetary.fx_monthly EUR (= frozen path eurczk)",
               ticker, "monthly mean rounded to 3 dp", monthly_average(b), fxm, decimals=3, tol=0.001)
        assess(M, "nowcast eurczk_mm, path fx_mm: m/m of the monthly average", "fixture core_features.eurczk_mm (= m/m of monetary.fx_monthly)",
               ticker, "m/m of monthly mean rounded to 3 dp", pct(monthly_average(b)), features.eurczk_mm, tol=0.01)
    fixing = raw.get("EURCZK CNB Curncy")
    if fixing is not None:
        by_year = []
        for label, frame in (("daily fixing", pd.concat([fixing.rename("b"), cnb_eur.rename("r")], axis=1, sort=True).dropna()),
                             ("monthly average, 3 dp", pd.concat([monthly_average(fixing).rename("b"), fxm.rename("r")], axis=1, sort=True).dropna())):
            gap = (frame.b - frame.r).abs()
            table = gap.groupby(np.asarray(frame.index.year)).agg(n="size", exact_share=lambda x: round(float((x <= 1e-6).mean()), 4),
                                                                  max_abs_gap="max")
            by_year.append(table.assign(series=label).reset_index(names="year"))
        pd.concat(by_year).to_csv(out / "eurczk_cnb_fixing_by_year.csv", index=False)
    for ticker in ("USDCZK CNB Curncy", "USDCZKF Curncy", "USDCZK F143 Curncy", "USDCZK BFIX Curncy", "USDCZK Curncy"):
        assess(M, "R14 fuel: CNB USD/CZK fixing (daily)", "CNB daily USD fixing (R14 fx_daily)", ticker, "daily level, CZK",
               raw.get(ticker), cnb_fx.usdczk.dropna(), decimals=3, tol=0.005)
    eia = pd.read_csv(ROOT / "data/research_r14/fuel/brent_daily.csv", parse_dates=["date"]).set_index("date").brent_usd
    co1 = raw.get("CO1 Comdty")
    assess(M, "R14 fuel Brent (daily)", "EIA Europe Brent spot FOB (data/research_r14/fuel/brent_daily.csv)", "CO1 Comdty",
           "daily level, USD/bbl", co1, eia, tol=0.5)
    assess(M, "R14 fuel Brent (monthly change)", "m/m of EIA monthly mean", "CO1 Comdty", "m/m of monthly mean",
           pct(month_mean(co1)), pct(month_mean(eia)), tol=0.5)
    ref, src = cmp.a6_row(60)
    assess(M, "CNB paper row 60 Brent", src, "CO1 Comdty", "monthly mean, USD/bbl", month_mean(co1), ref, decimals=2, tol=0.05)
    for number, ticker in ((61, "TTFGDAHD BCFV Index"), (62, "BCOMINSP Index"), (63, "BCOMAGSP Index")):
        ref, src = cmp.a6_row(number)
        assess(M, f"CNB paper row {number}", f"log m/m of {src}", ticker, "log m/m of monthly mean", dlog(month_mean(raw.get(ticker))),
               dlog(ref), tol=0.1)
        assess(M, f"CNB paper row {number}", f"log m/m of {src}", ticker, "log m/m of month-end value", dlog(month_last(raw.get(ticker))),
               dlog(ref), tol=0.1)
    for number, ticker in ((58, "LONSCZNF Index"), (59, "CZBLHHTV Index")):
        ref, src = cmp.a6_row(number)
        assess(M, f"CNB paper row {number} loans", f"y/y of {src}", ticker, "y/y from level", pct(m(ticker), 12), pct(ref, 12), tol=0.2)
    ref, src = cmp.a6_row(25)
    b25 = m("CZCMTRBA Index")
    if b25 is not None:
        scale = cmp.power_of_ten(b25, ref)
        assess(M, "CNB paper row 25 trade balance", src, "CZCMTRBA Index", f"level divided by {scale:g}", b25 / scale, ref, tol=500.0)
    for number, ticker in ((57, "OECZFRAA Index"), (57, "935.028 Index"), (56, "935.028 Index")):
        ref, src = cmp.a6_row(number, "cnb_arad")
        assess(M, f"CNB paper row {number} REER", f"log m/m of {src}", ticker, "log m/m", dlog(m(ticker)), dlog(ref), tol=0.1)

    # --- weekly pump prices -----------------------------------------------------------------------------------------------
    F = "Weekly pump prices"
    week = lambda s: s.groupby(s.index.to_period("W-SUN")).last()  # noqa: E731
    pump = pd.read_csv(ROOT / "data/research_r14/fuel/pump_weekly.csv", parse_dates=["date"]).set_index("date")
    czso_weekly = pd.read_csv(cmp.FIX / "fuel_weekly.csv", parse_dates=["date"]).set_index("date")
    for ticker, column, czso_column in (("ECOBETCZ Index", "gross_petrol95", "petrol95"), ("ECOBOTCZ Index", "gross_diesel", "diesel"),
                                        ("ECOBEFCZ Index", "net_petrol95", None), ("ECOBOFCZ Index", "net_diesel", None)):
        b = week(raw[ticker]) / 1000.0
        assess(F, "R14 fuel pump panel", f"EC Oil Bulletin files, {column}", ticker, "ISO week, CZK/l", b, week(pump[column]),
               exact_tol=1e-5, tol=0.01)
        if czso_column:
            assess(F, "nowcast weekly fuel", f"fixture fuel_weekly.{czso_column} (CZSO CENPHMT Monday survey)", ticker,
                   "ISO week, CZK/l", b, week(czso_weekly[czso_column]), tol=0.2)
    con.close()

    table = pd.DataFrame(ROWS)
    table.to_csv(out / "exactness.csv", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 62)
    show = ["area", "model_use", "ticker", "transform", "first", "last", "n", "exact_share", "equal_after_rounding", "within_tol",
            "mean_abs_gap", "max_abs_gap", "corr", "verdict"]
    print(table[show].to_string(index=False, float_format=lambda v: f"{v:.4g}"))
    print("\nverdicts:", table.verdict.value_counts().to_dict())


if __name__ == "__main__":
    main()
