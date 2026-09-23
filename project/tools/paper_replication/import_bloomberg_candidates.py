"""Import an immutable Bloomberg capture as a separate CNB WP 9/2026 candidate panel.

The snapshot folder is read-only input.  Its MANIFEST hashes are verified
before anything is read, and nothing is written back into it.

The output is a *candidate* panel.  A Bloomberg history does not become an
exact Table A6 input by being imported: `validate_candidates.py` compares it
with the official source, and the A6 audit decides admission.  Exact inputs
are assembled separately from official downloads.  Every output column name
in the wide file therefore starts with ``bbg__``.

Monthly statistical observations keep their Bloomberg observation date.
Daily and weekly quotes are aggregated explicitly; the month mean and the
last quote of the month are different statistics and are kept apart.
``available_from_assumed`` comes from a declared rule for each series.  It is
not a publication timestamp: Bloomberg returns current-vintage histories and
``ECO_RELEASE_DT`` is only the next scheduled release at the pull.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT = ROOT / "data" / "market_snapshots" / "20260911_bloomberg_full_refresh"
DEFAULT_OUTPUT = ROOT / "data" / "paper_replication" / "bloomberg_candidates_20260911_full_refresh"
TOOL = "import_bloomberg_candidates"


@dataclass(frozen=True)
class Candidate:
    a6: tuple[int, ...]
    role: str        # a6_candidate, a6_challenger, a6_benchmark, conversion, diagnostic, legacy, not_a6, invalid_ticker
    frequency: str   # daily, weekly, monthly, quarterly, annual, none
    rule: str        # key of RULES
    note: str = ""


RULES = {
    "market_next_day": "Daily quote usable from the next calendar day in Prague (snapshot request rule); "
                       "a month mean is usable from the first day after the month.",
    "ec_bcs_next_month": "EC business and consumer survey results for month M are published in the last "
                         "days of M; usable from the first day of M+1.",
    "czso_t41": "CZSO industry/construction release: 37th day after the period plus at most 3 days of "
                "exceptions (2026 release rules), 09:00; usable from period end + 41 days.",
    "czso_import_prices_t45": "CZSO import-price release: 41st day after the period plus at most 3 days of "
                              "exceptions (2026 release rules); usable from period end + 45 days.",
    "eurostat_lfs_t32": "Monthly unemployment rate published about 30 days after the period; usable from "
                        "period end + 32 days.",
    "destatis_hicp_m1d16": "German HICP final value for M published in mid M+1 (the flash is later revised "
                           "into the current-vintage value); usable from day 16 of M+1.",
    "eurostat_ulc_q75": "Quarterly nominal unit labour cost published about 65 days after the quarter; "
                        "usable from quarter end + 75 days.",
    "ecb_mfi_t31": "Czech MFI loan stock for M published about four weeks after month end; usable from "
                   "period end + 31 days.",
    "cnb_rushin_week_plus7": "Weekly Rushin estimate usable 7 days after its observation date; a monthly "
                             "aggregate is usable 7 days after the last week in the month.",
    "annual_benchmark": "Annual benchmark only; never used as a monthly input.",
    "none": "No data returned.",
}

BCS, MKT = "ec_bcs_next_month", "market_next_day"


def _bcs(a6: int | None, note: str = "") -> Candidate:
    return Candidate((a6,) if a6 else (), "a6_candidate" if a6 else "diagnostic", "monthly", BCS, note)


def _mkt(a6: int | None, role: str = "a6_candidate", note: str = "") -> Candidate:
    return Candidate((a6,) if a6 else (), role, "daily", MKT, note)


REGISTRY: dict[str, Candidate] = {
    # G1 real activity, Czechia: detailed EC balances and hard data
    "EUI6CZ Index": _bcs(1), "EUI1CZ Index": _bcs(2), "EUS1CZ Index": _bcs(3),
    "EUS2CZ Index": _bcs(4, "Bloomberg long name is 'evolution of demand'; Nov-2025 annex spot check failed"),
    "EUR1CZ Index": _bcs(5, "Bloomberg SEASONALITY field says NSA"),
    "EUB1CZ Index": _bcs(6),
    "EUB5F4CZ Index": _bcs(7), "EUB5F5CZ Index": _bcs(8), "EUB5F7CZ Index": _bcs(9),
    "EUB5F6CZ Index": _bcs(None, "construction limiting factor 'other'; never A6 #9"),
    "EUA2CZ Index": _bcs(10, "candidate A for the financial-situation-next-12-months question"),
    "EUA4CZ Index": _bcs(10, "candidate B for the financial-situation-next-12-months question"),
    "EUCCCZ Index": _bcs(None, "broad consumer confidence indicator; not a Table A6 question"),
    "UMRTCZ Index": Candidate((11,), "a6_candidate", "monthly", "eurostat_lfs_t32"),
    "CZIPITS Index": Candidate((12,), "a6_candidate", "monthly", "czso_t41"),
    "CZIPITN Index": Candidate((12,), "a6_challenger", "monthly", "czso_t41", "NSA level; X-13 challenger only"),
    "CZGRIDX Index": Candidate((13,), "a6_candidate", "monthly", "czso_t41"),
    "CZRUSHIN Index": Candidate((14,), "a6_candidate", "weekly", "cnb_rushin_week_plus7"),
    "LCTQCZI Index": Candidate((17,), "a6_candidate", "quarterly", "eurostat_ulc_q75",
                               "quarterly; the paper disaggregates it with Chow-Lin"),
    "LCTOCZI Index": Candidate((17,), "a6_benchmark", "annual", "annual_benchmark"),
    # G2 foreign influence
    "EUICDE Index": _bcs(18), "EUSCDE Index": _bcs(19), "EURTDE Index": _bcs(20), "EUCODE Index": _bcs(21),
    "EURTPL Index": _bcs(22, "Table A6 applies a log difference to this signed balance"),
    "GRCPHCPI Index": Candidate((23,), "a6_candidate", "monthly", "destatis_hicp_m1d16"),
    "UMRTDE Index": Candidate((24,), "a6_candidate", "monthly", "eurostat_lfs_t32"),
    "CZEII Index": Candidate((26,), "a6_candidate", "monthly", "czso_import_prices_t45"),
    "EUA8EMU Index": _bcs(27, "euro-area price trends over the next 12 months"),
    "EUA7EMU Index": _bcs(28, "euro-area price trends over the last 12 months"),
    # G3 confidence and sentiment, Czechia
    "EUICCZ Index": _bcs(29), "EUS3CZ Index": _bcs(30), "EUS5CZ Index": _bcs(31), "EUSCCZ Index": _bcs(32),
    "EUR3CZ Index": _bcs(33), "EUR4CZ Index": _bcs(34), "EUR5CZ Index": _bcs(35), "EURTCZ Index": _bcs(36),
    "EUB3CZ Index": _bcs(37), "EUCOCZ Index": _bcs(38), "EUA1CZ Index": _bcs(39), "EUA0CZ Index": _bcs(40),
    "EUAUCZ Index": _bcs(41), "EUA6CZ Index": _bcs(42),
    "EEUR3CZ Index": Candidate((), "invalid_ticker", "none", "none",
                               "misspelling of EUR3CZ; no BDH or BDP response; removed from the active pull map"),
    # G5 financial
    "PRIB03M Index": _mkt(54, note="Table A6 #54 uses the value at the end of the month"),
    "LONSCZNF Index": Candidate((58,), "a6_candidate", "monthly", "ecb_mfi_t31",
                                "EUR millions; compare in CZK using the month-end EUR/CZK quote"),
    # G6 commodities and energy
    "CO1 Comdty": _mkt(60, note="front-month ICE Brent future, not dated Brent spot"),
    "TTFGDAHD BCFV Index": _mkt(61, note="TTF day-ahead fair value; paper index identity unknown"),
    "BCOMINSP Index": _mkt(62, note="Bloomberg industrial metals spot; paper index identity unknown"),
    "BCOMAGSP Index": _mkt(63, note="Bloomberg agriculture spot; paper food index identity unknown"),
    "TTFGCY1 Index": _mkt(65, note="Year-1 TTF strip fair value, not a constant 12-month Refinitiv contract"),
    "FSBTY1 Index": _mkt(66, note="Year-1 Brent strip fair value, not a constant 12-month Refinitiv contract"),
    "CO7 Comdty": _mkt(None, "legacy"), "CO13 Comdty": _mkt(None, "legacy"),
    # G7 inflation expectations
    "EUI5CZ Index": _bcs(67), "EUB4CZ Index": _bcs(68),
    # Support and non-A6 series kept in the same immutable capture
    "EURCZK Curncy": _mkt(None, "conversion"), "USDCZK Curncy": _mkt(None, "conversion"),
    "CKFR0CF Curncy": _mkt(None, "not_a6"), "CKFR0FI Curncy": _mkt(None, "not_a6"),
    "CKFR0I1 Curncy": _mkt(None, "not_a6"), "CKFR011C Curncy": _mkt(None, "not_a6"),
    "CKFR1C1F Curncy": _mkt(None, "not_a6"), "CKFR1F1I Curncy": _mkt(None, "not_a6"),
    "CKFR1I2 Curncy": _mkt(None, "not_a6"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_snapshot(folder: Path) -> dict:
    """Check every file listed in MANIFEST.json and that no file is unlisted."""
    folder = Path(folder)
    manifest = json.loads((folder / "MANIFEST.json").read_text(encoding="utf-8"))
    listed = manifest["sha256"]
    for rel, expected in listed.items():
        path = folder / rel
        if not path.is_file():
            raise FileNotFoundError(f"snapshot file missing: {rel}")
        if sha256_file(path) != expected:
            raise ValueError(f"snapshot hash mismatch: {rel}")
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    unlisted = sorted(present - set(listed) - {"MANIFEST.json"})
    if unlisted:
        raise ValueError(f"snapshot contains unlisted files: {unlisted[:5]}")
    return manifest


def _available(rule: str, period: pd.Period, last_obs: pd.Timestamp | None) -> pd.Timestamp:
    if rule in ("annual_benchmark", "none"):
        return pd.NaT
    if rule == "cnb_rushin_week_plus7":
        return last_obs.normalize() + pd.Timedelta(days=7)
    end = period.end_time.normalize()
    if rule == MKT:
        return end + pd.Timedelta(days=1)
    if rule == BCS:
        return (period + 1).start_time.normalize()
    if rule == "destatis_hicp_m1d16":
        return (period + 1).start_time.normalize() + pd.Timedelta(days=15)
    days = {"czso_t41": 41, "czso_import_prices_t45": 45, "eurostat_lfs_t32": 32,
            "ecb_mfi_t31": 31, "eurostat_ulc_q75": 75}[rule]
    return end + pd.Timedelta(days=days)


def _bdp(metadata: dict, ticker: str) -> dict:
    fields = metadata.get(ticker, {}).get("fields", {}).get(ticker, {})
    return {"bdp_name": fields.get("name"), "bdp_seasonality": fields.get("seasonality_and_transformation"),
            "bdp_source": fields.get("indx_source"), "bdp_country": fields.get("country"),
            "bdp_currency": fields.get("crncy"), "bdp_quote_units": fields.get("quote_units"),
            "bdp_next_release_at_pull": fields.get("eco_release_dt")}


def monthly_rows(ticker: str, alias: str, cand: Candidate, series: pd.Series, end_date: pd.Timestamp) -> list[dict]:
    """Aggregate one raw history to complete periods without filling anything."""
    obs = series.dropna()
    if obs.empty:
        return []
    rows = []
    base = {"ticker": ticker, "alias": alias, "a6_numbers": ";".join(map(str, cand.a6)), "role": cand.role,
            "source_frequency": cand.frequency, "availability_rule": cand.rule}
    if cand.frequency in ("monthly", "quarterly", "annual"):
        offset = {"monthly": pd.offsets.MonthEnd(0), "quarterly": pd.offsets.QuarterEnd(0),
                  "annual": pd.offsets.YearEnd(0)}[cand.frequency]
        misaligned = obs.index[obs.index != obs.index + offset]
        if len(misaligned):
            raise ValueError(f"{ticker}: {cand.frequency} observations not dated at period end: {list(misaligned[:3])}")
        freq = {"monthly": "M", "quarterly": "Q", "annual": "Y"}[cand.frequency]
        periods = obs.index.to_period(freq)
        if periods.has_duplicates:
            raise ValueError(f"{ticker}: more than one observation per {cand.frequency} period")
        for period, (date, value) in zip(periods, obs.items()):
            rows.append({**base, "statistic": "as_reported", "period": str(period), "value": float(value),
                         "n_observations": 1, "first_observation_date": date.date().isoformat(),
                         "last_observation_date": date.date().isoformat(),
                         "available_from_assumed": _available(cand.rule, period, date)})
        return rows
    months = obs.index.to_period("M")
    for period, block in obs.groupby(months):
        if period.end_time.normalize() > end_date:
            continue  # month-to-date quotes are not a monthly observation
        first, last = block.index.min(), block.index.max()
        stats = [("month_mean", float(block.mean())), ("month_last", float(block.iloc[-1]))]
        if cand.frequency == "weekly":
            stats = [("week_mean", float(block.mean())), ("week_last", float(block.iloc[-1]))]
        for name, value in stats:
            if cand.frequency == "weekly":
                available = _available(cand.rule, period, last)
            elif name == "month_last":
                available = last.normalize() + pd.Timedelta(days=1)
            else:
                available = _available(cand.rule, period, last)
            rows.append({**base, "statistic": name, "period": str(period), "value": value,
                         "n_observations": int(len(block)), "first_observation_date": first.date().isoformat(),
                         "last_observation_date": last.date().isoformat(),
                         "days_last_quote_before_month_end": int((period.end_time.normalize() - last.normalize()).days),
                         "available_from_assumed": available})
    return rows


def import_snapshot(snapshot: Path = DEFAULT_SNAPSHOT, output: Path = DEFAULT_OUTPUT, replace: bool = False) -> dict:
    snapshot, output = Path(snapshot), Path(output)
    snap_manifest = verify_snapshot(snapshot)
    request = json.loads((snapshot / "request.json").read_text(encoding="utf-8"))
    metadata = json.loads((snapshot / "metadata.json").read_text(encoding="utf-8"))
    errors = json.loads((snapshot / "errors.json").read_text(encoding="utf-8"))
    coverage = pd.read_csv(snapshot / "coverage.csv")
    daily = pd.read_csv(snapshot / "daily.csv", index_col="observation_date", parse_dates=["observation_date"])
    end_date = pd.Timestamp(request["end_date"])

    requested = request["tickers"]
    unknown = sorted(set(requested) - set(REGISTRY))
    if unknown:
        raise ValueError(f"requested tickers without a registry entry: {unknown}")
    ok = set(coverage.loc[coverage.status.eq("ok"), "ticker"])
    if ok != set(daily.columns):
        raise ValueError("daily.csv columns do not match successful coverage rows")

    if output.exists():
        previous = output / "manifest.json"
        if not replace or not previous.exists() or json.loads(previous.read_text(encoding="utf-8")).get("tool") != TOOL:
            raise FileExistsError(f"{output} exists; pass replace=True only for this tool's own output")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    rows, catalog = [], []
    snapshot_id = snapshot.name
    for ticker, alias in requested.items():
        cand = REGISTRY[ticker]
        bdp = _bdp(metadata, ticker)
        cov = coverage.loc[coverage.ticker.eq(ticker)].iloc[0].to_dict()
        ticker_rows = monthly_rows(ticker, alias, cand, daily[ticker], end_date) if ticker in daily else []
        for row in ticker_rows:
            row.update(bdp)
        rows.extend(ticker_rows)
        catalog.append({"ticker": ticker, "alias": alias, "a6_numbers": ";".join(map(str, cand.a6)),
                        "role": cand.role, "source_frequency": cand.frequency, "availability_rule": cand.rule,
                        "availability_rule_text": RULES[cand.rule], "registry_note": cand.note,
                        "capture_status": cov.get("status"), "capture_error": cov.get("error"),
                        "raw_observations": cov.get("observations"), "raw_first_date": cov.get("first_date"),
                        "raw_last_date": cov.get("last_date"), "monthly_rows": len(ticker_rows),
                        "import_status": "unvalidated_candidate" if ticker_rows else "no_data",
                        **bdp})
    long = pd.DataFrame(rows)
    long["available_from_assumed"] = pd.to_datetime(long["available_from_assumed"]).dt.strftime("%Y-%m-%d")
    long["availability_basis"] = "declared_rule_not_recorded_vintage"
    long["snapshot"] = snapshot_id
    long["validation_status"] = "unvalidated_candidate"
    cols = ["ticker", "alias", "a6_numbers", "role", "source_frequency", "statistic", "period", "value",
            "n_observations", "first_observation_date", "last_observation_date", "days_last_quote_before_month_end",
            "availability_rule", "available_from_assumed", "availability_basis", "bdp_name", "bdp_seasonality",
            "bdp_source", "bdp_country", "bdp_currency", "bdp_quote_units", "bdp_next_release_at_pull",
            "snapshot", "validation_status"]
    long = long.reindex(columns=cols).sort_values(["ticker", "statistic", "period"]).reset_index(drop=True)

    monthly = long[long.period.str.fullmatch(r"\d{4}-\d{2}")]
    wide = monthly.assign(column="bbg__" + monthly.alias + "__" + monthly.statistic).pivot(
        index="period", columns="column", values="value").sort_index()

    paths = {"long": output / "candidate_periods_long.csv", "wide_monthly": output / "candidate_monthly_wide.csv",
             "catalog": output / "candidate_catalog.csv", "rules": output / "availability_rules.csv"}
    long.to_csv(paths["long"], index=False)
    wide.to_csv(paths["wide_monthly"], index_label="period")
    pd.DataFrame(catalog).to_csv(paths["catalog"], index=False)
    pd.DataFrame([{"rule": k, "text": v} for k, v in RULES.items()]).to_csv(paths["rules"], index=False)
    manifest = {
        "tool": TOOL, "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": str(snapshot), "snapshot_end_date": request["end_date"],
        "snapshot_retrieved_at": request["retrieved_at"], "snapshot_status": request.get("status"),
        "snapshot_manifest_sha256": sha256_file(snapshot / "MANIFEST.json"),
        "snapshot_files_verified": len(snap_manifest["sha256"]),
        "snapshot_errors": errors,
        "status": "candidate panel; no series is an exact Table A6 input until validated and admitted",
        "vintage": "current-vintage Bloomberg histories; not original publication vintages",
        "tickers_requested": len(requested), "tickers_with_data": int(len(ok)),
        "outputs": {k: {"file": p.name, "sha256": sha256_file(p)} for k, p in paths.items()},
        "tool_sha256": sha256_file(Path(__file__)),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replace", action="store_true", help="rebuild this tool's own earlier output")
    args = parser.parse_args(argv)
    result = import_snapshot(args.snapshot, args.output, replace=args.replace)
    print(json.dumps({k: result[k] for k in ("snapshot_files_verified", "tickers_requested", "tickers_with_data",
                                             "outputs")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
