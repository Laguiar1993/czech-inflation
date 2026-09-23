"""Forward monthly inflation path: the product and its comparison lines.

Origin = the first month without a first release (the month the live
nowcast targets). h = 0 is the frozen trio's live nowcast (BASE_RIDGE as the
anchor; PAST_FULL, PAST_HALF and the survey-free reference reported).
h = 1..12 come from the product engine (PATH_SPEC_v2 RESULTS: F1b, the
component bridge with the plain frame at every horizon and the food
seasonal mean from h = 4). Two trend lines are always computed and shown
next to the product: the survey-anchored trend-and-gap path (F2_D1_fixed,
the scored second line) and the target-anchored, survey-free path
(E1_ML, PATH_SPEC_v3, information). The index path is chained on the
official CPI index (CZSO, 2015 = 100); a published FLASH is a known first
release (FLASH_KNOWN). Benchmarks: naive seasonal path, random walk in y/y,
the CNB FMIE one-year expectation, the CNB Monetary Policy Report quarterly
path (information only, flagged where we differ by CNB_FLAG_PP or more).
Error scale: the corrected step-1 run, all origins and 2024+ targets.
Every run is appended to output/path_live_log.csv and never edited.
Usage: python path_live.py [--flash YYYY-MM=VALUE] [--no-log] [--engine F1a|F1b|F2|F1b+F2]
"""
import argparse
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402
from data.struct_inputs import load_m3_yoy, load_housing_channel  # noqa: E402
from models.trend_gap import fit_forecast  # noqa: E402
from path_experiment import load_fmie_1y, lg, pct  # noqa: E402
from path_step2_backtest import load_drivers  # noqa: E402

NAIVE_YEARS = 5
BLK = ("core", "food", "admin", "alc", "fuel", "wedge")
DEFAULT_ENGINE = "F1b"
# trend lines: (label, variant). F2_* = survey-anchored (PATH_SPEC_v2); E*_* = target-anchored, survey-free (PATH_SPEC_v3)
TREND_LINES = [("trend", "F2_D1_fixed"), ("target", "E7_ML")]   # target line E7 by the PATH_SPEC_v4 rule (flagged in its RESULTS: worse than E1 on the long span)
TREND_DRIVERS = {"E1": [], "E2": ["fx_mm", "un_d", "rr_gap6"], "E3": ["fx_mm", "un_d", "rr_gap6", "reer_mm"]}
# PATH_SPEC_v4 variants: target-anchored, centred robust seasonal, drivers at their proper lags
STEP4_DRIVERS = {"E1R": [], "E4": ["un_d", "fx_yoy_l3", "rr_gap12"], "E5": ["un_d", "fx_yoy_l3", "rr_gap18"],
                 "E6": ["un_d", "fx_yoy_l3", "rr_gap12", "wage_yoy"], "E7": ["un_d", "fx_yoy_l3", "rr_gap12", "imp_mm"]}
F2_START = pd.Period("1998-01", "M")
CNB_FLAG_PP = 0.5
# published flash first releases not yet in the CPI-family tables (CZSO flash, m/m %): documented, dated
FLASH_KNOWN = {"2026-08": (0.3, "CZSO flash 4 Sep 2026: +0.3% m/m, +1.9% y/y")}


def naive_mm(y_known: pd.Series, target: pd.Period) -> float:
    same = y_known[y_known.index.month == target.month]
    return float(same.tail(NAIVE_YEARS).mean()) if len(same) >= 3 else float(y_known.tail(24).mean())


def official_index() -> pd.Series:
    con = S.la._con()
    d = con.sql("""SELECT date, value FROM cpi_czso.cpi_long WHERE coicop_code='0' AND period_type='monthly'
                   AND base='base_2015_eq_100' AND hh_group_code='0' ORDER BY date""").df()
    con.close()
    s = pd.Series(d["value"].astype(float).values, index=pd.PeriodIndex(pd.to_datetime(d["date"]), freq="M"))
    return s[~s.index.duplicated(keep="last")]


def cnb_benchmarks():
    out = {}
    try:
        con = S.la._con()
        f = con.sql("""SELECT survey_date, value_pct FROM consensus.inflation_expectations WHERE source='cnb_fmie'
                       AND horizon_kind='rolling_months' AND horizon_value=12 AND metric='mean' ORDER BY survey_date DESC LIMIT 1""").df()
        con.close()
        if len(f):
            out["fmie_1y"] = (str(pd.Period(pd.to_datetime(f.survey_date[0]), freq="M")), float(f.value_pct[0]))
        # CNB Monetary Policy Report QUARTERLY CPI y/y path (tools/cnb_mpr_cpi_quarterly.py); the cnb.mpr_vintages table
        # stores the first quarterly column of each year, not annual averages (found 8 Sep 2026)
        cq = pd.read_csv(os.path.join(HERE, "data", "cnb_mpr_cpi_quarterly.csv"))
        last = cq[cq.report_date == cq.report_date.max()]
        out["cnb_mpr_q"] = (str(last.report_date.iloc[0]), str(last.season.iloc[0]), {r.quarter: float(r.value) for r in last.itertuples() if bool(r.is_forecast)})
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:80]
    return out


def trend_history(t: pd.Period, as_of: pd.Timestamp, flash: dict) -> pd.Series:
    """Released headline m/m from 1998 through t-1, with published flashes appended as known first releases."""
    y_ext = S.la.load_headline_cpi_mm_extended(); y_ext = y_ext[(y_ext.index >= F2_START) & (y_ext.index <= t - 1)].dropna()
    y_ext = y_ext[S._released_index(y_ext.index, as_of)]
    for k_, (v_, _) in sorted(flash.items()):
        pk = pd.Period(k_, freq="M")
        if pk == y_ext.index.max() + 1 and pk <= t - 1:
            y_ext.loc[pk] = v_
    assert y_ext.index.max() == t - 1, f"trend history ends {y_ext.index.max()}, origin {t}"
    return y_ext


def fit_trend(variant: str, y_ext: pd.Series, t: pd.Period) -> dict:
    """One trend-and-gap fit at origin t. Model h = 1 is the nowcast month t; target t+h uses h+1."""
    kw = {}
    if variant.startswith("F2"):
        fm = load_fmie_1y()
        if fm is not None and "noFMIE" not in variant:
            kw["m_hist"] = fm[fm.index <= t - 1]
        if variant.startswith("F2_D2"):
            drv = load_drivers()
            X2 = pd.DataFrame({"fx_mm": drv["fx_mm"], "un_d": drv["un_d"], "esi_dev": drv["esi"] - drv["esi"][drv["esi"].index <= t - 1].mean()})
            kw["x_hist"] = X2[X2.index <= t - 1].reindex(y_ext.index).fillna(0.0)
    elif variant.split("_")[0] in STEP4_DRIVERS:
        kw["anchored"] = True; kw["robust_seasonal"] = True
        cols = STEP4_DRIVERS[variant.split("_")[0]]
        if cols:
            from path_step4_backtest import load_import_prices, load_lci
            drv = load_drivers()
            con = S.la._con()
            pr = con.sql("SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='SFTP04M2206' ORDER BY period, snapshot_id").df().drop_duplicates("period", keep="last")
            fx = con.sql("SELECT year, month, czk_per_unit FROM monetary.fx_monthly WHERE currency_code='EUR' ORDER BY 1,2").df()
            con.close()
            pribor = pd.Series(pr.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(pr.period), freq="M"))
            fxs = pd.Series(fx.czk_per_unit.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(dict(year=fx.year, month=fx.month, day=1)), freq="M"))
            yl = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
            yoy = pd.Series({m: pct(float(yl.loc[m - 11:m].sum())) for m in y_ext.index if (m - 11) in y_ext.index})
            X4 = pd.DataFrame({"un_d": drv["un_d"], "fx_yoy_l3": (100 * (fxs / fxs.shift(12) - 1)).shift(3), "rr_gap12": (pribor - yoy).shift(12),
                               "rr_gap18": (pribor - yoy).shift(18), "wage_yoy": load_lci() if "wage_yoy" in cols else np.nan,
                               "imp_mm": load_import_prices().shift(1) if "imp_mm" in cols else np.nan})   # month s row = import prices of s-1 (public mid s+1)
            kw["x_hist"] = X4[cols][X4.index <= t - 1].reindex(y_ext.index).fillna(0.0)
    else:
        kw["anchored"] = True
        cols = TREND_DRIVERS[variant.split("_")[0]]
        if cols:
            drv = load_drivers()
            con = S.la._con()
            rr = con.sql("SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='SREERM101' ORDER BY period, snapshot_id").df().drop_duplicates("period", keep="last")
            pr = con.sql("SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='SFTP04M2206' ORDER BY period, snapshot_id").df().drop_duplicates("period", keep="last")
            con.close()
            reer = pd.Series(rr.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(rr.period), freq="M"))
            pribor = pd.Series(pr.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(pr.period), freq="M"))
            yl = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
            yoy = pd.Series({m: pct(float(yl.loc[m - 11:m].sum())) for m in y_ext.index if (m - 11) in y_ext.index})
            X3 = pd.DataFrame({"fx_mm": drv["fx_mm"], "un_d": drv["un_d"], "rr_gap6": (pribor - yoy).shift(6), "reer_mm": 100 * reer.pct_change()})
            kw["x_hist"] = X3[cols][X3.index <= t - 1].reindex(y_ext.index).fillna(0.0)
    if variant.endswith("fixed"):
        kw["fixed_snr"] = True
    return fit_forecast(y_ext, range(1, 14), **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flash", action="append", default=[], help="YYYY-MM=VALUE extra known flash m/m")
    ap.add_argument("--no-log", action="store_true")
    ap.add_argument("--engine", choices=["F1a", "F1b", "F2", "F1b+F2"], default=DEFAULT_ENGINE)
    a = ap.parse_args()
    flash = dict(FLASH_KNOWN)
    for kv in a.flash:
        k, v = kv.split("="); flash[k] = (float(v), "operator-supplied flash")

    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    slow = pd.concat([load_m3_yoy(), load_housing_channel()], axis=1)
    feats_slow = pd.concat([feats, slow.reindex(feats.index)], axis=1)
    fuel_official = comp["fuel"].dropna()
    idx = official_index()
    now = S._now_prague() if hasattr(S, "_now_prague") else pd.Timestamp.now()
    if isinstance(now, tuple):              # cz_struct returns (zone-aware, naive Prague wall time)
        now = now[1]
    as_of = pd.Timestamp(now)
    if as_of.tzinfo is not None:
        as_of = as_of.tz_localize(None)
    edge = idx.index.max()
    known_first = max([edge] + [pd.Period(k, freq="M") for k in flash])
    t = known_first + 1                       # the month the live nowcast targets
    print(f"official index through {edge}; flash first releases {sorted(flash)}; origin (h0) = {t}; clock {as_of}")

    # h0: the frozen trio, live (dry run, nothing logged here)
    live = S.struct_live(target=t, log=False)
    h0 = {"BASE_RIDGE": float(live["h0_base_ridge"]), "PAST_FULL": float(live["h0_past_full"]), "PAST_HALF": float(live["h0_past_half"]),
          "NO_SURVEY": float(live.get("h0_base_ridge_ns", np.nan))}
    # trend lines
    y_ext = trend_history(t, as_of, flash)
    trends = {}
    for label, variant in TREND_LINES:
        f = fit_trend(variant, y_ext, t); trends[label] = (variant, f)
        print(f"{label} line {variant}: level {f.get('level', float('nan')):+.3f} gap {f.get('gap', float('nan')):+.3f} phi {f.get('phi', float('nan')):.2f} "
              f"rho {f.get('rho', float('nan')):.3f} survey bias {f.get('bias_m', float('nan')):+.3f} converged {f.get('converged')} n {f.get('n')}")
    # h >= 1: the product engine
    y_known = y.dropna(); y_known = y_known[y_known.index <= t - 1]; y_known = y_known[S._released_index(y_known.index, as_of)]
    wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc); wt = wmap[S._regime(t)]
    wedge_tv = S._weighted_wedge(y, comp, alc, core, reg, wedge, wmap, as_of=as_of)
    food_hist = comp["food"].dropna(); food_hist = food_hist[food_hist.index <= t - 1]; food_hist = food_hist[S._released_index(food_hist.index, as_of)]
    fc, blocks, notes = {0: h0["BASE_RIDGE"]}, {}, {}
    f2_engine = trends["trend"][1] if a.engine in ("F2", "F1b+F2") else None
    for h in range(1, 13):
        plain = a.engine in ("F1b", "F1b+F2")
        frame = feats if (plain or h <= 3) else feats_slow
        wh = wmap.get(S._regime(t + h), wt)
        core_h, _, _ = S._ridge_predict(frame, core, t, h=h, as_of=as_of)
        if plain and h >= 4:
            fm_ = food_hist[food_hist.index.month == (t + h).month]
            food_h = float(fm_.tail(5).mean()) if len(fm_) >= 3 else float(food_hist.tail(24).mean())
        else:
            food_h = S.food_forecast(comp["food"], food_feats, t, h=h, as_of=as_of)
        adm_h = S.admin_forecast(reg, t + h, known_through=t - 1, as_of=as_of, announce_mode="documented", w_adm=wh["administered"])
        alc_h = S.alc_forecast(alc, t + h, t - 1, as_of=as_of)
        fh = fuel_official[fuel_official.index <= t - 1]; fh = fh[S._released_index(fh.index, as_of)]
        fm = fh[fh.index.month == (t + h).month]
        fuel_h = float(fm.tail(8).median()) if len(fm) >= 3 else float(fh.tail(24).median())
        wdg = S._wedge_at(wedge_tv, t + h, t - 1)
        fc[h] = wh["fuel"] * fuel_h + wh["administered"] * adm_h + wh["alc"] * alc_h + wh["food"] * food_h + wh["core"] * core_h + wdg
        blocks[h] = {"core": wh["core"] * core_h, "food": wh["food"] * food_h, "admin": wh["administered"] * adm_h,
                     "alc": wh["alc"] * alc_h, "fuel": wh["fuel"] * fuel_h, "wedge": wdg}
        use_f2 = a.engine == "F2" or (a.engine == "F1b+F2" and h >= 4)
        if use_f2 and f2_engine is not None and np.isfinite(f2_engine["mm"].get(h + 1, np.nan)):
            fc[h] = float(f2_engine["mm"][h + 1]); blocks[h] = {k: np.nan for k in BLK}
        if (t + h).month == 1:
            notes[h] = "January: administered block = seasonal median only" + ("" if S._gate_fires(t + h, as_of, "documented") else " (no announcement entry yet; ERU decisions due end-Nov)")
    # index chains: product, naive, each trend line (all anchored at the nowcast month)
    chain = idx.copy()
    for k, (v, _) in sorted(flash.items()):
        p = pd.Period(k, freq="M")
        if p == chain.index.max() + 1:
            chain.loc[p] = chain.loc[p - 1] * (1 + v / 100.0)
    naive_chain = chain.copy(); tchains = {lab: chain.copy() for lab in trends}
    rows = []
    for h in range(0, 13):
        m = t + h
        chain.loc[m] = chain.loc[m - 1] * (1 + fc[h] / 100.0)
        nv = naive_mm(y_known, m); naive_chain.loc[m] = naive_chain.loc[m - 1] * (1 + nv / 100.0)
        rec = {"target": str(m), "h": h, "mm": fc[h], "index": chain.loc[m], "yoy": 100 * (chain.loc[m] / chain.loc[m - 12] - 1),
               "naive_mm": nv, "naive_yoy": 100 * (naive_chain.loc[m] / naive_chain.loc[m - 12] - 1)}
        for lab, (variant, f) in trends.items():
            tm = fc[0] if h == 0 else float(f["mm"].get(h + 1, np.nan))
            tchains[lab].loc[m] = tchains[lab].loc[m - 1] * (1 + tm / 100.0) if np.isfinite(tm) else np.nan
            rec[f"{lab}_mm"] = tm; rec[f"{lab}_yoy"] = 100 * (tchains[lab].loc[m] / tchains[lab].loc[m - 12] - 1) if np.isfinite(tchains[lab].loc[m]) else np.nan
        rec.update({f"blk_{k}": blocks[h][k] for k in BLK} if h >= 1 else {"blk_core": np.nan})
        rec["note"] = notes.get(h, "")
        rows.append(rec)
    df = pd.DataFrame(rows)
    try:
        pe = pd.read_csv(os.path.join(HERE, "output", "path_experiment.csv"))
        pe = pe[pe[["model_yy_pct", "naive_yy_pct", "real_yy_pct"]].notna().all(axis=1)]; pe["tp"] = pd.PeriodIndex(pe["target"], freq="M")
        s_all = pe.groupby("h").apply(lambda g: float(np.sqrt(np.mean((g.model_yy_pct - g.real_yy_pct) ** 2))))
        s_24 = pe[pe.tp >= pd.Period("2024-01", "M")].groupby("h").apply(lambda g: float(np.sqrt(np.mean((g.model_yy_pct - g.real_yy_pct) ** 2))))
        df["yoy_rmse_all"] = df["h"].map(s_all); df["yoy_rmse_2024p"] = df["h"].map(s_24)
    except Exception:  # noqa: BLE001
        df["yoy_rmse_all"] = np.nan; df["yoy_rmse_2024p"] = np.nan
    bench = cnb_benchmarks()
    rw_yoy = 100 * (chain.loc[t - 1] / chain.loc[t - 13] - 1)

    pd.set_option("display.width", 260)
    print(f"\nFORWARD PATH from origin {t} (engine {a.engine}; h0 = live trio BASE_RIDGE {h0['BASE_RIDGE']:+.2f} / PAST_FULL {h0['PAST_FULL']:+.2f} / PAST_HALF {h0['PAST_HALF']:+.2f}; "
          f"no-survey reference {h0['NO_SURVEY']:+.2f}; anchor BASE_RIDGE)")
    print(f"{'month':8s} {'h':>2s} {'m/m':>6s} {'y/y':>6s} | trend(survey) {'m/m':>6s} {'y/y':>6s} | target(no survey) {'m/m':>6s} {'y/y':>6s} | {'naive y/y':>9s} | {'core':>6s} {'food':>6s} {'admin':>6s} {'alc':>6s} {'fuel':>6s} {'wedge':>6s} | RMSE all/2024+ | note")
    for r in df.itertuples():
        b = "" if r.h == 0 else f"{r.blk_core:+6.2f} {r.blk_food:+6.2f} {r.blk_admin:+6.2f} {r.blk_alc:+6.2f} {r.blk_fuel:+6.2f} {r.blk_wedge:+6.2f}"
        print(f"{r.target:8s} {r.h:2d} {r.mm:+6.2f} {r.yoy:6.2f} | {r.trend_mm:+20.2f} {r.trend_yoy:6.2f} | {r.target_mm:+24.2f} {r.target_yoy:6.2f} | {r.naive_yoy:9.2f} | {b:41s} | {r.yoy_rmse_all:5.2f}/{r.yoy_rmse_2024p:5.2f} | {r.note}")
    df["tp"] = pd.PeriodIndex(df["target"], freq="M")
    from evaluation.path_calendar import complete_quarters
    known_yoy = (chain / chain.shift(12) - 1) * 100
    known_yoy = known_yoy.loc[known_yoy.index < t]
    q = pd.DataFrame({lab: complete_quarters(known_yoy, pd.Series(df[col].values, index=pd.PeriodIndex(df.target, freq='M')))
                      for lab, col in [('product','yoy'),('trend','trend_yoy'),('target','target_yoy')]})
    q.index = q.index.astype(str)
    q['count'] = 3
    print("\ncomplete quarterly averages of y/y, including observed months: product (F1b) | trend line (survey-anchored) | target line (survey-free)")
    print(q.round(2).to_string())
    for yr in sorted(set(df.tp.dt.year)):
        months = pd.period_range(f"{yr}-01", f"{yr}-12", freq="M")
        yy = [100 * (chain.loc[m] / chain.loc[m - 12] - 1) for m in months if m in chain.index and (m - 12) in chain.index]
        nf = int(sum(1 for m in months if m >= t and m in chain.index))
        print(f"calendar-year average y/y {yr} (product): {np.mean(yy):.2f} over {len(yy)} months ({nf} forecast)")
    print(f"\nbenchmarks: random walk in y/y (last known, {t-1}) {rw_yoy:.2f}; " +
          (f"CNB FMIE one-year expectation, survey {bench['fmie_1y'][0]}: {bench['fmie_1y'][1]:.2f} for {pd.Period(bench['fmie_1y'][0], freq='M') + 12}" if 'fmie_1y' in bench else ""))
    if "cnb_mpr_q" in bench:
        print(f"\nCNB COMPARISON, report {bench['cnb_mpr_q'][1]} {bench['cnb_mpr_q'][0]} (information, never an input): quarter | product | trend | target | CNB | flags at |difference| >= {CNB_FLAG_PP:.1f} pp")
        for k, v in bench["cnb_mpr_q"][2].items():
            if k not in q.index:
                continue
            qp = pd.Period(k, freq="Q"); months = pd.period_range(qp.asfreq("M", "s"), qp.asfreq("M", "e"), freq="M")
            has_jan = any(m.month == 1 for m in months)
            flags = [f"{lab} {q.loc[k, lab] - v:+.2f}" for lab in ("product", "trend", "target") if np.isfinite(q.loc[k, lab]) and abs(q.loc[k, lab] - v) >= CNB_FLAG_PP]
            note = " (quarter contains a January whose administered block is the seasonal median only)" if (has_jan and flags) else ""
            print(f"  {k}: product {q.loc[k, 'product']:.2f} | trend {q.loc[k, 'trend']:.2f} | target {q.loc[k, 'target']:.2f} | CNB {v:.2f} | {'FLAG ' + ', '.join(flags) + note if flags else 'within band'}")
    print("\nCAVEATS: product engine F1b (PATH_SPEC_v2 RESULTS: +25.7 / +29.6 / +17.2% over the seasonal-naive path at 3 / 6 / 12 months, publishable). Trend line = survey-anchored "
          "trend-and-gap (scored second line: better when nothing breaks, 2024-26 beyond six months 0.87 vs 1.10; worse in a shock, 2022-23 8.76 vs 7.30). Target line = the same model "
          "anchored to the CNB target with no survey, drivers unemployment change, koruna/euro twelve-month change lagged 3, real rate lagged 12, CZSO import prices (E7 by the PATH_SPEC_v4 rule; FLAGGED in its RESULTS: "
          "worse than the anchor-only line on 2008-2026 at twelve months, 4.18 vs 3.96, survey line 3.84; the survey saw the 2024 disinflation first). No calibrated bands; RMSE columns are the step-1 engine's historical y/y error scale. January 2027 carries no energy entry until the ERU decisions "
          "(end November). Direction at twelve months is near a coin flip for every family; quarterly averages to three quarters ahead are the useful product.")
    out = df.drop(columns=["tp"]).copy()
    out.insert(0, "engine", a.engine); out.insert(0, "spec", S.SPEC_TAG); out.insert(0, "as_of", as_of.isoformat(timespec="seconds")); out.insert(0, "origin", str(t))
    out.insert(0, "run_ts", pd.Timestamp.now().isoformat(timespec="seconds"))
    out["h0_past_full"] = h0["PAST_FULL"]; out["h0_past_half"] = h0["PAST_HALF"]; out["h0_no_survey"] = h0["NO_SURVEY"]
    out["trend_variant"] = trends["trend"][0]; out["target_variant"] = trends["target"][0]
    out.to_csv(os.path.join(HERE, "output", "path_live_latest.csv"), index=False)
    if not a.no_log:
        p = os.path.join(HERE, "output", "path_live_log.csv")
        hist = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
        pd.concat([hist, out], ignore_index=True).to_csv(p, index=False)
        print(f"logged -> {p} (append-only)")


if __name__ == "__main__":
    main()
