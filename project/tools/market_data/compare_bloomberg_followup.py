"""Follow-up checks on the 12 Sep 2026 Bloomberg probes: CPI index levels, REER, unemployment and services candidates.

  python tools/market_data/compare_bloomberg_followup.py \
      --probe data/market_snapshots/20260912_bloomberg_probe ... data/market_snapshots/20260912_bloomberg_probe7 \
      --output output/bloomberg_probe_comparison_20260912/followup

A. Bloomberg CZSO CPI index levels against CZSO's own 2025=100 levels (czechia.duckdb), and the m/m derived from those
   levels against the model input (m/m from CZSO's 2015=100 levels) and the official one-decimal m/m, with the rounding
   band implied by one-decimal levels.
B. REER candidates against CNB ARAD SREERM101 (PPI-deflated) and SREERM103 (CPI-deflated), the CNB-paper A6 rows 56-57
   (paper transform 2, a log difference), plus y/y and levels rebased to the 2020 average. Daily tickers are averaged by
   month.
C. Unemployment candidates against CZSO's 15-64 LFS rate (latest NSA and trend-cycle, last SA release) and A6 row 11.
D. Services: the ARAD tradables/non-tradables split (y/y) and the CZSO service groups of the R10 category model against
   HICP and OECD components.
A later probe overrides an earlier one for the same ticker. Nothing here changes a model input.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_bloomberg_probe as cmp  # noqa: E402

ROOT = cmp.ROOT
DB_PATH = Path(os.environ.get("CZ_CPI_DB", Path.home() / "economic_db" / "czechia.duckdb"))
CZSO_TICKERS = {"0": "CZCPI Index", "01": "CZCPF Index", "02": "CZCPA Index", "03": "CZCPC Index", "04": "CZCPH Index",
                "05": "CZCPN Index", "06": "CZCPHE Index", "07": "CZCPTR Index", "08": "CZCPP Index", "09": "CZCPR Index",
                "10": "CZCPE Index", "11": "CZCPSH Index", "12": "CZCP12 Index", "13": "CZCP13 Index"}
REER_TICKERS = [("BRERCZ Index", "user list"), ("BISBCZR Index", "user list"), ("935.028 Index", "user list"),
                ("BREERCZK Index", "user list"), ("OECZFRAA Index", "user list"), ("JBDCCZK Index", "search"),
                ("JBDPCZK Index", "search"), ("JBMCCZK Index", "search"), ("JBMPCZK Index", "search"),
                ("OECZFRAB Index", "search"), ("OEEOCZXA Index", "search"), (".REER_CZK G Index", "search")]
UNEMPLOYMENT_TICKERS = ["UMRTCZ Index", "CZJLUNR Index", "CZUEUR Index", "OECZRUAX Index", "OECZRUAW Index"]


def to_month(s: pd.Series) -> pd.Series:
    years = max((s.index.max() - s.index.min()).days / 365.25, 1.0)
    grouped = s.groupby(s.index.to_period("M"))
    return grouped.mean() if len(s) / years > 20 else grouped.last()


def load_probes(folders: list[Path]) -> dict[str, pd.Series]:
    raw: dict[str, pd.Series] = {}
    for folder in folders:
        if not (folder / "history_long.csv").exists():
            continue
        for ticker, g in pd.read_csv(folder / "history_long.csv", parse_dates=["observation_date"]).groupby("ticker"):
            s = pd.Series(g.value.to_numpy(float), index=pd.DatetimeIndex(g.observation_date)).sort_index()
            raw[ticker] = s[~s.index.duplicated(keep="last")]
    return {t: to_month(s) for t, s in raw.items()}


def pct(level: pd.Series) -> pd.Series:
    return 100.0 * (level / level.shift(1) - 1.0)


def yoy(level: pd.Series) -> pd.Series:
    return 100.0 * (level / level.shift(12) - 1.0)


def band(level: pd.Series) -> pd.Series:
    """Largest m/m error (pp) from rounding both levels to one decimal: 0.05/L_t + 0.05/L_(t-1), in percent."""
    return 100.0 * 0.05 * (1.0 / (level - 0.05) + 1.0 / (level.shift(1) - 0.05))


def cpi_levels(bbg: dict[str, pd.Series], out: Path) -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    lv = con.sql("""SELECT date, coicop_code, base, value FROM cpi_czso.cpi_long
                    WHERE subgroup_code='' AND hh_group_code='0' AND base IN ('base_2015_eq_100','base_2025_eq_100')""").df()
    con.close()
    lv["m"] = pd.PeriodIndex(pd.to_datetime(lv.date), freq="M")
    levels = {(c, b): g.set_index("m").value.sort_index() for (c, b), g in lv.groupby(["coicop_code", "base"])}
    rows = []
    for code, ticker in CZSO_TICKERS.items():
        b, ref = bbg[ticker], levels[(code, "base_2025_eq_100")]
        j = pd.concat([b.rename("bbg"), ref.rename("czso")], axis=1).dropna()
        gap = (j.bbg - j.czso).abs()
        rows.append(dict(coicop=code, ticker=ticker, n=len(j), first=str(j.index.min()), last=str(j.index.max()),
                         bloomberg_last=str(b.index.max()), exact_share=round(float((gap < 1e-9).mean()), 3), max_gap=round(float(gap.max()), 3)))
    table = pd.DataFrame(rows)
    table.to_csv(out / "cpi_levels_vs_czso_2025base.csv", index=False)
    print("A1. Bloomberg CZSO index levels vs CZSO's own 2025=100 levels")
    print(table.to_string(index=False))

    fixtures = {"0": ("Headline", cmp.fixture("target_headline_cpi_mm.csv"), "CZCPMOM Index"),
                "01": ("Food (01)", cmp.fixture("component_food_fuel_mm.csv", "food"), "CZCPFMOM Index"),
                "02": ("Alcohol and tobacco (02)", cmp.fixture("alcohol_tobacco.csv"), "CZCPAMOM Index")}
    rows, detail = [], []
    for code, (label, model_input, official_ticker) in fixtures.items():
        l15, l25, official = levels[(code, "base_2015_eq_100")], bbg[CZSO_TICKERS[code]], bbg[official_ticker]
        frame = pd.concat([model_input.rename("model_input"), pct(l15).rename("mm_2015base"), pct(l25).rename("mm_bbg_2025base"),
                           official.rename("official_1dp"), band(l15).rename("band_2015base"), band(l25).rename("band_2025base"),
                           l15.rename("level_2015base"), l25.rename("level_2025base")], axis=1).dropna()
        frame["gap_bbg_vs_model"] = frame.mm_bbg_2025base - frame.model_input
        frame["within_rounding_band"] = frame.gap_bbg_vs_model.abs() <= frame.band_2015base + frame.band_2025base + 1e-9
        detail.append(frame.assign(series=label))
        for window, mask in (("2015-2026", np.full(len(frame), True)), ("2015-2019", frame.index.year <= 2019),
                             ("2024-2026", frame.index.year >= 2024)):
            f = frame.loc[mask]
            rows.append(dict(series=label, window=window, n=len(f),
                             model_input_vs_2015base_mm_max=float((f.model_input - f.mm_2015base).abs().max()),
                             bbg_level_mm_equal_to_model_share=round(float((f.gap_bbg_vs_model.abs() <= 0.005).mean()), 3),
                             mean_abs_gap=round(float(f.gap_bbg_vs_model.abs().mean()), 3),
                             max_abs_gap=round(float(f.gap_bbg_vs_model.abs().max()), 3),
                             within_rounding_band_share=round(float(f.within_rounding_band.mean()), 3),
                             mean_band_2025base=round(float(f.band_2025base.mean()), 3), mean_band_2015base=round(float(f.band_2015base.mean()), 3),
                             rms_vs_official_2015base=round(float(np.sqrt(((f.mm_2015base - f.official_1dp) ** 2).mean())), 3),
                             rms_vs_official_bbg_2025base=round(float(np.sqrt(((f.mm_bbg_2025base - f.official_1dp) ** 2).mean())), 3),
                             rounds_to_official_2015base=round(float((f.mm_2015base.round(1) - f.official_1dp).abs().lt(1e-9).mean()), 3),
                             rounds_to_official_bbg_2025base=round(float((f.mm_bbg_2025base.round(1) - f.official_1dp).abs().lt(1e-9).mean()), 3)))
    table = pd.DataFrame(rows)
    table.to_csv(out / "cpi_mm_from_levels.csv", index=False)
    everything = pd.concat(detail).reset_index(names="month")
    everything.to_csv(out / "cpi_mm_from_levels_detail.csv", index=False)
    print("\nA2. m/m from the Bloomberg 2025=100 levels vs the model input (m/m from CZSO's 2015=100 levels) and the official 1dp m/m")
    print(table.to_string(index=False))
    worst = everything.loc[everything.gap_bbg_vs_model.abs().sort_values(ascending=False).index[:8]]
    print(worst[["month", "series", "level_2015base", "level_2025base", "model_input", "mm_bbg_2025base", "gap_bbg_vs_model",
                 "band_2015base", "band_2025base", "official_1dp"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def reer(bbg: dict[str, pd.Series], out: Path) -> None:
    rows = []
    for number, deflator in ((56, "PPI"), (57, "CPI")):
        ref, source = cmp.a6_row(number, "cnb_arad")
        ref_dlog, ref_yy = 100 * np.log(ref).diff(), yoy(ref)
        for ticker, listed in REER_TICKERS:
            if ticker not in bbg or bbg[ticker].dropna().empty:
                rows.append(dict(reference=source, deflator=deflator, ticker=ticker, listed=listed, n=0, note="no Bloomberg data"))
                continue
            b = bbg[ticker].dropna()
            b_dlog, b_yy = 100 * np.log(b).diff(), yoy(b)
            j = pd.concat([b_dlog.rename("b"), ref_dlog.rename("r")], axis=1).dropna()
            jy = pd.concat([b_yy.rename("b"), ref_yy.rename("r")], axis=1).dropna()
            common = pd.concat([b.rename("b"), ref.rename("r")], axis=1).dropna()
            base = common.loc[common.index.year == 2020]
            rebased = common.b / base.b.mean() * base.r.mean() if len(base) == 12 else common.b / common.b.mean() * common.r.mean()
            lags = [pd.concat([b_dlog.shift(k).rename("b"), ref_dlog.rename("r")], axis=1).dropna().corr().iloc[0, 1] for k in (-1, 0, 1)]
            rows.append(dict(reference=source, deflator=deflator, ticker=ticker, listed=listed, first=str(j.index.min()), last=str(j.index.max()),
                             n=len(j), corr_dlog=round(float(j.corr().iloc[0, 1]), 3), mae_dlog=round(float((j.b - j.r).abs().mean()), 3),
                             max_dlog=round(float((j.b - j.r).abs().max()), 2), dlog_within_0p1=round(float(((j.b - j.r).abs() <= 0.1).mean()), 3),
                             corr_dlog_bbg_lead_same_lag="/".join(f"{v:.2f}" for v in lags),
                             corr_yy=round(float(jy.corr().iloc[0, 1]), 3), mae_yy=round(float((jy.b - jy.r).abs().mean()), 2),
                             level_mae_rebased_2020=round(float((rebased - common.r).abs().mean()), 2)))
    table = pd.DataFrame(rows)
    table.to_csv(out / "reer_candidates.csv", index=False)
    print("\nB. REER candidates vs CNB ARAD (log m/m = paper transform 2)")
    print(table.drop(columns=["reference"]).to_string(index=False))


def unemployment(bbg: dict[str, pd.Series], out: Path) -> None:
    snap = pd.read_csv(ROOT / "data/vintages/unemployment_latest_snapshot.csv", dtype={"reference_period": str})
    vintages = pd.read_csv(ROOT / "data/vintages/unemployment.csv.gz", dtype={"reference_period": str})
    refs = {f"CZSO 15-64 {name.replace('unemployment_', '')}, release {g.release_date.iloc[0]}":
            pd.Series(g.value.to_numpy(float), index=pd.PeriodIndex(g.reference_period, freq="M")) for name, g in snap.groupby("series")}
    sa = vintages[vintages.series.eq("unemployment_sa")]
    sa = sa[sa.release_date.eq(sa.release_date.max())]
    refs[f"CZSO 15-64 sa, last SA release {sa.release_date.iloc[0]}"] = pd.Series(sa.value.to_numpy(float), index=pd.PeriodIndex(sa.reference_period, freq="M"))
    paper, source = cmp.a6_row(11)
    if len(paper):
        refs[source] = paper
    rows = []
    for name, ref in refs.items():
        for ticker in UNEMPLOYMENT_TICKERS:
            if ticker not in bbg:
                continue
            j = pd.concat([bbg[ticker].dropna().rename("b"), ref.rename("r")], axis=1).dropna()
            if len(j) < 12:
                continue
            monthly_rows = (np.diff(j.index.asi8) == 1).mean() > 0.9
            d, d12 = j.diff().dropna(), (j - j.shift(12)).dropna()
            gap = (j.b - j.r).abs()
            rows.append(dict(reference=name, ticker=ticker, first=str(j.index.min()), last=str(j.index.max()), n=len(j),
                             bloomberg_frequency="monthly" if monthly_rows else "quarterly", level_corr=round(float(j.corr().iloc[0, 1]), 4),
                             level_mae=round(float(gap.mean()), 3), level_max=round(float(gap.max()), 2), within_0p05=round(float((gap <= 0.05).mean()), 3),
                             change_1m_corr=round(float(d.corr().iloc[0, 1]), 3) if monthly_rows else np.nan,
                             change_12m_corr=round(float(d12.corr().iloc[0, 1]), 3) if monthly_rows and len(d12) > 12 else np.nan))
    table = pd.DataFrame(rows)
    table.to_csv(out / "unemployment_candidates.csv", index=False)
    print("\nC. Unemployment candidates")
    print(table.to_string(index=False))


def services(bbg: dict[str, pd.Series], out: Path) -> None:
    package = ROOT / "data/core_split"
    broad = pd.read_csv(package / "broad_yoy.csv", dtype={"target_month": str})
    broad.index = pd.PeriodIndex(broad.pop("target_month"), freq="M")
    groups = pd.read_csv(package / "monthly_levels.csv", dtype={"target_month": str})
    groups.index = pd.PeriodIndex(groups.pop("target_month"), freq="M")
    services_ref = "ARAD non-tradables excl. regulated prices, y/y (SCPICLEM03YOYPECNA)"
    goods_ref = "ARAD other tradables excl. food and fuel, y/y (SCPICLEM02YOYPECNA)"
    pairs = [(services_ref, broad["services"], "CPSVCZY Index", "HICP services, published y/y", lambda t: bbg[t]),
             (services_ref, broad["services"], "OECZGSJM Index", "OECD services less housing, y/y from level", lambda t: yoy(bbg[t])),
             (goods_ref, broad["goods"], "CPNGCZYY Index", "HICP non-energy industrial goods, published y/y", lambda t: bbg[t]),
             ("CZSO catering (111) m/m", pct(groups["catering"]), "CP1SCZ Index", "HICP catering, m/m from level", lambda t: pct(bbg[t])),
             ("CZSO catering (111) m/m", pct(groups["catering"]), "CP1SCZMM Index", "HICP catering, published m/m", lambda t: bbg[t]),
             ("CZSO accommodation (112) m/m", pct(groups["accommodation"]), "CP1ACZ Index", "HICP accommodation, m/m from level", lambda t: pct(bbg[t])),
             ("CZSO accommodation (112) m/m", pct(groups["accommodation"]), "CP1ACZMM Index", "HICP accommodation, published m/m", lambda t: bbg[t]),
             ("CZSO actual rent (041) m/m", pct(groups["actual_rent"]), "CP41CZ Index", "HICP actual rentals, m/m from level", lambda t: pct(bbg[t])),
             ("CZSO actual rent (041) m/m", pct(groups["actual_rent"]), "CP41CZMM Index", "HICP actual rentals, published m/m", lambda t: bbg[t]),
             ("CZSO actual rent (041) m/m", pct(groups["actual_rent"]), "OECZGSHA Index", "OECD services rent, m/m from level", lambda t: pct(bbg[t])),
             ("CZSO package holidays (098) m/m", pct(groups["package_holidays"]), "CP96CZ Index", "HICP package holidays, m/m from level", lambda t: pct(bbg[t])),
             ("CZSO package holidays (098) m/m", pct(groups["package_holidays"]), "CP96CZMM Index", "HICP package holidays, published m/m", lambda t: bbg[t])]
    rows: list = []
    for label, ref, ticker, transform, series in pairs:
        if ticker in bbg:
            cmp.compare(rows, label, "data/core_split (R10 package)", ticker, transform, series(ticker), ref, 0.1)
    table = pd.DataFrame(rows)
    table.to_csv(out / "services_candidates.csv", index=False)
    print("\nD. Services candidates (no Bloomberg series exists for CZSO imputed rent, group 042)")
    print(table.drop(columns=["reference"]).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    bbg = load_probes([p if p.is_absolute() else ROOT / p for p in args.probe])
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 300)
    cpi_levels(bbg, out)
    reer(bbg, out)
    unemployment(bbg, out)
    services(bbg, out)


if __name__ == "__main__":
    main()
