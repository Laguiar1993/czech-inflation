"""Every input of every Czech CPI model against the Bloomberg series held: strict equality, per model and variable.

  python tools/market_data/compare_bloomberg_model_inputs.py --output output/bloomberg_model_inputs_20260913

The strict tests in output/bloomberg_probe_comparison_20260912/exactness/exactness.csv (compare_bloomberg_exactness.py)
are reused as they stand (referenced as X<row>). This tool adds the tests that file lacks (N_*), with the same verdict
rules (compare_bloomberg_exactness.assess):
  - the nowcast's derived columns: core and food lags, state dummy, interactions, services, farm prices, food PPI lag,
    CNB component rates, extended headline and trailing y/y;
  - the CNB daily EUR/CZK fixings behind the live month-to-date FX;
  - the path roster's headline, koruna average and unemployment vintages;
  - path_live's PRIBOR leg, real-rate gaps and REER;
  - CNB paper rows 12-14, 17, 25, 43, 47, 52, 56-57, 59, 65-66 and the paper target;
  - the first prints used for scoring.
It then maps every input of every model to its tests.

Status per model input:
  exact                               a Bloomberg series equals the model's series on every tested observation
  exact where Bloomberg has history   equal wherever both exist, but part of the model history predates the Bloomberg
                                      series held
  not exact                           tested; no Bloomberg series held is equal (closest verdict shown)
  no Bloomberg series held            nothing held measures it
  no data / static / from another model / Bloomberg already   not a separate time series to match

Bloomberg data held = the 11 Sep wide daily snapshot plus the 20260912_bloomberg_probe* folders
(compare_bloomberg_exactness.load_raw). Nothing here changes a model input.
Outputs: new_tests.csv, model_input_inventory.csv, MANIFEST.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_bloomberg_exactness as cbe  # noqa: E402

ROOT = cbe.ROOT
sys.path.insert(0, str(ROOT))
import cz_struct as S  # noqa: E402
from data import local_adapter as la  # noqa: E402
from data.vintages import released_unemployment  # noqa: E402
from path_experiment import lg, pct as pct_from_log  # noqa: E402

EXISTING = ROOT / "output/bloomberg_probe_comparison_20260912/exactness/exactness.csv"
EXISTING_ANCHORS = {0: "CZCIXM Index", 50: "EUESCZ Index", 100: "EURCZK CNB Curncy", 138: "ECOBOFCZ Index"}
FIX = ROOT / "tests/fixtures/cleanup"
PAPER = ROOT / "data/paper_replication"
A6_EXACT = PAPER / "a6_inputs_20260912/exact_inputs_long.csv"
A6_OVERRIDES = PAPER / "a6_exact_overrides_20260912/overrides_long.csv"
A6_CANDIDATES = PAPER / "a6_inputs_20260912/candidate_inputs_long.csv"
A6_PANEL = PAPER / "paper_model_panel_20260912_exact"
A6_AUDIT = ROOT / "output/cnb_paper_a6_audit_20260912/a6_audit.csv"
FIXINGS = ROOT / "data/cnb_daily_eur_fixings_20260912/eurczk_daily.csv"
FROZEN_PATH = ROOT / "output/independent_path_frozen_inputs.csv"
UNEMPLOYMENT = ROOT / "data/vintages/unemployment.csv.gz"
SURVEY = ROOT / "data/czcpmom_survey_history_extended.csv"
VINTAGE_AS_OF = pd.Timestamp("2026-09-13", tz="UTC")
REER_TICKERS = ("BISBCZR Index", "BRERCZ Index", ".REER_CZK G Index", "BREERCZK Index")
RANK = {"exact": 0, "extremely similar": 1, "similar": 2, "different": 3, "not testable": 4}
NEW: dict[str, dict] = {}

# CNB paper A6 rows -> tests (exact panel sources: paper_model_panel_20260912_exact/manifest.json)
A6_REFS = {1: ["X51"], 2: ["X52"], 3: ["X53"], 4: ["X54"], 5: ["X55"], 6: ["X56"], 7: ["X57"], 8: ["X58"], 9: ["X59"],
           10: ["X60"], 11: ["X86"], 12: ["N_a6_12"], 13: ["N_a6_13"], 14: ["N_a6_14"], 15: [], 16: [],
           17: ["N_a6_17"], 18: ["X61"], 19: ["X62"], 20: ["X63"], 21: ["X64"], 22: ["X65"], 23: ["X85"],
           24: ["X84"], 25: ["X129", "N_a6_25_CZTBNAL", "N_a6_25_CZTBAL"], 26: ["X28"], 27: ["X66"], 28: ["X67"],
           29: ["X68"], 30: ["X69"], 31: ["X70"], 32: ["X71"], 33: ["X72"], 34: ["X73"], 35: ["X74"], 36: ["X75"],
           37: ["X76"], 38: ["X77"], 39: ["X78"], 40: ["X79"], 41: ["X80"], 42: ["X81"], 43: ["N_a6_43"],
           44: ["X30"], 45: ["X33", "X34", "X31", "X32"], 46: ["X36", "X37", "X35"],
           47: ["N_a6_47_level", "N_a6_47_mm", "X38"], 48: ["X40", "X41", "X39"], 49: ["X43", "X44", "X42"],
           50: [], 51: [], 52: ["N_a6_52"], 53: ["X97"], 54: ["X95"], 55: ["X96"], 58: ["X127"],
           59: ["X128", "N_a6_59_CZBLHPTV"], 60: ["X120"], 61: ["X121", "X122"], 62: ["X123", "X124"],
           63: ["X125", "X126"], 64: [], 65: ["N_a6_65"], 66: ["N_a6_66"], 67: ["X82"], 68: ["X83"], 69: [], 70: [],
           71: ["X47"], 72: ["X46"]}
A6_NOTES = {15: "CNB LUCI total", 16: "CNB LUCI wages and labour costs component",
            18: "Bloomberg history starts 1985-01; the missing 1980-84 months are before the panel sample (2002-05 on)",
            20: "Bloomberg history starts 1985-01; the missing 1984 months are before the panel sample (2002-05 on)",
            21: "Bloomberg history starts 1985-01; the missing 1980-84 months are before the panel sample (2002-05 on)",
            27: "the panel reads the Eurostat EA20 aggregate; EUA8EMU is the ECFIN euro-area series",
            28: "the panel reads the Eurostat EA20 aggregate; EUA7EMU is the ECFIN euro-area series",
            43: "CZPPAYOY ends 2017-03; equal in most months of 1997-2004, rarely after", 50: "CZSO livestock products; Bloomberg series held cover the total only",
            51: "CZSO crop products; Bloomberg series held cover the total only", 52: "CZPPAMOM ends 2017-03; equal in 2013-14 only",
            56: "Bloomberg REERs held are BIS, Bloomberg and OECD indices, not CNB's", 57: "as row 56",
            64: "first principal component of four CZSO weekly fuel prices (Natural 95, Super Plus 98, diesel, LPG); "
                "Bloomberg series held are EC Oil Bulletin petrol and diesel",
            65: "the model already reads this Bloomberg series", 66: "the model already reads this Bloomberg series",
            69: "CNB financial-market inflation expectations", 70: "CNB financial-market inflation expectations"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(ticker: str) -> str:
    return "".join(ch for ch in ticker.split()[0] if ch.isalnum())


def fixture(name: str, column: str) -> pd.Series:
    frame = pd.read_csv(FIX / name, index_col=0, float_precision="round_trip")
    frame.index = pd.PeriodIndex(frame.index.astype(str), freq="M")
    return frame[column].astype(float)


def lag(s, k):
    return None if s is None else pd.Series(s.to_numpy(dtype=float), index=s.index + k)


def scaled(s, factor):
    return None if s is None else s * factor


def rounded(s, decimals):
    return None if s is None else s.round(decimals)


def product(a, b):
    return None if a is None or b is None else a * b


def dummy_above(yoy, threshold):
    """1 when the y/y rate of the previous month exceeds the threshold (the cz_struct state rule), NaN when unknown."""
    if yoy is None:
        return None
    previous = lag(yoy, 1)
    return (previous > threshold).astype(float).where(previous.notna())


def a6(path: Path, number: int, column: str | None = None) -> pd.Series:
    d = pd.read_csv(path, dtype={"period": str})
    d = d[d.a6_number == number]
    if column is not None:
        d = d[d["column"] == column]
    freq = "Q" if d.period.str.contains("Q").any() else "M"
    s = pd.Series(d.value.to_numpy(dtype=float), index=pd.PeriodIndex(d.period, freq=freq)).sort_index()
    return s[~s.index.duplicated(keep="last")]


def arad(con, code: str) -> pd.Series:
    """Latest snapshot per period, as path_live reads monetary.arad_data."""
    d = con.sql(f"SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='{code}' "
                "ORDER BY period, snapshot_id").df().drop_duplicates("period", keep="last")
    return pd.Series(d.value.astype(float).to_numpy(), index=pd.PeriodIndex(pd.to_datetime(d.period), freq="M")).sort_index()


def best_lag(bbg, ref, lags=(0, 1, 2, 3)):
    """Lag of the Bloomberg series with the highest correlation to the model column, for columns whose lag convention the
    column name does not state exactly."""
    scores = {}
    for k in (lags if bbg is not None else ()):
        j = pd.concat([lag(bbg, k).rename("b"), ref.rename("r")], axis=1, sort=True).dropna()
        if len(j) >= 24 and j.b.std() > 0 and j.r.std() > 0:
            scores[k] = float(j.corr().iloc[0, 1])
    if not scores:
        return 0, bbg
    k = max(scores, key=scores.get)
    return k, lag(bbg, k)


def test(test_id, area, model_use, reference, ticker, transform, bbg, ref, **kw):
    """compare_bloomberg_exactness.assess plus model coverage: observations of the model series with no Bloomberg value,
    and the start of the final run of equal observations."""
    if test_id in NEW:
        raise ValueError(f"duplicate test id {test_id}")
    cbe.ROWS.clear()
    cbe.assess(area, model_use, reference, ticker, transform, bbg, ref, **kw)
    row = dict(test_id=test_id, **cbe.ROWS[-1])
    if bbg is not None and ref is not None and not ref.dropna().empty:
        b, r = bbg.dropna(), ref.dropna()
        missing = r.index.difference(b.index)
        row.update(model_first=str(r.index.min())[:10], model_last=str(r.index.max())[:10], model_obs=len(r),
                   model_obs_without_bloomberg=len(missing),
                   without_bloomberg_span=f"{str(missing.min())[:10]}..{str(missing.max())[:10]}" if len(missing) else "")
        j = pd.concat([b.rename("b"), r.rename("r")], axis=1, sort=True).dropna()
        if len(j):
            bad = np.flatnonzero(((j.b - j.r).abs() > kw.get("exact_tol", 1e-6)).to_numpy())
            run = j.index[bad[-1] + 1:] if len(bad) else j.index
            row.update(exact_since=str(run[0])[:10] if len(run) else "", exact_run_n=len(run))
    NEW[test_id] = row


def run_tests(raw: dict[str, pd.Series]) -> None:
    m = lambda t: cbe.month_last(raw.get(t))  # noqa: E731
    mean = lambda t: cbe.month_mean(raw.get(t))  # noqa: E731
    yoy_czso, yoy_cnb = m("CZCPYOY Index"), m("CZCIPY Index")
    state_czso, state_cnb = dummy_above(yoy_czso, S.STATE_THRESHOLD), dummy_above(yoy_cnb, S.STATE_THRESHOLD)
    fx_mm = cbe.pct(rounded(mean("EURCZK CNB Curncy"), 3))

    # --- nowcast trio, SENTIMENT and bridge: frozen fixture columns ---------------------------------------------------
    A = "nowcast fixture"
    for col, k in (("core_l1", 1), ("core_l2", 2), ("core_l12", 12)):
        test(f"N_{col}", A, f"core ridge {col}", f"tests/fixtures/cleanup core_features.{col}", "CZCIXM Index",
             f"published m/m, lag {k}", lag(m("CZCIXM Index"), k), fixture("core_features.csv", col), decimals=1)
    state = fixture("core_features.csv", "state")
    for test_id, ticker, series, label in (("N_state_czcipy", "CZCIPY Index", state_cnb, "CNB-published"),
                                           ("N_state_czcpyoy", "CZCPYOY Index", state_czso, "CZSO-published")):
        test(test_id, A, "core ridge state; HALF/FULL error states",
             "core_features.state (1 if compounded y/y of the extended headline at t-1 > 4)", ticker,
             f"1 if {label} y/y at t-1 > {S.STATE_THRESHOLD:g}", series, state)
    test("N_eurczk_x_state", A, "core ridge eurczk_mm_x_state", "core_features.eurczk_mm_x_state",
         "EURCZK CNB Curncy; CZCPYOY Index", "m/m of monthly mean (3 dp) x state from published y/y",
         product(fx_mm, state_czso), fixture("core_features.csv", "eurczk_mm_x_state"))
    test("N_import_x_state", A, "core ridge import_l2_x_state", "core_features.import_l2_x_state",
         "CZEIIMOM Index; CZCPYOY Index", "published m/m, lag 2, x state from published y/y",
         product(lag(m("CZEIIMOM Index"), 2), state_czso), fixture("core_features.csv", "import_l2_x_state"))
    services = fixture("core_features.csv", "services_l1")
    k, b = best_lag(m("CPSVCZM Index"), services)
    test("N_services_l1", A, "core ridge services_l1", "core_features.services_l1 (CZSO services m/m)", "CPSVCZM Index",
         f"HICP services m/m, lag {k} (best of lags 0-3)", b, services, decimals=1)
    for col, k in (("food_l1", 1), ("food_l12", 12)):
        test(f"N_{col}", A, f"food block {col}", f"food_block_features.{col} (CZSO COICOP 01 m/m)", "CZCPFMOM Index",
             f"published m/m, lag {k}", lag(m("CZCPFMOM Index"), k), fixture("food_block_features.csv", col), decimals=1)
    test("N_food_cnb", A, "food block target (COICOP 01 m/m)", "component_food_fuel_mm.food (CZSO)", "CZCIBM Index",
         "CNB-published m/m (Bloomberg label: Czech Inflation Food Beverage)", m("CZCIBM Index"),
         fixture("component_food_fuel_mm.csv", "food"), decimals=1)
    test("N_fuel_cnb", A, "fuel block target (07.22 m/m)", "component_food_fuel_mm.fuel (CZSO)", "CZCIFM Index",
         "CNB-published m/m (Bloomberg label: Czech Inflation Fuel MoM)", m("CZCIFM Index"),
         fixture("component_food_fuel_mm.csv", "fuel"), decimals=1)
    for col in ("agri_l0", "agri_l1"):
        ref = fixture("food_block_features.csv", col)
        k, b = best_lag(m("CZPPAMOM Index"), ref)
        test(f"N_{col}", A, f"food block {col}", f"food_block_features.{col} (CZSO farm-price product basket)",
             "CZPPAMOM Index", f"CZSO agricultural PPI m/m, lag {k} (best of lags 0-3)", b, ref, decimals=1)
    food_ppi = fixture("food_block_features.csv", "food_ppi_l1")
    k, b = best_lag(m("CZPPA10M Index"), food_ppi)
    test("N_food_ppi_l1", A, "food block food_ppi_l1", "food_block_features.food_ppi_l1 (CZSO CEN0201B division 10)",
         "CZPPA10M Index", f"published m/m, lag {k} (best of lags 0-3)", b, food_ppi, decimals=1)
    k, b = best_lag(cbe.pct(m("EPT010CZ Index")), food_ppi)
    test("N_food_ppi_l1_eurostat", A, "food block food_ppi_l1", "food_block_features.food_ppi_l1", "EPT010CZ Index",
         f"m/m from level, lag {k} (best of lags 0-3)", b, food_ppi, tol=0.05)
    ext = fixture("headline_extended_and_states.csv", "headline_mm_extended")
    test("N_ext_mm", A, "HALF/FULL error states; path_live trend history",
         "headline_extended_and_states.headline_mm_extended (FRED CZECPIALLMINMEI to 2014, CZSO from 2015)",
         "CZCIPM Index", "published m/m", m("CZCIPM Index"), ext, decimals=1)
    trailing = fixture("headline_extended_and_states.csv", "trailing_yoy_pct")
    for test_id, ticker, series in (("N_trailing_czcipy", "CZCIPY Index", yoy_cnb),
                                    ("N_trailing_czcpyoy", "CZCPYOY Index", yoy_czso)):
        test(test_id, A, "state input: trailing y/y", "headline_extended_and_states.trailing_yoy_pct (compounded m/m)",
             ticker, "published y/y", series, trailing, decimals=1)

    # --- CNB daily fixings behind the live month-to-date EUR/CZK (cz_struct._eurczk_mtd_mm) ---------------------------
    fixings = pd.read_csv(FIXINGS, parse_dates=["date"]).set_index("date").iloc[:, 0].astype(float)
    test("N_cnb_daily_fixings", "live month-to-date FX", "month-to-date EUR/CZK before the monthly average is published",
         "data/cnb_daily_eur_fixings_20260912/eurczk_daily.csv (frozen CNB daily fixings)", "EURCZK CNB Curncy",
         "daily level, CZK", raw.get("EURCZK CNB Curncy"), fixings, decimals=3)

    # --- path roster --------------------------------------------------------------------------------------------------
    B = "path roster"
    frozen = pd.read_csv(FROZEN_PATH, index_col=0, float_precision="round_trip")
    frozen.index = pd.PeriodIndex(frozen.index.astype(str), freq="M")
    for ticker in ("CZCIPM Index", "CZCPMOM Index"):
        test(f"N_path_headline_{slug(ticker)}", B, "headline m/m history",
             "output/independent_path_frozen_inputs.csv headline_mm (FRED to 2014, CZSO from 2015)", ticker,
             "published m/m", m(ticker), frozen["headline_mm"].astype(float), decimals=1)
    test("N_path_eurczk", B, "fx12_l3 (12-month change of the monthly average, lag 3)",
         "independent_path_frozen_inputs.csv eurczk (CNB monthly average)", "EURCZK CNB Curncy",
         "monthly mean rounded to 3 dp", rounded(mean("EURCZK CNB Curncy"), 3), frozen["eurczk"].astype(float), decimals=3)
    vintages = pd.read_csv(UNEMPLOYMENT, dtype={"reference_period": str})
    adjusted = vintages[vintages.series.isin(["unemployment_sa", "unemployment_trend_cycle"])]
    adjusted = adjusted.assign(_t=pd.to_datetime(adjusted.available_from, utc=True)).sort_values(["reference_period", "_t"])
    first = adjusted.drop_duplicates("reference_period", keep="first")
    first = pd.Series(first.value.to_numpy(dtype=float), index=pd.PeriodIndex(first.reference_period, freq="M"))
    latest = released_unemployment(VINTAGE_AS_OF, UNEMPLOYMENT)
    umrtcz = m("UMRTCZ Index")
    use = "un_d (unemployment change, lag 1) in TARGET_U_FX_ML, BVAR_U_FX, RF_U_FX"
    test("N_u_latest", B, use, f"data/vintages released_unemployment as of {VINTAGE_AS_OF.date()} (CZSO 15-64, published adjusted)",
         "UMRTCZ Index", "level", umrtcz, latest, decimals=1)
    test("N_u_first", B, use, "first published value of each month (CZSO 15-64, SA or trend-cycle)", "UMRTCZ Index",
         "level (the Bloomberg series held is the current vintage)", umrtcz, first, decimals=1)
    test("N_u_change", B, use, "monthly change of the current vintage", "UMRTCZ Index", "first difference",
         None if umrtcz is None else umrtcz.diff(), latest.diff(), decimals=1)

    # --- path_live ----------------------------------------------------------------------------------------------------
    C = "path_live"
    con = duckdb.connect(str(la.DB_PATH), read_only=True)
    pribor, reer101 = arad(con, "SFTP04M2206"), arad(con, "SREERM101")
    un = con.sql("SELECT data_month, rate_pct FROM czso.unemployment_ri WHERE series='unemployment' "
                 "AND adjusted='trend_cycle' AND gender='total' ORDER BY 1").df()
    con.close()
    un_level = pd.Series(un.rate_pct.astype(float).to_numpy(), index=pd.PeriodIndex(pd.to_datetime(un.data_month), freq="M"))
    un_level = un_level[~un_level.index.duplicated(keep="last")]
    test("N_un_level_db", C, "un_d before differencing (F2_D2 variants, E-lines)",
         "czso.unemployment_ri trend-cycle 15-64 (czechia.duckdb)", "UMRTCZ Index", "level", umrtcz, un_level, decimals=1)
    pribor_b = mean("PRIB03M Index")
    test("N_pribor_avg", C, "real-rate gap, PRIBOR leg (rr_gap6/12/18)", "ARAD SFTP04M2206 (3M PRIBOR monthly average)",
         "PRIB03M Index", "monthly mean of daily", pribor_b, pribor, decimals=2)
    y_ext = la.load_headline_cpi_mm_extended()
    y_ext = y_ext[y_ext.index >= pd.Period("1998-01", "M")].dropna()           # path_live F2_START
    logs = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
    yoy_model = pd.Series({p: float(pct_from_log(float(logs.loc[p - 11:p].sum())))
                           for p in y_ext.index if (p - 11) in y_ext.index})
    for k in (6, 12, 18):
        bbg_gap = None if pribor_b is None or yoy_czso is None else (pribor_b.round(2) - yoy_czso).shift(k)
        test(f"N_rr_gap{k}", C, f"rr_gap{k}", f"ARAD SFTP04M2206 minus compounded headline y/y (FRED to 2014, CZSO), lag {k}",
             "PRIB03M Index; CZCPYOY Index", f"monthly mean (2 dp) minus published y/y, lag {k}", bbg_gap,
             (pribor - yoy_model).shift(k), decimals=2)
    candidates = {t: (mean(t) if t in ("BRERCZ Index", "BREERCZK Index") else m(t)) for t in REER_TICKERS}
    for ticker, series in candidates.items():
        test(f"N_reer_mm_{slug(ticker)}", C, "reer_mm (trend line E3)", "ARAD SREERM101 m/m", ticker,
             "m/m of the monthly value (monthly mean for daily series)", cbe.pct(series), cbe.pct(reer101))

    # --- CNB paper TVW-QRF, exact panel ---------------------------------------------------------------------------------
    P = "CNB paper TVW-QRF (exact panel)"
    test("N_a6_12", P, "row 12 industrial production", "A6 row 12: czso:PRU01C SA and calendar-adjusted level",
         "CZIPITS Index", "index level", m("CZIPITS Index"), a6(A6_EXACT, 12), decimals=1)
    test("N_a6_13", P, "row 13 building permits", "override czso:bvzcr_tab6 permits granted", "CZGRIDX Index",
         "level (count)", m("CZGRIDX Index"), a6(A6_OVERRIDES, 13), decimals=0)
    test("N_a6_14", P, "row 14 Rushin", "A6 row 14: cnb:rushin monthly mean of weekly", "CZRUSHIN Index",
         "monthly mean of the weekly values", mean("CZRUSHIN Index"), a6(A6_EXACT, 14), tol=0.005)
    test("N_a6_17", P, "row 17 unit labour costs", "override cnb_arad:MLULNULXXADJYOYPECQ (SA y/y, quarterly)",
         "LCTQCZI Index", "y/y from level (4 quarters)", cbe.pct(cbe.quarter_last(raw.get("LCTQCZI Index")), 4),
         a6(A6_OVERRIDES, 17), decimals=2)
    for ticker in ("CZTBNAL Index", "CZTBAL Index"):
        test(f"N_a6_25_{slug(ticker)}", P, "row 25 trade balance", "override cnb_arad:SVEVZM4 (CZK million)", ticker,
             "level x 1000 (CZK billion to million)", scaled(m(ticker), 1000.0), a6(A6_OVERRIDES, 25), tol=0.5)
    test("N_a6_43", P, "row 43 agricultural PPI y/y", "override cnb_arad:MOPAAPPXXNAJYOYPECM", "CZPPAYOY Index",
         "published y/y", m("CZPPAYOY Index"), a6(A6_OVERRIDES, 43), decimals=1)
    test("N_a6_52", P, "row 52 agricultural PPI m/m",
         "override czso:CEN02032 total (previous month = 100) minus 100; before 2010 rebuilt from ARAD y/y",
         "CZPPAMOM Index", "published m/m", m("CZPPAMOM Index"), a6(A6_OVERRIDES, 52) - 100.0, decimals=1)
    level47 = a6(A6_EXACT, 47)
    test("N_a6_47_level", P, "row 47 domestic PPI, manufacturing", "A6 row 47: eurostat sts_inppd_m PRC_PRR_DOM C I21",
         "EPT00CCZ Index", "index level (Bloomberg series: total market)", m("EPT00CCZ Index"), level47, decimals=1)
    test("N_a6_47_mm", P, "row 47 domestic PPI, manufacturing", "m/m of A6 row 47", "EPT00CCZ Index", "m/m from level",
         cbe.pct(m("EPT00CCZ Index")), cbe.pct(level47), tol=0.05)
    for number, code in ((56, "SREERM101"), (57, "SREERM103")):
        ref = cbe.dlog(a6(A6_EXACT, number))
        for ticker, series in candidates.items():
            test(f"N_a6_{number}_{slug(ticker)}", P, f"row {number} REER", f"log m/m of A6 row {number}: cnb_arad:{code}",
                 ticker, "log m/m", cbe.dlog(series), ref)
    test("N_a6_59_CZBLHPTV", P, "row 59 household loans", "y/y of override cnb_arad:SUCM102211XXX101101",
         "CZBLHPTV Index", "y/y from level", cbe.pct(m("CZBLHPTV Index"), 12), cbe.pct(a6(A6_OVERRIDES, 59), 12), tol=0.05)
    for number, ticker, column in ((65, "TTFGCY1 Index", "bbg__gas_year1_user_selected__month_mean"),
                                   (66, "FSBTY1 Index", "bbg__brent_year1_user_selected__month_mean")):
        test(f"N_a6_{number}", P, f"row {number} (the model already reads Bloomberg)",
             f"a6_inputs_20260912/candidate_inputs_long.csv {column}", ticker, "monthly mean of daily", mean(ticker),
             a6(A6_CANDIDATES, number, column))
    target = pd.read_csv(A6_PANEL / "target_cpi_mm.csv", index_col=0, float_precision="round_trip")
    target.index = pd.PeriodIndex(target.index.astype(str), freq="M")
    test("N_a6_target", P, "target CPI m/m", "paper_model_panel_20260912_exact/target_cpi_mm.csv", "CZCIPM Index",
         "published m/m", m("CZCIPM Index"), target["cpi_mm"].astype(float), decimals=1)

    # --- scoring ------------------------------------------------------------------------------------------------------
    survey = pd.read_csv(SURVEY)
    actual = pd.Series(survey.actual.astype(float).to_numpy(), index=pd.PeriodIndex(survey.target_month.astype(str), freq="M"))
    for ticker in ("CZCPMOM Index", "CZCIPM Index"):
        test(f"N_score_actual_{slug(ticker)}", "scoring", "first print used to score nowcasts",
             "data/czcpmom_survey_history_extended.csv actual", ticker, "published m/m (current vintage)", m(ticker),
             actual, decimals=1)
    test("N_score_actual_combined", "scoring", "first print used to score nowcasts",
         "data/czcpmom_survey_history_extended.csv actual", "CZCIPM Index; CZCPMOM Index",
         "published m/m: CZCIPM, and CZCPMOM where CZCIPM has no value", m("CZCIPM Index").combine_first(m("CZCPMOM Index")),
         actual, decimals=1)

    # --- joined Bloomberg y/y for the state dummy: CNB-published to 2014, CZSO-published from 2015 -----------------------
    cnb_yoy = m("CZCIPY Index")
    joined = cnb_yoy[cnb_yoy.index <= pd.Period("2014-12", "M")].combine_first(m("CZCPYOY Index"))
    test("N_state_combined", "nowcast fixture", "core ridge state; HALF/FULL error states",
         "core_features.state (1 if compounded y/y of the extended headline at t-1 > 4)", "CZCIPY Index; CZCPYOY Index",
         f"1 if published y/y at t-1 > {S.STATE_THRESHOLD:g} (CZCIPY to 2014, CZCPYOY from 2015)",
         dummy_above(joined, S.STATE_THRESHOLD), fixture("core_features.csv", "state"))


def inventory_spec() -> list[dict]:
    rows: list[dict] = []

    def add(model, block, variable, source, tests=(), kind="series", note=""):
        rows.append(dict(model=model, block=block, variable=variable, source_used=source, kind=kind, tests=list(tests),
                         note=note))

    NOW = "Nowcast HARD_BASE / HARD_HALF / HARD_FULL"
    add(NOW, "target and wedge", "headline CPI m/m", "m/m of CZSO 2015=100 index (fixture target_headline_cpi_mm)", ["X2", "X3"])
    add(NOW, "core block", "CNB core m/m", "ARAD SCPIMZM09MOMPECNA (fixture cnb_core_mm)", ["X0"])
    add(NOW, "administered block", "CNB regulated prices m/m", "ARAD SCPIMZM02MOMPECNA (fixture cnb_regulated_mm)", ["X1"])
    add(NOW, "food block", "food (COICOP 01) m/m", "CZSO (fixture component_food_fuel_mm.food)", ["X4", "N_food_cnb"])
    add(NOW, "fuel block", "fuels (07.22) m/m", "CZSO (fixture component_food_fuel_mm.fuel)", ["X6", "N_fuel_cnb"])
    add(NOW, "alcohol and tobacco block", "alcohol and tobacco (02) m/m", "CZSO (fixture alcohol_tobacco)", ["X5"])
    add(NOW, "core ridge", "eurczk_mm", "m/m of CNB monthly average EUR/CZK (monetary.fx_monthly)",
        ["X100", "X112", "X106", "X109", "X103"],
        note="the monthly mean of EURCZK CNB Curncy (3 dp) differs from the CNB-published average by 0.001 in seven months since 2015")
    add(NOW, "core ridge (live calls)", "month-to-date eurczk_mm before the monthly average is published",
        "CNB daily fixings via cz_struct._eurczk_mtd_mm", ["N_cnb_daily_fixings"])
    add(NOW, "core ridge", "services_l1", "CZSO services m/m, lag 1", ["N_services_l1"])
    add(NOW, "core ridge", "import_l2", "CZSO import prices m/m, lag 2", ["X26"])
    for col in ("core_l1", "core_l2", "core_l12"):
        add(NOW, "core ridge", col, "CNB core m/m, lagged", [f"N_{col}"])
    add(NOW, "core ridge", "state", "1 if compounded extended-headline y/y at t-1 > 4", ["N_state_combined"],
        note="equal in every month except 2007-11 (CNB-published y/y 4.0 for 2007-10 against compounded 4.04) and 2007-01 "
             "(no Bloomberg y/y for 2006-12); CZCPYOY alone is equal from 2015-02 (N_state_czcpyoy)")
    add(NOW, "core ridge", "eurczk_mm_x_state", "eurczk_mm x state", ["N_eurczk_x_state"])
    add(NOW, "core ridge", "import_l2_x_state", "import_l2 x state", ["N_import_x_state"],
        note="equal only because the two fixture months where lagged CZEIIMOM differs from import_l2 (2017-02, 2017-08) have state 0")
    add(NOW, "core ridge", "mon_2 ... mon_12", "calendar-month dummies", kind="no data")
    add(NOW, "food block", "food_l1", "CZSO 01 m/m, lag 1", ["N_food_l1"])
    add(NOW, "food block", "food_l12", "CZSO 01 m/m, lag 12", ["N_food_l12"])
    add(NOW, "food block", "agri_l0", "CZSO farm-price product basket m/m", ["N_agri_l0"], note="CZPPAMOM ends 2017-03")
    add(NOW, "food block", "agri_l1", "CZSO farm-price product basket m/m, lag 1", ["N_agri_l1"], note="CZPPAMOM ends 2017-03")
    add(NOW, "food block", "food_ppi_l1", "CZSO food-products PPI m/m (CEN0201B division 10), lag 1",
        ["N_food_ppi_l1", "X29", "N_food_ppi_l1_eurostat"])
    add(NOW, "fuel block", "weekly Natural 95 price", "CZSO CENPHMT Monday survey (fixture fuel_weekly.petrol95)", ["X134"])
    add(NOW, "fuel block", "weekly diesel price", "CZSO CENPHMT Monday survey (fixture fuel_weekly.diesel)", ["X136"])
    add(NOW, "fuel block", "petrol share", "cz_struct official petrol share", kind="static")
    add(NOW, "administered block", "January announcement ledger", "data/admin_announcements_history.csv", kind="static")
    add(NOW, "administered block", "energy item weights", "cz_struct._ENERGY_ITEM_WEIGHTS (CZSO basket)", kind="static")
    add(NOW, "weights", "basket anchors", "CZSO basket weights in cz_struct", kind="static")
    add(NOW, "clock", "release calendar", "data/release_calendar_cz_cpi.csv", kind="static")
    add(NOW, "past-error correction (HALF, FULL)", "historical core ridge errors",
        "data/exact_historical_core_errors.csv plus sequential ridge errors", kind="from another model")
    add(NOW, "past-error correction (HALF, FULL)", "error state: extended headline m/m",
        "FRED CZECPIALLMINMEI to 2014, CZSO from 2015", ["N_ext_mm"])
    add(NOW, "past-error correction (HALF, FULL)", "error state: trailing y/y", "compounded extended headline m/m",
        ["N_trailing_czcipy", "N_trailing_czcpyoy"])
    add(NOW, "fixture columns dropped by HARD and SENTIMENT", "exp12, exp36, exp12_x_state", "CNB FMIE 12m and 36m mean")
    add(NOW, "fixture columns dropped by HARD and SENTIMENT", "household_exp", "EC consumer price expectations, CZ", ["X45"])

    SEN = "Nowcast SENTIMENT_BASE / HALF / FULL"
    add(SEN, "all blocks", "every HARD input", "same frozen fixture", kind="from another model")
    add(SEN, "core ridge", "esi", "fixture core_features.esi", ["X48"],
        note="ECFIN's official CZ.ESI equals EUESCZ exactly (X50), but the fixture column is a different series")

    BR = "INDEPENDENT_BRIDGE"
    add(BR, "h0 and block paths", "every HARD input", "same frozen fixture frames; h0 = HARD_BASE", kind="from another model")
    add(BR, "month-to-date FX (live calls)", "gated month-to-date EUR/CZK", "CNB daily fixings via cz_struct._eurczk_mtd_mm",
        ["N_cnb_daily_fixings"])
    add(BR, "y/y accounting", "headline m/m history", "output/independent_path_frozen_inputs.csv headline_mm",
        ["N_path_headline_CZCIPM", "N_path_headline_CZCPMOM"])
    add(BR, "comparison only", "CNB MPR quarterly CPI path", "data/cnb_mpr_cpi_quarterly.csv")

    PR = "Path roster TARGET_ML, TARGET_FX_ML, TARGET_U_FX_ML, BVAR_U_FX, RF_U_FX, NAIVE"
    add(PR, "all models", "headline m/m history (1991 on)", "frozen headline_mm: FRED CZECPIALLMINMEI to 2014, CZSO from 2015",
        ["N_path_headline_CZCIPM", "N_path_headline_CZCPMOM"])
    add(PR, "FX models", "fx12_l3", "12-month change of the CNB monthly average EUR/CZK, lag 3", ["N_path_eurczk"],
        note="the monthly mean of EURCZK CNB Curncy (3 dp) differs from the CNB-published average by 0.001 in seven months since 2015")
    add(PR, "U models", "un_d", "CZSO 15-64 unemployment, historical release vintages, change lag 1",
        ["N_u_latest", "N_u_first", "N_u_change"])
    add(PR, "all models", "h0", "HARD_BASE nowcast", kind="from another model")
    add(PR, "target-anchored models", "inflation target path", "CNB target constants", kind="static")

    PL = "path_live (F1b engine, F2 trend line, E7 target line, E variants)"
    add(PL, "F1b engine", "nowcast frame", "cz_struct.load_all live database: the series of the HARD fixture",
        kind="from another model")
    add(PL, "F1b engine core ridge (full frame, surveys kept)", "exp12, exp36, exp12_x_state",
        "CNB FMIE 12m and 36m mean (live database)")
    add(PL, "F1b engine core ridge (full frame, surveys kept)", "household_exp", "EC consumer price expectations, CZ",
        ["X45"])
    add(PL, "F1b engine core ridge (full frame, surveys kept)", "esi", "la.load_esi (live database)", ["X48"],
        note="X48 tests the frozen fixture esi column")
    add(PL, "F1b engine", "m3_yoy", "ARAD SMV5M108 y/y, lag 1", ["X93", "X92"])
    add(PL, "F1b engine", "hpi_yoy", "CZSO old-apartment prices y/y (czso.hpi)", ["X91"])
    add(PL, "F1b engine", "constr_ppi_yoy", "CZSO construction PPI (czso.cen0202a)")
    add(PL, "trend history", "headline m/m 1998 on", "load_headline_cpi_mm_extended", ["N_ext_mm"])
    add(PL, "F2 trend line", "FMIE one-year expectation", "consensus.inflation_expectations cnb_fmie 12m mean")
    add(PL, "F2_D2 variants", "fx_mm", "m/m of CNB monthly average EUR/CZK", ["X100"])
    add(PL, "F2_D2 variants, E lines", "un_d", "CZSO 15-64 trend-cycle change, lag 1 (czso.unemployment_ri)",
        ["X87", "N_un_level_db"])
    add(PL, "F2_D2 variants", "esi", "eurostat.bcs_survey BS-ESI-I (czechia.duckdb)", ["X49"])
    add(PL, "E4-E7 lines", "fx_yoy_l3", "12-month change of the CNB monthly average, lag 3", ["X99"])
    add(PL, "E4, E6, E7 lines", "rr_gap12", "3M PRIBOR monthly average minus compounded headline y/y, lag 12",
        ["N_rr_gap12", "N_pribor_avg", "X94"])
    add(PL, "E5 line", "rr_gap18", "as rr_gap12, lag 18", ["N_rr_gap18"])
    add(PL, "E6 line", "wage_yoy", "Eurostat lc_lci_r2_q D11 B-S NSA y/y", ["X90"])
    add(PL, "E7 line", "imp_mm", "CZSO CEN0303 import prices m/m, lag 1", ["X27"])
    add(PL, "E2, E3 lines", "rr_gap6", "as rr_gap12, lag 6", ["N_rr_gap6"])
    add(PL, "E3 line", "reer_mm", "ARAD SREERM101 m/m", [f"N_reer_mm_{slug(t)}" for t in REER_TICKERS])
    add(PL, "benchmarks", "CNB MPR quarterly CPI path", "data/cnb_mpr_cpi_quarterly.csv")
    add(PL, "benchmarks", "latest FMIE one-year expectation", "consensus.inflation_expectations cnb_fmie")
    add(PL, "clock", "known flash first releases", "path_live FLASH_KNOWN", kind="static")

    TV = "CNB WP9 TVW-QRF (exact panel)"
    audit = pd.read_csv(A6_AUDIT).set_index("number")
    sources = json.loads((A6_PANEL / "manifest.json").read_text(encoding="utf-8"))["realtime_convention"]["rows"]
    for number in range(1, 73):
        refs = A6_REFS.get(number, [f"N_a6_{number}_{slug(t)}" for t in REER_TICKERS] + (["X132"] if number == 56 else ["X130", "X131"]))
        add(TV, str(audit.loc[number, "group"]), f"row {number}: {audit.loc[number, 'description']}",
            str((sources.get(str(number)) or {}).get("source") or ""), refs, note=A6_NOTES.get(number, ""))
    add(TV, "target", "CPI m/m", "paper_model_panel_20260912_exact/target_cpi_mm.csv", ["N_a6_target"])

    SC = "Scoring and benchmarks"
    add(SC, "actuals", "first print CPI m/m", "data/czcpmom_survey_history_extended.csv actual",
        ["N_score_actual_combined"], note="each ticker is also equal on its own span (N_score_actual_CZCIPM, N_score_actual_CZCPMOM)")
    add(SC, "benchmark", "consensus median and mean", "same file: Bloomberg CZCPMOM survey fields", kind="Bloomberg already")

    RL = "Earlier research lanes (R10 category model, R14 fuel)"
    for label, ref in (("actual rent m/m", "X22"), ("catering m/m", "X23"), ("package holidays m/m", "X24"),
                       ("accommodation m/m", "X25")):
        add(RL, "R10 category model", label, "m/m of CZSO group level (data/core_split)", [ref])
    for label, ref in (("gross Euro-super 95", "X133"), ("gross diesel", "X135"), ("net Euro-super 95", "X137"),
                       ("net diesel", "X138")):
        add(RL, "R14 fuel pump panel", label, "EC Oil Bulletin files", [ref])
    add(RL, "R14 fuel", "CNB daily EUR/CZK fixing 2004 on", "R14 fx_daily plus 2018 capture", ["X98"])
    add(RL, "R14 fuel", "CNB daily USD/CZK fixing", "R14 fx_daily", ["X113"])
    add(RL, "R14 fuel", "Brent daily and monthly change", "EIA Europe Brent spot FOB", ["X118", "X119"])
    return rows


def number(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return v if np.isfinite(v) else 0.0


def evaluate(spec: list[dict], existing: pd.DataFrame) -> pd.DataFrame:
    out = []
    for item in spec:
        tests = []
        for ref in item["tests"]:
            row = dict(existing.iloc[int(ref[1:])].to_dict(), test_id=ref) if ref.startswith("X") else NEW[ref]
            tests.append(row)
        base = {k: item[k] for k in ("model", "block", "variable", "source_used")}
        listing = "; ".join(f"{t['test_id']} {t['ticker']}: {t['verdict']}" for t in tests)
        if item["kind"] != "series":
            out.append(dict(base, status=item["kind"], tests=listing, note=item["note"]))
            continue
        if not tests:
            out.append(dict(base, status="no Bloomberg series held", tests="", note=item["note"]))
            continue
        exact = [t for t in tests if t.get("verdict") == "exact"]
        if exact:
            best = min(exact, key=lambda t: number(t.get("model_obs_without_bloomberg")))
            status = "exact" if number(best.get("model_obs_without_bloomberg")) == 0 else "exact where Bloomberg has history"
        else:
            best = min(tests, key=lambda t: (RANK.get(t.get("verdict"), 9), -number(t.get("exact_share"))))
            status = "not testable" if best.get("verdict") == "not testable" else "not exact"
        out.append(dict(base, status=status,
                        exact_bloomberg="; ".join(f"{t['ticker']} ({t['transform']})" for t in exact),
                        closest_ticker=best.get("ticker"), closest_transform=best.get("transform"),
                        closest_verdict=best.get("verdict"), n=best.get("n"), first=best.get("first"), last=best.get("last"),
                        exact_share=best.get("exact_share"), max_abs_gap=best.get("max_abs_gap"),
                        exact_since=best.get("exact_since", ""),
                        model_obs_without_bloomberg=best.get("model_obs_without_bloomberg", ""),
                        without_bloomberg_span=best.get("without_bloomberg_span", ""), tests=listing, note=item["note"]))
    return pd.DataFrame(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")
    existing = pd.read_csv(EXISTING)
    for row, ticker in EXISTING_ANCHORS.items():
        if len(existing) != 139 or existing.loc[row, "ticker"] != ticker:
            raise ValueError(f"{EXISTING} changed: row {row} is not {ticker}; X references would point at other tests")
    run_tests(cbe.load_raw())
    new = pd.DataFrame(NEW.values())
    new.to_csv(out / "new_tests.csv", index=False)
    inventory = evaluate(inventory_spec(), existing)
    inventory.to_csv(out / "model_input_inventory.csv", index=False)
    inputs = [EXISTING, FIX / "MANIFEST.json", A6_EXACT, A6_OVERRIDES, A6_CANDIDATES, A6_PANEL / "manifest.json",
              A6_PANEL / "target_cpi_mm.csv", A6_AUDIT, FIXINGS, FROZEN_PATH, UNEMPLOYMENT, SURVEY]
    manifest = dict(tool=str(Path(__file__).resolve().relative_to(ROOT)), tool_sha256=sha256(Path(__file__).resolve()),
                    created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    bloomberg_data="compare_bloomberg_exactness.load_raw: 20260911 wide daily + 20260912_bloomberg_probe*",
                    database=str(la.DB_PATH), unemployment_vintage_as_of=str(VINTAGE_AS_OF),
                    inputs={str(p.relative_to(ROOT)): sha256(p) for p in inputs},
                    new_tests=len(new), inventory_rows=len(inventory),
                    status_counts=inventory.status.value_counts().to_dict())
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 70)
    print(new[["test_id", "ticker", "n", "exact_share", "max_abs_gap", "verdict", "exact_since",
               "model_obs_without_bloomberg"]].to_string(index=False))
    for model, group in inventory.groupby("model", sort=False):
        print(f"\n== {model}: " + ", ".join(f"{k} {v}" for k, v in group.status.value_counts().items()))
        for r in group.itertuples():
            detail = r.exact_bloomberg if str(r.status).startswith("exact") else (
                f"closest {r.closest_ticker} {r.closest_verdict}" if isinstance(r.closest_ticker, str) else "")
            print(f"   [{r.status}] {r.variable[:70]} | {detail}")


if __name__ == "__main__":
    main()
