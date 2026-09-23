"""Hash-verified current-vintage CZSO category inputs for R35 descriptive analysis.

Only observed levels and frozen 2026 basket weights are prepared here.
No forecast, seasonal adjustment, database or frozen-file writes occur.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import time
import urllib.request

import numpy as np
import pandas as pd

from tools.live_bundle_r32.adapter import checked_files, required
from tools.research_r18 import category_inputs as frozen

SOURCE_URL = frozen.SOURCE_URL
GROUPS = [definition[0] for definition in frozen.CATEGORIES.values()]
START = pd.Period("2015-01", "M")
THROUGH = "2026-08"
FILES = ("monthly_levels.csv", "series_metadata.csv", "weights.csv", "provenance.json")
SELECTION = {"IndicatorType": "6134", "TYPUDAJE4A": "IZ2015", "EKAKTIOCDS": "0", "UZ02P": "CZ"}


def _now():
    return pd.Timestamp(datetime.now(timezone.utc))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _clock(value):
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            raise ValueError()
        return stamp.tz_convert("UTC")
    except (TypeError, ValueError) as exc:
        raise ValueError("clock requires an explicit timezone-aware timestamp") from exc


def _decision(value=None):
    stamp = _now() if value is None else _clock(value)
    if stamp > _now():
        raise ValueError("future as_of clock is not permitted")
    return stamp


def _month(value):
    if not re.fullmatch(r"\d{4}-\d{2}", str(value)):
        raise ValueError("through must be YYYY-MM")
    return pd.Period(value, freq="M")


def _read_csv(data, **kwargs):
    return pd.read_csv(io.BytesIO(data), encoding="utf-8", float_precision="round_trip", **kwargs)


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def _manifest(path, filename="MANIFEST.json", nested=False):
    path = Path(path).resolve()
    raw = (path/filename).read_bytes()
    manifest = json.loads(raw)
    hashes = ({name: record["sha256"] for name, record in manifest["files"].items()}
              if nested else manifest["files"])
    data = checked_files(path, hashes)
    return data, manifest, {"path": str(path), "manifest_sha256": _sha(raw), "files": hashes}


def _attributes(path):
    # Create-only: never alter attributes another worker has already set.
    attribute = path/".gitattributes"
    try:
        with attribute.open("x", encoding="utf-8") as stream:
            stream.write("* -text\n")
    except FileExistsError:
        if attribute.read_text(encoding="utf-8").strip() != "* -text":
            raise ValueError("existing local attributes differ; coordinate with directory owner")


def _seal(path):
    _json(path/"MANIFEST.json", {"schema_version": 1, "files": {
        item.name: _sha(item.read_bytes()) for item in sorted(path.iterdir())
        if item.is_file() and item.name != "MANIFEST.json"
    }})


def capture(output, *, timeout=45):
    """Read only the fixed official URL; archive create-only deterministic gzip."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite capture {output}")
    if not 0 < timeout <= 55:
        raise ValueError("capture timeout must be 0..55 seconds")
    output.mkdir(parents=True, exist_ok=False)
    _attributes(output)
    started = _now()
    deadline = time.monotonic()+timeout
    chunks = []
    with urllib.request.urlopen(SOURCE_URL, timeout=min(timeout, 20)) as response:
        headers, final_url = dict(response.headers), response.url
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("bounded official capture deadline exceeded")
            chunk = response.read(1024*1024)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    completed = _now()
    if not raw:
        raise ValueError("empty official response")
    (output/"CEN0101E.csv.gz").write_bytes(gzip.compress(raw, mtime=0))
    request = {
        "source_url": SOURCE_URL, "final_url": final_url,
        "retrieved_at": started.isoformat(), "completed_at": completed.isoformat(),
        "headers": headers, "raw_sha256": _sha(raw), "raw_bytes": len(raw),
        "compression": "gzip, mtime=0; decompression preserves original response bytes",
        "vintage": "current-vintage official national CPI levels; not historical first-release data",
    }
    _json(output/"request.json", request)
    _seal(output)
    return request


def extract_current(raw, *, expected_columns, through=THROUGH, as_of=None):
    """Reuse the unchanged frozen selector only after exact schema comparison."""
    clock, last = _decision(as_of), _month(through)
    if list(raw.columns) != list(expected_columns) or len(raw.columns) != len(set(raw.columns)):
        raise ValueError("changed official raw schema; a reviewed adapter is required")
    if last >= clock.tz_convert("Europe/Prague").tz_localize(None).to_period("M"):
        raise ValueError("future/current reference month cannot be declared observed")
    # Frozen parser requires string codes to preserve leading zeros and national selectors.
    raw = raw.copy()
    for col in ("IndicatorType", "TYPUDAJE4A", "EKAKTIOCDS", "UZ02P",
                "CZCOICOP2.CZCOP1", "CZCOICOP2.CZCOP23", "CASMKMQRM12"):
        raw[col] = raw[col].astype("string")
    result = frozen.extract_levels(raw)
    result.index = pd.PeriodIndex(result.index, freq="M", name="period")
    if (result.index > last).any():
        raise ValueError("future/extra reference months beyond declared through month")
    expected = pd.period_range(START, last, freq="M", name="period")
    if not result.index.equals(expected) or list(result) != GROUPS:
        raise ValueError("missing required coverage: January 2015 through declared month, all 37 groups")
    _valid_levels(result, last)
    return result.astype(float)


def _valid_levels(levels, last):
    expected = pd.period_range(START, last, freq="M", name="period")
    if (list(levels) != GROUPS or not levels.index.equals(expected)
            or levels.index.has_duplicates):
        raise ValueError("invalid monthly coverage, duplicate months or mapped groups")
    values = levels.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("finite positive observed category levels required; no interpolation")


def _valid_metadata(meta):
    if "column" not in meta or meta.column.tolist() != GROUPS or meta.column.duplicated().any():
        raise ValueError("metadata must map the 37 unique frozen groups in order")
    for code, (name, sector, primary, scope) in frozen.CATEGORIES.items():
        row = meta.loc[meta.column == name].iloc[0]
        expected = {
            "coicop2018_code": code, "sector": sector, "primary_measurement": primary,
            "scope_note": scope, "geography": "CZ", "households": "all households (0)",
            "index_base": "2015=100", "seasonal_adjustment": "NSA",
            "source_url": SOURCE_URL, "source_dataset": "CZSO CEN0101E",
            "level": "group" if len(code) == 3 else "division",
        }
        for key, value in expected.items():
            if key not in row or row[key] != value:
                raise ValueError(f"frozen metadata mapping/definition differs: {name}.{key}")
        if not isinstance(row.get("label_cs"), str) or not row.label_cs.strip():
            raise ValueError("frozen metadata requires official labels")



def _verify_source_labels(raw, metadata):
    """Prevent unchanged numeric codes from silently acquiring a different scope."""
    mask = raw.CASMKMQRM12.str.fullmatch(r"\d{4}-\d{2}", na=False)
    for column, value in SELECTION.items():
        mask &= raw[column].eq(value)
    selected = raw.loc[mask].copy()
    selected["code"] = selected["CZCOICOP2.CZCOP23"].fillna(selected["CZCOICOP2.CZCOP1"])
    for row in metadata.itertuples():
        field = ("Klasifikace COICOP 2018-Skupina a třída" if len(row.coicop2018_code) == 3
                 else "Klasifikace COICOP 2018-Oddíl")
        labels = selected.loc[selected.code == row.coicop2018_code, field]
        if labels.empty or labels.isna().any() or not labels.eq(row.label_cs).all():
            raise ValueError(f"official category label/mapping changed: {row.column}; review required")


def _weights(baskets, files):
    wanted = baskets.loc[(baskets.effective_year == 2026) & baskets.mapped_series.isin(GROUPS)].copy()
    if (len(wanted) != 37 or wanted.mapped_series.duplicated().any()
            or set(wanted.mapped_series) != set(GROUPS)):
        raise ValueError("2026 weights must map each of the 37 groups exactly once")
    if (not wanted.basis_year.eq(2024).all()
            or not wanted.mapping_status.eq("current_COICOP2018_code").all()
            or not wanted.source_file.eq("raw/spot_kos2026.xlsx").all()):
        raise ValueError("wrong frozen basket year, source or mapping definition")
    by_name = {name: code for code, (name, *_) in frozen.CATEGORIES.items()}
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(required(files, "raw/spot_kos2026.xlsx")),
                               read_only=True, data_only=True)
    try:
        sheets = {name: list(wb[name].values) for name in wanted.source_sheet.unique()}
        for row in wanted.itertuples():
            if str(row.basket_code).replace(".", "") != by_name[row.mapped_series]:
                raise ValueError("2026 weight code does not match frozen category")
            match = re.fullmatch(r"E(\d+)", row.source_cell)
            if not match:
                raise ValueError("weight workbook cell is not an E-column value")
            actual = sheets[row.source_sheet][int(match.group(1))-1]
            if (str(actual[0]).strip().removeprefix("E") != row.basket_code
                    or str(actual[1]) != row.basket_label_cs
                    or float(actual[4]) != float(row.weight_permille)):
                raise ValueError("frozen weight differs from original 2026 workbook cell")
    finally:
        wb.close()
    weights = wanted.set_index("mapped_series").weight_permille.reindex(GROUPS).astype(float)
    weights.index.name = "group"
    _valid_weights(weights)
    return weights, wanted


def _valid_weights(weights):
    if list(weights.index) != GROUPS or weights.index.has_duplicates:
        raise ValueError("weights must contain the 37 groups in frozen order")
    if (not np.isfinite(weights.to_numpy()).all() or (weights <= 0).any()
            or abs(float(weights.sum())-1000.) > 1e-8):
        raise ValueError("positive frozen weights must sum to 1000 permille; no renormalisation")


def _frozen(package):
    files, manifest, info = _manifest(package, "manifest.json", nested=True)
    source_path = Path(frozen.__file__).resolve()
    if _sha(source_path.read_bytes()) != manifest["builder_sha256"]:
        raise ValueError("frozen extractor source hash differs from original package")
    original = gzip.decompress(required(files, "raw/CEN0101E.csv.gz"))
    if (_sha(original) != frozen.RAW_SHA256
            or manifest["source_raw_uncompressed_sha256"] != frozen.RAW_SHA256):
        raise ValueError("frozen raw source hash mismatch")
    columns = _read_csv(original, nrows=0).columns.tolist()
    meta = _read_csv(required(files, "series_metadata.csv"), dtype={"coicop2018_code": str})
    _valid_metadata(meta)
    if not meta.source_raw_sha256.eq(frozen.RAW_SHA256).all():
        raise ValueError("frozen metadata source hash mismatch")
    if (not meta.first_month.eq("2015-01").all() or not meta.last_month.eq("2026-07").all()
            or not meta.observations.eq(139).all()):
        raise ValueError("frozen metadata coverage changed")
    old = _read_csv(required(files, "monthly_levels.csv"), index_col=0)
    old.index = pd.PeriodIndex(old.index, freq="M", name="period")
    _valid_levels(old, pd.Period("2026-07", "M"))
    baskets = _read_csv(required(files, "basket_weights_long.csv"), dtype={"basket_code": str})
    weights, selected_weights = _weights(baskets, files)
    info.update(extractor_path=str(source_path), extractor_sha256=_sha(source_path.read_bytes()),
                raw_sha256=frozen.RAW_SHA256, created_at=manifest["created_at_utc"],
                weight_effective_year=2026, weight_basis_year=2024,
                weight_cells=selected_weights[["mapped_series", "basket_code", "weight_permille",
                                               "source_file", "source_sheet", "source_cell"]].to_dict("records"))
    return old, meta, weights, columns, info


def _captured(path, clock):
    files, _, info = _manifest(path)
    request = json.loads(required(files, "request.json"))
    if request.get("source_url") != SOURCE_URL:
        raise ValueError("capture is not the exact official CEN0101E source")
    start, completed = _clock(request["retrieved_at"]), _clock(request["completed_at"])
    if start > completed or completed > clock or completed > _now():
        raise ValueError("capture clock reversed, future, or not available by requested as_of")
    if not isinstance(request.get("headers"), dict):
        raise ValueError("capture must retain original response headers")
    raw = gzip.decompress(required(files, "CEN0101E.csv.gz"))
    if _sha(raw) != request["raw_sha256"] or len(raw) != request["raw_bytes"]:
        raise ValueError("uncompressed raw source hash/size mismatch")
    info.update(raw_sha256=request["raw_sha256"], raw_bytes=request["raw_bytes"],
                source_url=SOURCE_URL, completed_at=completed.isoformat())
    return raw, request, info


def _audit(levels, old):
    if not old.index.isin(levels.index).all():
        raise ValueError("fresh source does not cover the frozen overlap")
    fresh = levels.loc[old.index, GROUPS]
    differences = fresh-old
    changed = differences.to_numpy() != 0
    records = []
    for i, j in np.argwhere(changed):
        records.append({"period": str(old.index[i]), "group": GROUPS[j],
                        "old": float(old.iloc[i, j]), "new": float(fresh.iloc[i, j]),
                        "delta": float(differences.iloc[i, j])})
    return {
        "compared_cells": int(old.size), "first": str(old.index.min()), "last": str(old.index.max()),
        "changed_cells": len(records), "max_abs_level_change": float(np.abs(differences.to_numpy()).max()),
        "groups_with_revisions": [name for name in GROUPS if differences[name].ne(0).any()],
        "changes": records,
        "policy": "Record and permit official overlap revisions for current descriptive analysis only; frozen observations and forecasts stay unchanged.",
    }


def _metadata(original, last, request):
    meta = original.copy()
    meta["last_month"] = str(last)
    meta["observations"] = len(pd.period_range(START, last, freq="M"))
    meta["source_raw_sha256"] = request["raw_sha256"]
    meta["classification_vintage"] = "current COICOP2018 history retrieved "+request["completed_at"]
    meta["available_from_rule"] = "entire current-vintage source available no earlier than retrieval completion"
    meta["available_from_kind"] = "actual retrieval completion, not historical first-release availability"
    meta["available_from"] = _clock(request["completed_at"]).isoformat()
    return meta


def prepare(capture_dir, output, *, as_of=None, through=THROUGH, frozen_package=frozen.PACKAGE):
    """Prepare a create-only snapshot and return the same four keys as load_prepared."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite prepared inputs {output}")
    clock, last = _decision(as_of), _month(through)
    raw, request, source = _captured(capture_dir, clock)
    old, metadata, weights, columns, old_source = _frozen(frozen_package)
    if _clock(old_source["created_at"]) > clock:
        raise ValueError("frozen definitions/weights not available by requested clock")
    raw_frame = _read_csv(raw, dtype=str)
    levels = extract_current(raw_frame, expected_columns=columns,
                             through=str(last), as_of=clock)
    _verify_source_labels(raw_frame, metadata)
    metadata = _metadata(metadata, last, request)
    audit = _audit(levels, old)
    prov = {
        "schema_version": 1, "kind": "observed_category_momentum_inputs",
        "prepared_at": _now().isoformat(), "as_of": clock.isoformat(),
        "available_from": max(_clock(request["completed_at"]), _clock(old_source["created_at"])).isoformat(),
        "capture_completed_at": _clock(request["completed_at"]).isoformat(),
        "first_month": str(START), "last_month": str(last), "through": str(last),
        "months": len(levels), "groups": len(GROUPS), "source_url": SOURCE_URL,
        "sources": {"capture": source, "frozen_package": old_source},
        "selection": {**SELECTION, "reference_month": "YYYY-MM", "classification": "current COICOP2018"},
        "schema": {"matches_frozen_exactly": True, "columns": columns},
        "extractor": "unchanged tools.research_r18.category_inputs.extract_levels",
        "transformations": "Exact selection/pivot of positive NSA 2015-base index levels; no filling, interpolation, rebasing, seasonal or tax adjustment.",
        "weights": {"effective_year": 2026, "basis_year": 2024, "sum_permille": float(weights.sum()),
                    "definition": "fixed 2026 national CPI basket weights from frozen official workbook; analytical weights, not official current chain weights"},
        "use_scope": "current-vintage descriptive analysis only; no retrospective forecast revision or historical real-time claim",
        "overlap_revision_audit": audit,
        "readiness": {"ready": True, "complete_through": str(last), "missing_cells": 0, "duplicate_keys": 0},
    }
    output.mkdir(parents=True, exist_ok=False)
    _attributes(output)
    levels.to_csv(output/"monthly_levels.csv", index_label="period", encoding="utf-8")
    metadata.to_csv(output/"series_metadata.csv", index=False, encoding="utf-8")
    weights.to_frame("weight_permille").to_csv(output/"weights.csv", index_label="group", encoding="utf-8")
    _json(output/"provenance.json", prov)
    _seal(output)
    return {"levels": levels, "metadata": metadata, "weights": weights, "provenance": prov}


def load_prepared(path, as_of=None):
    """Validate output hashes and original capture/frozen evidence at the given clock.

    Omitted as_of means actual UTC now, never an unbounded or future decision.
    All historical values belong to the current capture vintage.
    """
    clock = _decision(as_of)
    files, _, _ = _manifest(path)
    prov = json.loads(required(files, "provenance.json"))
    if prov.get("schema_version") != 1 or prov.get("kind") != "observed_category_momentum_inputs":
        raise ValueError("unsupported prepared input schema")
    if _clock(prov["available_from"]) > clock or _clock(prov["capture_completed_at"]) > clock:
        raise ValueError("prepared capture not available by requested clock")
    if _clock(prov["prepared_at"]) > _now():
        raise ValueError("future prepared timestamp")
    last = _month(prov["through"])
    raw, request, source = _captured(prov["sources"]["capture"]["path"], clock)
    old, frozen_meta, frozen_weights, columns, old_source = _frozen(prov["sources"]["frozen_package"]["path"])
    if source != prov["sources"]["capture"] or old_source != prov["sources"]["frozen_package"]:
        raise ValueError("recorded source evidence/hash mismatch")
    if _clock(old_source["created_at"]) > clock:
        raise ValueError("frozen definitions/weights not available by requested clock")
    raw_frame = _read_csv(raw, dtype=str)
    expected = extract_current(raw_frame, expected_columns=columns, through=str(last), as_of=clock)
    _verify_source_labels(raw_frame, frozen_meta)
    levels = _read_csv(required(files, "monthly_levels.csv"), index_col=0)
    levels.index = pd.PeriodIndex(levels.index, freq="M", name="period")
    _valid_levels(levels, last)
    if not levels.equals(expected):
        raise ValueError("prepared levels differ from verified official raw extraction")
    metadata = _read_csv(required(files, "series_metadata.csv"), dtype={"coicop2018_code": str})
    _valid_metadata(metadata)
    expected_meta = _metadata(frozen_meta, last, request)
    if not metadata.equals(expected_meta):
        raise ValueError("prepared metadata differs from verified source definitions")
    table = _read_csv(required(files, "weights.csv"))
    if list(table) != ["group", "weight_permille"]:
        raise ValueError("weights export schema invalid")
    weights = table.set_index("group").weight_permille.astype(float)
    _valid_weights(weights)
    if not weights.equals(frozen_weights):
        raise ValueError("prepared weights differ from frozen official 2026 weights")
    if _audit(levels, old) != prov["overlap_revision_audit"]:
        raise ValueError("recorded overlap revision audit differs from source observations")
    return {"levels": levels, "metadata": metadata, "weights": weights, "provenance": prov}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--output", type=Path, required=True)
    cap.add_argument("--timeout", type=float, default=45)
    prep = sub.add_parser("prepare")
    prep.add_argument("--capture", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--as-of")
    prep.add_argument("--through", default=THROUGH)
    prep.add_argument("--frozen-package", type=Path, default=frozen.PACKAGE)
    check = sub.add_parser("verify")
    check.add_argument("--prepared", type=Path, required=True)
    check.add_argument("--as-of")
    args = parser.parse_args()
    if args.command == "capture":
        print(json.dumps(capture(args.output, timeout=args.timeout), indent=2))
    else:
        result = (prepare(args.capture, args.output, as_of=args.as_of, through=args.through,
                          frozen_package=args.frozen_package) if args.command == "prepare"
                  else load_prepared(args.prepared, as_of=args.as_of))
        p = result["provenance"]
        print(json.dumps({"ready": p["readiness"]["ready"], "months": len(result["levels"]),
                          "groups": len(result["weights"]), "through": p["through"],
                          "available_from": p["available_from"],
                          "revised_overlap_cells": p["overlap_revision_audit"]["changed_cells"]}, indent=2))


if __name__ == "__main__":
    main()
