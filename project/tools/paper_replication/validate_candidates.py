"""Validate the imported Bloomberg Table A6 candidates against official sources.

Nothing here admits a series to the exact paper panel.  For every candidate
the output records what it was compared with, the statistics and a verdict
under the thresholds below, which were declared before the first full
comparison was run (12 September 2026).

Survey balances are compared value by value with every monthly ECFIN series
of the same geography, seasonally adjusted and unadjusted, so a mnemonic that
belongs to a different question is found rather than assumed.  Where ECFIN
publishes identical adjusted and unadjusted values for a question, the tie is
reported instead of being resolved by row order.  The official ECFIN download
is also checked against the Eurostat series that the paper's wording points
to.  Hard-data candidates are compared with official or authority series
available offline, in levels where units agree and in growth rates where
bases or currencies differ.

All inputs are current vintages.  Agreement validates identity and
definition, not historical real-time availability.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.paper_replication.a6_catalog import BY_NUMBER, ROWS, ecfin_nsa_code  # noqa: E402
from tools.paper_replication.import_bloomberg_candidates import REGISTRY, sha256_file  # noqa: E402

DATA = ROOT / "data" / "paper_replication"
CANDIDATES = DATA / "bloomberg_candidates_20260911_full_refresh" / "candidate_periods_long.csv"
ECFIN = DATA / "official_bcs_ecfin_2608" / "ecfin_bcs_long.csv"
EUROSTAT = DATA / "official_eurostat_20260912" / "tidy"
DEFAULT_OUTPUT = ROOT / "output" / "cnb_paper_candidate_validation_20260912"

# Thresholds declared before the first comparison.
MIN_OVERLAP = 60                 # months
MIN_OVERLAP_SHORT = 24           # short official comparators (permits, quarterly ULC)
IDENTICAL_TOL = 0.051            # one-decimal values: equal, allowing a rounding tie
IDENTICAL_SHARE = 0.95
MIRROR_MAE = 0.5                 # balance points: SA re-estimation noise, not another question
MIRROR_CORR_LEVEL = 0.98
MIRROR_CORR_DIFF = 0.90
APPROX_MAE = 2.0
APPROX_CORR_LEVEL = 0.90
RECENT = 36
PRICE_GROWTH_MAE = 0.10          # percentage points, same index at different bases
PRICE_GROWTH_CORR = 0.98
IP_GROWTH_MAE = 0.50
IP_GROWTH_CORR = 0.95
YOY_MAE = 1.0
YOY_CORR = 0.98
ULC_YOY_MAE = 0.15
RATE_MAE = 0.02                  # percentage points, monthly average of the same fixing
LOAN_GROWTH_CORR = 0.90
RUSHIN_CORR = 0.90

EUROSTAT_GEO = {"CZ": "CZ", "DE": "DE", "PL": "PL", "EA": "EA20"}


def series(values, index, freq: str = "M") -> pd.Series:
    """Numeric series on a contiguous PeriodIndex (gaps stay missing)."""
    s = pd.Series(pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(),
                  index=pd.PeriodIndex([str(i) for i in index], freq=freq))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if len(s):
        s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq=freq))
    return s


def compare(a: pd.Series, b: pd.Series, tol: float = IDENTICAL_TOL, recent: int = RECENT) -> dict:
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1).sort_index()
    if len(both):
        both = both.reindex(pd.period_range(both.index.min(), both.index.max(), freq=both.index.freq))
    level = both.dropna()
    out = {"n": int(len(level))}
    if level.empty:
        return out
    d = level["a"] - level["b"]
    diffs = both.diff().dropna()
    tail = d.iloc[-recent:]
    out.update(first=str(level.index.min()), last=str(level.index.max()),
               mae=float(d.abs().mean()), max_abs=float(d.abs().max()), mean_diff=float(d.mean()),
               share_identical=float((d.abs() < tol).mean()),
               corr_level=float(level["a"].corr(level["b"])) if len(level) > 2 else np.nan,
               corr_diff=float(diffs["a"].corr(diffs["b"])) if len(diffs) > 2 else np.nan,
               mae_recent=float(tail.abs().mean()), share_identical_recent=float((tail.abs() < tol).mean()))
    return out


def growth(s: pd.Series, lag: int = 1, log: bool = False) -> pd.Series:
    if log:
        return 100.0 * np.log(s / s.shift(lag))
    return 100.0 * (s / s.shift(lag) - 1.0)


def _candidate(cands: pd.DataFrame, ticker: str, statistic: str, freq: str = "M") -> pd.Series:
    sub = cands[cands.ticker.eq(ticker) & cands.statistic.eq(statistic)]
    return series(sub.value, sub.period, freq)


def ticker_geo(ticker: str) -> str | None:
    root = ticker.split()[0]
    for suffix, geo in (("EMU", "EA"), ("CZ", "CZ"), ("DE", "DE"), ("PL", "PL")):
        if root.endswith(suffix):
            return geo
    return None


def _close(stats: dict) -> bool:
    return (stats.get("n", 0) >= MIN_OVERLAP and stats["mae"] <= MIRROR_MAE
            and stats["corr_level"] >= MIRROR_CORR_LEVEL and stats["corr_diff"] >= MIRROR_CORR_DIFF)


def bcs_verdict(matrix: pd.DataFrame, intended_sa: str | None) -> tuple[str, dict]:
    """Classify one survey ticker from its comparison matrix.

    Ties on MAE are broken in favour of the seasonally adjusted series and are
    then reported through ``official_sa_equals_nsa`` by the caller.
    """
    eligible = matrix[matrix.n >= MIN_OVERLAP].sort_values(["mae", "official_sa"], ascending=[True, False])
    if eligible.empty:
        return "insufficient_overlap", {}
    best = eligible.iloc[0].to_dict()
    if intended_sa is None:
        return ("diagnostic_matches_" + best["official_code"]) if _close(best) else "diagnostic_no_close_match", best
    intended = {intended_sa: "SA", ecfin_nsa_code(intended_sa): "NSA"}
    if best["official_code"] in intended and _close(best):
        tag = "identical" if best["share_identical"] >= IDENTICAL_SHARE else "validated_mirror"
        return f"{tag}_{intended[best['official_code']]}", best
    if _close(best):
        return "matches_other_official_series", best
    row = matrix[matrix.official_code.eq(intended_sa)]
    if not row.empty:
        r = row.iloc[0]
        if r.n >= MIN_OVERLAP and r.mae <= APPROX_MAE and r.corr_level >= APPROX_CORR_LEVEL:
            return "approximate_not_validated", best
    return "mismatch", best


def validate_bcs(cands: pd.DataFrame, ecfin: pd.DataFrame, bdp: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = ecfin[ecfin.frequency.eq("M") & ecfin.survey.ne("MAIN")]
    official = {code: series(g.value, g.period) for code, g in monthly.groupby("series_code")}
    matrices, verdicts = [], []
    for ticker, cand in REGISTRY.items():
        if cand.rule != "ec_bcs_next_month":
            continue
        a = _candidate(cands, ticker, "as_reported")
        geo = ticker_geo(ticker)
        geos = {"EA", "EU"} if geo == "EA" else {geo}
        rows = []
        for code, b in official.items():
            if code.split(".")[1] not in geos:
                continue
            stats = compare(a, b)
            stats.update(ticker=ticker, official_code=code, official_sa=code.split(".")[4].endswith("S"))
            rows.append(stats)
        matrix = pd.DataFrame(rows)
        matrix["rank_by_mae"] = matrix["mae"].where(matrix.n >= MIN_OVERLAP).rank(method="min")
        matrices.append(matrix)
        intended_codes = [BY_NUMBER[n].ecfin for n in cand.a6 if BY_NUMBER[n].ecfin]
        intended_sa = intended_codes[0] if intended_codes else None
        verdict, best = bcs_verdict(matrix, intended_sa)
        hit = matrix[matrix.official_code.eq(intended_sa)].head(1) if intended_sa else matrix.head(0)
        intended = hit.iloc[0].to_dict() if len(hit) else {}
        # Does ECFIN publish identical SA and NSA values for the matched question?
        best_code = best.get("official_code")
        sa_nsa = {}
        if isinstance(best_code, str) and best_code.split(".")[4].endswith("S"):
            nsa = ecfin_nsa_code(best_code)
            if nsa in official:
                sa_nsa = compare(official[best_code], official[nsa])
        label = bdp.get(ticker)
        verdicts.append({
            "ticker": ticker, "a6_numbers": ";".join(map(str, cand.a6)), "role": cand.role, "geo": geo,
            "bloomberg_seasonality": label, "intended_official_code": intended_sa,
            "intended_n": intended.get("n"), "intended_mae": intended.get("mae"),
            "intended_share_identical": intended.get("share_identical"),
            "intended_corr_level": intended.get("corr_level"), "intended_corr_diff": intended.get("corr_diff"),
            "best_official_code": best_code, "best_n": best.get("n"), "best_mae": best.get("mae"),
            "best_max_abs": best.get("max_abs"), "best_share_identical": best.get("share_identical"),
            "best_corr_level": best.get("corr_level"), "best_corr_diff": best.get("corr_diff"),
            "best_mae_recent": best.get("mae_recent"), "best_first": best.get("first"), "best_last": best.get("last"),
            "best_is_sa": best.get("official_sa"),
            "official_sa_equals_nsa_share": sa_nsa.get("share_identical"),
            "official_sa_nsa_mae": sa_nsa.get("mae"),
            "bloomberg_label_says_sa": (label.endswith(" SA") if isinstance(label, str) else None),
            "verdict": verdict,
        })
    return pd.concat(matrices, ignore_index=True), pd.DataFrame(verdicts)


def ecfin_vs_eurostat(ecfin: pd.DataFrame, eurostat_dir: Path) -> pd.DataFrame:
    """Check that each official ECFIN series equals the Eurostat series the paper names."""
    monthly = ecfin[ecfin.frequency.eq("M")]
    official = {code: series(g.value, g.period) for code, g in monthly.groupby("series_code")}
    tidy = {p.stem: pd.read_csv(p) for p in Path(eurostat_dir).glob("ei_bs*.csv")}
    rows = []
    for row in ROWS:
        if not row.eurostat or not row.ecfin:
            continue
        dataset, indic = row.eurostat.split(":")
        frame = tidy[dataset]
        geos = ["EA20", "EA21"] if row.geo == "EA" else [EUROSTAT_GEO[row.geo]]
        for geo in geos:
            mask = frame.indic.eq(indic) & frame.s_adj.eq("SA") & frame.geo.eq(geo)
            if "unit" in frame.columns and not indic.endswith(("-BAL", "-PC")):
                mask &= frame.unit.eq("BAL")
            sub = frame[mask]
            stats = compare(official.get(row.ecfin, pd.Series(dtype=float)), series(sub.value, sub.time))
            enough = stats.get("n", 0) >= MIN_OVERLAP
            rows.append({"a6_number": row.number, "ecfin_code": row.ecfin, "eurostat": f"{row.eurostat}:SA:{geo}",
                         "eurostat_rows": int(len(sub)), **stats,
                         "verdict": ("identical" if enough and stats["share_identical"] >= IDENTICAL_SHARE
                                     else "different" if enough else "insufficient_overlap")})
    return pd.DataFrame(rows)


def _eurostat(eurostat_dir: Path, name: str) -> pd.DataFrame:
    path = Path(eurostat_dir) / f"{name}.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _hard_row(ticker, comparator, basis, stats, verdict, note="", **extra) -> dict:
    cand = REGISTRY[ticker]
    return {"ticker": ticker, "a6_numbers": ";".join(map(str, cand.a6)), "role": cand.role,
            "comparator": comparator, "basis": basis, **stats, **extra, "verdict": verdict, "note": note}


def validate_hard(cands: pd.DataFrame, eurostat_dir: Path, root: Path = ROOT) -> pd.DataFrame:
    rows = []
    data = root / "data"

    # A6 #12: Bloomberg SA industrial production against the CZSO PRU01C adjusted level.
    ip = pd.read_csv(data / "cz_ip_sa_level.csv")
    a, b = _candidate(cands, "CZIPITS Index", "as_reported"), series(ip.Hodnota, ip.ym)
    s = compare(growth(a, log=True), growth(b, log=True), tol=0.01)
    ok = s.get("n", 0) >= MIN_OVERLAP and s["mae"] <= IP_GROWTH_MAE and s["corr_level"] >= IP_GROWTH_CORR
    rows.append(_hard_row("CZIPITS Index", "CZSO PRU01C seasonally and calendar adjusted level (data/cz_ip_sa_level.csv)",
                          "100*dlog", s, "validated_mirror" if ok else "not_validated",
                          "different base years; growth rates compared",
                          level_log_ratio_std=float(np.log(a / b).std())))

    # A6 #11 and #24: unemployment rates against Eurostat une_rt_m (SA, total, 15-74).
    une = _eurostat(eurostat_dir, "une_rt_m_cz_de")
    for ticker, geo in (("UMRTCZ Index", "CZ"), ("UMRTDE Index", "DE")):
        sub = une[une.geo.eq(geo) & une.s_adj.eq("SA") & une.age.eq("TOTAL") & une.sex.eq("T") & une.unit.eq("PC_ACT")]
        s = compare(_candidate(cands, ticker, "as_reported"), series(sub.value, sub.time))
        enough = s.get("n", 0) >= MIN_OVERLAP
        verdict = ("identical" if enough and s["share_identical"] >= IDENTICAL_SHARE
                   else "validated_mirror" if enough and s["mae"] <= 0.1 else "not_validated")
        rows.append(_hard_row(ticker, f"Eurostat une_rt_m {geo} SA TOTAL T PC_ACT", "level", s, verdict))

    # A6 #23: German HICP level against Eurostat (2025=100) and growth against the 2015=100 series.
    minr = _eurostat(eurostat_dir, "prc_hicp_minr_de_total")
    midx = _eurostat(eurostat_dir, "prc_hicp_midx_de_cp00")
    a = _candidate(cands, "GRCPHCPI Index", "as_reported")
    sub = minr[minr.unit.eq("I25")]
    s_level = compare(a, series(sub.value, sub.time))
    enough = s_level.get("n", 0) >= MIN_OVERLAP
    rows.append(_hard_row("GRCPHCPI Index", "Eurostat prc_hicp_minr DE TOTAL I25", "level", s_level,
                          "identical" if enough and s_level["share_identical"] >= IDENTICAL_SHARE else "not_identical",
                          "Bloomberg rounds the 2025=100 level to one decimal"))
    sub = midx[midx.unit.eq("I15")]
    s = compare(growth(a, log=True), growth(series(sub.value, sub.time), log=True), tol=0.01)
    ok = s.get("n", 0) >= MIN_OVERLAP and s["mae"] <= PRICE_GROWTH_MAE and s["corr_level"] >= PRICE_GROWTH_CORR
    rows.append(_hard_row("GRCPHCPI Index", "Eurostat prc_hicp_midx DE CP00 I15 (ends 2025-12)", "100*dlog", s,
                          "validated_mirror" if ok else "not_validated", "one-decimal rounding of the level adds noise"))

    # A6 #26: Czech import prices against CZSO CEN0303 month-on-month changes.
    imp = pd.read_csv(data / "research_r14b" / "imports" / "imports_monthly_verified.csv")
    s = compare(growth(_candidate(cands, "CZEII Index", "as_reported")), series(imp.import_mm, imp.source_month))
    ok = s.get("n", 0) >= MIN_OVERLAP and s["mae"] <= PRICE_GROWTH_MAE and s["corr_level"] >= PRICE_GROWTH_CORR
    rows.append(_hard_row("CZEII Index", "CZSO CEN0303 SITC total import price index, m/m % (imports_monthly_verified.csv)",
                          "100*(X/X[-1]-1)", s, "validated_mirror" if ok else "not_validated",
                          "CZSO publishes one decimal; the Bloomberg level is also rounded"))

    # A6 #13: permit counts against the CZSO year-on-year index of permits (latest release per month).
    con = pd.read_csv(data / "paper_replication" / "czso_construction_release.csv", low_memory=False)
    permits = _candidate(cands, "CZGRIDX Index", "as_reported")
    cumulative = permits.groupby(permits.index.year).cumsum()
    for code in sorted(c for c in con.code.astype(str).unique() if "stavebních_povo" in c):
        sub = con[con.code.eq(code)].sort_values(["data_month", "release_date"]).drop_duplicates("data_month", keep="last")
        official = series(sub.yoy_index, pd.to_datetime(sub.data_month).dt.to_period("M"))
        for basis, cand_yoy in (("monthly count yoy index", 100.0 * permits / permits.shift(12)),
                                ("year-to-date cumulative yoy index", 100.0 * cumulative / cumulative.shift(12))):
            s = compare(cand_yoy, official)
            ok = s.get("n", 0) >= MIN_OVERLAP_SHORT and s["mae"] <= YOY_MAE and s["corr_level"] >= YOY_CORR
            rows.append(_hard_row("CZGRIDX Index", f"CZSO construction release code {code}", basis, s,
                                  "validated_mirror" if ok else "not_validated",
                                  f"overlap below the declared {MIN_OVERLAP_SHORT} months"
                                  if s.get("n", 0) < MIN_OVERLAP_SHORT else ""))

    # A6 #17: quarterly ULC growth against Eurostat namq_10_lp_ulc variants.
    ulc = _eurostat(eurostat_dir, "namq_10_lp_ulc_cz")
    q = _candidate(cands, "LCTQCZI Index", "as_reported", freq="Q")
    for (item, adj, unit), sub in ulc.groupby(["na_item", "s_adj", "unit"]) if not ulc.empty else []:
        cand = growth(q, 4) if unit == "PCH_SM" else growth(q, 1)
        s = compare(cand, series(sub.value, sub.time, freq="Q"))
        ok = s.get("n", 0) >= MIN_OVERLAP_SHORT and s["mae"] <= ULC_YOY_MAE and s["corr_level"] >= PRICE_GROWTH_CORR
        rows.append(_hard_row("LCTQCZI Index", f"Eurostat namq_10_lp_ulc CZ {item} {adj} {unit}",
                              "quarterly growth", s, "validated_mirror" if ok else "not_validated"))

    # A6 #58: NFC loan stock in CZK against the ARAD VST total (ARAD stores CZK units).
    arad = pd.read_csv(data / "paper_replication" / "arad_selected.csv")
    nfc = arad[arad.indicator_id.eq("SUCM100311XXX101101")]
    official = series(nfc.value, pd.to_datetime(nfc.period).dt.to_period("M"))
    loans = _candidate(cands, "LONSCZNF Index", "as_reported")
    for fx_stat in ("month_last", "month_mean"):
        czk = loans * 1e6 * _candidate(cands, "EURCZK Curncy", fx_stat)
        s = compare(growth(czk, log=True), growth(official, log=True), tol=0.01)
        ok = s.get("n", 0) >= MIN_OVERLAP and s["corr_level"] >= LOAN_GROWTH_CORR
        both = pd.concat([czk, official], axis=1).dropna()
        rows.append(_hard_row("LONSCZNF Index", "CNB ARAD SUCM100311XXX101101 (VST NFC client loans, CZK)",
                              f"100*dlog, EUR mn converted with EURCZK {fx_stat}", s,
                              "validated_proxy" if ok else "not_validated",
                              "ECB/MFI perimeter is not the VST commercial-bank perimeter; never an exact mirror",
                              level_ratio_median=float((both.iloc[:, 0] / both.iloc[:, 1]).median()) if len(both) else np.nan,
                              level_corr=float(both.iloc[:, 0].corr(both.iloc[:, 1])) if len(both) > 2 else np.nan))

    # A6 #54: PRIBOR fixings; the monthly mean must reproduce the ARAD monthly average.
    pribor = arad[arad.indicator_id.eq("SFTP04M2206")]
    official = series(pribor.value, pd.to_datetime(pribor.period).dt.to_period("M"))
    s = compare(_candidate(cands, "PRIB03M Index", "month_mean"), official, tol=0.011)
    ok = s.get("n", 0) >= MIN_OVERLAP and s["mae"] <= RATE_MAE
    gap = compare(_candidate(cands, "PRIB03M Index", "month_last"), _candidate(cands, "PRIB03M Index", "month_mean"))
    rows.append(_hard_row("PRIB03M Index", "CNB ARAD SFTP04M2206 (PRIBOR 3M monthly average)", "monthly mean level", s,
                          "validated_mirror" if ok else "not_validated",
                          "validates the daily fixings; A6 #54 uses the month-end fixing",
                          month_end_vs_mean_mae=gap.get("mae"), month_end_vs_mean_max_abs=gap.get("max_abs")))

    # A6 #14: Rushin weekly estimates against the CNB workbook monthly series in the frozen panel.
    panel = pd.read_csv(data / "paper_replication" / "paper_predictor_panel.csv")
    local = series(panel.rushin, pd.to_datetime(panel.date).dt.to_period("M"))
    for stat in ("week_mean", "week_last"):
        s = compare(_candidate(cands, "CZRUSHIN Index", stat), local)
        enough = s.get("n", 0) >= MIN_OVERLAP
        verdict = ("identical" if enough and s["share_identical"] >= IDENTICAL_SHARE
                   else "concept_match" if enough and s["corr_level"] >= RUSHIN_CORR else "not_validated")
        rows.append(_hard_row("CZRUSHIN Index", "CNB Rushin monthly series in the frozen panel (paper_predictor_panel.csv:rushin)",
                              f"level, Bloomberg {stat}", s, verdict,
                              "the paper does not state how weekly estimates become months"))

    # A6 #60: front-month ICE Brent against dated Brent spot (EIA series in the R14 fuel snapshot).
    brent = pd.read_csv(data / "research_r14" / "fuel" / "brent_daily.csv", parse_dates=["date"])
    spot = brent.groupby(brent.date.dt.to_period("M"))["brent_usd"].mean()
    spot = series(spot.values, spot.index)
    front = _candidate(cands, "CO1 Comdty", "month_mean")
    s = compare(front, spot, tol=0.5)
    rows.append(_hard_row("CO1 Comdty", "Europe Brent spot FOB, monthly mean (data/research_r14/fuel/brent_daily.csv)",
                          "level USD", s, "proxy_quality_reported", "front-month future versus spot",
                          corr_dlog=compare(growth(front, log=True), growth(spot, log=True)).get("corr_level")))

    for ticker in ("TTFGDAHD BCFV Index", "BCOMINSP Index", "BCOMAGSP Index", "TTFGCY1 Index", "FSBTY1 Index"):
        rows.append(_hard_row(ticker, "none: the paper does not identify the index or contract", "n/a", {"n": 0},
                              "no_official_comparator", REGISTRY[ticker].note))
    return pd.DataFrame(rows)


def run(output: Path = DEFAULT_OUTPUT, candidates: Path = CANDIDATES, ecfin_path: Path = ECFIN,
        eurostat_dir: Path = EUROSTAT) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cands = pd.read_csv(candidates)
    catalog = pd.read_csv(Path(candidates).with_name("candidate_catalog.csv"))
    bdp = dict(zip(catalog.ticker, catalog.bdp_seasonality))
    ecfin = pd.read_csv(ecfin_path)
    matrix, bcs = validate_bcs(cands, ecfin, bdp)
    identity = ecfin_vs_eurostat(ecfin, eurostat_dir)
    hard = validate_hard(cands, eurostat_dir)
    paths = {"bcs_matrix": output / "bcs_match_matrix.csv", "bcs_verdicts": output / "bcs_candidate_verdicts.csv",
             "ecfin_vs_eurostat": output / "ecfin_vs_eurostat_identity.csv",
             "hard_checks": output / "hard_candidate_checks.csv"}
    matrix.to_csv(paths["bcs_matrix"], index=False)
    bcs.to_csv(paths["bcs_verdicts"], index=False)
    identity.to_csv(paths["ecfin_vs_eurostat"], index=False)
    hard.to_csv(paths["hard_checks"], index=False)
    thresholds = {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float))}
    manifest = {
        "tool": "validate_candidates", "created_at": datetime.now(timezone.utc).isoformat(),
        "thresholds_declared_before_run": thresholds,
        "inputs": {str(p): sha256_file(p) for p in [Path(candidates), Path(ecfin_path)]
                   + sorted(Path(eurostat_dir).glob("*.csv"))},
        "outputs": {k: {"file": p.name, "sha256": sha256_file(p)} for k, p in paths.items()},
        "tool_sha256": sha256_file(Path(__file__)),
        "status": "validation evidence only; admission is decided in the A6 audit",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = run(args.output)
    print(json.dumps(result["outputs"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
