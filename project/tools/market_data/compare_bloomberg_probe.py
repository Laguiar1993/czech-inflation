"""Compare Bloomberg probe snapshots with the series the Czech CPI models use today.

  python tools/market_data/compare_bloomberg_probe.py \
      --probe data/market_snapshots/20260912_bloomberg_probe data/market_snapshots/20260912_bloomberg_probe2 \
      --output output/bloomberg_probe_comparison_20260912

Each comparison names the model input, the reference file it is read from, the Bloomberg ticker and the transform
(level, m/m or y/y from levels, or the published rate). Verdicts: identical (at least 95% of observations within the
tolerance and no gap above three tolerances), close (correlation at least 0.98) or different.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests/fixtures/cleanup"
A6_FILES = [ROOT / "data/paper_replication/a6_inputs_20260912/exact_inputs_long.csv",
            ROOT / "data/paper_replication/a6_exact_overrides_20260912/overrides_long.csv"]


def monthly(series: pd.Series) -> pd.Series:
    s = series.dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))


def mm(level: pd.Series) -> pd.Series:
    s = monthly(level)
    return 100.0 * (s / s.shift(1) - 1.0)


def yy(level: pd.Series) -> pd.Series:
    s = monthly(level)
    return 100.0 * (s / s.shift(12) - 1.0)


def compounded_yy(monthly_change: pd.Series) -> pd.Series:
    s = monthly(monthly_change)
    return 100.0 * np.expm1(np.log1p(s / 100.0).rolling(12).sum())


def fixture(name: str, column: str | int = 0) -> pd.Series:
    frame = pd.read_csv(FIX / name, index_col=0)
    frame.index = pd.PeriodIndex(frame.index, freq="M")
    return (frame.iloc[:, column] if isinstance(column, int) else frame[column]).astype(float)


def a6_row(number: int, source_prefix: str | None = None) -> tuple[pd.Series, str]:
    frame = pd.concat([pd.read_csv(p, dtype={"period": str}) for p in A6_FILES], ignore_index=True)
    frame = frame[frame.a6_number.eq(number) & frame.component.isna()]
    if source_prefix:
        frame = frame[frame.source_id.str.startswith(source_prefix)]
    frame = frame[~frame.period.str.contains("Q")]
    if frame.empty:
        return pd.Series(dtype=float), ""
    s = pd.Series(frame.value.to_numpy(float), index=pd.PeriodIndex(frame.period, freq="M"))
    kinds = ", ".join(sorted(frame.value_kind.astype(str).unique()))
    return s[~s.index.duplicated(keep="last")].sort_index(), f"A6 row {number}: {frame.source_id.iloc[-1]} ({kinds})"


def food_ppi_mm() -> pd.Series:
    """cz_struct.load_food_ppi_mm on the local CEN0201B file, without the live fetch that would rewrite it."""
    raw = pd.read_csv(ROOT / "data/cz_ppi_product_raw.csv", low_memory=False)
    sub = raw[(raw["CZCPA3.CZCPA_U2"].astype(str).str.replace(".0", "", regex=False) == "10") & raw["CZCPA3.CZCPA_U3"].isna()
              & (raw["TYPUDAJE5A"] == "IZ2015")]
    sub = sub[sub["CASMKMQRM12"].astype(str).str.match(r"^\d{4}-\d{2}$")]
    level = pd.Series(sub["Hodnota"].to_numpy(float), index=pd.PeriodIndex(sub["CASMKMQRM12"], freq="M")).groupby(level=0).last()
    return mm(level)


def power_of_ten(bbg: pd.Series, ref: pd.Series) -> float:
    joined = pd.concat([bbg.rename("b"), ref.rename("r")], axis=1).dropna()
    joined = joined[joined.r.abs() > 1e-9]
    if joined.empty:
        return 1.0
    ratio = float((joined.b / joined.r).median())
    scale = 10.0 ** round(np.log10(abs(ratio))) if ratio else 1.0
    return scale if abs(ratio / scale - 1.0) < 0.05 else 1.0


def compare(rows: list, label: str, reference: str, ticker: str, transform: str, bbg: pd.Series, ref: pd.Series, tol: float) -> None:
    joined = pd.concat([bbg.rename("bbg"), ref.rename("ref")], axis=1).dropna()
    if joined.empty:
        rows.append(dict(model_input=label, reference=reference, ticker=ticker, transform=transform, n=0, verdict="no overlap"))
        return
    gap = (joined.bbg - joined.ref).abs()
    within = float((gap <= tol + 1e-9).mean())
    corr = float(joined.corr().iloc[0, 1]) if len(joined) > 2 else np.nan
    verdict = "identical" if within >= 0.95 and gap.max() <= 3 * tol + 1e-9 else ("close" if corr >= 0.98 else "different")
    rows.append(dict(model_input=label, reference=reference, ticker=ticker, transform=transform, first=str(joined.index.min())[:10],
                     last=str(joined.index.max())[:10], n=len(joined), corr=round(corr, 4), mean_abs_gap=round(float(gap.mean()), 4),
                     max_abs_gap=round(float(gap.max()), 4), max_gap_at=str(gap.idxmax())[:10], share_within_tol=round(within, 3),
                     tol=tol, verdict=verdict))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    probes = [p if p.is_absolute() else ROOT / p for p in args.probe]
    out = args.output if args.output.is_absolute() else ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    coverage = pd.concat([pd.read_csv(p / "coverage.csv").assign(probe=p.name) for p in probes], ignore_index=True)
    history = pd.concat([pd.read_csv(p / "history_long.csv", parse_dates=["observation_date"]) for p in probes], ignore_index=True)
    history = history.drop_duplicates(["ticker", "observation_date"], keep="last")
    daily = {t: pd.Series(g.value.to_numpy(float), index=pd.DatetimeIndex(g.observation_date)).sort_index() for t, g in history.groupby("ticker")}
    bbg = {t: (s.groupby(s.index.to_period("M")).mean() if t.endswith("Govt") else s.groupby(s.index.to_period("M")).last()) for t, s in daily.items()}
    has = lambda t: t in bbg  # noqa: E731
    rows: list = []

    headline, food = fixture("target_headline_cpi_mm.csv"), fixture("component_food_fuel_mm.csv", "food")
    fuel, alcohol = fixture("component_food_fuel_mm.csv", "fuel"), fixture("alcohol_tobacco.csv")
    core, regulated = fixture("cnb_core_mm.csv"), fixture("cnb_regulated_mm.csv")
    features = pd.read_csv(FIX / "core_features.csv", index_col=0)
    features.index = pd.PeriodIndex(features.index, freq="M")
    imports = features.import_l2.copy()
    imports.index = imports.index - 2
    sitc = pd.read_csv(ROOT / "data/czso_import_prices_sitc_monthly.csv")
    sitc = pd.Series(sitc.value.to_numpy(float), index=pd.PeriodIndex(sitc.month, freq="M"))

    # --- CPI -------------------------------------------------------------------------------------------------
    if has("CZCPMOM Index"):
        compare(rows, "Headline CPI m/m", "fixture target_headline_cpi_mm, rounded 0.1", "CZCPMOM Index", "published m/m", bbg["CZCPMOM Index"], headline.round(1), 0.05)
    if has("CZCPYOY Index"):
        compare(rows, "Headline CPI y/y", "compounded from fixture m/m", "CZCPYOY Index", "published y/y", bbg["CZCPYOY Index"], compounded_yy(headline), 0.06)
    for ticker, label, ref in (("CZCPI Index", "Headline CPI m/m", headline), ("CZCPF Index", "CPI food (01) m/m", food), ("CZCPA Index", "CPI alcohol and tobacco (02) m/m", alcohol)):
        if has(ticker):
            compare(rows, label, "fixture (CZSO base-2015 index)", ticker, "m/m from 2025=100 level", mm(bbg[ticker]), ref, 0.05)
    if has("CZCIRM Index"):
        compare(rows, "CNB regulated prices m/m", "fixture cnb_regulated_mm (CNB ARAD)", "CZCIRM Index", "published m/m", bbg["CZCIRM Index"], regulated, 0.05)
    for ticker, label, ref in (("CZCIPM Index", "Headline CPI m/m", headline), ("CZCIFM Index", "CPI fuel (07.22) m/m", fuel),
                               ("CZCPFMOM Index", "CPI food (01) m/m", food), ("CZCPAMOM Index", "CPI alcohol and tobacco (02) m/m", alcohol)):
        if has(ticker):
            compare(rows, label, "fixture, rounded 0.1", ticker, "published m/m", bbg[ticker], ref.round(1), 0.05)
    services = features.services_l1.copy()
    services.index = services.index - 1          # row t of the fixture holds services m/m of t-1
    if has("CPSVCZM Index"):
        compare(rows, "CPI services m/m", "fixture services_l1 shifted back 1 month (CZSO cpi_services)", "CPSVCZM Index", "HICP services, published m/m", bbg["CPSVCZM Index"], services, 0.1)
    if has("CPSVCZ Index"):
        compare(rows, "CPI services m/m", "fixture services_l1 shifted back 1 month (CZSO cpi_services)", "CPSVCZ Index", "HICP services, m/m from level", mm(bbg["CPSVCZ Index"]), services, 0.1)
    for ticker in ("CZCIXM Index", "CZCINM Index", "CZCIMPM Index", "CZCIAM Index", "CZCICM Index"):
        if has(ticker):
            compare(rows, "CNB core inflation m/m", "fixture cnb_core_mm (CNB ARAD)", ticker, "published m/m", bbg[ticker], core, 0.05)
    if has("CPAPCZMM Index"):
        compare(rows, "CNB regulated prices m/m", "fixture cnb_regulated_mm (CNB ARAD)", "CPAPCZMM Index", "HICP administered, published m/m", bbg["CPAPCZMM Index"], regulated, 0.1)
    if has("CPEXCZM Index"):
        compare(rows, "CNB core inflation m/m", "fixture cnb_core_mm (CNB ARAD)", "CPEXCZM Index", "HICP core, published m/m", bbg["CPEXCZM Index"], core, 0.1)
    if has("CP7FCZ Index"):
        compare(rows, "CPI fuel (07.22) m/m", "fixture component_food_fuel_mm.fuel (CZSO)", "CP7FCZ Index", "HICP fuels, m/m from level", mm(bbg["CP7FCZ Index"]), fuel, 0.1)
    if has("CP7FCZMM Index"):
        compare(rows, "CPI fuel (07.22) m/m", "fixture component_food_fuel_mm.fuel (CZSO)", "CP7FCZMM Index", "HICP fuels, published m/m", bbg["CP7FCZMM Index"], fuel, 0.1)

    # --- producer and import prices ------------------------------------------------------------------------------
    ppi = food_ppi_mm()
    if has("CZPPA10M Index"):
        compare(rows, "Food-products PPI (CZ-CPA 10) m/m", "data/cz_ppi_product_raw.csv (CZSO CEN0201B)", "CZPPA10M Index", "published m/m", bbg["CZPPA10M Index"], ppi, 0.1)
    if has("EPT010CZ Index"):
        compare(rows, "Food-products PPI (CZ-CPA 10) m/m", "data/cz_ppi_product_raw.csv (CZSO CEN0201B)", "EPT010CZ Index", "Eurostat index, m/m from level", mm(bbg["EPT010CZ Index"]), ppi, 0.1)
    arad26, source26 = a6_row(26, "cnb_arad")
    for ticker, transform in (("CZEII Index", "m/m from level"), ("CZEIIMOM Index", "published m/m")):
        if has(ticker):
            series = mm(bbg[ticker]) if transform == "m/m from level" else bbg[ticker]
            compare(rows, "Import prices m/m", "fixture import_l2 shifted back 2 months (CZSO CEN0301)", ticker, transform, series, imports, 0.1)
            compare(rows, "Import prices m/m", "data/czso_import_prices_sitc_monthly.csv (CZSO CEN0303)", ticker, transform, series, sitc, 0.1)
            if len(arad26):
                compare(rows, "A6 row 26 import prices", source26, ticker, transform, series, arad26 - 100.0, 0.1)

    # --- surveys and labour ----------------------------------------------------------------------------------------
    for ticker, column, number in (("EUA8CZ Index", "household_exp", 72), ("EUA7CZ Index", None, 71)):
        if has(ticker):
            if column:
                compare(rows, "Household price expectations (BS-PT-NY)", "fixture core_features.household_exp", ticker, "level", bbg[ticker], features[column], 0.05)
            ref, source = a6_row(number)
            compare(rows, f"A6 row {number}", source, ticker, "level", bbg[ticker], ref, 0.05)
    for ticker in ("EUESCZ Index", "CZCCCOM Index"):
        if has(ticker):
            compare(rows, "Economic sentiment indicator", "fixture core_features.esi (Eurostat)", ticker, "level", bbg[ticker], features.esi, 0.05)
    unemployment = pd.read_csv(ROOT / "data/vintages/unemployment_latest_snapshot.csv", dtype={"reference_period": str})
    for series_name, g in unemployment.groupby("series"):
        ref = pd.Series(g.value.to_numpy(float), index=pd.PeriodIndex(g.reference_period, freq="M"))
        for ticker in ("CZUEUR Index", "UMRTCZ Index", "CZJLUNR Index"):
            if has(ticker):
                compare(rows, f"Unemployment rate ({series_name})", "data/vintages/unemployment_latest_snapshot.csv (CZSO)", ticker, "level", bbg[ticker], ref, 0.05)

    # --- CNB-paper inputs (Table A6 rows) --------------------------------------------------------------------------
    specs = [("EUPPCZY Index", 44, None, "published y/y", 0.05), ("EPT00BCZ Index", 46, None, "m/m from levels", 0.1),
             ("EPT00CCZ Index", 47, None, "m/m from levels", 0.1), ("CZPPAYOY Index", 52, None, "published m/m vs index-100", 0.1),
             ("CZPPAMOM Index", 52, None, "published rate vs index-100", 0.1), ("GTCZK10Y Govt", 53, None, "monthly mean level", 0.05),
             ("CZBRREPO Index", 55, None, "month-end level", 0.01), ("BISBCZR Index", 57, None, "m/m from levels", 0.1),
             ("OECZFRAA Index", 57, None, "m/m from levels", 0.1), ("BRERCZ Index", 57, None, "m/m from levels", 0.1),
             ("BISBCZR Index", 56, None, "m/m from levels", 0.1), ("CZBLHPTV Index", 59, None, "y/y from levels", 0.2),
             ("CZBLHHTV Index", 59, None, "y/y from levels", 0.2), ("CZHHHHTV Index", 59, None, "y/y from levels", 0.2),
             ("LONSCZHH Index", 59, None, "y/y from levels", 0.2), ("CZTBAL Index", 25, None, "scaled level", 1.0),
             ("CZTBNAL Index", 25, None, "scaled level", 1.0), ("CZCMTRBA Index", 25, None, "scaled level", 1.0)]
    for ticker, number, prefix, transform, tol in specs:
        if not has(ticker):
            continue
        ref, source = a6_row(number, prefix)
        if ref.empty:
            continue
        b = bbg[ticker]
        if transform == "m/m from levels":
            b, ref = mm(b), mm(ref)
        elif transform.endswith("index-100"):
            ref = ref - 100.0
        elif transform == "y/y from levels":
            b, ref = yy(b), yy(ref)
        elif transform == "scaled level":
            scale = power_of_ten(b, ref)
            b, transform = b / scale, f"level divided by {scale:g}"
        compare(rows, f"A6 row {number}", source, ticker, transform, b, ref, tol)

    # --- weekly pump prices (EC Weekly Oil Bulletin) ------------------------------------------------------------------
    # Bloomberg dates the bulletin on the Friday after its Monday price date, so both sides are keyed by ISO week.
    week = lambda s: s.groupby(s.index.to_period("W-SUN")).last()  # noqa: E731
    pump = pd.read_csv(ROOT / "data/research_r14/fuel/pump_weekly.csv", parse_dates=["date"]).set_index("date")
    czso_weekly = pd.read_csv(FIX / "fuel_weekly.csv", parse_dates=["date"]).set_index("date")
    for ticker, column, czso_column in (("ECOBETCZ Index", "gross_petrol95", "petrol95"), ("ECOBOTCZ Index", "gross_diesel", "diesel"),
                                        ("ECOBEFCZ Index", "net_petrol95", None), ("ECOBOFCZ Index", "net_diesel", None)):
        if ticker not in daily:
            continue
        b, ref = week(daily[ticker]), week(pump[column])
        scale = power_of_ten(b, ref)
        compare(rows, f"EC Oil Bulletin {column} (CZK/l)", "data/research_r14/fuel/pump_weekly.csv", ticker, f"ISO-week level divided by {scale:g}", b / scale, ref, 0.01)
        if czso_column:
            compare(rows, f"CZSO weekly {czso_column} (CZK/l)", "fixture fuel_weekly.csv (CZSO CENPHMT, Mondays)", ticker,
                    f"ISO-week level divided by {scale:g}", b / scale, week(czso_weekly[czso_column]), 0.2)

    table = pd.DataFrame(rows)
    table.to_csv(out / "comparisons.csv", index=False)
    coverage.to_csv(out / "ticker_validity.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 48)
    bad = coverage[~coverage.status.eq("ok")]
    print(f"tickers probed {len(coverage)}: valid {int(coverage.status.eq('ok').sum())}; invalid or empty {len(bad)}")
    if len(bad):
        print(bad[["probe", "ticker", "status", "error"]].to_string(index=False))
    fresh = coverage[coverage.probe.eq(probes[-1].name)]
    print(fresh[["group", "ticker", "status", "name", "source", "adjustment", "first_date", "last_date"]].to_string(index=False))
    print()
    print(table.drop(columns=["reference"]).to_string(index=False))
    search = probes[-1] / "instrument_search.json"
    if search.exists():
        found = json.loads(search.read_text(encoding="utf-8"))
        summary = []
        for query, hits in found.items():
            czech = [h for h in hits if "CZ" in h["security"].upper() or "czech" in h["description"].lower()]
            summary.append({"query": query, "hits": [f"{h['security']} | {h['description']}" for h in czech]})
        (out / f"instrument_search_{probes[-1].name}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print("\nINSTRUMENT SEARCH (Czech hits):")
        for item in summary:
            print(f"- {item['query']}:")
            for hit in item["hits"][:25]:
                print(f"    {hit}")


if __name__ == "__main__":
    main()
