"""Append-only local forecast bundles with explicit replay/prospective timing.

This is an integrity-checked software archive, not a signature, trusted external
timestamp or filesystem WORM service. Source availability is a caller declaration;
the archive validates its timing but cannot certify historical source vintages.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

NOW_WINDOW_SECONDS = 120
ARTIFACT_ROLES = ("model_code", "inputs", "source_manifests")


def _utc_now():
    return datetime.now(timezone.utc)


def _timestamp(value, label):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {label} timestamp") from exc
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError(f"{label} requires an explicit timezone")
    return stamp.astimezone(timezone.utc)


def _iso(stamp):
    return stamp.isoformat().replace("+00:00", "Z")


def _month(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError(f"Invalid {label}; expected YYYY-MM")
    if value.startswith("0000"):
        raise ValueError(f"Invalid {label} year")
    return value


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Forecasts must be finite numbers")
    return float(value)


def _path_rows(path_forecasts, target_origin):
    rows = []
    previous = None
    if path_forecasts is not None and not isinstance(path_forecasts, list):
        raise ValueError("Path forecasts must be a list")
    for row in path_forecasts or []:
        if not isinstance(row, dict) or set(row) != {"target_month", "point"}:
            raise ValueError("Each path row requires target_month and point")
        month = _month(row["target_month"], "path month")
        if month < target_origin:
            raise ValueError("Path month cannot precede target origin")
        if previous is not None and month <= previous:
            raise ValueError("Path months must be unique and chronological")
        rows.append({"target_month": month, "point": _number(row["point"])})
        previous = month
    return rows


def _clock_gate(mode, issued, release, now):
    if mode not in ("replay", "prospective"):
        raise ValueError("Explicit mode must be replay or prospective")
    if issued > now:
        raise ValueError("Issue timestamp is in the future")
    if issued >= release:
        raise ValueError("Issue must precede target first release")
    if mode == "prospective":
        if now - issued > timedelta(seconds=NOW_WINDOW_SECONDS):
            raise ValueError("Prospective issue is outside the actual now window")
        if now >= release:
            raise ValueError("Actual archive time must precede target first release")


def _json_bytes(value):
    try:
        return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Metadata must contain finite JSON values") from exc


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _availability(data_availability, required_paths, issued):
    if not isinstance(data_availability, dict):
        raise ValueError("Source availability must be a path-keyed mapping")
    result = {}
    for path, item in data_availability.items():
        resolved = str(Path(path).resolve())
        if resolved in result:
            raise ValueError("Duplicate source availability declaration")
        if not isinstance(item, dict) or "available_from" not in item:
            raise ValueError("Every source availability needs available_from")
        available = _timestamp(item["available_from"], "source availability")
        if available > issued:
            raise ValueError("Future source availability relative to issue time")
        result[resolved] = {**item, "available_from": _iso(available)}
    if set(result) != set(required_paths):
        raise ValueError("Source availability must exactly cover input and source-manifest files")
    _json_bytes(result)
    return result


def _snapshot_artifacts(artifact_paths):
    if not isinstance(artifact_paths, dict) or set(artifact_paths) != set(ARTIFACT_ROLES):
        raise ValueError("Require model_code, inputs and source_manifests artifact groups")
    result = {}
    all_paths = set()
    for role in ARTIFACT_ROLES:
        values = artifact_paths[role]
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(f"Require at least one {role} artifact")
        result[role] = []
        for value in values:
            path = Path(value).resolve(strict=True)
            if not path.is_file():
                raise ValueError("Artifacts must be regular files")
            if str(path) in all_paths:
                raise ValueError("Duplicate artifact path")
            all_paths.add(str(path))
            before = path.stat()
            payload = path.read_bytes()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(payload) != after.st_size:
                raise ValueError("Source artifact changed during hashing")
            result[role].append({"path": str(path), "bytes": len(payload), "sha256": _digest(payload)})
    return result


def _write_exclusive(path, payload):
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def archive_forecast(archive_root, *, mode, issued_at, target_origin,
                     target_first_release_at, model, point_forecast,
                     artifact_paths, data_availability, path_forecasts=None,
                     bundle_id=None, metadata=None):
    """Validate, reserve a new UUID directory and commit one forecast bundle.

    artifact_paths has nonempty lists under model_code, inputs, source_manifests.
    data_availability maps each input/source-manifest path to {available_from: an
    aware ISO timestamp, ...optional source/reference-period/assumption metadata}.
    path_forecasts is an optional chronological list of {target_month, point}.

    Returned directory is immutable through this API. Validation errors before
    reservation leave no archive. An I/O failure after reservation leaves a
    rejected uncommitted directory; its UUID must never be reused.
    """
    issued = _timestamp(issued_at, "issued_at")
    release = _timestamp(target_first_release_at, "first release")
    _clock_gate(mode, issued, release, _utc_now())
    target_origin = _month(target_origin, "target origin")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("A forecast model name is required")
    point = _number(point_forecast)
    path_rows = _path_rows(path_forecasts, target_origin)
    identifier = str(UUID(str(bundle_id))) if bundle_id is not None else str(uuid4())
    artifacts = _snapshot_artifacts(artifact_paths)
    source_paths = [item["path"] for role in ("inputs", "source_manifests") for item in artifacts[role]]
    availability = _availability(data_availability, source_paths, issued)
    archived = _utc_now()
    _clock_gate(mode, issued, release, archived)
    payload = {"schema_version": 1, "bundle_id": identifier, "mode": mode,
               "issued_at_utc": _iso(issued), "archived_at_utc": _iso(archived),
               "target_origin": target_origin, "target_first_release_at_utc": _iso(release),
               "model": model, "point_forecast": point, "path_forecasts": path_rows,
               "artifacts": artifacts, "data_availability": availability,
               "metadata": {} if metadata is None else metadata,
               "timing_policy": {"prospective_window_seconds": NOW_WINDOW_SECONDS,
                                 "clock": "actual UTC wall clock", "release_gate": "strictly before first release"},
               "record_type": "prospective_issuance" if mode == "prospective" else "historical_replay",
               "source_caveat": "Availability is declared, not certified; hashes do not establish historical first-release vintages."}
    content = _json_bytes(payload)
    archive = Path(archive_root).resolve()
    archive.mkdir(parents=True, exist_ok=True)
    destination = archive / identifier
    destination.mkdir(exist_ok=False)
    _write_exclusive(destination / "bundle.json", content)
    committed = _utc_now()
    _clock_gate(mode, issued, release, committed)
    seal = _json_bytes({"schema_version": 1, "bundle_id": identifier,
                        "bundle_sha256": _digest(content), "bundle_bytes": len(content),
                        "committed_at_utc": _iso(committed)})
    temporary = destination / ".commit.pending"
    _write_exclusive(temporary, seal)
    _clock_gate(mode, issued, release, _utc_now())
    # Hard-link publication is atomic and fails if the destination already exists.
    # No fallback to a replacing rename or partially visible commit file.
    os.link(temporary, destination / "COMMITTED.json")
    temporary.unlink()
    return destination


def verify_bundle(bundle_directory, *, verify_artifacts=False):
    """Read a sealed bundle and reject partial, changed or invalid records.

    With verify_artifacts=False, frozen hashes remain readable if original paths
    have moved. True additionally verifies that present artifact bytes still match.
    """
    directory = Path(bundle_directory)
    if not (directory / "COMMITTED.json").is_file():
        raise ValueError("Uncommitted forecast bundle")
    try:
        seal = json.loads((directory / "COMMITTED.json").read_bytes())
        content = (directory / "bundle.json").read_bytes()
        if len(content) != seal["bundle_bytes"] or _digest(content) != seal["bundle_sha256"]:
            raise ValueError("Forecast bundle integrity failure")
        payload = json.loads(content)
        if seal["schema_version"] != 1 or payload["schema_version"] != 1:
            raise ValueError("Unknown forecast archive schema")
        if str(UUID(directory.name)) != payload["bundle_id"] or seal["bundle_id"] != payload["bundle_id"]:
            raise ValueError("Forecast bundle identity mismatch")
        issued = _timestamp(payload["issued_at_utc"], "issued_at")
        archived = _timestamp(payload["archived_at_utc"], "archived_at")
        release = _timestamp(payload["target_first_release_at_utc"], "first release")
        committed = _timestamp(seal["committed_at_utc"], "commit")
        _clock_gate(payload["mode"], issued, release, archived)
        _clock_gate(payload["mode"], issued, release, committed)
        if committed < archived:
            raise ValueError("Commit precedes archive timestamp")
        expected_type = "prospective_issuance" if payload["mode"] == "prospective" else "historical_replay"
        if payload["record_type"] != expected_type:
            raise ValueError("Replay/prospective record mismatch")
        _month(payload["target_origin"], "target origin")
        _number(payload["point_forecast"])
        _path_rows(payload["path_forecasts"], payload["target_origin"])
        if set(payload["artifacts"]) != set(ARTIFACT_ROLES):
            raise ValueError("Invalid artifact roles")
        source_paths = [item["path"] for role in ("inputs", "source_manifests") for item in payload["artifacts"][role]]
        _availability(payload["data_availability"], source_paths, issued)
        if verify_artifacts:
            for role in ARTIFACT_ROLES:
                for item in payload["artifacts"][role]:
                    path = Path(item["path"])
                    if not path.is_file():
                        raise ValueError(f"Missing source artifact: {path}")
                    current = path.read_bytes()
                    if len(current) != item["bytes"] or _digest(current) != item["sha256"]:
                        raise ValueError(f"Changed source artifact: {path}")
        return payload
    except (KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
        raise ValueError("Invalid forecast bundle integrity/structure") from exc
