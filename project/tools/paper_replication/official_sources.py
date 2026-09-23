"""Official comparison sources for the CNB WP 9/2026 Table A6 audit.

Two public sources are handled here.

* European Commission (DG ECFIN) Business and Consumer Survey archives.  The
  ZIPs are saved once into a dated ``nace2_ecfin_<yymm>`` folder and never
  edited.  ``ecfin_manifest`` records the HTTP headers and SHA-256 of what was
  saved; ``read_ecfin_archive`` turns one workbook into a long table.
* Eurostat's dissemination API (JSON-stat 2.0).  ``download_eurostat`` writes
  the raw responses, tidy CSVs and a manifest into a new folder.

Both are current-vintage downloads.  Seasonally adjusted balances are revised
and neither source publishes the historical vintages the paper used, so a
match against them validates identity and definition, not real-time
availability.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import pandas as pd

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
ECFIN_BASE = "https://ec.europa.eu/economy_finance/db_indicators/surveys/documents/series/"

# Geographies needed by Table A6: Czechia (G1, G3, G7), Germany and Poland
# (G2 confidence), and the euro area (G2 price balances).  Eurostat names the
# changing euro-area composition EA20 (2023-2025) and EA21 (from 2026).
BCS_GEOS = ["CZ", "DE", "PL", "EA20", "EA21", "EU27_2020"]
EUROSTAT_QUERIES: dict[str, tuple[str, dict]] = {
    "une_rt_m_cz_de": ("une_rt_m", {"geo": ["CZ", "DE"], "s_adj": ["SA", "NSA"], "age": "TOTAL",
                                    "sex": "T", "unit": "PC_ACT"}),
    "prc_hicp_minr_de_total": ("prc_hicp_minr", {"geo": "DE", "coicop18": "TOTAL", "unit": ["I25", "I15"]}),
    "prc_hicp_midx_de_cp00": ("prc_hicp_midx", {"geo": "DE", "coicop": "CP00", "unit": "I15"}),
    # For Czechia this dataset publishes nominal ULC only as growth rates;
    # index levels (I10/I15/I20) exist for labour productivity alone.
    "namq_10_lp_ulc_cz": ("namq_10_lp_ulc", {"geo": "CZ", "na_item": ["NULC_PER", "NULC_HW"],
                                            "unit": ["PCH_SM", "PCH_PRE"], "s_adj": ["NSA", "SCA"]}),
    "ei_bsin_m_r2": ("ei_bsin_m_r2", {"geo": BCS_GEOS}),
    "ei_bsse_m_r2": ("ei_bsse_m_r2", {"geo": BCS_GEOS}),
    "ei_bsrt_m_r2": ("ei_bsrt_m_r2", {"geo": BCS_GEOS}),
    "ei_bsbu_m_r2": ("ei_bsbu_m_r2", {"geo": BCS_GEOS}),
    "ei_bsco_m": ("ei_bsco_m", {"geo": BCS_GEOS}),
}
# Domestic producer prices for Table A6 rows 44-49.  The CZSO CEN0201A section
# totals equal these Eurostat series in growth (2015-2026, MAE <= 0.035 pp), and
# Eurostat carries the history back to 1990.
EUROSTAT_PPI_QUERIES: dict[str, tuple[str, dict]] = {
    "sts_inppd_m_cz": ("sts_inppd_m", {"geo": "CZ", "nace_r2": ["B-E36", "B", "C", "D", "E36"],
                                       "unit": ["I21", "PCH_SM"]}),
}
EUROSTAT_QUERY_SETS = {"validation": EUROSTAT_QUERIES, "ppi": EUROSTAT_PPI_QUERIES}

ECFIN_SERIES = re.compile(
    r"^(?P<survey>[A-Z]{4})\.(?P<geo>[A-Z0-9_]+)\.(?P<subsector>[A-Z0-9_]+)\."
    r"(?P<question>[A-Z0-9]+)\.(?P<answer>[A-Z0-9]+)\.(?P<frequency>[MQ])$")
ECFIN_MAIN_SERIES = re.compile(r"^(?P<geo>[A-Z0-9_]+)\.(?P<indicator>[A-Z]+)$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- Eurostat

def jsonstat_to_frame(payload: dict) -> pd.DataFrame:
    """Return one row per published cell of a JSON-stat 2.0 dataset.

    Cells absent from ``value`` are not invented.  Eurostat status flags
    (for example ``p`` provisional) are kept in ``status`` when present.
    """
    dims = list(payload["id"])
    sizes = list(payload["size"])
    categories = []
    for dim in dims:
        index = payload["dimension"][dim]["category"]["index"]
        if isinstance(index, list):
            categories.append(list(index))
        else:
            categories.append(sorted(index, key=index.get))
    values = payload.get("value", {})
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values) if v is not None}
    status = payload.get("status", {}) or {}
    if isinstance(status, list):
        status = {str(i): s for i, s in enumerate(status) if s is not None}
    if not values:
        return pd.DataFrame(columns=dims + ["value", "status"])
    flat = np.array(sorted(int(k) for k in values), dtype=np.int64)
    coords = np.unravel_index(flat, sizes)
    frame = pd.DataFrame({dim: np.asarray(categories[i], dtype=object)[coords[i]]
                          for i, dim in enumerate(dims)})
    frame["value"] = pd.to_numeric(pd.Series([values[str(k)] for k in flat]), errors="coerce")
    frame["status"] = [status.get(str(k)) for k in flat]
    return frame


def download_eurostat(folder: Path, queries: dict[str, tuple[str, dict]] = EUROSTAT_QUERIES,
                      session=None) -> dict:
    """Save each declared Eurostat query into a new folder with a manifest."""
    import requests

    session = session or requests.Session()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "raw").mkdir()
    (folder / "tidy").mkdir()
    manifest = {"source": "Eurostat dissemination API, JSON-stat 2.0", "base_url": EUROSTAT_BASE,
                "vintage_status": "current vintage at retrieval; not a historical publication archive",
                "started_at": _utc_now(), "queries": {}, "errors": []}
    for name, (dataset, params) in queries.items():
        retrieved_at = _utc_now()
        try:
            response = session.get(EUROSTAT_BASE + dataset, params=params, timeout=300)
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise ValueError(payload["error"])
            raw_path = folder / "raw" / f"{name}.json"
            raw_path.write_bytes(response.content)
            tidy = jsonstat_to_frame(payload)
            if tidy.empty:
                raise ValueError("query returned no observations; check the dimension codes")
            tidy.insert(0, "dataset", dataset)
            tidy_path = folder / "tidy" / f"{name}.csv"
            tidy.to_csv(tidy_path, index=False)
            manifest["queries"][name] = {
                "dataset": dataset, "params": params, "url": response.url,
                "retrieved_at": retrieved_at, "dataset_updated": payload.get("updated"),
                "label": payload.get("label"), "rows": int(len(tidy)),
                "raw_sha256": sha256_file(raw_path), "tidy_sha256": sha256_file(tidy_path),
            }
        except Exception as exc:  # recorded, never silently dropped
            manifest["errors"].append({"query": name, "dataset": dataset, "params": params,
                                       "retrieved_at": retrieved_at,
                                       "error": f"{type(exc).__name__}: {exc}"})
    manifest["completed_at"] = _utc_now()
    manifest["status"] = "complete" if not manifest["errors"] else "partial"
    manifest["module_sha256"] = sha256_file(Path(__file__))
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    return manifest


# ------------------------------------------------------------------- ECFIN

def _parse_headers(text: str) -> dict:
    """Headers of the final HTTP response in a ``curl -D`` dump.

    Blocks are separated by a blank line whatever the line ending (LF, CRLF, or
    CRCRLF after a text-mode round trip); redirects before the final response
    are skipped.
    """
    blocks = [b for b in re.split(r"\r*\n\r*\n", text.strip()) if b.strip()]
    responses = [b for b in blocks if b.lstrip().startswith("HTTP/")]
    if not responses:
        return {}
    lines = [line.strip() for line in re.split(r"\r*\n", responses[-1].strip()) if line.strip()]
    out = {"status_line": lines[0]}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip().lower()] = value.strip()
    return out


def ecfin_manifest(folder: Path) -> dict:
    """Describe the saved ECFIN archives; refuse to rewrite a different manifest."""
    folder = Path(folder)
    entries = {}
    for archive in sorted(folder.glob("*.zip")):
        headers_path = folder / f"{archive.name}.headers.txt"
        stamp_path = folder / f"{archive.name}.retrieved_at.txt"
        # Bytes, not text mode: universal-newline translation would split CRLF headers.
        headers = _parse_headers(headers_path.read_bytes().decode("latin-1")) if headers_path.exists() else {}
        entries[archive.name] = {
            "url": f"{ECFIN_BASE}{folder.name}/{archive.name}",
            "retrieved_at_utc": stamp_path.read_text(encoding="utf-8").strip() if stamp_path.exists() else None,
            "http_status": headers.get("status_line"), "last_modified": headers.get("last-modified"),
            "etag": headers.get("etag"), "content_type": headers.get("content-type"),
            "bytes": archive.stat().st_size, "sha256": sha256_file(archive),
        }
    manifest = {"source": "European Commission DG ECFIN, BCS time series (NACE Rev. 2)",
                "vintage_folder": folder.name,
                "vintage_status": "current vintage of the monthly archive; balances are revised",
                "archives": entries}
    path = folder / "DOWNLOAD_MANIFEST.json"
    text = json.dumps(manifest, indent=2, ensure_ascii=False)
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise ValueError(f"{path} exists with different content; archives must stay immutable")
    path.write_text(text, encoding="utf-8")
    return manifest


def _workbook(archive: Path):
    import openpyxl

    with zipfile.ZipFile(archive) as zf:
        members = [i for i in zf.infolist() if i.filename.lower().endswith(".xlsx")]
        if len(members) != 1:
            raise ValueError(f"{archive.name}: expected one workbook, found {[m.filename for m in members]}")
        return openpyxl.load_workbook(io.BytesIO(zf.read(members[0])), read_only=True), members[0].filename


def _period_label(cell) -> str | None:
    if isinstance(cell, datetime):
        return f"{cell.year:04d}-{cell.month:02d}"
    if isinstance(cell, str) and re.fullmatch(r"\d{4}-Q[1-4]", cell.strip()):
        return cell.strip()
    return None


def read_ecfin_archive(archive: Path, geos: list[str] | None = None) -> pd.DataFrame:
    """Long table of every monthly/quarterly series in one ECFIN archive.

    ``seasonally_adjusted`` follows the ECFIN answer code: ``BS``/``F4S``/``QPS``
    are seasonally adjusted, ``B``/``F4``/``QP`` are not.  ``NA`` cells are
    dropped rather than filled.
    """
    archive = Path(archive)
    wb, member = _workbook(archive)
    frames = []
    for ws in wb.worksheets:
        title = ws.title.upper()
        if not (title.endswith("MONTHLY") or title.endswith("QUARTERLY")):
            continue
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            continue
        columns = []
        for j, code in enumerate(header):
            if not isinstance(code, str):
                continue
            code = code.strip()
            match = ECFIN_SERIES.match(code)
            if match:
                meta = match.groupdict()
            else:
                main = ECFIN_MAIN_SERIES.match(code)
                if not main:
                    continue
                meta = {"survey": "MAIN", "geo": main["geo"], "subsector": "TOT",
                        "question": main["indicator"], "answer": "SA",
                        "frequency": "M" if title.endswith("MONTHLY") else "Q"}
            if geos is not None and meta["geo"] not in geos:
                continue
            columns.append((j, code, meta))
        if not columns:
            continue
        periods, cells = [], []
        for row in rows:
            label = _period_label(row[0]) if row else None
            if label is None:
                continue
            periods.append(label)
            cells.append([row[j] if j < len(row) else None for j, _, _ in columns])
        if not periods:
            continue
        # Positional column labels keep a repeated series code from breaking
        # the reshape; repeats are reconciled after all sheets are read.
        block = pd.DataFrame(cells, columns=[str(j) for j, _, _ in columns])
        block.insert(0, "period", periods)
        long = block.melt(id_vars="period", var_name="column", value_name="raw")
        long["series_code"] = long["column"].map({str(j): code for j, code, _ in columns})
        long["value"] = pd.to_numeric(long["raw"], errors="coerce")
        long = long.dropna(subset=["value"]).drop(columns=["raw", "column"])
        meta = pd.DataFrame([{"series_code": code, **m} for _, code, m in columns]).drop_duplicates("series_code")
        long = long.merge(meta, on="series_code", how="left")
        long["sheet"] = ws.title
        frames.append(long)
    wb.close()
    if not frames:
        return pd.DataFrame(columns=["period", "series_code", "value", "survey", "geo", "subsector",
                                     "question", "answer", "frequency", "sheet"])
    out = pd.concat(frames, ignore_index=True)
    out["seasonally_adjusted"] = out["answer"].str.endswith("S") | out["answer"].eq("SA")
    out["unit"] = np.where(out["answer"].isin(["B", "BS"]), "balance",
                           np.where(out["answer"].str.match(r"^F\d"), "percent_of_firms",
                                    np.where(out["survey"].eq("MAIN"), "indicator", "other")))
    out["archive"] = archive.name
    out["workbook"] = member
    return out[["survey", "geo", "subsector", "question", "answer", "frequency", "seasonally_adjusted",
                "unit", "series_code", "period", "value", "sheet", "archive", "workbook"]]


def read_ecfin_index(archive: Path) -> pd.DataFrame:
    """Question and answer wording from an archive's ``Index`` sheet."""
    wb, member = _workbook(Path(archive))
    rows = []
    section = None
    if "Index" in wb.sheetnames:
        for row in wb["Index"].iter_rows(values_only=True):
            cells = [c for c in row if c is not None]
            if len(cells) == 1 and isinstance(cells[0], str):
                section = cells[0].strip()
                continue
            if len(cells) >= 2 and isinstance(cells[0], (str, int)):
                rows.append({"archive": Path(archive).name, "section": section,
                             "code": str(cells[0]).strip(), "description": str(cells[1]).strip()})
    notes = []
    if "INFO" in wb.sheetnames:
        for row in wb["INFO"].iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None]
            if cells:
                notes.append({"archive": Path(archive).name, "when": cells[0] if len(cells) > 1 else None,
                              "note": cells[-1]})
    wb.close()
    return pd.DataFrame(rows).assign(kind="catalog"), pd.DataFrame(notes)


def build_ecfin_long(folder: Path, output: Path, geos: list[str]) -> dict:
    """Write the long BCS table, question catalog and revision notes to a new folder."""
    folder, output = Path(folder), Path(output)
    manifest_in = ecfin_manifest(folder)
    output.mkdir(parents=True, exist_ok=False)
    frames, catalogs, notes = [], [], []
    for archive in sorted(folder.glob("*.zip")):
        if archive.name.startswith("consumer_inflation"):
            continue  # micro-level quantitative estimates, not the balance archives
        frames.append(read_ecfin_archive(archive, geos=geos))
        catalog, info = read_ecfin_index(archive)
        catalogs.append(catalog)
        notes.append(info)
    long = pd.concat(frames, ignore_index=True)
    dupes = long.duplicated(["series_code", "period"], keep=False)
    if dupes.any():
        # SA and NSA archives never share a series code; a duplicate means
        # the same code appears twice inside one workbook.
        conflict = long[dupes].groupby(["series_code", "period"])["value"].nunique()
        if (conflict > 1).any():
            raise ValueError(f"conflicting duplicate ECFIN cells: {conflict[conflict > 1].head()}")
        long = long.drop_duplicates(["series_code", "period"])
    paths = {"long": output / "ecfin_bcs_long.csv", "catalog": output / "ecfin_question_catalog.csv",
             "notes": output / "ecfin_revision_notes.csv"}
    long.sort_values(["survey", "geo", "series_code", "period"]).to_csv(paths["long"], index=False)
    pd.concat(catalogs, ignore_index=True).drop_duplicates().to_csv(paths["catalog"], index=False)
    pd.concat(notes, ignore_index=True).drop_duplicates().to_csv(paths["notes"], index=False)
    manifest = {"created_at": _utc_now(), "input_folder": str(folder), "geos": geos,
                "input_archives": {k: v["sha256"] for k, v in manifest_in["archives"].items()},
                "outputs": {k: {"file": p.name, "sha256": sha256_file(p)} for k, p in paths.items()},
                "rows": int(len(long)), "series": int(long["series_code"].nunique()),
                "module_sha256": sha256_file(Path(__file__))}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


# --------------------------------------------------------------------- CZSO

CZSO_OPEN_DATA = "https://data.csu.gov.cz/opendata/sady/{code}/distribuce/csv"
# DataStat open-data sets consulted for Table A6 rows 50-52 and 64.
CZSO_DATASETS = {
    "CEN02A": "Aggregated producer price indices, monthly (agricultural producer price index)",
    "CENPHMT": "Average consumer fuel prices, weekly survey",
    "CEN0101J": "Average consumer fuel prices, monthly (to 2025)",
}
# Agricultural producer price indices by main group, previous month = 100, from 2010.
CZSO_AGRI_DATASETS = {
    "CEN02032": "Agricultural producer price indices by main agricultural group (previous period = 100)",
}
CZSO_DATASET_SETS = {"a6": CZSO_DATASETS, "agri": CZSO_AGRI_DATASETS}


def download_czso(folder: Path, datasets: dict[str, str] = CZSO_DATASETS, session=None) -> dict:
    """Save CZSO DataStat open-data CSVs into a new folder with a manifest."""
    import requests

    session = session or requests.Session()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"source": "Czech Statistical Office DataStat open data", "started_at": _utc_now(),
                "vintage_status": "current vintage at retrieval", "datasets": {}, "errors": []}
    for code, title in datasets.items():
        url = CZSO_OPEN_DATA.format(code=code)
        retrieved_at = _utc_now()
        try:
            response = session.get(url, timeout=300)
            response.raise_for_status()
            if response.content.lstrip()[:15].lower().startswith(b"<!doctype html"):
                raise ValueError("HTML error page instead of CSV")
            path = folder / f"{code}.csv"
            path.write_bytes(response.content)
            frame = pd.read_csv(path)
            manifest["datasets"][code] = {"title": title, "url": url, "retrieved_at": retrieved_at,
                                          "rows": int(len(frame)), "columns": list(frame.columns),
                                          "sha256": sha256_file(path)}
        except Exception as exc:
            manifest["errors"].append({"dataset": code, "url": url, "retrieved_at": retrieved_at,
                                       "error": f"{type(exc).__name__}: {exc}"})
    manifest["status"] = "complete" if not manifest["errors"] else "partial"
    manifest["module_sha256"] = sha256_file(Path(__file__))
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("czso", help="download the declared CZSO open-data sets into a new folder")
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--set", choices=sorted(CZSO_DATASET_SETS), default="a6")
    e = sub.add_parser("eurostat", help="download the declared Eurostat queries into a new folder")
    e.add_argument("--output", type=Path, required=True)
    e.add_argument("--set", choices=sorted(EUROSTAT_QUERY_SETS), default="validation")
    m = sub.add_parser("ecfin-manifest", help="record provenance of saved ECFIN archives")
    m.add_argument("folder", type=Path)
    l = sub.add_parser("ecfin-long", help="parse saved ECFIN archives into a long table")
    l.add_argument("folder", type=Path)
    l.add_argument("--output", type=Path, required=True)
    l.add_argument("--geos", nargs="+", default=["CZ", "DE", "PL", "EA", "EU"])
    args = parser.parse_args(argv)
    if args.command == "czso":
        result = download_czso(args.output, CZSO_DATASET_SETS[args.set])
        print(json.dumps({"status": result["status"], "errors": result["errors"],
                          "datasets": {k: v["rows"] for k, v in result["datasets"].items()}}, indent=2))
        return 0 if result["status"] == "complete" else 1
    if args.command == "eurostat":
        result = download_eurostat(args.output, EUROSTAT_QUERY_SETS[args.set])
        print(json.dumps({"status": result["status"], "errors": result["errors"],
                          "queries": {k: v["rows"] for k, v in result["queries"].items()}}, indent=2))
        return 0 if result["status"] == "complete" else 1
    if args.command == "ecfin-manifest":
        print(json.dumps(ecfin_manifest(args.folder), indent=2))
        return 0
    result = build_ecfin_long(args.folder, args.output, args.geos)
    print(json.dumps({k: result[k] for k in ("rows", "series")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
