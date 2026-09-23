"""Recover CZSO unemployment release tables and rebuild a portable vintage store.

Run from the repository: python -m tools.archive_unemployment --start 2018-01
--end 2026-07. A rerun reuses archived bytes; --offline rebuilds without network.
Requires requests, beautifulsoup4 and openpyxl in addition to project pandas.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "vintages"
MONTH_SLUGS = ("leden", "unor", "brezen", "duben", "kveten", "cerven", "cervenec",
               "srpen", "zari", "rijen", "listopad", "prosinec")
BASE = "https://csu.gov.cz/rychle-informace/miry-zamestnanosti-nezamestnanosti-a-ekonomicke-aktivity-"


def parse_release_page(html, source):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    dates = re.findall(r"Datum vydání:\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
    if len(set(dates)) != 1:
        raise ValueError("Release must contain one explicit publication date")
    day, month, year = map(int, dates[0])
    release = pd.Timestamp(year=year, month=month, day=day)
    # The source has no verified intraday clock. Whole release day is excluded.
    available = (release + pd.Timedelta(days=1)).tz_localize("Europe/Prague").tz_convert("UTC")
    tables = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"_[12]\.xlsx?(?:\?|$)", href, re.I):
            continue
        label = a.get_text(" ", strip=True) or a.get("title", "")
        low = label.lower()
        if "trendcyklus" in low or "trend-cycle" in low:
            adjustment = "trend_cycle"
        elif "neočištěn" in low or "unadjusted" in low:
            adjustment = "nsa"
        elif "míra" in low and "sezón" in low:
            adjustment = "sa"
        else:
            continue  # Historical table 2 is counts, not another rate series.
        url = urljoin(source, href)
        tables[url] = dict(source=url, adjustment=adjustment, label=label)
    return dict(release_date=release.date().isoformat(), available_from=available.isoformat(),
                availability_precision="date_only_next_local_midnight",
                tables=list(tables.values()))


def parse_rate_table(frame, release_reference_period):
    """Read original stored numbers, checking header, dates and terminal month."""
    if frame.shape[1] < 6:
        raise ValueError("Unexpected unemployment table width")
    heading = " ".join(frame.iloc[:5, 5].dropna().astype(str)).lower()
    if "unemployment" not in heading or "15 to 64" not in heading or "total" not in heading:
        raise ValueError("Expected total unemployment rate ages 15 to 64 in column F")
    rows = []
    current_year = None
    for record in frame.itertuples(index=False, name=None):
        if isinstance(record[0], (int, float)) and pd.notna(record[0]) and 1990 <= record[0] <= 2100:
            current_year = int(record[0])
        month = re.fullmatch(r"M\s*(\d{1,2})", str(record[1]).strip())
        if month is None:
            continue
        if current_year is None or not 1 <= int(month[1]) <= 12:
            raise ValueError("Invalid reference month in archival table")
        period = f"{current_year:04d}-{int(month[1]):02d}"
        if period > str(release_reference_period):
            raise ValueError("Future reference month in historical attachment")
        try:
            value = float(record[5])
        except (TypeError, ValueError) as exc:
            raise ValueError("Non-numeric unemployment rate in archival table") from exc
        if not np.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Invalid unemployment percentage")
        rows.append(dict(reference_period=period, value=value))
    if not rows or rows[-1]["reference_period"] != str(release_reference_period):
        raise ValueError("Attachment does not end at its release reference month")
    periods = [r["reference_period"] for r in rows]
    expected = pd.period_range(periods[0], periods[-1], freq="M").astype(str).tolist()
    if periods != expected:
        raise ValueError("Missing or duplicate reference months in archival attachment")
    return rows


def _download(url, path, offline):
    if path.exists():
        return path.read_bytes()
    if offline:
        raise FileNotFoundError(f"Offline archive missing {path.name}")
    if urlparse(url).hostname not in {"csu.gov.cz", "statistikaamy.csu.gov.cz"}:
        raise ValueError("Only official CZSO hosts may be archived")
    response = requests.get(url, timeout=(8, 20), headers={"User-Agent": "CPI-research-vintage-archive/1.0"})
    response.raise_for_status()
    path.write_bytes(response.content)
    return response.content


def archive_release(period, directory, offline=False):
    period = pd.Period(period, "M")
    source = BASE + MONTH_SLUGS[period.month - 1] + f"-{period.year}"
    raw = directory / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    page_path = raw / f"{period}.html"
    page = _download(source, page_path, offline)
    meta = parse_release_page(page, source)
    release = pd.Timestamp(meta["release_date"])
    if release <= period.end_time.normalize() or release > (period + 3).end_time:
        raise ValueError("Publication date is inconsistent with the release reference month")
    if not meta["tables"]:
        raise ValueError("No recognized unemployment rate attachment")
    result = dict(reference_release=str(period), source=source, page_file=page_path.relative_to(directory).as_posix(),
                  page_sha256=hashlib.sha256(page).hexdigest(), **meta)
    all_rows = []
    for table in result["tables"]:
        extension = Path(urlparse(table["source"]).path).suffix
        path = raw / f"{period}-{table['adjustment']}{extension}"
        content = _download(table["source"], path, offline)
        table.update(raw_file=path.relative_to(directory).as_posix(), sha256=hashlib.sha256(content).hexdigest())
        frame = pd.read_excel(path, header=None)
        rows = parse_rate_table(frame, str(period))
        table.update(rows=len(rows), reference_start=rows[0]["reference_period"],
                     reference_end=rows[-1]["reference_period"])
        for r in rows:
            all_rows.append(dict(series=f"unemployment_{table['adjustment']}", **r,
                available_from=meta["available_from"], source=table["source"], sha256=table["sha256"],
                adjustment=table["adjustment"], vintage_kind="historical_release",
                release_date=meta["release_date"], reference_release=str(period),
                availability_precision=meta["availability_precision"], release_source=source,
                release_page_sha256=result["page_sha256"], raw_file=table["raw_file"]))
    result["status"] = "ok"
    return result, all_rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2018-01")
    parser.add_argument("--end", default="2026-07")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    args.directory.mkdir(parents=True, exist_ok=True)
    periods = pd.period_range(args.start, args.end, freq="M")
    manifests, rows = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(archive_release, p, args.directory, args.offline): p for p in periods}
        for future in as_completed(futures):
            period = futures[future]
            try:
                meta, release_rows = future.result()
                rows.extend(release_rows)
                print(f"{period}: archived {len(release_rows)} rows", flush=True)
            except Exception as exc:
                meta = dict(reference_release=str(period), status="unavailable", error=str(exc))
                print(f"{period}: unavailable ({type(exc).__name__})", flush=True)
            manifests.append(meta)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        from data.vintages import select_vintages
        select_vintages(frame, "2100-01-01T00:00:00Z")  # validate before emitting
        frame.sort_values(["available_from", "series", "reference_period"]).to_csv(
            args.directory / "unemployment.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    coverage = []
    if not frame.empty:
        for series, group in frame.groupby("series"):
            coverage.append(dict(series=series, releases=int(group["available_from"].nunique()), rows=len(group),
                first_available=group["available_from"].min(), last_available=group["available_from"].max(),
                reference_start=group["reference_period"].min(), reference_end=group["reference_period"].max()))
    manifest = dict(schema_version=1, retrieved_at=datetime.now(timezone.utc).isoformat(),
        requested_start=args.start, requested_end=args.end, availability_policy="date_only_next_local_midnight",
        coverage=coverage, releases=sorted(manifests, key=lambda x: x["reference_release"]),
        limitation="Historical release attachments recovered today; retained source page dates and raw hashes. "
                   "Intraday time not verified. NSA history is never backdated before its actual publication.")
    (args.directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(coverage, indent=2), flush=True)


if __name__ == "__main__":
    main()
